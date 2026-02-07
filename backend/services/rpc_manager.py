import time
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("rpc_manager")


class RpcEndpoint:
    def __init__(self, url: str, wss: str = None, pool: str = "fast", role: str = "general"):
        self.url = url
        self.wss = wss
        self.pool = pool
        self.role = role
        self.latency_ms = 0.0
        self.slot_lag = 0
        self.recent_429s = 0
        self.cooldown_until = 0.0
        self.health_score = 100.0
        self.last_check = 0.0

    def is_available(self):
        return time.time() > self.cooldown_until

    def mark_429(self):
        self.recent_429s += 1
        self.cooldown_until = time.time() + 4
        self.health_score = max(0, self.health_score - 20)

    def update_health(self, latency_ms: float, slot_lag: int = 0):
        self.latency_ms = latency_ms
        self.slot_lag = slot_lag
        self.health_score = max(0, 100 - (latency_ms / 10) - (slot_lag * 5) - (self.recent_429s * 10))
        self.last_check = time.time()


class BlockhashContext:
    def __init__(self, rpc_id: str, url: str, blockhash: str, last_valid_block_height: int):
        self.rpc_id = rpc_id
        self.url = url
        self.blockhash = blockhash
        self.last_valid_block_height = last_valid_block_height
        self.timestamp = time.time()

    def is_fresh(self, current_slot: int = 0):
        if time.time() - self.timestamp > 30:
            return False
        if current_slot > 0 and current_slot >= self.last_valid_block_height - 10:
            return False
        return True


class RpcManagerService:
    def __init__(self):
        self.fast_pool: List[RpcEndpoint] = []
        self.cold_pool: List[RpcEndpoint] = []
        self.jito_endpoints: List[RpcEndpoint] = []
        self._blockhash_cache: Dict[str, BlockhashContext] = {}

    def configure(self, endpoints: List[Dict]):
        self.fast_pool.clear()
        self.cold_pool.clear()
        self.jito_endpoints.clear()
        for ep in endpoints:
            rpc_ep = RpcEndpoint(ep["url"], ep.get("wss"), ep.get("pool", "fast"), ep.get("role", "general"))
            if rpc_ep.pool == "jito":
                self.jito_endpoints.append(rpc_ep)
            elif rpc_ep.pool == "cold":
                self.cold_pool.append(rpc_ep)
            else:
                self.fast_pool.append(rpc_ep)

    def configure_from_env(self, env_data: dict):
        endpoints = []
        for i in range(1, 4):
            url = env_data.get(f"HELIUS_RPC_URL{i}")
            wss = env_data.get(f"HELIUS_RPC_WSS{i}")
            if url:
                endpoints.append({"url": url, "wss": wss, "pool": "fast", "role": "helius"})
        for i in range(1, 3):
            url = env_data.get(f"QUICKNODE_RPC_URL{i}")
            wss = env_data.get(f"QUICKNODE_RPC_WSS{i}")
            if url:
                endpoints.append({"url": url, "wss": wss, "pool": "cold", "role": "quicknode"})
        extr = env_data.get("EXTRNODE_RPC_URL")
        if extr:
            endpoints.append({"url": extr, "pool": "fast", "role": "extrnode"})
        self.configure(endpoints)
        logger.info(f"RPC configured: {len(self.fast_pool)} fast, {len(self.cold_pool)} cold, {len(self.jito_endpoints)} jito")

    def get_tx_fetch_connection(self) -> Optional[RpcEndpoint]:
        available = [ep for ep in self.fast_pool if ep.is_available()]
        if not available:
            available = [ep for ep in self.cold_pool if ep.is_available()]
        if not available:
            all_eps = self.fast_pool + self.cold_pool
            return all_eps[0] if all_eps else None
        return sorted(available, key=lambda e: -e.health_score)[0]

    def get_all_available_rpcs(self) -> List[RpcEndpoint]:
        """Return all available RPC endpoints sorted by health score."""
        all_eps = [ep for ep in (self.fast_pool + self.cold_pool) if ep.is_available()]
        # CRITICAL FIX: Never return RPCs in cooldown - forces proper fallback to cold_pool
        return sorted(all_eps, key=lambda e: -e.health_score)

    def mark_auth_failure(self, url: str):
        """Mark an endpoint as having auth failure (heavy penalty)."""
        for ep in self.fast_pool + self.cold_pool:
            if ep.url == url:
                ep.health_score = 0
                ep.cooldown_until = time.time() + 300  # 5 min cooldown
                logger.warning(f"RPC auth failure, cooldown 5min: {url[:50]}...")
                break

    def get_scoring_connection(self) -> Optional[RpcEndpoint]:
        available = [ep for ep in self.fast_pool if ep.is_available()]
        if len(available) > 1:
            return sorted(available, key=lambda e: -e.health_score)[1]
        return available[0] if available else None

    def get_jito_connection(self) -> Optional[RpcEndpoint]:
        available = [ep for ep in self.jito_endpoints if ep.is_available()]
        return available[0] if available else (self.jito_endpoints[0] if self.jito_endpoints else None)

    def get_jito_fallback(self) -> Optional[RpcEndpoint]:
        available = [ep for ep in self.jito_endpoints if ep.is_available()]
        return available[1] if len(available) > 1 else None

    async def get_jito_context(self) -> Optional[BlockhashContext]:
        jito = self.get_jito_connection()
        rpc_id = jito.url if jito else "default"
        cached = self._blockhash_cache.get(rpc_id)
        if cached and cached.is_fresh():
            return cached
        ctx = BlockhashContext(
            rpc_id=rpc_id,
            url=rpc_id,
            blockhash="sim_" + str(int(time.time())),
            last_valid_block_height=999999999
        )
        self._blockhash_cache[rpc_id] = ctx
        return ctx

    def health_check(self) -> Dict:
        all_eps = self.fast_pool + self.cold_pool
        return {
            "fast_pool": len(self.fast_pool),
            "cold_pool": len(self.cold_pool),
            "jito_endpoints": len(self.jito_endpoints),
            "total_429s": sum(ep.recent_429s for ep in all_eps),
            "avg_latency_ms": round(sum(ep.latency_ms for ep in all_eps) / max(1, len(all_eps)), 1),
            "endpoints": self.get_all_endpoints_info()
        }

    def get_all_endpoints_info(self) -> list:
        result = []
        for ep in self.fast_pool + self.cold_pool + self.jito_endpoints:
            result.append({
                "url": ep.url[:60] + "..." if len(ep.url) > 60 else ep.url,
                "pool": ep.pool, "role": ep.role,
                "health_score": round(ep.health_score, 1),
                "latency_ms": round(ep.latency_ms, 1),
                "recent_429s": ep.recent_429s,
                "available": ep.is_available()
            })
        return result
