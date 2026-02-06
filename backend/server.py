from fastapi import FastAPI, APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import json
import logging
import asyncio
from pathlib import Path
from typing import List, Dict, Any

from config import get_default_config, deep_merge, set_nested_value
from models import (
    WalletSetup, WalletUnlock, WalletStatus, SetupConfig,
    ConfigUpdate, SetParam, TradeRequest, PositionAction
)
from services.security import SecurityService
from services.rpc_manager import RpcManagerService
from services.hft_gate import HftGateService
from services.parse_service import ParseService
from services.strategy_engine import StrategyEngine
from services.execution_engine import ExecutionEngine
from services.jito_service import JitoService
from services.position_manager import PositionManager
from services.metrics_service import MetricsService
from services.bot_manager import BotManager
from services.telegram_service import TelegramService
from services.wallet_service import WalletService

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")

# --- Services ---
rpc_manager = RpcManagerService()
wallet_service = WalletService(rpc_manager)
hft_gate = HftGateService(max_in_flight=3)
parse_service = ParseService(rpc_manager)
current_config = get_default_config()
strategy_engine = StrategyEngine(current_config)
jito_service = JitoService(rpc_manager)
execution_engine = ExecutionEngine(rpc_manager, jito_service)
position_manager = PositionManager(db, current_config)
metrics = MetricsService()
bot_manager = BotManager(
    db, current_config, rpc_manager, hft_gate, parse_service,
    strategy_engine, execution_engine, jito_service, position_manager, metrics
)
telegram_service = TelegramService(bot_manager, db)

# --- WebSocket Manager ---
ws_clients: List[WebSocket] = []


async def ws_broadcast(message: dict):
    dead = []
    for ws in ws_clients:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in ws_clients:
            ws_clients.remove(ws)

bot_manager.ws_broadcast = ws_broadcast

# --- Wallet State ---
wallet_state = {"encrypted_key": None, "unlocked": False, "address": None}


# --- API Routes ---
@api_router.get("/")
async def root():
    return {"message": "Solana HFT Bot API", "version": "1.0.0"}


@api_router.get("/health")
async def health():
    return {"status": "ok", "bot": bot_manager.status, "mode": bot_manager.mode}


# -- Config --
@api_router.get("/config")
async def get_config():
    saved = await db.config.find_one({}, {"_id": 0})
    if saved and "strategy" in saved:
        return {"config": saved["strategy"], "source": "database"}
    return {"config": current_config, "source": "default"}


@api_router.put("/config")
async def update_config(body: ConfigUpdate):
    global current_config
    current_config = deep_merge(current_config, body.config)
    strategy_engine.update_config(current_config)
    position_manager.update_config(current_config)
    bot_manager.config = current_config
    await db.config.update_one({}, {"$set": {"strategy": current_config}}, upsert=True)
    return {"config": current_config, "updated": True}


@api_router.post("/config/set")
async def set_config_param(body: SetParam):
    global current_config
    success = set_nested_value(current_config, body.path, body.value)
    if success:
        strategy_engine.update_config(current_config)
        position_manager.update_config(current_config)
        bot_manager.config = current_config
        await db.config.update_one({}, {"$set": {"strategy": current_config}}, upsert=True)
        return {"success": True, "path": body.path, "value": body.value}
    return {"success": False, "error": f"Invalid path: {body.path}"}


# -- Wallet --
@api_router.post("/wallet/encrypt")
async def encrypt_wallet(body: WalletSetup):
    if not body.private_key or not body.passphrase:
        return {"error": "private_key and passphrase required"}
    encrypted = SecurityService.encrypt(body.private_key, body.passphrase)
    wallet_state["encrypted_key"] = encrypted
    wallet_state["address"] = body.private_key[:8] + "..." + body.private_key[-4:]
    await db.wallet.update_one({}, {"$set": {"encrypted_key": encrypted, "address": wallet_state["address"]}}, upsert=True)
    return {"success": True, "address": wallet_state["address"]}


@api_router.post("/wallet/unlock")
async def unlock_wallet(body: WalletUnlock):
    if not wallet_state["encrypted_key"]:
        saved = await db.wallet.find_one({}, {"_id": 0})
        if saved:
            wallet_state["encrypted_key"] = saved.get("encrypted_key")
            wallet_state["address"] = saved.get("address")
    if not wallet_state["encrypted_key"]:
        return {"error": "No wallet configured. Set up wallet first."}
    try:
        SecurityService.decrypt(wallet_state["encrypted_key"], body.passphrase)
        wallet_state["unlocked"] = True
        return {"success": True, "address": wallet_state["address"]}
    except Exception:
        return {"error": "Invalid passphrase"}


@api_router.post("/wallet/reset")
async def reset_wallet():
    wallet_state["encrypted_key"] = None
    wallet_state["unlocked"] = False
    wallet_state["address"] = None
    await db.wallet.delete_many({})
    return {"success": True, "message": "Wallet reset"}


@api_router.get("/wallet/status")
async def get_wallet_status():
    if not wallet_state["encrypted_key"]:
        saved = await db.wallet.find_one({}, {"_id": 0})
        if saved:
            wallet_state["encrypted_key"] = saved.get("encrypted_key")
            wallet_state["address"] = saved.get("address")
    return WalletStatus(
        is_setup=wallet_state["encrypted_key"] is not None,
        is_unlocked=wallet_state["unlocked"],
        address=wallet_state["address"]
    )


