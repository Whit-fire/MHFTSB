# Solana HFT Bot - PRD

## Problem Statement
Professional Solana HFT Bot (Pump.fun) with production-grade dashboard, backend API, and Telegram bot integration.

## Architecture
- **Backend**: FastAPI (Python) + MongoDB
- **Frontend**: React + Tailwind CSS + Shadcn UI + Recharts
- **Mode**: Simulation (default) / Live

## What's Been Implemented

### Live Trading Pipeline (Fixed Feb 7, 2026)
1. WSS detects CREATE events via QuickNode endpoints
2. Transaction parsed with retry logic (4 attempts, endpoint rotation)
3. Token program auto-detected (Token-2022 vs legacy SPL)
4. **Creator extracted from CREATE tx** for creator_vault PDA derivation
5. Blockhash fetched from working RPC (ExtrNode/QuickNode)
6. Buy TX built with **complete 16-account layout** per latest pump.fun IDL:
   - global, fee_recipient (from Global), mint, bonding_curve, associated_bonding_curve
   - buyer_ata (Token-2022), buyer, system_program, token_program (Token-2022)
   - creator_vault (PDA), event_authority, program
   - global_volume_accumulator (PDA), user_volume_accumulator (PDA)
   - fee_config (PDA), fee_program
7. TX signed and sent via Jito sender

### Critical Fixes Applied
1. **Token-2022 Support** - pump.fun migrated to Token-2022
2. **16-account Buy Instruction** - pump.fun IDL updated with new accounts
3. **Fee recipient updated** - `62qc2CNXwrYqQScmEdiZFFAnJR262PxWEuNQtxfafNgV`
4. **RPC resilience** - Auth failure detection, endpoint rotation

### Trading Parameters
- Buy amount: 0.03 SOL | Jito tip: 0.015 SOL | Slippage: 25%

## Known Issues
- Wallet has 0 SOL - needs funding for on-chain execution
- Helius API key expired

## Prioritized Backlog

### P0 (DONE)
- ~~Live trade execution via Jito~~ ✅
- ~~Token-2022 support~~ ✅
- ~~16-account buy instruction (IDL update)~~ ✅

### P1 (Next)
- Sell logic (TP/SL on-chain)
- Strategy engine for live mode filtering
- Real price feed for position PnL

### P2 (Enhancement)
- Phantom Wallet display | Token balances | Telegram notifications
- Persistent positions storage

### P3 (Future)
- RugCheck API | Creator analysis | Deploy scripts
