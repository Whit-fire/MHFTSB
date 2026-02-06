import os
import asyncio
import logging
import aiohttp
from typing import Optional

logger = logging.getLogger("telegram_bot")


class TelegramService:
    def __init__(self, bot_manager, db):
        self.bot_manager = bot_manager
        self.db = db
        self.token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        self.admin_ids = set()
        if self.chat_id:
            self.admin_ids.add(str(self.chat_id))
        self._running = False
        self._session: Optional[aiohttp.ClientSession] = None
        self._offset = 0

    @property
    def api_url(self):
        return f"https://api.telegram.org/bot{self.token}"

    async def start(self):
        if not self.token:
            logger.warning("No TELEGRAM_BOT_TOKEN configured")
            return
        self._running = True
        self._session = aiohttp.ClientSession()
        asyncio.create_task(self._poll_loop())
        logger.info("Telegram bot started polling")

    async def stop(self):
        self._running = False
        if self._session:
            await self._session.close()
            self._session = None

    async def send_message(self, text: str, chat_id: str = None):
        if not self.token:
            return
        target = chat_id or self.chat_id
        if not target:
            return
        try:
            if not self._session or self._session.closed:
                self._session = aiohttp.ClientSession()
            async with self._session.post(f"{self.api_url}/sendMessage", json={
                "chat_id": target, "text": text, "parse_mode": "HTML"
            }) as resp:
                if resp.status != 200:
                    data = await resp.text()
                    logger.error(f"Telegram send failed: {resp.status} {data}")
        except Exception as e:
            logger.error(f"Telegram send error: {e}")

    async def _poll_loop(self):
        while self._running:
            try:
                if not self._session or self._session.closed:
                    self._session = aiohttp.ClientSession()
                async with self._session.get(
                    f"{self.api_url}/getUpdates",
                    params={"offset": self._offset, "timeout": 10},
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for update in data.get("result", []):
                            self._offset = update["update_id"] + 1
                            await self._handle_update(update)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Telegram poll error: {e}")
                await asyncio.sleep(5)

    async def _handle_update(self, update: dict):
        msg = update.get("message", {})
        text = msg.get("text", "")
        chat_id = str(msg.get("chat", {}).get("id", ""))
        if not text.startswith("/"):
            return
        parts = text.split()
        cmd = parts[0].lower().split("@")[0]
        args = parts[1:]

        handlers = {
            "/start": self._cmd_start,
            "/stop": self._cmd_stop,
            "/status": self._cmd_status,
            "/panic": self._cmd_panic,
            "/set": self._cmd_set,
            "/logs": self._cmd_logs,
            "/help": self._cmd_help,
        }
        handler = handlers.get(cmd)
        if handler:
            await handler(chat_id, args)
        else:
            await self.send_message(f"Unknown command: {cmd}\nUse /help", chat_id)

    async def _cmd_start(self, chat_id, args):
        result = await self.bot_manager.start()
        mode = self.bot_manager.mode.upper()
        await self.send_message(f"<b>Bot Started</b>\nMode: {mode}", chat_id)

    async def _cmd_stop(self, chat_id, args):
        await self.bot_manager.stop()
        await self.send_message("<b>Bot Stopped</b>", chat_id)

    async def _cmd_status(self, chat_id, args):
        s = self.bot_manager.get_full_status()
        gate = s.get("hft_gate", {})
        pos = s.get("positions", {})
        exe = s.get("execution", {})
        text = (
            f"<b>STATUS: {s['status'].upper()}</b> ({s['mode']})\n"
            f"HFT Gate: {gate.get('in_flight',0)}/{gate.get('max_in_flight',3)} | {gate.get('dropped_count',0)} dropped\n"
            f"Positions: {pos.get('open_positions',0)}/{pos.get('max_positions',30)} | PnL: {pos.get('total_pnl_sol',0):.4f} SOL\n"
            f"Win Rate: {pos.get('win_rate',0):.1f}%\n"
            f"Exec: {exe.get('success_rate',0):.1f}% success | {exe.get('avg_latency_ms',0):.0f}ms avg\n"
            f"Uptime: {s['uptime_seconds']:.0f}s"
        )
        await self.send_message(text, chat_id)

    async def _cmd_panic(self, chat_id, args):
        await self.bot_manager.panic()
        await self.send_message("<b>PANIC EXECUTED</b>\nAll positions closed. Bot stopped.", chat_id)

    async def _cmd_set(self, chat_id, args):
        if len(args) < 2:
            await self.send_message("Usage: /set FILTERS.MIN_LIQUIDITY_SOL 1.0", chat_id)
            return
        from config import set_nested_value
        path, value = args[0], args[1]
        config = self.bot_manager.config
        if set_nested_value(config, path, value):
            self.bot_manager.strategy_engine.update_config(config)
            self.bot_manager.position_manager.update_config(config)
            try:
                await self.db.config.update_one({}, {"$set": {"strategy": config}}, upsert=True)
            except Exception:
                pass
            await self.send_message(f"Updated <b>{path}</b> = {value}", chat_id)
        else:
            await self.send_message(f"Invalid path: {path}", chat_id)

    async def _cmd_logs(self, chat_id, args):
        limit = int(args[0]) if args and args[0].isdigit() else 5
        logs = await self.db.logs.find({}, {"_id": 0}).sort("timestamp", -1).to_list(limit)
        if not logs:
            await self.send_message("No logs yet.", chat_id)
            return
        text = "\n".join(
            f"[{l.get('level','')}] {l.get('service','')}: {l.get('message','')}"
            for l in reversed(logs)
        )
        await self.send_message(f"<pre>{text[:3000]}</pre>", chat_id)

    async def _cmd_help(self, chat_id, args):
        text = (
            "<b>Solana HFT Bot Commands</b>\n\n"
            "/start - Start the bot\n"
            "/stop - Stop the bot\n"
            "/status - Show bot status\n"
            "/panic - Emergency close all\n"
            "/set path value - Update config\n"
            "/logs [n] - Show recent logs\n"
            "/help - Show this help"
        )
        await self.send_message(text, chat_id)
