import os
import json
import time
import asyncio
import logging
import aiohttp
from typing import Optional, Set, Callable
from collections import OrderedDict

logger = logging.getLogger("liquidity_monitor")

PUMP_FUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"


class LRUDedup:
    def __init__(self, max_size: int = 50000, ttl: float = 60.0):
        self._cache = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl

    def add(self, key: str) -> bool:
        now = time.time()
        if key in self._cache:
            return False
        self._cache[key] = now
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)
        return True

    def cleanup(self):
        now = time.time()
        keys_to_remove = [k for k, v in self._cache.items() if now - v > self._ttl]
        for k in keys_to_remove:
            del self._cache[k]


class LiquidityMonitorService:
    def __init__(self, on_candidate: Callable, rpc_manager=None):
        self.on_candidate = on_candidate
        self.rpc_manager = rpc_manager
        self._dedup = LRUDedup(max_size=50000, ttl=60)
        self._running = False
        self._tasks = []
        self._poll_task = None
        self._wss_urls = []
        self._reconnect_delay = 2
        self._poll_interval = 1.5
        self._poll_index = 0

    def configure(self, wss_urls: list):
        self._wss_urls = [u for u in wss_urls if u]
        logger.info(f"Configured {len(self._wss_urls)} WSS endpoints")

    def configure_from_env(self):
        urls = []
        for i in range(1, 4):
            u = os.environ.get(f"HELIUS_RPC_WSS{i}")
            if u:
                urls.append(u)
        for i in range(1, 3):
            u = os.environ.get(f"QUICKNODE_RPC_WSS{i}")
            if u:
                urls.append(u)
        self.configure(urls)

    async def start(self):
        if self._running:
            return
        self._running = True
        if not self._wss_urls:
            self.configure_from_env()
        for i, url in enumerate(self._wss_urls):
            task = asyncio.create_task(self._wss_loop(url, f"wss_{i}"))
            self._tasks.append(task)
        if self.rpc_manager:
            self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info(f"Started {len(self._tasks)} WSS listeners")

    async def stop(self):
        self._running = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        if self._poll_task:
            self._poll_task.cancel()
            self._poll_task = None
        logger.info("WSS listeners stopped")

    async def _poll_loop(self):
        while self._running:
            try:
                await self._poll_once()
            except Exception as e:
                logger.error(f"[poll] error: {e}")
            await asyncio.sleep(self._poll_interval)

    async def _poll_once(self):
        if not self.rpc_manager:
            return
        rpcs = [ep.url for ep in self.rpc_manager.get_all_available_rpcs()]
        if not rpcs:
            return
        non_helius = [u for u in rpcs if "helius-rpc.com" not in u]
        if non_helius:
            rpcs = non_helius
        rpcs = sorted(rpcs, key=lambda u: 0 if "extrnode" in u else 1)
        url = rpcs[self._poll_index % len(rpcs)]
        self._poll_index += 1
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [PUMP_FUN_PROGRAM, {"limit": 20, "commitment": "confirmed"}]
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                    data = await resp.json()
                    if "error" in data:
                        err_code = data["error"].get("code", 0) if isinstance(data["error"], dict) else 0
                        if err_code == -32401:
                            self.rpc_manager.mark_auth_failure(url)
                        else:
                            logger.warning(f"[poll] RPC error: {data['error']}")
                        return
                    result = data.get("result", [])
                    for entry in result:
                        sig = entry.get("signature")
                        if not sig:
                            continue
                        if not self._dedup.add(sig):
                            continue
                        candidate = {
                            "signature": sig,
                            "slot": entry.get("slot", 0),
                            "source_wss_id": "poll",
                            "timestamp": time.time(),
                            "logs": []
                        }
                        logger.info(f"[poll] candidate: {sig[:20]}...")
                        await self.on_candidate(candidate)
        except Exception as e:
            logger.error(f"[poll] RPC error: {e}")

    async def _wss_loop(self, url: str, source_id: str):
        consecutive_failures = 0
        max_consecutive_failures = 5
        while self._running:
            try:
                logger.info(f"[{source_id}] Connecting to {url[:50]}...")
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(url, timeout=30, heartbeat=20) as ws:
                        subscribe_msg = {
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "logsSubscribe",
                            "params": [
                                {"mentions": [PUMP_FUN_PROGRAM]},
                                {"commitment": "processed"}
                            ]
                        }
                        await ws.send_json(subscribe_msg)
                        logger.info(f"[{source_id}] Subscribed to Pump.fun logs")
                        consecutive_failures = 0

                        async for msg in ws:
                            if not self._running:
                                break
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    data = json.loads(msg.data)
                                    await self._handle_log_message(data, source_id)
                                except json.JSONDecodeError:
                                    pass
                            elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                                break

            except asyncio.CancelledError:
                break
            except Exception as e:
                consecutive_failures += 1
                err_text = str(e)
                if "401" in err_text or "Unauthorized" in err_text or "Invalid response status" in err_text:
                    logger.info(f"[{source_id}] WSS auth error, disabling endpoint")
                    break
                logger.error(f"[{source_id}] WSS error (fail {consecutive_failures}): {e}")
                if consecutive_failures >= max_consecutive_failures:
                    logger.warning(f"[{source_id}] Max reconnect failures reached, disabling this endpoint")
                    break

            if self._running:
                delay = min(self._reconnect_delay * (2 ** min(consecutive_failures, 4)), 60)
                await asyncio.sleep(delay)

    async def _handle_log_message(self, data: dict, source_id: str):
        params = data.get("params", {})
        result = params.get("result", {})
        value = result.get("value", {})
        signature = value.get("signature")
        logs = value.get("logs", [])

        if not signature or not logs:
            return

        is_create = False
        for log_line in logs:
            if "Program log: Instruction: Create" in log_line:
                is_create = True
                break
            if "InitializeMint" in log_line and PUMP_FUN_PROGRAM in str(logs):
                is_create = True
                break

        if not is_create:
            return

        if not self._dedup.add(signature):
            return

        candidate = {
            "signature": signature,
            "slot": value.get("slot", 0),
            "source_wss_id": source_id,
            "timestamp": time.time(),
            "logs": logs[:10],
        }

        logger.info(f"[{source_id}] CREATE detected: {signature[:20]}...")

        try:
            await self.on_candidate(candidate)
        except Exception as e:
            logger.error(f"on_candidate error: {e}")