# -- Setup --
@api_router.post("/setup")
async def save_setup(body: SetupConfig):
    setup_data = body.model_dump()
    await db.setup.update_one({}, {"$set": setup_data}, upsert=True)
    endpoints = []
    for ep in body.rpc_endpoints:
        endpoints.append({"url": ep.url, "wss": ep.wss, "pool": "fast" if ep.type in ("helius", "extrnode") else "cold", "role": ep.type})
    if body.jito_endpoint:
        endpoints.append({"url": body.jito_endpoint, "pool": "jito", "role": "jito"})
    rpc_manager.configure(endpoints)
    bot_manager.mode = body.mode
    return {"success": True, "endpoints_configured": len(endpoints)}


@api_router.get("/setup")
async def get_setup():
    saved = await db.setup.find_one({}, {"_id": 0})
    if saved:
        return {"setup": saved, "source": "database"}
    env_rpcs = []
    for key in ["HELIUS_RPC_URL1", "HELIUS_RPC_URL2", "HELIUS_RPC_URL3"]:
        url = os.environ.get(key)
        wss_key = key.replace("_URL", "_WSS")
        wss = os.environ.get(wss_key)
        if url:
            env_rpcs.append({"url": url, "wss": wss, "type": "helius", "role": "fast"})
    for key in ["QUICKNODE_RPC_URL1", "QUICKNODE_RPC_URL2"]:
        url = os.environ.get(key)
        wss_key = key.replace("_URL", "_WSS")
        wss = os.environ.get(wss_key)
        if url:
            env_rpcs.append({"url": url, "wss": wss, "type": "quicknode", "role": "cold"})
    extr = os.environ.get("EXTRNODE_RPC_URL")
    if extr:
        env_rpcs.append({"url": extr, "type": "extrnode", "role": "fast"})
    return {"setup": {"rpc_endpoints": env_rpcs, "mode": "simulation"}, "source": "env"}


# -- Bot Control --
@api_router.post("/bot/start")
async def start_bot():
    if bot_manager.status == "running":
        return {"error": "Bot already running"}
    env_data = {k: v for k, v in os.environ.items() if any(k.startswith(p) for p in ["HELIUS_", "QUICKNODE_", "EXTRNODE_"])}
    if not rpc_manager.fast_pool and not rpc_manager.cold_pool:
        rpc_manager.configure_from_env(env_data)
    result = await bot_manager.start()
    return result


@api_router.post("/bot/stop")
async def stop_bot():
    result = await bot_manager.stop()
    return result


@api_router.get("/bot/status")
async def get_bot_status():
    return bot_manager.get_full_status()


@api_router.post("/bot/panic")
async def panic():
    result = await bot_manager.panic()
    return result


@api_router.post("/bot/toggle-mode")
async def toggle_mode():
    if bot_manager.mode == "simulation":
        bot_manager.mode = "live"
    else:
        bot_manager.mode = "simulation"
    return {"mode": bot_manager.mode}


# -- Positions --
@api_router.get("/positions")
async def get_positions():
    return {"positions": position_manager.get_open_positions()}


@api_router.get("/positions/history")
async def get_position_history():
    return {"positions": position_manager.get_closed_positions(100)}


@api_router.post("/positions/{position_id}/close")
async def close_position(position_id: str):
    result = await position_manager.close_position(position_id, "manual")
    if result:
        return {"success": True, "position": result}
    return {"error": "Position not found"}


@api_router.post("/positions/{position_id}/force-sell")
async def force_sell(position_id: str):
    result = await position_manager.close_position(position_id, "force_sell")
    if result:
        return {"success": True, "position": result}
    return {"error": "Position not found"}


@api_router.put("/positions/{position_id}/sl")
async def set_sl(position_id: str, body: PositionAction):
    if body.value is None:
        return {"error": "value required"}
    success = await position_manager.set_stop_loss(position_id, body.value)
    return {"success": success}


# -- Metrics & Logs --
@api_router.get("/metrics")
async def get_metrics():
    return metrics.get_snapshot()


@api_router.get("/metrics/kpi")
async def get_kpi():
    return position_manager.get_kpi()


@api_router.get("/metrics/latencies")
async def get_latencies():
    return {"latencies": metrics.get_recent_latencies(200)}


@api_router.get("/metrics/rpc")
async def get_rpc_health():
    return rpc_manager.health_check()


@api_router.get("/metrics/prometheus")
async def prometheus_metrics():
    return PlainTextResponse(metrics.get_prometheus_text(), media_type="text/plain")


@api_router.get("/logs")
async def get_logs(limit: int = 50):
    logs = await db.logs.find({}, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    return {"logs": list(reversed(logs))}


# -- Manual Trade --
@api_router.post("/trade/buy")
async def manual_buy(body: TradeRequest):
    if bot_manager.status != "running":
        return {"error": "Bot not running"}
    await bot_manager.log("TRADE", "manual", f"Manual buy: {body.mint} amount={body.amount_sol} SOL")
    return {"success": True, "message": "Manual buy queued (simulation)"}


# -- WebSocket --
@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_clients.append(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if websocket in ws_clients:
            ws_clients.remove(websocket)


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    env_data = {k: v for k, v in os.environ.items()}
    rpc_manager.configure_from_env(env_data)
    saved_config = await db.config.find_one({}, {"_id": 0})
    global current_config
    if saved_config and "strategy" in saved_config:
        current_config = deep_merge(current_config, saved_config["strategy"])
        strategy_engine.update_config(current_config)
        position_manager.update_config(current_config)
        bot_manager.config = current_config
    saved_wallet = await db.wallet.find_one({}, {"_id": 0})
    if saved_wallet:
        wallet_state["encrypted_key"] = saved_wallet.get("encrypted_key")
        wallet_state["address"] = saved_wallet.get("address")
    await telegram_service.start()
    logger.info("Solana HFT Bot API started")


@app.on_event("shutdown")
async def shutdown():
    if bot_manager.status == "running":
        await bot_manager.stop()
    await telegram_service.stop()
    client.close()
