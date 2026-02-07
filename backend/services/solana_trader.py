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
    creator_vault: Pubkey, user_volume_accumulator: Pubkey,
    token_program: Pubkey = None
) -> Instruction:
    tp = token_program or TOKEN_2022_PROGRAM
    # Data: discriminator(8) + amount(8) + max_sol_cost(8) + track_volume(1)
    data = BUY_DISCRIMINATOR + struct.pack("<Q", token_amount) + struct.pack("<Q", max_sol_cost) + bytes([0])
    accounts = [
        AccountMeta(PUMP_GLOBAL, is_signer=False, is_writable=False),          # 0: global
        AccountMeta(PUMP_FEE_RECIPIENT, is_signer=False, is_writable=True),    # 1: fee_recipient
        AccountMeta(mint, is_signer=False, is_writable=False),                 # 2: mint
        AccountMeta(bonding_curve, is_signer=False, is_writable=True),         # 3: bonding_curve
        AccountMeta(associated_bonding_curve, is_signer=False, is_writable=True), # 4: associated_bonding_curve
        AccountMeta(buyer_ata, is_signer=False, is_writable=True),             # 5: associated_user
        AccountMeta(buyer, is_signer=True, is_writable=True),                  # 6: user (signer)
        AccountMeta(SYSTEM_PROGRAM, is_signer=False, is_writable=False),       # 7: system_program
        AccountMeta(tp, is_signer=False, is_writable=False),                   # 8: token_program
        AccountMeta(creator_vault, is_signer=False, is_writable=True),         # 9: creator_vault
        AccountMeta(PUMP_EVENT_AUTHORITY, is_signer=False, is_writable=False), # 10: event_authority
        AccountMeta(PUMP_FUN_PROGRAM, is_signer=False, is_writable=False),     # 11: program
        AccountMeta(GLOBAL_VOLUME_ACCUMULATOR, is_signer=False, is_writable=False), # 12: global_volume_accumulator
        AccountMeta(user_volume_accumulator, is_signer=False, is_writable=True),    # 13: user_volume_accumulator
        AccountMeta(FEE_CONFIG, is_signer=False, is_writable=False),           # 14: fee_config
        AccountMeta(FEE_PROGRAM, is_signer=False, is_writable=False),          # 15: fee_program
    ]
    return Instruction(PUMP_FUN_PROGRAM, data, accounts)


