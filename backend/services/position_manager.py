import time
import random
import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional
import uuid

logger = logging.getLogger("position_manager")


class PositionData:
    def __init__(self, token_mint, token_name, entry_price, amount_sol, pump_score, tx_signature,
                 bonding_curve=None, associated_bonding_curve=None, token_program=None, creator=None, token_amount=None):
        self.id = str(uuid.uuid4())
        self.token_mint = token_mint
        self.token_name = token_name
        try:
            self.entry_price_sol = float(entry_price)
        except Exception:
            self.entry_price_sol = 0.0
        self.current_price_sol = self.entry_price_sol
        try:
            self.amount_sol = float(amount_sol)
        except Exception:
            self.amount_sol = 0.0
        self.pnl_sol = 0.0
        self.pnl_percent = 0.0
        self.entry_time = datetime.now(timezone.utc).isoformat()
        self.pump_score = pump_score
        self.status = "open"
        self.stop_loss = -10.0
        self.trailing_active = False
        self.trailing_high = entry_price
        self.close_reason = None
        self.close_time = None
        self.tx_signature = tx_signature
        self.tp_hits = []
        # New fields for sell execution
        self.bonding_curve = bonding_curve
        self.associated_bonding_curve = associated_bonding_curve
        self.token_program = token_program
        self.creator = creator
        self.token_amount = token_amount

    def update_price(self, new_price):
        try:
            self.current_price_sol = float(new_price)
        except Exception:
            self.current_price_sol = 0.0
        if self.entry_price_sol > 0:
            self.pnl_percent = ((self.current_price_sol - self.entry_price_sol) / self.entry_price_sol) * 100
        self.pnl_sol = (self.current_price_sol - self.entry_price_sol) * (self.amount_sol / max(self.entry_price_sol, 0.000001))
        if self.current_price_sol > self.trailing_high:
            self.trailing_high = self.current_price_sol

    def to_dict(self):
        return {
            "id": self.id, "token_mint": self.token_mint, "token_name": self.token_name,
            "entry_price_sol": self.entry_price_sol, "current_price_sol": self.current_price_sol,
            "amount_sol": round(self.amount_sol, 6), "pnl_sol": round(self.pnl_sol, 6),
            "pnl_percent": round(self.pnl_percent, 2), "entry_time": self.entry_time,
            "pump_score": self.pump_score, "status": self.status,
            "stop_loss": self.stop_loss, "trailing_active": self.trailing_active,
            "trailing_high": self.trailing_high, "close_reason": self.close_reason,
            "close_time": self.close_time, "tx_signature": self.tx_signature,
            "bonding_curve": self.bonding_curve,
            "associated_bonding_curve": self.associated_bonding_curve,
            "token_program": self.token_program,
            "creator": self.creator,
            "token_amount": self.token_amount
        }


