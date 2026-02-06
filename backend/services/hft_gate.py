import logging
import asyncio

logger = logging.getLogger("hft_gate")


class HftGateService:
    def __init__(self, max_in_flight: int = 3):
        self.max_in_flight = max_in_flight
        self._in_flight = 0
        self._dropped_count = 0
        self._total_entered = 0
        self._lock = asyncio.Lock()

    async def try_enter(self, candidate_id: str) -> bool:
        async with self._lock:
            if self._in_flight >= self.max_in_flight:
                self._dropped_count += 1
                logger.info(f"[HFT_GATE] DROP max inflight ({self._in_flight}/{self.max_in_flight}) candidate={candidate_id[:16]}")
                return False
            self._in_flight += 1
            self._total_entered += 1
            logger.info(f"[HFT_GATE] ENTER ({self._in_flight}/{self.max_in_flight}) candidate={candidate_id[:16]}")
            return True

    async def exit(self, candidate_id: str):
        async with self._lock:
            self._in_flight = max(0, self._in_flight - 1)
            logger.info(f"[HFT_GATE] EXIT ({self._in_flight}/{self.max_in_flight}) candidate={candidate_id[:16]}")

    @property
    def in_flight(self):
        return self._in_flight

    @property
    def dropped_count(self):
        return self._dropped_count

    @property
    def total_entered(self):
        return self._total_entered

    def get_status(self) -> dict:
        return {
            "in_flight": self._in_flight,
            "max_in_flight": self.max_in_flight,
            "dropped_count": self._dropped_count,
            "total_entered": self._total_entered,
            "utilization_percent": round((self._in_flight / self.max_in_flight) * 100, 1) if self.max_in_flight > 0 else 0
        }
