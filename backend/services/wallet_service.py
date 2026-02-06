import json
import base58
import aiohttp
import logging
from typing import List, Dict, Optional
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger("wallet_service")

TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"


class WalletService:
    def __init__(self, rpc_manager):
        self.rpc_manager = rpc_manager
        self._address: Optional[str] = None
        self._key_bytes: Optional[bytes] = None

    def derive_address(self, private_key_str: str) -> str:
        raw = private_key_str.strip()
        if raw.startswith('['):
            key_bytes = bytes(json.loads(raw))
        else:
            key_bytes = base58.b58decode(raw)

        if len(key_bytes) == 64:
            seed = key_bytes[:32]
            pub = key_bytes[32:]
        elif len(key_bytes) == 32:
            seed = key_bytes
            priv = Ed25519PrivateKey.from_private_bytes(seed)
            pub = priv.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
        else:
            raise ValueError(f"Invalid key length: {len(key_bytes)} (expected 32 or 64)")

        self._key_bytes = seed
        self._address = base58.b58encode(pub).decode()
        logger.info(f"Derived wallet address: {self._address}")
        return self._address

    @property
    def address(self):
        return self._address

    async def _rpc_call(self, method: str, params: list, rpc_url: str = None) -> dict:
        url = rpc_url
        if not url:
            ep = self.rpc_manager.get_tx_fetch_connection()
            url = ep.url if ep else None
        if not url:
            raise Exception("No RPC endpoint available")

        async with aiohttp.ClientSession() as session:
            payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                if "error" in data:
                    logger.error(f"RPC error ({method}): {data['error']}")
                return data

    async def get_sol_balance(self, address: str = None) -> float:
        addr = address or self._address
        if not addr:
            return 0.0
        try:
            data = await self._rpc_call("getBalance", [addr])
            lamports = data.get("result", {}).get("value", 0)
            return lamports / 1e9
        except Exception as e:
            logger.error(f"get_sol_balance failed: {e}")
            return 0.0

    async def get_token_accounts(self, address: str = None) -> List[Dict]:
        addr = address or self._address
        if not addr:
            return []
        try:
            data = await self._rpc_call(
                "getTokenAccountsByOwner",
                [addr, {"programId": TOKEN_PROGRAM_ID}, {"encoding": "jsonParsed"}]
            )
            accounts = data.get("result", {}).get("value", [])
            tokens = []
            for acc in accounts:
                info = acc.get("account", {}).get("data", {}).get("parsed", {}).get("info", {})
                ta = info.get("tokenAmount", {})
                amount = float(ta.get("uiAmount", 0) or 0)
                if amount > 0:
                    tokens.append({
                        "mint": info.get("mint", ""),
                        "amount": amount,
                        "decimals": ta.get("decimals", 0),
                        "ui_amount": ta.get("uiAmountString", "0"),
                    })
            tokens.sort(key=lambda t: t["amount"], reverse=True)
            return tokens
        except Exception as e:
            logger.error(f"get_token_accounts failed: {e}")
            return []

    async def get_full_balance(self, address: str = None) -> Dict:
        addr = address or self._address
        sol = await self.get_sol_balance(addr)
        tokens = await self.get_token_accounts(addr)
        return {
            "address": addr or "",
            "sol_balance": round(sol, 9),
            "token_count": len(tokens),
            "tokens": tokens[:50],
        }
