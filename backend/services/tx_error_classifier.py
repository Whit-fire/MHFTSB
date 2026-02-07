import json


class TxErrorClassifier:
    EXPECTED_PATTERNS = {
        "seeds constraint violated": "seeds_constraint",
        "incorrect program id": "incorrect_program_id",
        "not authorized": "not_authorized",
        "unauthorized": "not_authorized",
        "accountnotinitialized": "account_not_initialized",
        "account not initialized": "account_not_initialized",
        "custom": "custom_error",
        "blockhash not found": "blockhash_not_found",
        "insufficient funds": "insufficient_funds",
        "slippage": "slippage_exceeded",
    }

    @staticmethod
    def classify(error: object) -> dict:
        text = ""
        if isinstance(error, dict):
            text = json.dumps(error)
        else:
            text = str(error or "")

        lower = text.lower()
        for pattern, code in TxErrorClassifier.EXPECTED_PATTERNS.items():
            if pattern in lower:
                expected = code in {
                    "seeds_constraint",
                    "incorrect_program_id",
                    "not_authorized",
                    "account_not_initialized",
                    "slippage_exceeded",
                    "custom_error",
                }
                return {"type": code, "expected": expected, "raw": text}

        return {"type": "unknown", "expected": False, "raw": text}