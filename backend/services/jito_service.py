import time
import random
import string
import logging
import asyncio

logger = logging.getLogger("jito_service")


class JitoService:
    def __init__(self, rpc_manager):
        self.rpc_manager = rpc_manager
        self._bundles_sent = 0
        self._bundles_failed = 0
        self._avg_send_latency_ms = 0.0
        self._total_tips_sol = 0.0

    async def send_bundle(self, transactions: list, tip_config: dict, context=None, simulation: bool = True) -> dict:
        start = time.time()

        if simulation:
            await asyncio.sleep(random.uniform(0.02, 0.06))
            bundle_id = "bundle_" + ''.join(random.choices(string.ascii_lowercase + string.digits, k=32))
            latency = (time.time() - start) * 1000
            self._bundles_sent += 1
            tip = tip_config.get("tip", 0.001)
            self._total_tips_sol += tip
            self._avg_send_latency_ms = (self._avg_send_latency_ms * (self._bundles_sent - 1) + latency) / self._bundles_sent
            logger.info(f"[JITO] Bundle sent (sim) id={bundle_id[:16]}... tip={tip} latency={latency:.1f}ms")
            return {"success": True, "bundle_id": bundle_id, "latency_ms": latency}

        return {"success": False, "error": "LiveModeNotImplemented"}

    async def simulate_bundle(self, transactions: list) -> dict:
        await asyncio.sleep(0.01)
        return {"success": True, "simulated": True, "logs": ["Simulation OK"]}

    def get_stats(self) -> dict:
        return {
            "bundles_sent": self._bundles_sent,
            "bundles_failed": self._bundles_failed,
            "avg_send_latency_ms": round(self._avg_send_latency_ms, 1),
            "total_tips_sol": round(self._total_tips_sol, 4)
        }
