import time
import random
import string
import logging
import asyncio

logger = logging.getLogger("execution_engine")


class ExecutionEngine:
    def __init__(self, rpc_manager, jito_service):
        self.rpc_manager = rpc_manager
        self.jito_service = jito_service
        self._total_executions = 0
        self._successful = 0
        self._failed = 0
        self._avg_latency_ms = 0.0

    async def execute_clone_and_inject(self, parsed_event, buy_amount_sol: float, simulation: bool = True) -> dict:
        start = time.time()
        self._total_executions += 1

        if simulation:
            await asyncio.sleep(random.uniform(0.03, 0.08))
            success = random.random() < 0.90

            if success:
                sig = "sim_" + ''.join(random.choices(string.ascii_lowercase + string.digits, k=64))
                latency = (time.time() - start) * 1000
                self._successful += 1
                self._avg_latency_ms = (self._avg_latency_ms * (self._successful - 1) + latency) / self._successful
                logger.info(f"[EXEC] SUCCESS {parsed_event.token_name} amount={buy_amount_sol} SOL latency={latency:.1f}ms")
                return {
                    "success": True, "signature": sig, "latency_ms": latency,
                    "token_name": parsed_event.token_name, "mint": parsed_event.mint,
                    "amount_sol": buy_amount_sol,
                    "entry_price_sol": random.uniform(0.000001, 0.005)
                }
            else:
                self._failed += 1
                latency = (time.time() - start) * 1000
                logger.warning(f"[EXEC] FAILED {parsed_event.token_name} latency={latency:.1f}ms")
                return {"success": False, "error": "SimulatedFailure", "latency_ms": latency}

        return {"success": False, "error": "LiveModeNotImplemented"}

    def get_stats(self) -> dict:
        return {
            "total_executions": self._total_executions,
            "successful": self._successful,
            "failed": self._failed,
            "avg_latency_ms": round(self._avg_latency_ms, 1),
            "success_rate": round(self._successful / max(1, self._total_executions) * 100, 1)
        }