def build_sell_instruction(
    seller: Pubkey, mint: Pubkey, bonding_curve: Pubkey,
    associated_bonding_curve: Pubkey, seller_ata: Pubkey,
    token_amount: int, min_sol_output: int,
    creator_vault: Pubkey, user_volume_accumulator: Pubkey,
    token_program: Pubkey = None
) -> Instruction:
    tp = token_program or TOKEN_2022_PROGRAM
    # Data: discriminator(8) + amount(8) + min_sol_output(8) + track_volume(1)
    data = SELL_DISCRIMINATOR + struct.pack("<Q", token_amount) + struct.pack("<Q", min_sol_output) + bytes([0])
    accounts = [
        AccountMeta(PUMP_GLOBAL, is_signer=False, is_writable=False),          # 0: global
        AccountMeta(PUMP_FEE_RECIPIENT, is_signer=False, is_writable=True),    # 1: fee_recipient
        AccountMeta(mint, is_signer=False, is_writable=False),                 # 2: mint
        AccountMeta(bonding_curve, is_signer=False, is_writable=True),         # 3: bonding_curve
        AccountMeta(associated_bonding_curve, is_signer=False, is_writable=True), # 4: associated_bonding_curve
        AccountMeta(seller_ata, is_signer=False, is_writable=True),            # 5: associated_user
        AccountMeta(seller, is_signer=True, is_writable=True),                 # 6: user (signer)
        AccountMeta(SYSTEM_PROGRAM, is_signer=False, is_writable=False),       # 7: system_program
        AccountMeta(tp, is_signer=False, is_writable=False),                   # 8: token_program
        AccountMeta(creator_vault, is_signer=False, is_writable=True),         # 9: creator_vault
        AccountMeta(PUMP_EVENT_AUTHORITY, is_signer=False, is_writable=False), # 10: event_authority
        AccountMeta(PUMP_FUN_PROGRAM, is_signer=False, is_writable=False),     # 11: program
        AccountMeta(GLOBAL_VOLUME_ACCUMULATOR, is_signer=False, is_writable=False), # 12: global_volume_accumulator
        AccountMeta(user_volume_accumulator, is_signer=False, is_writable=True),    # 13: user_volume_accumulator
        AccountMeta(FEE_CONFIG, is_signer=False, is_writable=False),           # 14: fee_config
        AccountMeta(FEE_PROGRAM, is_signer=False, is_writable=False),          # 15: fee_program
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

    async def fetch_bonding_curve_creator(self, bonding_curve_str: str) -> Optional[Pubkey]:
        """Fetch the creator pubkey from the on-chain BondingCurve account data."""
        rpcs = [ep.url for ep in self.rpc_manager.get_all_available_rpcs()]
        if not rpcs:
            return None
        for url in rpcs[:2]:
            try:
                async with aiohttp.ClientSession() as session:
                    payload = {
                        "jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
                        "params": [bonding_curve_str, {"encoding": "base64"}]
                    }
                    async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        data = await resp.json()
                        if "error" in data:
                            err_code = data["error"].get("code", 0) if isinstance(data["error"], dict) else 0
                            if err_code == -32401:
                                self.rpc_manager.mark_auth_failure(url)
                                continue
                            continue
                        value = data.get("result", {}).get("value")
                        if not value:
                            continue
                        import base64 as b64
                        raw = b64.b64decode(value["data"][0])
                        # BondingCurve layout: disc(8) + 5*u64(40) + bool(1) + creator(32)
                        if len(raw) < 81:
                            continue
                        creator_bytes = raw[49:81]
                        creator = Pubkey.from_bytes(creator_bytes)
                        logger.info(f"BC creator: {str(creator)[:12]}...")
                        return creator
            except Exception as e:
                logger.error(f"fetch_bonding_curve_creator error: {e}")
        return None

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


    async def clone_and_inject_buy_transaction(
        self, parsed_create_data: Dict, buy_amount_sol: float,
        slippage_pct: float = 25.0, blockhash_ctx: Dict = None
    ) -> Optional[Dict]:
        """Clone & Inject: Clone the original CREATE instruction and inject our buy."""
        if not self._keypair:
            if not self.load_keypair_from_wallet():
                logger.error("No keypair loaded")
                return None

        try:
            mint_str = parsed_create_data["mint"]
            token_program_str = parsed_create_data.get("token_program", TOKEN_2022_PROGRAM_STR)
            account_metas_clone = parsed_create_data.get("account_metas_clone", [])
            
            if not account_metas_clone:
                logger.error("No account_metas_clone available - cannot perform Clone & Inject")
                return None
            
            mint = Pubkey.from_string(mint_str)
            buyer = self._keypair.pubkey()
            
            # Determine token program
            tp = TOKEN_2022_PROGRAM if token_program_str == TOKEN_2022_PROGRAM_STR else TOKEN_PROGRAM
            buyer_ata = get_associated_token_address(buyer, mint, tp)
            
            if not blockhash_ctx:
                blockhash_ctx = await self.get_latest_blockhash()
            if not blockhash_ctx or not blockhash_ctx.get("blockhash"):
                logger.error("Failed to get blockhash")
                return None

            # Calculate buy parameters
            max_sol_lamports = int(buy_amount_sol * 1e9)
            token_amount = int(max_sol_lamports * 30)
            max_sol_with_slippage = int(max_sol_lamports * (1 + slippage_pct / 100))

            # Build instruction data for BUY (discriminator + amount + max_sol_cost + track_volume)
            data = BUY_DISCRIMINATOR + struct.pack("<Q", token_amount) + struct.pack("<Q", max_sol_with_slippage) + bytes([0])

            # Clone account metas EXACTLY from original CREATE instruction
            # Modify ONLY: signer (index 6) and associated_user (index 5 = buyer_ata)
            cloned_accounts = []
            for i, am in enumerate(account_metas_clone):
                pubkey = Pubkey.from_string(am["pubkey"])
                is_signer = am["isSigner"]
                is_writable = am["isWritable"]
                
                # Replace creator (signer at index 6) with our buyer
                if i == 6 and is_signer:
                    pubkey = buyer
                    logger.info(f"CLONE: Replacing signer at index {i} with buyer {str(buyer)[:12]}...")
                
                # Replace associated_user (index 5) with our buyer_ata
                elif i == 5:
                    pubkey = buyer_ata
                    logger.info(f"CLONE: Replacing buyer_ata at index {i} with {str(buyer_ata)[:12]}...")
                
                cloned_accounts.append(AccountMeta(pubkey, is_signer=is_signer, is_writable=is_writable))

            # Build the cloned buy instruction
            buy_ix = Instruction(PUMP_FUN_PROGRAM, data, cloned_accounts)

            # Build complete transaction
            ixs = [
                set_compute_unit_limit(200_000),
                set_compute_unit_price(500_000),
                build_create_ata_idempotent(buyer, buyer, mint, tp),
                buy_ix,  # CLONED instruction
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

            logger.info(f"Built CLONED buy TX for mint={mint_str[:8]}... amount={buy_amount_sol} SOL (Clone & Inject)")
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
            logger.error(f"clone_and_inject_buy_transaction failed: {e}", exc_info=True)
            return None


    async def build_buy_transaction(
        self, mint_str: str, bonding_curve_str: str,
        assoc_bonding_curve_str: str, buy_amount_sol: float,
        slippage_pct: float = 25.0, blockhash_ctx: Dict = None,
        token_program_str: str = None, creator_str: str = None
    ) -> Optional[Dict]:
        if not self._keypair:
            if not self.load_keypair_from_wallet():
                logger.error("No keypair loaded")
                return None

        tp = TOKEN_2022_PROGRAM
        if token_program_str == TOKEN_PROGRAM_STR:
            tp = TOKEN_PROGRAM

        try:
            mint = Pubkey.from_string(mint_str)
            bonding_curve = Pubkey.from_string(bonding_curve_str)
            assoc_bc = Pubkey.from_string(assoc_bonding_curve_str)
            buyer = self._keypair.pubkey()
            buyer_ata = get_associated_token_address(buyer, mint, tp)

            # Get creator for creator_vault derivation
            creator = None
            if creator_str:
                creator = Pubkey.from_string(creator_str)
            else:
                creator = await self.fetch_bonding_curve_creator(bonding_curve_str)

            if not blockhash_ctx:
                blockhash_ctx = await self.get_latest_blockhash()
            if not blockhash_ctx or not blockhash_ctx.get("blockhash"):
                logger.error("Failed to get blockhash")
                return None

            # Derive creator_vault PDA
            if creator:
                creator_vault, _ = Pubkey.find_program_address(
                    [b"creator-vault", bytes(creator)], PUMP_FUN_PROGRAM
                )
            else:
                logger.error("No creator available for creator_vault derivation")
                return None

            # Derive user_volume_accumulator PDA
            user_volume_acc, _ = Pubkey.find_program_address(
                [b"user_volume_accumulator", bytes(buyer)], PUMP_FUN_PROGRAM
            )

            max_sol_lamports = int(buy_amount_sol * 1e9)
            token_amount = int(max_sol_lamports * 30)
            max_sol_with_slippage = int(max_sol_lamports * (1 + slippage_pct / 100))

            ixs = [
                set_compute_unit_limit(200_000),
                set_compute_unit_price(500_000),
                build_create_ata_idempotent(buyer, buyer, mint, tp),
                build_buy_instruction(
                    buyer, mint, bonding_curve, assoc_bc, buyer_ata,
                    token_amount, max_sol_with_slippage,
                    creator_vault, user_volume_acc, tp
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

    async def wait_for_bonding_curve_init(self, bonding_curve_str: str, timeout_sec: float = 8.0) -> bool:
        """Poll the bonding_curve account until it's owned by the pump.fun program."""
        rpcs = [ep.url for ep in self.rpc_manager.get_all_available_rpcs()]
        if not rpcs:
            logger.error("No RPC available for bonding_curve check")
            return False
        
        start = time.time()
        attempt = 0
        delay_ms = 250  # Start with 250ms delay
        
        while (time.time() - start) < timeout_sec:
            attempt += 1
            url = rpcs[attempt % len(rpcs)]
            
            try:
                async with aiohttp.ClientSession() as session:
                    payload = {
                        "jsonrpc": "2.0", "id": 1, "method": "getAccountInfo",
                        "params": [bonding_curve_str, {"encoding": "base64", "commitment": "confirmed"}]
                    }
                    async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                        data = await resp.json()
                        
                        if "error" in data:
                            err_code = data["error"].get("code", 0) if isinstance(data["error"], dict) else 0
                            if err_code == -32401:
                                self.rpc_manager.mark_auth_failure(url)
                            logger.warning(f"BC check error (attempt {attempt}): {data['error']}")
                            await asyncio.sleep(delay_ms / 1000)
                            continue
                        
                        value = data.get("result", {}).get("value")
                        if not value:
                            logger.info(f"BC account not found yet (attempt {attempt}), waiting {delay_ms}ms...")
                            await asyncio.sleep(delay_ms / 1000)
                            delay_ms = min(delay_ms + 50, 400)  # Increase delay gradually
                            continue
                        
                        owner = value.get("owner")
                        if owner == str(PUMP_FUN_PROGRAM):
                            elapsed_ms = (time.time() - start) * 1000
                            logger.info(f"BC account ready! Owner verified as pump.fun program after {elapsed_ms:.0f}ms (attempt {attempt})")
                            return True
                        elif owner == str(SYSTEM_PROGRAM):
                            logger.info(f"BC still owned by System Program (attempt {attempt}), waiting {delay_ms}ms...")
                            await asyncio.sleep(delay_ms / 1000)
                            delay_ms = min(delay_ms + 50, 400)
                            continue
                        else:
                            logger.error(f"BC owned by unexpected program: {owner}")
                            return False
                            
            except Exception as e:
                logger.warning(f"BC check attempt {attempt} failed: {e}")
                await asyncio.sleep(delay_ms / 1000)
        
        logger.error(f"BC check timeout after {timeout_sec}s ({attempt} attempts)")
        return False


    async def execute_buy_cloned(
        self, parsed_create_data: Dict, buy_amount_sol: float,
        slippage_pct: float = 25.0
    ) -> Dict:
        """Execute buy using Clone & Inject pattern - NO PDA DERIVATION."""
        start = time.time()
        mint_str = parsed_create_data.get("mint", "")
        bonding_curve_str = parsed_create_data.get("bonding_curve", "")
        
        logger.info(f"execute_buy_cloned (Clone & Inject): mint={mint_str[:12]}... amount={buy_amount_sol} SOL")
        try:
            # CRITICAL FIX: Wait for bonding_curve to be initialized before sending TX
            logger.info("Waiting for bonding_curve account to be initialized by pump.fun...")
            bc_ready = await self.wait_for_bonding_curve_init(bonding_curve_str, timeout_sec=8.0)
            if not bc_ready:
                logger.error("Bonding curve not initialized in time - aborting buy")
                return {"success": False, "error": "Bonding curve not ready (AccountOwnedByWrongProgram avoided)"}
            
            blockhash_ctx = await self.get_latest_blockhash()
            if not blockhash_ctx:
                return {"success": False, "error": "Failed to get blockhash"}

            # Use Clone & Inject instead of reconstruction
            tx_data = await self.clone_and_inject_buy_transaction(
                parsed_create_data, buy_amount_sol, slippage_pct, blockhash_ctx
            )
            if not tx_data:
                return {"success": False, "error": "Failed to clone & inject TX"}

            sig = await self.send_transaction(tx_data["tx_base64"])
            latency = (time.time() - start) * 1000

            if sig:
                logger.info(f"execute_buy_cloned SUCCESS: sig={sig[:20]}... latency={latency:.0f}ms")
                return {
                    "success": True, "signature": sig,
                    "latency_ms": latency, "mint": mint_str,
                    "amount_sol": buy_amount_sol,
                    "entry_price_sol": buy_amount_sol,
                }
            return {"success": False, "error": "Send failed", "latency_ms": latency}

        except Exception as e:
            logger.error(f"execute_buy_cloned failed: {e}", exc_info=True)
            return {"success": False, "error": str(e), "latency_ms": (time.time() - start) * 1000}


    async def execute_buy(
        self, mint_str: str, bonding_curve_str: str,
        assoc_bonding_curve_str: str, buy_amount_sol: float,
        slippage_pct: float = 25.0, token_program_str: str = None,
        creator_str: str = None
    ) -> Dict:
        start = time.time()
        tp_label = "T22" if (not token_program_str or token_program_str == TOKEN_2022_PROGRAM_STR) else "SPL"
        logger.info(f"execute_buy: mint={mint_str[:12]}... amount={buy_amount_sol} SOL token_program={tp_label}")
        try:
            # CRITICAL FIX: Wait for bonding_curve to be initialized before sending TX
            logger.info("Waiting for bonding_curve account to be initialized by pump.fun...")
            bc_ready = await self.wait_for_bonding_curve_init(bonding_curve_str, timeout_sec=8.0)
            if not bc_ready:
                logger.error("Bonding curve not initialized in time - aborting buy")
                return {"success": False, "error": "Bonding curve not ready (AccountOwnedByWrongProgram avoided)"}
            
            blockhash_ctx = await self.get_latest_blockhash()
            if not blockhash_ctx:
                return {"success": False, "error": "Failed to get blockhash"}

            tx_data = await self.build_buy_transaction(
                mint_str, bonding_curve_str, assoc_bonding_curve_str,
                buy_amount_sol, slippage_pct, blockhash_ctx, token_program_str,
                creator_str
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

    async def fetch_and_parse_tx(self, signature: str, rpc_url: str = None, max_retries: int = 2) -> Optional[Dict]:
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
                            # Drop silently - RPC errors are common in HFT, not worth warning
                            logger.debug(f"getTransaction RPC error (attempt {attempt+1}): {data['error']}")
                            await asyncio.sleep(0.2)
                            continue
                        tx_data = data.get("result")
                        if not tx_data:
                            if attempt < max_retries - 1:
                                await asyncio.sleep(0.3 + 0.2 * attempt)
                                continue
                            # Drop silently - TX not found is expected (timing, failed TX)
                            logger.debug(f"TX {signature[:16]}... not found after {max_retries} attempts (normal)")
                            return None
                        parsed = self._extract_pump_accounts(tx_data)
                        if parsed:
                            logger.info(f"Parsed TX {signature[:16]}... on attempt {attempt+1}: mint={parsed['mint'][:12]}...")
                        return parsed
            except Exception as e:
                logger.debug(f"fetch_and_parse_tx attempt {attempt+1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.2)
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
                # Extract creator from tx signers (first signer that isn't the mint)
                creator = None
                for k in keys_list:
                    ak_entry = None
                    for raw_ak in account_keys:
                        pk = raw_ak.get("pubkey", "") if isinstance(raw_ak, dict) else str(raw_ak)
                        if pk == k:
                            ak_entry = raw_ak
                            break
                    if isinstance(ak_entry, dict) and ak_entry.get("signer") and k != mint:
                        creator = k
                        break

                logger.info(f"Extracted: mint={mint[:12]}... creator={creator[:12] if creator else 'None'}... tp={'T22' if token_program_str == TOKEN_2022_PROGRAM_STR else 'SPL'}")
                
                # Build complete account metas list for cloning
                account_metas_for_clone = []
                for idx in ix_accounts:
                    if idx < len(account_keys):
                        ak = account_keys[idx]
                        pubkey_str = ak.get("pubkey", "") if isinstance(ak, dict) else str(ak)
                        is_signer = ak.get("signer", False) if isinstance(ak, dict) else False
                        is_writable = ak.get("writable", False) if isinstance(ak, dict) else False
                        account_metas_for_clone.append({
                            "pubkey": pubkey_str,
                            "isSigner": is_signer,
                            "isWritable": is_writable
                        })
                
                return {
                    "mint": mint,
                    "bonding_curve": bonding_curve,
                    "associated_bonding_curve": assoc_bonding_curve or "",
                    "token_program": token_program_str,
                    "creator": creator,
                    "accounts": ix_accounts,
                    "all_keys": keys_list,
                    "instruction_data": pump_ix.get("data", ""),
                    "account_metas_clone": account_metas_for_clone,
                }
            return None

        except Exception as e:
            # Drop silently - exceptions during extraction are common in HFT
            logger.debug(f"_extract_pump_accounts failed: {e}")
            return None


    async def build_sell_transaction(
        self, mint_str: str, bonding_curve_str: str,
        assoc_bonding_curve_str: str, token_amount: int,
        slippage_pct: float = 25.0, blockhash_ctx: Dict = None,
        token_program_str: str = None, creator_str: str = None
    ) -> Optional[Dict]:
        """Build a sell transaction for pump.fun tokens."""
        if not self._keypair:
            if not self.load_keypair_from_wallet():
                logger.error("No keypair loaded")
                return None

        tp = TOKEN_2022_PROGRAM
        if token_program_str == TOKEN_PROGRAM_STR:
            tp = TOKEN_PROGRAM

        try:
            mint = Pubkey.from_string(mint_str)
            bonding_curve = Pubkey.from_string(bonding_curve_str)
            assoc_bc = Pubkey.from_string(assoc_bonding_curve_str)
            seller = self._keypair.pubkey()
            seller_ata = get_associated_token_address(seller, mint, tp)

            # Get creator for creator_vault derivation
            creator = None
            if creator_str:
                creator = Pubkey.from_string(creator_str)
            else:
                creator = await self.fetch_bonding_curve_creator(bonding_curve_str)

            if not blockhash_ctx:
                blockhash_ctx = await self.get_latest_blockhash()
            if not blockhash_ctx or not blockhash_ctx.get("blockhash"):
                logger.error("Failed to get blockhash")
                return None

            # Derive creator_vault PDA
            if creator:
                creator_vault, _ = Pubkey.find_program_address(
                    [b"creator-vault", bytes(creator)], PUMP_FUN_PROGRAM
                )
            else:
                logger.error("No creator available for creator_vault derivation")
                return None

            # Derive user_volume_accumulator PDA
            user_volume_acc, _ = Pubkey.find_program_address(
                [b"user_volume_accumulator", bytes(seller)], PUMP_FUN_PROGRAM
            )

            # Calculate min SOL output with slippage
            # Estimate: token_amount / 30 (inverse of buy ratio) with slippage protection
            estimated_sol = token_amount / 30 / 1e9
            min_sol_lamports = int(estimated_sol * 1e9 * (1 - slippage_pct / 100))

            ixs = [
                set_compute_unit_limit(200_000),
                set_compute_unit_price(500_000),
                build_sell_instruction(
                    seller, mint, bonding_curve, assoc_bc, seller_ata,
                    token_amount, min_sol_lamports,
                    creator_vault, user_volume_acc, tp
                ),
            ]

            if self.jito_tip_account:
                tip_lamports = int(self.tip_amount_sol * 1e9)
                tip_ix = transfer(TransferParams(
                    from_pubkey=seller,
                    to_pubkey=Pubkey.from_string(self.jito_tip_account),
                    lamports=tip_lamports
                ))
                ixs.append(tip_ix)

            recent_hash = Hash.from_string(blockhash_ctx["blockhash"])
            msg = Message.new_with_blockhash(ixs, seller, recent_hash)
            tx = Transaction.new_unsigned(msg)
            tx.sign([self._keypair], recent_hash)

            tx_bytes = bytes(tx)
            import base64
            tx_b64 = base64.b64encode(tx_bytes).decode()

            logger.info(f"Built sell TX for mint={mint_str[:8]}... tokens={token_amount} tip={self.tip_amount_sol}")
            return {
                "tx_bytes": tx_bytes,
                "tx_base64": tx_b64,
                "mint": mint_str,
                "seller": str(seller),
                "seller_ata": str(seller_ata),
                "token_amount": token_amount,
                "blockhash": blockhash_ctx["blockhash"],
                "rpc_url": blockhash_ctx.get("rpc_url"),
            }

        except Exception as e:
            logger.error(f"build_sell_transaction failed: {e}")
            return None

    async def execute_sell(
        self, mint_str: str, bonding_curve_str: str,
        assoc_bonding_curve_str: str, token_amount: int,
        slippage_pct: float = 25.0, token_program_str: str = None,
        creator_str: str = None
    ) -> Dict:
        """Execute a sell transaction for pump.fun tokens."""
        start = time.time()
        tp_label = "T22" if (not token_program_str or token_program_str == TOKEN_2022_PROGRAM_STR) else "SPL"
        logger.info(f"execute_sell: mint={mint_str[:12]}... tokens={token_amount} token_program={tp_label}")
        try:
            # Get latest blockhash
            blockhash_ctx = await self.get_latest_blockhash()
            if not blockhash_ctx:
                return {"success": False, "error": "Failed to get blockhash"}

            tx_data = await self.build_sell_transaction(
                mint_str, bonding_curve_str, assoc_bonding_curve_str,
                token_amount, slippage_pct, blockhash_ctx, token_program_str,
                creator_str
            )
            if not tx_data:
                return {"success": False, "error": "Failed to build sell TX"}

            sig = await self.send_transaction(tx_data["tx_base64"])
            latency = (time.time() - start) * 1000

            if sig:
                logger.info(f"execute_sell SUCCESS: sig={sig[:20]}... latency={latency:.0f}ms")
                return {
                    "success": True, "signature": sig,
                    "latency_ms": latency, "mint": mint_str,
                    "token_amount": token_amount,
                }
            return {"success": False, "error": "Send failed", "latency_ms": latency}

        except Exception as e:
            logger.error(f"execute_sell failed: {e}", exc_info=True)
            return {"success": False, "error": str(e), "latency_ms": (time.time() - start) * 1000}

