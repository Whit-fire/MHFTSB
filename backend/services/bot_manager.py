import time
import asyncio
import random
import logging
from datetime import datetime, timezone

logger = logging.getLogger("bot_manager")


class BotManager:
    def __init__(self, db, config, rpc_manager, hft_gate, parse_service,
                 strategy_engine, execution_engine, jito_service, position_manager, metrics):
        self.db = db
        self.config = config
        self.rpc_manager = rpc_manager
        self.hft_gate = hft_gate
        self.parse_service = parse_service
        self.strategy_engine = strategy_engine
        self.execution_engine = execution_engine
        self.jito_service = jito_service
        self.position_manager = position_manager
        self.metrics = metrics
        self.ws_broadcast = None
        self.solana_trader = None
        self.liquidity_monitor = None
        self.status = "stopped"
        self.mode = "simulation"
        self.start_time = None
        self._tasks = []
        self._running = False

    async def start(self):
        if self._running:
            return {"error": "Already running"}
        self._running = True
        self.status = "running"
        self.start_time = time.time()
        await self.log("INFO", "bot_manager", f"Bot starting in {self.mode.upper()} mode")

        self._tasks = [
            asyncio.create_task(self._position_eval_loop()),
            asyncio.create_task(self._metrics_broadcast_loop()),
        ]

        if self.mode == "simulation":
            self._tasks.append(asyncio.create_task(self._simulation_loop()))
        else:
            if self.solana_trader:
                self.solana_trader.load_keypair_from_wallet()
            if self.liquidity_monitor:
                self.liquidity_monitor.on_candidate = self._on_live_candidate
                await self.liquidity_monitor.start()
                await self.log("INFO", "bot_manager", f"Live WSS monitoring started ({len(self.liquidity_monitor._wss_urls)} endpoints)")
            else:
                await self.log("WARN", "bot_manager", "No liquidity monitor configured for live mode")

        await self.log("INFO", "bot_manager", "Bot started successfully")
        return {"status": "running", "mode": self.mode}

    async def stop(self):
        self._running = False
        self.status = "stopped"
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        if self.liquidity_monitor:
            await self.liquidity_monitor.stop()
        await self.log("INFO", "bot_manager", "Bot stopped")
        return {"status": "stopped"}

    async def panic(self):
        await self.log("WARN", "bot_manager", "PANIC - Closing all positions")
        await self.position_manager.close_all("panic")
        await self.stop()
        return {"status": "panic_executed", "positions_closed": True}

    async def _on_live_candidate(self, candidate: dict):
        """Handle a real Pump.fun CREATE event from WSS."""
        if not self._running:
            return
        sig = candidate["signature"]
        self.metrics.increment("wss_events_total")
        logger.info(f"LIVE CREATE detected: {sig[:20]}...")
        await self.log("INFO", "liquidity_monitor", f"LIVE CREATE detected: {sig[:20]}...")

        entered = await self.hft_gate.try_enter(sig)
        self.metrics.set_gauge("hft_inflight_count", self.hft_gate.in_flight)
        if not entered:
            self.metrics.increment("hft_dropped_count")
            await self.log("WARN", "hft_gate", "DROP - max inflight")
            return

        try:
            start_t = time.time()

            if not self.solana_trader:
                logger.error("No solana_trader configured")
                await self.log("ERROR", "execution", "No solana_trader configured")
                return

            parsed = await self.solana_trader.fetch_and_parse_tx(sig)
            parse_ms = (time.time() - start_t) * 1000
            self.metrics.record_latency("parse_latency_ms", parse_ms)

            if not parsed:
                # Expected: 10-20% of CREATE events fail parsing (incomplete/failed TX, timing issues)
                # This is NORMAL in HFT - drop silently and move on
                self.metrics.increment("parse_dropped")
                # TEMPORARY DEBUG: Changed to INFO to see why 100% TX are dropped in live
                logger.info(f"[DEBUG] Dropped unparseable TX {sig[:16]}... after {parse_ms:.0f}ms - fetch returned None")
                return
            
            self.metrics.increment("parse_success")

            mint = parsed["mint"]
            bc = parsed["bonding_curve"]
            abc = parsed.get("associated_bonding_curve", "")
            token_prog = parsed.get("token_program")
            creator = parsed.get("creator")
            logger.info(f"Parsed CREATE mint={mint[:12]}... bc={bc[:12]}... creator={creator[:12] if creator else 'N/A'}... tp={'T22' if token_prog and 'zQd' in token_prog else 'SPL'} in {parse_ms:.0f}ms")
            await self.log("INFO", "parse_service",
                           f"Parsed CREATE mint={mint[:8]}... bc={bc[:8]}... in {parse_ms:.0f}ms")

            raw_buy_amount = self.config.get("FILTERS", {}).get("MAX_INITIAL_BUY_AMOUNT", 0.03)
            try:
                buy_amount = float(raw_buy_amount)
            except Exception:
                buy_amount = 0.03

            exec_start = time.time()
            # Use Clone & Inject pattern - pass complete parsed data instead of individual fields
            result = await self.solana_trader.execute_buy_cloned(
                parsed, buy_amount, slippage_pct=25.0
            )
            exec_ms = (time.time() - exec_start) * 1000
            self.metrics.record_latency("execution_latency_ms", exec_ms)
            self.metrics.record_latency("jito_send_latency_ms", exec_ms)

            if result["success"]:
                # Calculate token_amount for potential sell later
                token_amount = int(float(buy_amount) * 1e9 * 30)  # Approximate token amount from SOL
                
                await self.position_manager.register_buy(
                    mint, mint[:8] + "...", result.get("entry_price_sol", buy_amount),
                    buy_amount, 80.0, result["signature"],
                    bonding_curve=bc, associated_bonding_curve=abc,
                    token_program=token_prog, creator=creator, token_amount=token_amount
                )
                total_ms = (time.time() - start_t) * 1000
                self.metrics.record_latency("wss_to_jito_ms", total_ms)
                self.metrics.increment("trades_success")
                logger.info(f"BUY SUCCESS mint={mint[:12]}... sig={result['signature'][:16]}... latency={total_ms:.0f}ms")
                await self.log("TRADE", "execution",
                               f"BUY LIVE mint={mint[:8]}... sig={result['signature'][:16]}... latency={total_ms:.0f}ms")
            else:
                self.metrics.increment("trades_failed")
                logger.error(f"BUY FAILED mint={mint[:12]}...: {result.get('error')}")
                await self.log("ERROR", "execution", f"BUY FAILED: {result.get('error')}")

        except Exception as e:
            logger.error(f"Live candidate error: {e}", exc_info=True)
            await self.log("ERROR", "bot_manager", f"Live error: {e}")
        finally:
            await self.hft_gate.exit(sig)
            self.metrics.set_gauge("hft_inflight_count", self.hft_gate.in_flight)

    async def _simulation_loop(self):
        while self._running:
            try:
                await asyncio.sleep(random.uniform(2, 5))
                if not self._running:
                    break

                sig = f"sim_sig_{int(time.time()*1000)}_{random.randint(1000,9999)}"
                await self.log("INFO", "liquidity_monitor", f"New candidate detected sig={sig[:24]}...")
                self.metrics.increment("wss_events_total")

                entered = await self.hft_gate.try_enter(sig)
                self.metrics.set_gauge("hft_inflight_count", self.hft_gate.in_flight)

                if not entered:
                    self.metrics.increment("hft_dropped_count")
                    await self.log("WARN", "hft_gate", "DROP - max inflight reached")
                    continue

                try:
                    start_parse = time.time()
                    parsed = await self.parse_service.parse_create_instruction(sig, simulation=True)
                    parse_ms = (time.time() - start_parse) * 1000
                    self.metrics.record_latency("parse_latency_ms", parse_ms)

                    if not parsed:
                        # Expected: Parse failures are normal in simulation - drop silently
                        self.metrics.increment("parse_dropped")
                        logger.debug(f"Simulation parse failed for {sig[:16]}... after {parse_ms:.0f}ms (normal)")
                        continue

                    self.metrics.increment("parse_success")

                    await self.log("INFO", "parse_service",
                                   f"Parsed {parsed.token_name} liq={parsed.liquidity_sol:.2f} SOL in {parse_ms:.0f}ms")

                    eval_result = await self.strategy_engine.evaluate(parsed, simulation=True)

                    if not eval_result["passed"]:
                        await self.log("INFO", "strategy", f"REJECTED {parsed.token_name}: {eval_result['reason']}")
                        self.metrics.increment("strategy_rejected")
                        continue

                    await self.log("TRADE", "strategy",
                                   f"APPROVED {parsed.token_name} score={eval_result['pump_score']} buy={eval_result['buy_amount_sol']} SOL")
                    self.metrics.increment("strategy_approved")

                    start_exec = time.time()
                    exec_result = await self.execution_engine.execute_clone_and_inject(
                        parsed, eval_result["buy_amount_sol"], simulation=True
                    )
                    exec_ms = (time.time() - start_exec) * 1000
                    self.metrics.record_latency("execution_latency_ms", exec_ms)
                    self.metrics.record_latency("jito_send_latency_ms", exec_result.get("latency_ms", 0))

                    if exec_result["success"]:
                        pos_id = await self.position_manager.register_buy(
                            parsed.mint, parsed.token_name, exec_result["entry_price_sol"],
                            eval_result["buy_amount_sol"], eval_result["pump_score"],
                            exec_result["signature"]
                        )
                        if pos_id:
                            await self.log("TRADE", "execution",
                                           f"BUY {parsed.token_name} @ {exec_result['entry_price_sol']:.6f} SOL")
                            self.metrics.increment("trades_success")

                        total_ms = (time.time() - start_parse) * 1000
                        self.metrics.record_latency("wss_to_jito_ms", total_ms)
                    else:
                        await self.log("ERROR", "execution", f"EXEC FAILED: {exec_result.get('error')}")
                        self.metrics.increment("trades_failed")

                finally:
                    await self.hft_gate.exit(sig)
                    self.metrics.set_gauge("hft_inflight_count", self.hft_gate.in_flight)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Simulation loop error: {e}")
                await asyncio.sleep(1)

    async def _position_eval_loop(self):
        while self._running:
            try:
                await asyncio.sleep(0.8)
                if not self._running:
                    break
                await self.position_manager.simulate_price_updates()
                await self.position_manager.evaluate_positions()
                self.metrics.set_gauge("positions_open", len(self.position_manager._positions))
                kpi = self.position_manager.get_kpi()
                self.metrics.set_gauge("total_pnl_sol", kpi["total_pnl_sol"])
                self.metrics.set_gauge("win_rate", kpi["win_rate"])
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Position eval error: {e}")
                await asyncio.sleep(1)

    async def _metrics_broadcast_loop(self):
        while self._running:
            try:
                await asyncio.sleep(1)
                if not self._running:
                    break
                if self.ws_broadcast:
                    status = self.get_full_status()
                    positions = self.position_manager.get_open_positions()
                    await self.ws_broadcast({
                        "type": "metrics_update",
                        "data": status,
                        "positions": positions,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Metrics broadcast error: {e}")
                await asyncio.sleep(1)

    async def log(self, level: str, service: str, message: str, data: dict = None):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level, "service": service,
            "message": message, "data": data or {}
        }
        if self.ws_broadcast:
            await self.ws_broadcast({"type": "log", **log_entry})
        try:
            await self.db.logs.insert_one({**log_entry, "id": str(time.time())})
        except Exception:
            pass

    def get_full_status(self) -> dict:
        uptime = time.time() - self.start_time if self.start_time else 0
        return {
            "status": self.status,
            "mode": self.mode,
            "uptime_seconds": round(uptime, 1),
            "hft_gate": self.hft_gate.get_status(),
            "positions": self.position_manager.get_kpi(),
            "execution": self.execution_engine.get_stats(),
            "strategy": self.strategy_engine.get_stats(),
            "parse": self.parse_service.get_stats(),
            "jito": self.jito_service.get_stats(),
            "metrics": self.metrics.get_snapshot()
        }
