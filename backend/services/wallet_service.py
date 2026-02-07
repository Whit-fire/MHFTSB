import json
import base64
import hashlib
import base58
import aiohttp
import logging
from typing import List, Dict, Optional
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding as sym_padding

logger = logging.getLogger("wallet_service")

TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"


def _evp_bytes_to_key(password: bytes, salt: bytes, key_len: int = 32, iv_len: int = 16):
    d = b''
    d_i = b''
    while len(d) < key_len + iv_len:
        d_i = hashlib.md5(d_i + password + salt).digest()
        d += d_i
    return d[:key_len], d[key_len:key_len + iv_len]


def decrypt_cryptojs_aes(encrypted_b64: str, passphrase: str) -> str:
    raw = base64.b64decode(encrypted_b64)
    if raw[:8] != b'Salted__':
        raise ValueError("Not a CryptoJS AES encrypted string")
    salt = raw[8:16]
    ciphertext = raw[16:]
    key, iv = _evp_bytes_to_key(passphrase.encode('utf-8'), salt)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = sym_padding.PKCS7(128).unpadder()
    data = unpadder.update(padded) + unpadder.finalize()
    return data.decode('utf-8')


def is_cryptojs_encrypted(s: str) -> bool:
    try:
        raw = base64.b64decode(s.strip())
        return raw[:8] == b'Salted__'
    except Exception:
        return False


class WalletService:
    def __init__(self, rpc_manager):
        self.rpc_manager = rpc_manager
        self._address: Optional[str] = None
        self._key_bytes: Optional[bytes] = None

    def decrypt_and_derive(self, encrypted_or_raw: str, passphrase: str = None) -> str:
        raw_key = encrypted_or_raw.strip()

        if is_cryptojs_encrypted(raw_key):
            if not passphrase:
                raise ValueError("Passphrase required to decrypt CryptoJS AES key")
            logger.info("Detected CryptoJS AES encrypted key, decrypting...")
            raw_key = decrypt_cryptojs_aes(raw_key, passphrase)
            logger.info(f"Decrypted key length: {len(raw_key)} chars")

        return self.derive_address(raw_key)

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
        urls = []
        if rpc_url:
            urls.append(rpc_url)
        for ep in self.rpc_manager.get_all_available_rpcs():
            if ep.url not in urls:
                urls.append(ep.url)

        if not urls:
            raise Exception("No RPC endpoint available")

        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        last_error = None

        for url in urls[:4]:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        data = await resp.json()
                        if "error" in data:
                            error = data["error"]
                            err_code = error.get("code", 0) if isinstance(error, dict) else 0
                            if err_code == -32401:
                                logger.error(f"RPC auth failure ({method}): {error} - marking RPC as failed")
                                self.rpc_manager.mark_auth_failure(url)
                                last_error = error
                                continue
                            logger.error(f"RPC error ({method}): {error}")
                            last_error = error
                            continue
                        return data
            except Exception as e:
                last_error = str(e)
                logger.error(f"RPC call failed ({method}) on {url[:50]}...: {e}")
                continue

        return {"error": last_error or "RPC call failed"}

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
