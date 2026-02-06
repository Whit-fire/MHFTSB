import random
import logging

logger = logging.getLogger("strategy_engine")


class StrategyEngine:
    def __init__(self, config: dict):
        self.config = config
        self._evaluated_count = 0
        self._passed_count = 0
        self._rejected_count = 0
        self._score_buckets = {"0-50": 0, "50-70": 0, "70-85": 0, "85-90": 0, "90-100": 0}

    def update_config(self, config: dict):
        self.config = config

    def compute_pump_score(self, event_data: dict, simulation: bool = True) -> float:
        if simulation:
            weights = self.config.get("SCORING", {}).get("WEIGHTS", {})
            base_rug = random.uniform(40, 95) * weights.get("RUG_CHECK", 0.25)
            base_liq = min(100, event_data.get("liquidity_sol", 1) * 40) * weights.get("LIQUIDITY", 0.15)
            base_momentum = random.uniform(30, 100) * weights.get("MOMENTUM", 0.40)
            base_creator = random.uniform(20, 90) * weights.get("CREATOR", 0.20)
            score = base_rug + base_liq + base_momentum + base_creator
            return round(min(100, max(0, score)), 1)
        return 0

    async def evaluate(self, parsed_event, simulation: bool = True) -> dict:
        self._evaluated_count += 1
        event_data = {
            "liquidity_sol": parsed_event.liquidity_sol,
            "token_name": parsed_event.token_name,
            "mint": parsed_event.mint
        }

        pump_score = self.compute_pump_score(event_data, simulation)

        if pump_score < 50:
            self._score_buckets["0-50"] += 1
        elif pump_score < 70:
            self._score_buckets["50-70"] += 1
        elif pump_score < 85:
            self._score_buckets["70-85"] += 1
        elif pump_score < 90:
            self._score_buckets["85-90"] += 1
        else:
            self._score_buckets["90-100"] += 1

        thresholds = self.config.get("SCORING", {}).get("THRESHOLDS", {})
        filters = self.config.get("FILTERS", {})
        fast_buy_enabled = filters.get("FAST_BUY_ENABLED", True)
        fast_buy_threshold = thresholds.get("FAST_BUY", 85)
        min_score = thresholds.get("MIN_SCORE", 70)
        min_liquidity = filters.get("MIN_LIQUIDITY_SOL", 0.5)

        passed = True
        reason = "PASS"

        if parsed_event.liquidity_sol < min_liquidity:
            passed = False
            reason = f"LOW_LIQUIDITY ({parsed_event.liquidity_sol:.2f} < {min_liquidity})"
        elif fast_buy_enabled and pump_score < fast_buy_threshold:
            if pump_score < min_score:
                passed = False
                reason = f"LOW_SCORE ({pump_score} < {min_score})"
            else:
                passed = True
                reason = f"SCORE_OK ({pump_score} >= {min_score})"

        if passed:
            self._passed_count += 1
        else:
            self._rejected_count += 1

        buy_amount = filters.get("MAX_INITIAL_BUY_AMOUNT", 0.5)
        logger.info(f"[STRATEGY] {parsed_event.token_name} score={pump_score} liq={parsed_event.liquidity_sol:.2f} result={reason}")

        return {
            "passed": passed,
            "pump_score": pump_score,
            "reason": reason,
            "buy_amount_sol": buy_amount,
            "is_fast_buy": pump_score >= fast_buy_threshold and fast_buy_enabled
        }

    def get_stats(self) -> dict:
        return {
            "evaluated": self._evaluated_count,
            "passed": self._passed_count,
            "rejected": self._rejected_count,
            "score_buckets": dict(self._score_buckets)
        }
