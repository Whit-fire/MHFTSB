from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import uuid


class WalletSetup(BaseModel):
    private_key: Optional[str] = None
    passphrase: Optional[str] = None


class WalletUnlock(BaseModel):
    passphrase: str


class WalletStatus(BaseModel):
    is_setup: bool = False
    is_unlocked: bool = False
    address: Optional[str] = None


class RpcEndpointModel(BaseModel):
    url: str
    wss: Optional[str] = None
    type: str = "helius"
    role: str = "fast"


class SetupConfig(BaseModel):
    rpc_endpoints: List[RpcEndpointModel] = []
    jito_endpoint: Optional[str] = None
    jito_tip_accounts: List[str] = []
    tip_amount_sol: float = 0.001
    default_trade_amount_sol: float = 0.5
    slippage_percent: float = 1.0
    mode: str = "simulation"


class ConfigUpdate(BaseModel):
    config: Dict[str, Any]


class SetParam(BaseModel):
    path: str
    value: Any


class BotAction(BaseModel):
    action: str


class TradeRequest(BaseModel):
    mint: str
    amount_sol: float


class PositionAction(BaseModel):
    action: str
    value: Optional[float] = None


class Position(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    token_mint: str = ""
    token_name: str = ""
    entry_price_sol: float = 0
    current_price_sol: float = 0
    amount_sol: float = 0
    pnl_sol: float = 0.0
    pnl_percent: float = 0.0
    entry_time: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    pump_score: float = 0.0
    status: str = "open"
    stop_loss: float = -10.0
    trailing_active: bool = False
    close_reason: Optional[str] = None
    close_time: Optional[str] = None
    tx_signature: Optional[str] = None


class LogEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    level: str = "INFO"
    service: str = ""
    message: str = ""
    data: Dict[str, Any] = {}
    latency_ms: Optional[float] = None
