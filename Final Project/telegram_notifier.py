"""
telegram_notifier.py — Reusable Telegram Bot Notification Module
=================================================================
Provides a clean async interface for sending messages, photos,
documents, and captions to a Telegram chat via the Bot API.

Designed to be imported by any part of the project that needs
to push notifications or media to Telegram.

Setup
-----
1. Create a bot via @BotFather → get BOT_TOKEN
2. Send any message to your bot, then visit:
   https://api.telegram.org/bot<TOKEN>/getUpdates
   to find your CHAT_ID
3. Set the two env vars (or pass them directly):
   export TELEGRAM_BOT_TOKEN="123456:ABC-..."
   export TELEGRAM_CHAT_ID="987654321"

Usage
-----
    from telegram_notifier import TelegramNotifier

    tg = TelegramNotifier()                      # reads from env vars
    await tg.send_message("Hello from the car!")
    await tg.send_photo("/path/to/snap.jpg", caption="Snapshot 001")
    await tg.send_document("/path/to/log.csv", caption="Telemetry log")

Dependencies
------------
    pip install httpx python-dotenv
"""

import os
import asyncio
import mimetypes
from pathlib import Path
from datetime import datetime
from typing import Optional

import httpx
from dotenv import load_dotenv

# Load .env file if present (optional — env vars always take precedence)
load_dotenv()

# ─── Telegram API base ────────────────────────────────────────────────────────
_API_BASE = "https://api.telegram.org/bot{token}/{method}"

# ─── Default timeouts (seconds) ───────────────────────────────────────────────
_CONNECT_TIMEOUT = 5.0
_READ_TIMEOUT    = 30.0   # longer for photo uploads


