import os
import json
import struct
import time
import asyncio
import logging
import base58
import aiohttp
from typing import Optional, Dict, List, Any
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import TransferParams, transfer
from solders.transaction import Transaction
from solders.message import Message
from solders.instruction import Instruction, AccountMeta
from solders.hash import Hash
from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price

logger = logging.getLogger("solana_trader")

PUMP_FUN_PROGRAM = Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
PUMP_GLOBAL = Pubkey.from_string("4wTV1YmiEkRvAtNtsSGPtUrqRYQMe5SKy2uB4Jjaxnjf")
PUMP_FEE_RECIPIENT = Pubkey.from_string("62qc2CNXwrYqQScmEdiZFFAnJR262PxWEuNQtxfafNgV")
PUMP_EVENT_AUTHORITY = Pubkey.from_string("Ce6TQqeHC9p8KetsN6JsjHK7UTZk7nasjjnr7XxXp9F1")
TOKEN_PROGRAM = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
TOKEN_2022_PROGRAM = Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")
ASSOC_TOKEN_PROGRAM = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
SYSTEM_PROGRAM = Pubkey.from_string("11111111111111111111111111111111")
FEE_PROGRAM = Pubkey.from_string("pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ")

# Static PDAs (derived once, never change)
GLOBAL_VOLUME_ACCUMULATOR, _ = Pubkey.find_program_address([b"global_volume_accumulator"], PUMP_FUN_PROGRAM)
FEE_CONFIG_ADMIN_BYTES = bytes(PUMP_FUN_PROGRAM)
FEE_CONFIG, _ = Pubkey.find_program_address([b"fee_config", FEE_CONFIG_ADMIN_BYTES], FEE_PROGRAM)

BUY_DISCRIMINATOR = bytes.fromhex("66063d1201daebea")
SELL_DISCRIMINATOR = bytes.fromhex("33e685a4017f83ad")

TOKEN_PROGRAM_STR = str(TOKEN_PROGRAM)
TOKEN_2022_PROGRAM_STR = str(TOKEN_2022_PROGRAM)


def get_associated_token_address(wallet: Pubkey, mint: Pubkey, token_program: Pubkey = None) -> Pubkey:
    tp = token_program or TOKEN_2022_PROGRAM
    seeds = [bytes(wallet), bytes(tp), bytes(mint)]
    pda, _ = Pubkey.find_program_address(seeds, ASSOC_TOKEN_PROGRAM)
    return pda


