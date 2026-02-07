import copy

DEFAULT_STRATEGY_CONFIG = {
    "TELEGRAM": {"NOTIFY_ON_BUY": False, "NOTIFY_ON_SELL": True},
    "FILTERS": {
        "MIN_LIQUIDITY_SOL": 0.5, "MIN_LIQUIDITY_FAST_BUY": 1.0,
        "MAX_INITIAL_BUY_AMOUNT": 0.03, "FAST_BUY_ENABLED": True
    },
    "RISK": {
        "KILL_SWITCH": {"ENABLED": True, "MAX_TIME_SECONDS": 40, "DROP_THRESHOLD_PERCENT": -12, "VELOCITY_DUMP_PERCENT": -15},
        "MAX_RUGCHECK_SCORE": 500,
        "STOP_LOSS": {"LOW": -10, "MEDIUM": -12, "HIGH": -15, "ULTRA": -20},
        "TRAILING": {"START_PERCENT": 15, "DISTANCE_PERCENT": 10}
    },
    "TAKE_PROFIT": {
        "TP1": {"percent": 50, "gain": 100},
        "TP2": {"percent": 25, "gain": 200},
        "TP3": {"percent": 25, "gain": 500}
    },
    "SCORING": {
        "WEIGHTS": {"RUG_CHECK": 0.25, "LIQUIDITY": 0.15, "MOMENTUM": 0.40, "CREATOR": 0.20},
        "THRESHOLDS": {"FAST_BUY": 85, "MIN_SCORE": 70, "ULTRA_SCORE": 90}
    },
    "MOMENTUM": {"CHECK_WINDOW_MS": 5000, "MIN_BUYS": 3, "MIN_VOLUME_SOL": 0.15, "MIN_UNIQUE_WALLETS": 3},
    "CREATOR": {"MIN_TOKENS": 5, "BAD_WINRATE_THRESHOLD": 30, "HIGH_RISK_THRESHOLD": 70},
    "EXECUTION": {
        "MAX_OPEN_POSITIONS": 30, "MAX_PENDING_BUYS": 0, "MAX_QUEUE_SIZE": 0,
        "ENFORCE_ONE_PER_TOKEN": True, "STOP_LISTENING_WHEN_FULL": True
    },
    "HFT": {
        "EVAL_INTERVAL_MS": 150, "PRICE_UPDATE_INTERVAL_MS": 150,
        "MAX_POSITION_AGE_MS": 60000, "CANDIDATE_MAX_AGE_MS": 8000
    }
}


def get_default_config():
    return copy.deepcopy(DEFAULT_STRATEGY_CONFIG)


def deep_merge(base, override):
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def set_nested_value(config, path, value):
    keys = path.split('.')
    current = config
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            return False
        current = current[key]
    if keys[-1] in current:
        existing = current[keys[-1]]
        if isinstance(existing, bool):
            current[keys[-1]] = str(value).lower() in ('true', '1', 'yes')
        elif isinstance(existing, int):
            current[keys[-1]] = int(float(value))
        elif isinstance(existing, float):
            current[keys[-1]] = float(value)
        else:
            current[keys[-1]] = value
        return True
    return False