class PositionManager:
    def __init__(self, db, config: dict):
        self.db = db
        self.config = config
        self._positions: Dict[str, PositionData] = {}
        self._closed_positions: List[dict] = []

    def update_config(self, config: dict):
        self.config = config

    async def register_buy(self, mint, token_name, entry_price, amount_sol, pump_score, signature,
                          bonding_curve=None, associated_bonding_curve=None, token_program=None, 
                          creator=None, token_amount=None) -> Optional[str]:
        exec_config = self.config.get("EXECUTION", {})
        if len(self._positions) >= exec_config.get("MAX_OPEN_POSITIONS", 30):
            logger.warning(f"[POS] MAX_OPEN_POSITIONS reached, rejecting {token_name}")
            return None
        if exec_config.get("ENFORCE_ONE_PER_TOKEN", True):
            if any(p.token_mint == mint for p in self._positions.values()):
                logger.warning(f"[POS] Already have position for {mint[:8]}...")
                return None

        pos = PositionData(mint, token_name, entry_price, amount_sol, pump_score, signature,
                          bonding_curve, associated_bonding_curve, token_program, creator, token_amount)
        self._positions[pos.id] = pos
        try:
            await self.db.positions.insert_one({**pos.to_dict(), "created_at": datetime.now(timezone.utc).isoformat()})
        except Exception:
            pass
        logger.info(f"[POS] Opened {token_name} id={pos.id[:8]}... entry={entry_price:.6f} amount={amount_sol}")
        return pos.id

    async def close_position(self, position_id: str, reason: str = "manual") -> Optional[dict]:
        pos = self._positions.get(position_id)
        if not pos:
            return None
        pos.status = "closed"
        pos.close_reason = reason
        pos.close_time = datetime.now(timezone.utc).isoformat()
        closed_data = pos.to_dict()
        self._closed_positions.append(closed_data)
        del self._positions[position_id]
        try:
            await self.db.positions.update_one(
                {"id": position_id},
                {"$set": {"status": "closed", "close_reason": reason,
                          "close_time": pos.close_time, "pnl_sol": pos.pnl_sol,
                          "pnl_percent": pos.pnl_percent, "current_price_sol": pos.current_price_sol}}
            )
        except Exception:
            pass
        logger.info(f"[POS] Closed {pos.token_name} reason={reason} pnl={pos.pnl_percent:.1f}%")
        return closed_data

    async def set_stop_loss(self, position_id: str, sl: float) -> bool:
        pos = self._positions.get(position_id)
        if not pos:
            return False
        pos.stop_loss = sl
        return True

    async def close_all(self, reason: str = "panic"):
        ids = list(self._positions.keys())
        for pid in ids:
            await self.close_position(pid, reason)

    def get_open_positions(self) -> List[dict]:
        return [p.to_dict() for p in self._positions.values()]

    def get_closed_positions(self, limit: int = 50) -> List[dict]:
        return self._closed_positions[-limit:]

    async def simulate_price_updates(self):
        for pos in self._positions.values():
            change_pct = random.gauss(0.5, 3)
            new_price = pos.current_price_sol * (1 + change_pct / 100)
            new_price = max(0.000001, new_price)
            pos.update_price(new_price)

    async def evaluate_positions(self):
        risk = self.config.get("RISK", {})
        tp_config = self.config.get("TAKE_PROFIT", {})
        trailing = risk.get("TRAILING", {})
        kill_switch = risk.get("KILL_SWITCH", {})
        hft = self.config.get("HFT", {})
        to_close = []

        for pos in list(self._positions.values()):
            if kill_switch.get("ENABLED", True):
                try:
                    entry = datetime.fromisoformat(pos.entry_time)
                    age_s = (datetime.now(timezone.utc) - entry).total_seconds()
                    if age_s > kill_switch.get("MAX_TIME_SECONDS", 40):
                        if pos.pnl_percent < kill_switch.get("DROP_THRESHOLD_PERCENT", -12):
                            to_close.append((pos.id, "KILL_SWITCH"))
                            continue
                except Exception:
                    pass

            sl_levels = risk.get("STOP_LOSS", {})
            if pos.pnl_percent <= sl_levels.get("ULTRA", -20):
                to_close.append((pos.id, "STOP_LOSS_ULTRA"))
                continue
            elif pos.pnl_percent <= sl_levels.get("HIGH", -15):
                to_close.append((pos.id, "STOP_LOSS_HIGH"))
                continue

            for tp_key, tp_val in tp_config.items():
                if isinstance(tp_val, dict) and pos.pnl_percent >= tp_val.get("gain", 100) and tp_key not in pos.tp_hits:
                    pos.tp_hits.append(tp_key)
                    sell_pct = tp_val.get("percent", 25) / 100
                    pos.amount_sol *= (1 - sell_pct)
                    logger.info(f"[POS] TP hit {tp_key} for {pos.token_name} gain={pos.pnl_percent:.1f}%")

            if pos.pnl_percent >= trailing.get("START_PERCENT", 15):
                pos.trailing_active = True
            if pos.trailing_active and pos.trailing_high > 0:
                from_high = ((pos.current_price_sol - pos.trailing_high) / pos.trailing_high) * 100
                if from_high <= -trailing.get("DISTANCE_PERCENT", 10):
                    to_close.append((pos.id, "TRAILING_STOP"))
                    continue

            try:
                entry = datetime.fromisoformat(pos.entry_time)
                age_ms = (datetime.now(timezone.utc) - entry).total_seconds() * 1000
                if age_ms > hft.get("MAX_POSITION_AGE_MS", 60000):
                    to_close.append((pos.id, "MAX_AGE"))
            except Exception:
                pass

        for pid, reason in to_close:
            await self.close_position(pid, reason)

    def get_kpi(self) -> dict:
        closed = self._closed_positions
        wins = [p for p in closed if p.get("pnl_percent", 0) > 0]
        total_pnl = sum(p.pnl_sol for p in self._positions.values())
        return {
            "open_positions": len(self._positions),
            "max_positions": self.config.get("EXECUTION", {}).get("MAX_OPEN_POSITIONS", 30),
            "closed_positions": len(closed),
            "total_pnl_sol": round(total_pnl, 6),
            "win_rate": round(len(wins) / max(1, len(closed)) * 100, 1),
            "wins": len(wins),
            "losses": len(closed) - len(wins)
        }
