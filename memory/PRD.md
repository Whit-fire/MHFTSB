# Solana HFT Bot - PRD

## Problem Statement
Professional Solana HFT Bot (Pump.fun + Raydium) with production-grade dashboard, backend API, and Telegram bot integration.

## Architecture
- **Backend**: FastAPI (Python) + MongoDB
- **Frontend**: React + Tailwind CSS + Shadcn UI + Recharts
- **Telegram**: Bot integration via aiohttp polling
- **Mode**: Simulation (default) / Live

## What's Been Implemented

### Backend Services
- **RpcManagerService** - RPC pool management, health scoring, failover, auth failure detection (5min cooldown)
- **HftGateService** - Zero queue gate (MAX_IN_FLIGHT=3)
- **SolanaTrader** - LIVE buy TX builder with Token-2022 support + Jito sender
- **LiquidityMonitor** - WSS logsSubscribe for Pump.fun CREATE events with exponential backoff
- **PositionManager** - Position lifecycle (TP/SL/Trailing/KillSwitch/MaxAge)
- **MetricsService** - Prometheus-style metrics
- **SecurityService** - AES-256-GCM wallet encryption
- **BotManager** - Main orchestrator (simulation + live modes)
- **TelegramService** - Bot commands

### Live Trading Pipeline (Fixed Feb 7, 2026)
1. WSS detects CREATE events via QuickNode endpoints
2. Transaction parsed with retry logic (4 attempts, endpoint rotation)
3. **Token program auto-detected** (Token-2022 vs legacy SPL) from CREATE tx
4. Blockhash fetched from working RPC (ExtrNode/QuickNode)
5. Buy TX built with correct Token-2022 program for ATA + buy instruction
6. TX signed and sent via Jito sender

### Critical Fix: Token-2022 Support (Feb 7, 2026)
- pump.fun migrated to Token-2022 (`TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb`)
- ATA derivation, ATA creation, and buy instruction all use correct token program
- Auto-detection from CREATE transaction accounts (supports both legacy and Token-2022)

### RPC Resilience
- Auth failure detection (-32401) with 5-min cooldown
- Automatic endpoint rotation across fast + cold pools
- Helius endpoints currently invalid (API key expired)
- QuickNode WSS + ExtrNode HTTP functioning as primary

### Frontend Dashboard (5 pages)
- Control, Positions, Logs, Metrics, Setup

### Trading Parameters
- Buy amount: 0.03 SOL
- Jito tip: 0.015 SOL
- Slippage: 25%
- Compute units: 200,000 / price: 500,000

## Known Issues
- Helius API key expired - needs user to provide valid key
- Wallet needs SOL funding for on-chain execution

## Prioritized Backlog

### P0 (DONE)
- ~~Live trade execution via Jito~~ COMPLETED
- ~~Token-2022 support for pump.fun~~ COMPLETED

### P1 (Important)
- Sell logic (TP/SL on-chain)
- Strategy engine for live mode filtering
- Real price feed for position PnL

### P2 (Enhancement)
- Phantom Wallet display
- Token balances in wallet panel
- Telegram notifications for live trades
- Persistent positions storage

### P3 (Future)
- RugCheck API integration
- Creator history analysis
- Deploy scripts