class TelegramNotifier:
    """
    Async Telegram Bot client.

    All send_* methods return a result dict:
        {"ok": True,  "result": {...}}   on success
        {"ok": False, "error":  "..."}   on failure

    They never raise exceptions — failures are returned as error dicts
    so callers can decide how to handle them.
    """

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str]   = None,
    ):
        """
        Parameters
        ----------
        bot_token : Telegram Bot API token.
                    Falls back to env var TELEGRAM_BOT_TOKEN.
        chat_id   : Target chat / group / channel ID.
                    Falls back to env var TELEGRAM_CHAT_ID.
        """
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id   = chat_id   or os.getenv("TELEGRAM_CHAT_ID",   "")

        if not self.bot_token:
            raise ValueError(
                "TelegramNotifier: bot_token is required. "
                "Set TELEGRAM_BOT_TOKEN env var or pass bot_token= argument."
            )
        if not self.chat_id:
            raise ValueError(
                "TelegramNotifier: chat_id is required. "
                "Set TELEGRAM_CHAT_ID env var or pass chat_id= argument."
            )

    # ── Internal ──────────────────────────────────────────────────────────────

    def _url(self, method: str) -> str:
        return _API_BASE.format(token=self.bot_token, method=method)

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=_CONNECT_TIMEOUT,
                read=_READ_TIMEOUT,
                write=_READ_TIMEOUT,
                pool=_CONNECT_TIMEOUT,
            )
        )

    @staticmethod
    def _wrap_error(e: Exception) -> dict:
        return {"ok": False, "error": str(e)}

    # ── Public API ────────────────────────────────────────────────────────────

    async def send_message(
        self,
        text: str,
        parse_mode: str = "HTML",
        disable_notification: bool = False,
    ) -> dict:
        """
        Send a plain text message to the configured chat.

        Parameters
        ----------
        text                 : Message text (supports HTML or Markdown).
        parse_mode           : 'HTML' | 'Markdown' | 'MarkdownV2' | None
        disable_notification : Send silently (no sound/vibration).

        Example
        -------
            await tg.send_message("<b>Alert:</b> obstacle detected at 8 cm")
        """
        payload = {
            "chat_id":              self.chat_id,
            "text":                 text,
            "disable_notification": disable_notification,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:
            async with self._client() as client:
                r = await client.post(self._url("sendMessage"), json=payload)
                data = r.json()
                if not data.get("ok"):
                    return {"ok": False, "error": data.get("description", "Unknown error")}
                return {"ok": True, "result": data["result"]}
        except Exception as e:
            return self._wrap_error(e)

    async def send_photo(
        self,
        photo_path: str,
        caption: Optional[str] = None,
        parse_mode: str = "HTML",
        disable_notification: bool = False,
    ) -> dict:
        """
        Send a photo file to the configured chat.

        Parameters
        ----------
        photo_path           : Absolute or relative path to the image file.
        caption              : Optional caption text (HTML supported).
        parse_mode           : Caption parse mode.
        disable_notification : Send silently.

        Example
        -------
            await tg.send_photo(
                "/app/snapshots/snap_001.jpg",
                caption="<b>Snapshot</b> — 14:05:32"
            )
        """
        path = Path(photo_path)
        if not path.exists():
            return {"ok": False, "error": f"File not found: {photo_path}"}

        data = {
            "chat_id":              self.chat_id,
            "disable_notification": str(disable_notification).lower(),
        }
        if caption:
            data["caption"]    = caption
            data["parse_mode"] = parse_mode

        try:
            async with self._client() as client:
                with open(path, "rb") as f:
                    files = {"photo": (path.name, f, "image/jpeg")}
                    r = await client.post(
                        self._url("sendPhoto"),
                        data=data,
                        files=files,
                    )
                result = r.json()
                if not result.get("ok"):
                    return {"ok": False, "error": result.get("description", "Unknown error")}
                return {"ok": True, "result": result["result"]}
        except Exception as e:
            return self._wrap_error(e)

    async def send_document(
        self,
        file_path: str,
        caption: Optional[str] = None,
        parse_mode: str = "HTML",
        disable_notification: bool = False,
    ) -> dict:
        """
        Send any file as a Telegram document (not compressed).
        Useful for sending CSV logs, text files, etc.

        Parameters
        ----------
        file_path            : Path to the file to upload.
        caption              : Optional caption.
        parse_mode           : Caption parse mode.
        disable_notification : Send silently.

        Example
        -------
            await tg.send_document(
                "telemetry.csv",
                caption="Telemetry log export"
            )
        """
        path = Path(file_path)
        if not path.exists():
            return {"ok": False, "error": f"File not found: {file_path}"}

        mime, _ = mimetypes.guess_type(str(path))
        mime = mime or "application/octet-stream"

        data = {
            "chat_id":              self.chat_id,
            "disable_notification": str(disable_notification).lower(),
        }
        if caption:
            data["caption"]    = caption
            data["parse_mode"] = parse_mode

        try:
            async with self._client() as client:
                with open(path, "rb") as f:
                    files = {"document": (path.name, f, mime)}
                    r = await client.post(
                        self._url("sendDocument"),
                        data=data,
                        files=files,
                    )
                result = r.json()
                if not result.get("ok"):
                    return {"ok": False, "error": result.get("description", "Unknown error")}
                return {"ok": True, "result": result["result"]}
        except Exception as e:
            return self._wrap_error(e)

    async def send_snapshot_alert(
        self,
        photo_path: str,
        snapshot_num: int,
        source: str = "manual",
        extra_info: Optional[str] = None,
    ) -> dict:
        """
        Convenience wrapper: send a snapshot photo with a formatted caption.
        Intended for the surveillance car snapshot feature specifically,
        but can be reused for any snapshot alert pattern.

        Parameters
        ----------
        photo_path   : Path to the saved .jpg snapshot.
        snapshot_num : Sequential snapshot number.
        source       : 'manual' | 'auto' | 'obstacle' | any label string.
        extra_info   : Optional extra line appended to the caption.

        Example
        -------
            await tg.send_snapshot_alert(
                "snapshots/snap_0001.jpg",
                snapshot_num=1,
                source="auto",
            )
        """
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        caption_lines = [
            f"📸 <b>Snapshot #{snapshot_num:04d}</b>",
            f"🕐 {ts}",
            f"📌 Source: <code>{source}</code>",
        ]
        if extra_info:
            caption_lines.append(f"ℹ️ {extra_info}")

        caption = "\n".join(caption_lines)
        return await self.send_photo(photo_path, caption=caption)

    async def test_connection(self) -> dict:
        """
        Call getMe to verify the bot token is valid.
        Returns bot info on success.

        Example
        -------
            result = await tg.test_connection()
            print(result)  # {"ok": True, "result": {"username": "MyBot", ...}}
        """
        try:
            async with self._client() as client:
                r = await client.get(self._url("getMe"))
                data = r.json()
                if not data.get("ok"):
                    return {"ok": False, "error": data.get("description", "Invalid token")}
                return {"ok": True, "result": data["result"]}
        except Exception as e:
            return self._wrap_error(e)
