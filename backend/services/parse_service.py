import time
import random
import string
import logging
import asyncio
from typing import Optional, Tuple

logger = logging.getLogger("parse_service")

PUMP_FUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

TOKEN_NAMES = [
    "PEPE", "BONK", "DOGE", "SHIB", "FLOKI", "WIF", "POPCAT", "MOG",
    "BRETT", "NEIRO", "MYRO", "BOME", "MOCHI", "SLERF", "PENG", "TRUMP",
    "GIGACHAD", "PONKE", "GIGA", "SIGMA", "BASED", "COPE", "WAGMI", "MOON",
    "SOLCAT", "RAYD", "PUMP", "DEGEN", "YOLO", "CHAD", "ALPHA", "SNIPE"
]


class CloneInfo:
    def __init__(self, program_id: str, keys: list, data: str):
        self.program_id = program_id
        self.keys = keys
        self.data = data


class ParsedEvent:
    def __init__(self, signature, mint, token_name, bonding_curve,
                 clone_info, mapped_keys, liquidity_sol, slot):
        self.signature = signature
        self.mint = mint
        self.token_name = token_name
        self.bonding_curve = bonding_curve
        self.clone_info = clone_info
        self.mapped_keys = mapped_keys
        self.liquidity_sol = liquidity_sol
        self.slot = slot
        self.parse_time_ms = 0.0


class ParseService:
    def __init__(self, rpc_manager=None):
        self.rpc_manager = rpc_manager
        self._parse_attempt = 0
        self._parse_count = 0
        self._drop_count = 0
        self._drop_reasons = {}

    @staticmethod
    def _gen_addr() -> str:
        chars = string.ascii_letters + string.digits
        return ''.join(random.choices(chars, k=44))

    async def parse_create_instruction(self, signature: str, simulation: bool = True) -> Optional[ParsedEvent]:
        start = time.time()

        if simulation:
            await asyncio.sleep(random.uniform(0.02, 0.05))

            mint = self._gen_addr()
            token_name = random.choice(TOKEN_NAMES) + "_" + ''.join(random.choices(string.digits, k=4))
            bonding_curve = self._gen_addr()
            liquidity = random.uniform(0.3, 5.0)

            clone_info = CloneInfo(
                program_id=PUMP_FUN_PROGRAM_ID,
                keys=[self._gen_addr() for _ in range(8)],
                data="sim_data_" + signature[:8]
            )

            mapped_keys = {
                "mint": mint,
                "bondingCurve": bonding_curve,
                "associatedBondingCurve": self._gen_addr(),
                "global": self._gen_addr(),
                "feeRecipient": self._gen_addr()
            }

            event = ParsedEvent(
                signature=signature, mint=mint, token_name=token_name,
                bonding_curve=bonding_curve, clone_info=clone_info,
                mapped_keys=mapped_keys, liquidity_sol=liquidity,
                slot=random.randint(250000000, 260000000)
            )
            event.parse_time_ms = (time.time() - start) * 1000
            self._parse_attempt += 1
            self._parse_count += 1
            return event

        return None

    async def parse_live_signature(self, signature: str, solana_trader) -> Tuple[Optional[dict], Optional[str]]:
        self._parse_attempt += 1
        parsed, reason = await solana_trader.fetch_and_parse_tx(signature)
        if not parsed:
            self._drop_count += 1
            reason_key = reason or "unknown"
            self._drop_reasons[reason_key] = self._drop_reasons.get(reason_key, 0) + 1
            return None, reason_key
        self._parse_count += 1
        return parsed, None

    def get_stats(self) -> dict:
        return {
            "parse_attempt": self._parse_attempt,
            "parse_success": self._parse_count,
            "parse_drop_expected": self._drop_count,
            "drop_reasons": dict(self._drop_reasons)
        }
