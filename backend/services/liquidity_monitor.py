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
    def __init__(self, on_candidate: Callable):
        self.on_candidate = on_candidate
        self._dedup = LRUDedup(max_size=50000, ttl=60)
        self._running = False
        self._tasks = []
        self._wss_urls = []
        self._reconnect_delay = 2

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
        logger.info(f"Started {len(self._tasks)} WSS listeners")

    async def stop(self):
        self._running = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        logger.info("WSS listeners stopped")

    async def _wss_loop(self, url: str, source_id: str):
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
                logger.error(f"[{source_id}] WSS error: {e}")

            if self._running:
                await asyncio.sleep(self._reconnect_delay)

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
