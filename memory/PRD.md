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
- **RpcManagerService** - RPC pool management (Helius x3, QuickNode x2, ExtrNode x1), health scoring, failover, BlockhashContext, auth failure detection
- **HftGateService** - Zero queue gate (MAX_IN_FLIGHT=3), drop if full
- **ParseService** - Pump.fun create instruction parsing (simulation mode)
- **StrategyEngine** - PumpScore evaluation with configurable weights/thresholds
- **ExecutionEngine** - Clone & Inject execution (simulation mode)
- **JitoService** - Jito bundle sending (simulation mode)
- **PositionManager** - Position lifecycle (TP/SL/Trailing/KillSwitch/MaxAge)
- **MetricsService** - Prometheus-style metrics, counters, gauges, histograms
- **SecurityService** - AES-256-GCM wallet encryption
- **BotManager** - Main orchestrator with simulation loop + LIVE mode
- **TelegramService** - Full bot commands
- **SolanaTrader** - **LIVE** buy transaction builder + Jito sender (WORKING)
- **LiquidityMonitor** - WSS logsSubscribe for Pump.fun CREATE events (WORKING)

### Live Trading Pipeline (Fixed Feb 7, 2026)
1. WSS detects CREATE events via QuickNode endpoints
2. Transaction parsed via RPC with retry logic (4 attempts, rotating endpoints)
3. Blockhash fetched from working RPC (ExtrNode/QuickNode)
4. Buy TX built with compute budget, ATA creation, pump.fun buy, Jito tip
5. TX signed and sent via Jito sender (fra-sender.helius-rpc.com/fast)
6. Position registered on success

### RPC Resilience
- Auth failure detection (-32401) with 5-min cooldown
- Automatic endpoint rotation across fast and cold pools
- Helius endpoints currently invalid (API key expired)
- QuickNode WSS + ExtrNode HTTP functioning as primary

### Frontend Dashboard (5 pages)
- **Control** - Start/Stop, HFT Gate status, SIM/LIVE toggle, Strategy Config editor
- **Positions** - Live positions table with PnL, close/force-sell actions
- **Logs** - Terminal-style live logs with level filters
- **Metrics** - Latency histogram, PumpScore distribution, RPC health, KPI summary
- **Setup** - Wallet encryption (AES-256-GCM), RPC endpoints list

### API Endpoints (17+ routes)
- Config CRUD, Wallet encrypt/unlock/reset/balance
- Bot start/stop/panic/toggle-mode
- Positions list/history/close/force-sell/set-sl
- Metrics/KPI/Latencies/RPC health/Prometheus export
- WebSocket /api/ws for live logs & metrics

## Known Issues
- Helius API key (`hft-dashboard-4`) expired/invalid - needs user to provide valid key
- Wallet has 0 SOL - trades send to Jito but won't land on-chain until funded
- Positions are in-memory only (cleared on bot stop)

## Trading Parameters
- Buy amount: 0.03 SOL
- Jito tip: 0.015 SOL
- Slippage: 25%
- Compute units: 200,000
- Compute price: 500,000

## Prioritized Backlog

### P0 (DONE)
- ~~Real live trade execution via Jito~~ COMPLETED

### P1 (Important)
- Implement sell logic (take-profit, stop-loss)
- Strategy engine integration for live mode (liquidity/score filtering)
- Real price feed for position PnL tracking

### P2 (Enhancement)
- Phantom Wallet display integration
- Token balances display in wallet panel
- Finalize Telegram notifications for live trades
- Persistent positions storage (survive bot restart)

### P3 (Future)
- RugCheck API integration
- Creator history analysis
- Deploy scripts (Docker)
- Full test suite
