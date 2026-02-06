# Solana HFT Bot - PRD

## Problem Statement
Professional Solana HFT Bot (Pump.fun + Raydium) with production-grade dashboard, backend API, and Telegram bot integration.

## Architecture
- **Backend**: FastAPI (Python) + MongoDB
- **Frontend**: React + Tailwind CSS + Shadcn UI + Recharts
- **Telegram**: Bot integration via aiohttp polling
- **Mode**: Simulation (default) / Live

## What's Been Implemented (Feb 6, 2026)

### Backend Services
- **RpcManagerService** - RPC pool management (Helius x3, QuickNode x2, ExtrNode x1), health scoring, failover, BlockhashContext
- **HftGateService** - Zero queue gate (MAX_IN_FLIGHT=3), drop if full
- **ParseService** - Pump.fun create instruction parsing (simulation mode)
- **StrategyEngine** - PumpScore evaluation with configurable weights/thresholds
- **ExecutionEngine** - Clone & Inject execution (simulation mode)
- **JitoService** - Jito bundle sending (simulation mode)
- **PositionManager** - Position lifecycle (TP/SL/Trailing/KillSwitch/MaxAge)
- **MetricsService** - Prometheus-style metrics, counters, gauges, histograms
- **SecurityService** - AES-256-GCM wallet encryption
- **BotManager** - Main orchestrator with simulation loop
- **TelegramService** - Full bot commands (/start, /stop, /status, /panic, /set, /logs, /help)

### Frontend Dashboard (5 pages)
- **Control** - Start/Stop, HFT Gate status, SIM/LIVE toggle, Strategy Config editor (6 tabs)
- **Positions** - Live positions table with PnL, close/force-sell actions
- **Logs** - Terminal-style live logs with level filters (ALL/INFO/WARN/ERROR/TRADE)
- **Metrics** - Latency histogram, recent latencies chart, PumpScore distribution, RPC health, KPI summary
- **Setup** - Wallet encryption (AES-256-GCM), RPC endpoints list, trade defaults

### API Endpoints (17 routes)
- Config CRUD, Wallet encrypt/unlock, Bot start/stop/panic/toggle-mode
- Positions list/history/close/force-sell/set-sl
- Metrics/KPI/Latencies/RPC health/Prometheus export
- WebSocket /api/ws for live logs & metrics

### Telegram Bot Commands
/start, /stop, /status, /panic, /set, /logs, /help

## Test Results: 94% pass rate (16/17 API endpoints, all 5 frontend pages)

## Prioritized Backlog

### P0 (Critical for Live Mode)
- Real Solana RPC integration (actual getTransaction, sendBundle)
- Live WSS subscription for Pump.fun events
- Real Jito bundle submission

### P1 (Important)
- Position close/force-sell actual Solana transaction
- RugCheck API integration (cached TTL 3s)
- Creator history analysis
- Real price feed via batch getMultipleAccounts

### P2 (Enhancement)
- Deploy scripts (pm2, systemd, Docker)
- Full test suite (Jest-equivalent unit tests)
- Prometheus /metrics endpoint for Grafana
- Config backup/export encrypted
- Telegram alerts on jito_send_failure_count > 3/min