def build_buy_instruction(
    buyer: Pubkey, mint: Pubkey, bonding_curve: Pubkey,
    associated_bonding_curve: Pubkey, buyer_ata: Pubkey,
    token_amount: int, max_sol_cost: int,
    token_program: Pubkey = None
) -> Instruction:
    tp = token_program or TOKEN_2022_PROGRAM
    data = BUY_DISCRIMINATOR + struct.pack("<Q", token_amount) + struct.pack("<Q", max_sol_cost)
    accounts = [
        AccountMeta(PUMP_GLOBAL, is_signer=False, is_writable=False),
        AccountMeta(PUMP_FEE_RECIPIENT, is_signer=False, is_writable=True),
        AccountMeta(mint, is_signer=False, is_writable=False),
        AccountMeta(bonding_curve, is_signer=False, is_writable=True),
        AccountMeta(associated_bonding_curve, is_signer=False, is_writable=True),
        AccountMeta(buyer_ata, is_signer=False, is_writable=True),
        AccountMeta(buyer, is_signer=True, is_writable=True),
        AccountMeta(SYSTEM_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(tp, is_signer=False, is_writable=False),
        AccountMeta(RENT_SYSVAR, is_signer=False, is_writable=False),
        AccountMeta(PUMP_EVENT_AUTHORITY, is_signer=False, is_writable=False),
        AccountMeta(PUMP_FUN_PROGRAM, is_signer=False, is_writable=False),
    ]
    return Instruction(PUMP_FUN_PROGRAM, data, accounts)


def build_create_ata_idempotent(payer: Pubkey, owner: Pubkey, mint: Pubkey, token_program: Pubkey = None) -> Instruction:
    tp = token_program or TOKEN_2022_PROGRAM
    ata = get_associated_token_address(owner, mint, tp)
    accounts = [
        AccountMeta(payer, is_signer=True, is_writable=True),
        AccountMeta(ata, is_signer=False, is_writable=True),
        AccountMeta(owner, is_signer=False, is_writable=False),
        AccountMeta(mint, is_signer=False, is_writable=False),
        AccountMeta(SYSTEM_PROGRAM, is_signer=False, is_writable=False),
        AccountMeta(tp, is_signer=False, is_writable=False),
    ]
    data = bytes([1])
    return Instruction(ASSOC_TOKEN_PROGRAM, data, accounts)


class SolanaTrader:
    def __init__(self, rpc_manager, wallet_service):
        self.rpc_manager = rpc_manager
        self.wallet_service = wallet_service
        self.jito_url = os.environ.get("JITO_BLOCK_ENGINE_URL", "")
        self.jito_tip_account = os.environ.get("JITO_TIP_ACCOUNT", "")
        self.tip_amount_sol = float(os.environ.get("JITO_TIP_AMOUNT", "0.015"))
        self._keypair: Optional[Keypair] = None

    def load_keypair(self, key_bytes: bytes):
        if len(key_bytes) == 64:
            self._keypair = Keypair.from_bytes(key_bytes)
        elif len(key_bytes) == 32:
            self._keypair = Keypair.from_seed(key_bytes)
        logger.info(f"Keypair loaded: {self._keypair.pubkey()}")

    def load_keypair_from_wallet(self):
        if self.wallet_service._key_bytes:
            seed = self.wallet_service._key_bytes
            self._keypair = Keypair.from_seed(seed)
            logger.info(f"Keypair loaded from wallet service: {self._keypair.pubkey()}")
            return True
        return False

    async def get_latest_blockhash(self, rpc_url: str = None) -> Optional[Dict]:
        rpcs = []
        if rpc_url:
            rpcs.append(rpc_url)
        for ep in self.rpc_manager.get_all_available_rpcs():
            if ep.url not in rpcs:
                rpcs.append(ep.url)
        if not rpcs:
            logger.error("No RPC URL available for getLatestBlockhash")
            return None

        for url in rpcs[:3]:
            try:
                async with aiohttp.ClientSession() as session:
                    payload = {"jsonrpc": "2.0", "id": 1, "method": "getLatestBlockhash",
                               "params": [{"commitment": "processed"}]}
                    async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        data = await resp.json()
                        if "error" in data:
                            err_code = data["error"].get("code", 0) if isinstance(data["error"], dict) else 0
                            if err_code == -32401:
                                self.rpc_manager.mark_auth_failure(url)
                                continue
                            logger.error(f"getLatestBlockhash RPC error from {url[:40]}...: {data['error']}")
                            continue
                        result = data.get("result", {}).get("value", {})
                        bh = result.get("blockhash")
                        if not bh:
                            continue
                        logger.info(f"Got blockhash: {bh[:12]}... from {url[:40]}...")
                        return {
                            "blockhash": bh,
                            "last_valid_block_height": result.get("lastValidBlockHeight"),
                            "rpc_url": url
                        }
            except Exception as e:
                logger.error(f"getLatestBlockhash failed on {url[:40]}...: {e}")
        return None

    async def build_buy_transaction(
        self, mint_str: str, bonding_curve_str: str,
        assoc_bonding_curve_str: str, buy_amount_sol: float,
        slippage_pct: float = 25.0, blockhash_ctx: Dict = None,
        token_program_str: str = None
    ) -> Optional[Dict]:
        if not self._keypair:
            if not self.load_keypair_from_wallet():
                logger.error("No keypair loaded")
                return None

        # Determine which token program to use
        tp = TOKEN_2022_PROGRAM  # default to Token-2022 for pump.fun
        if token_program_str == TOKEN_PROGRAM_STR:
            tp = TOKEN_PROGRAM

        try:
            mint = Pubkey.from_string(mint_str)
            bonding_curve = Pubkey.from_string(bonding_curve_str)
            assoc_bc = Pubkey.from_string(assoc_bonding_curve_str)
            buyer = self._keypair.pubkey()
            buyer_ata = get_associated_token_address(buyer, mint, tp)

            if not blockhash_ctx:
                blockhash_ctx = await self.get_latest_blockhash()
            if not blockhash_ctx or not blockhash_ctx.get("blockhash"):
                logger.error("Failed to get blockhash")
                return None

            max_sol_lamports = int(buy_amount_sol * 1e9)
            token_amount = int(max_sol_lamports * 30)
            max_sol_with_slippage = int(max_sol_lamports * (1 + slippage_pct / 100))

            ixs = [
                set_compute_unit_limit(200_000),
                set_compute_unit_price(500_000),
                build_create_ata_idempotent(buyer, buyer, mint, tp),
                build_buy_instruction(
                    buyer, mint, bonding_curve, assoc_bc, buyer_ata,
                    token_amount, max_sol_with_slippage, tp
                ),
            ]

            if self.jito_tip_account:
                tip_lamports = int(self.tip_amount_sol * 1e9)
                tip_ix = transfer(TransferParams(
                    from_pubkey=buyer,
                    to_pubkey=Pubkey.from_string(self.jito_tip_account),
                    lamports=tip_lamports
                ))
                ixs.append(tip_ix)

            recent_hash = Hash.from_string(blockhash_ctx["blockhash"])
            msg = Message.new_with_blockhash(ixs, buyer, recent_hash)
            tx = Transaction.new_unsigned(msg)
            tx.sign([self._keypair], recent_hash)

            tx_bytes = bytes(tx)
            import base64
            tx_b64 = base64.b64encode(tx_bytes).decode()

            logger.info(f"Built buy TX for mint={mint_str[:8]}... amount={buy_amount_sol} SOL tip={self.tip_amount_sol}")
            return {
                "tx_bytes": tx_bytes,
                "tx_base64": tx_b64,
                "mint": mint_str,
                "buyer": str(buyer),
                "buyer_ata": str(buyer_ata),
                "amount_sol": buy_amount_sol,
                "blockhash": blockhash_ctx["blockhash"],
                "rpc_url": blockhash_ctx.get("rpc_url"),
            }

        except Exception as e:
            logger.error(f"build_buy_transaction failed: {e}")
            return None

    async def send_transaction(self, tx_b64: str, rpc_url: str = None) -> Optional[str]:
        url = self.jito_url if self.jito_url else rpc_url
        if not url:
            ep = self.rpc_manager.get_tx_fetch_connection()
            url = ep.url if ep else None
        if not url:
            logger.error("No RPC URL for sending transaction")
            return None

        logger.info(f"Sending TX via {url[:50]}...")
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "jsonrpc": "2.0", "id": 1, "method": "sendTransaction",
                    "params": [tx_b64, {"encoding": "base64", "skipPreflight": True,
                                        "preflightCommitment": "processed",
                                        "maxRetries": 0}]
                }
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    if "result" in data:
                        sig = data["result"]
                        logger.info(f"TX sent OK! signature={sig[:20]}...")
                        return sig
                    else:
                        err = data.get("error", {})
                        logger.error(f"sendTransaction error: {json.dumps(err) if isinstance(err, dict) else err}")
                        return None
        except Exception as e:
            logger.error(f"send_transaction failed: {e}")
            return None

    async def execute_buy(
        self, mint_str: str, bonding_curve_str: str,
        assoc_bonding_curve_str: str, buy_amount_sol: float,
        slippage_pct: float = 25.0, token_program_str: str = None
    ) -> Dict:
        start = time.time()
        tp_label = "T22" if (not token_program_str or token_program_str == TOKEN_2022_PROGRAM_STR) else "SPL"
        logger.info(f"execute_buy: mint={mint_str[:12]}... amount={buy_amount_sol} SOL token_program={tp_label}")
        try:
            blockhash_ctx = await self.get_latest_blockhash()
            if not blockhash_ctx:
                return {"success": False, "error": "Failed to get blockhash"}

            tx_data = await self.build_buy_transaction(
                mint_str, bonding_curve_str, assoc_bonding_curve_str,
                buy_amount_sol, slippage_pct, blockhash_ctx, token_program_str
            )
            if not tx_data:
                return {"success": False, "error": "Failed to build TX"}

            sig = await self.send_transaction(tx_data["tx_base64"])
            latency = (time.time() - start) * 1000

            if sig:
                logger.info(f"execute_buy SUCCESS: sig={sig[:20]}... latency={latency:.0f}ms")
                return {
                    "success": True, "signature": sig,
                    "latency_ms": latency, "mint": mint_str,
                    "amount_sol": buy_amount_sol,
                    "entry_price_sol": buy_amount_sol,
                }
            return {"success": False, "error": "Send failed", "latency_ms": latency}

        except Exception as e:
            logger.error(f"execute_buy failed: {e}", exc_info=True)
            return {"success": False, "error": str(e), "latency_ms": (time.time() - start) * 1000}

    async def fetch_and_parse_tx(self, signature: str, rpc_url: str = None, max_retries: int = 4) -> Optional[Dict]:
        rpcs = []
        if rpc_url:
            rpcs.append(rpc_url)
        for ep in self.rpc_manager.get_all_available_rpcs():
            if ep.url not in rpcs:
                rpcs.append(ep.url)
        if not rpcs:
            logger.error("No RPC URL available for getTransaction")
            return None

        for attempt in range(max_retries):
            url = rpcs[attempt % len(rpcs)]
            try:
                async with aiohttp.ClientSession() as session:
                    payload = {
                        "jsonrpc": "2.0", "id": 1, "method": "getTransaction",
                        "params": [signature, {"encoding": "jsonParsed", "commitment": "confirmed",
                                               "maxSupportedTransactionVersion": 0}]
                    }
                    async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        data = await resp.json()
                        if "error" in data:
                            err_code = data["error"].get("code", 0) if isinstance(data["error"], dict) else 0
                            if err_code == -32401:
                                self.rpc_manager.mark_auth_failure(url)
                                rpcs = [u for u in rpcs if u != url]
                                if not rpcs:
                                    logger.error("All RPCs have auth failures")
                                    return None
                                continue
                            logger.warning(f"getTransaction RPC error (attempt {attempt+1}): {data['error']}")
                            await asyncio.sleep(0.3)
                            continue
                        tx_data = data.get("result")
                        if not tx_data:
                            if attempt < max_retries - 1:
                                await asyncio.sleep(0.5 + 0.5 * attempt)
                                continue
                            logger.warning(f"TX {signature[:16]}... not found after {max_retries} attempts")
                            return None
                        parsed = self._extract_pump_accounts(tx_data)
                        if parsed:
                            logger.info(f"Parsed TX {signature[:16]}... on attempt {attempt+1}: mint={parsed['mint'][:12]}...")
                        return parsed
            except Exception as e:
                logger.error(f"fetch_and_parse_tx attempt {attempt+1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.3)
        return None

    def _extract_pump_accounts(self, tx_data: Dict) -> Optional[Dict]:
        try:
            meta = tx_data.get("meta", {})
            if meta.get("err"):
                return None

            tx_msg = tx_data.get("transaction", {}).get("message", {})
            account_keys = tx_msg.get("accountKeys", [])
            if not account_keys:
                return None

            keys_list = []
            for ak in account_keys:
                if isinstance(ak, dict):
                    keys_list.append(ak.get("pubkey", ""))
                else:
                    keys_list.append(str(ak))

            # Detect which token program is used in this transaction
            token_program_str = TOKEN_2022_PROGRAM_STR  # default to Token-2022
            if TOKEN_PROGRAM_STR in keys_list and TOKEN_2022_PROGRAM_STR not in keys_list:
                token_program_str = TOKEN_PROGRAM_STR

            instructions = tx_msg.get("instructions", [])
            pump_ix = None
            for ix in instructions:
                prog = ix.get("programId", "")
                if prog == str(PUMP_FUN_PROGRAM):
                    pump_ix = ix
                    break

            if not pump_ix:
                inner = meta.get("innerInstructions", [])
                for inner_group in inner:
                    for ix in inner_group.get("instructions", []):
                        if ix.get("programId", "") == str(PUMP_FUN_PROGRAM):
                            pump_ix = ix
                            break

            if not pump_ix:
                return None

            ix_accounts = pump_ix.get("accounts", [])
            post_balances = meta.get("postTokenBalances", [])

            mint = None
            bonding_curve = None
            assoc_bonding_curve = None

            for ptb in post_balances:
                m = ptb.get("mint", "")
                owner = ptb.get("owner", "")
                if m and owner:
                    mint = m
                    break

            if len(ix_accounts) >= 5:
                if not mint:
                    mint = ix_accounts[2] if len(ix_accounts) > 2 else None
                bonding_curve = ix_accounts[3] if len(ix_accounts) > 3 else None
                assoc_bonding_curve = ix_accounts[4] if len(ix_accounts) > 4 else None

            if mint and bonding_curve:
                logger.info(f"Extracted: mint={mint[:12]}... token_program={'T22' if token_program_str == TOKEN_2022_PROGRAM_STR else 'SPL'}")
                return {
                    "mint": mint,
                    "bonding_curve": bonding_curve,
                    "associated_bonding_curve": assoc_bonding_curve or "",
                    "token_program": token_program_str,
                    "accounts": ix_accounts,
                    "all_keys": keys_list,
                }
            return None

        except Exception as e:
            logger.error(f"_extract_pump_accounts failed: {e}")
            return None
