import os
import csv
import asyncio
import socket
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

from telegram_notifier import TelegramNotifier

# ─── Load environment ─────────────────────────────────────────────────────────
load_dotenv()

# ─── Configuration ────────────────────────────────────────────────────────────
ESP32_CAR_HOST = os.getenv("ESP32_CAR_HOST", "10.30.0.32")
ESP32_CAM_HOST = os.getenv("ESP32_CAM_HOST", "10.30.0.31")

ESP32_CAR_URL = None
ESP32_CAM_URL = None

LOG_FILE     = "telemetry.csv"
SNAPSHOT_DIR = Path("snapshots")

HTTP_TIMEOUT = 0.5
CAM_TIMEOUT  = 8.0

TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "true").lower() == "true"

# Valid discrete movement commands — must match CarController.set_move()
VALID_CMDS = {"forward", "backward", "left", "right", "stop"}

# ─── Shared HTTP client ──────────────────────────────────────────────────────
http_client: Optional[httpx.AsyncClient] = None

# ─── Telegram ────────────────────────────────────────────────────────────────
_telegram: Optional[TelegramNotifier] = None

def get_telegram():
    global _telegram
    if not TELEGRAM_ENABLED:
        return None
    if _telegram is None:
        try:
            _telegram = TelegramNotifier()
        except Exception as e:
            print(f"[Telegram] Not configured: {e}")
            return None
    return _telegram

# ─── mDNS Resolution ───────────────────────────────────────────────────────────
def resolve_mdns(hostname: str) -> str:
    """
    Resolve mDNS hostname to IP once at startup.
    Falls back to original hostname if resolution fails.
    """
    try:
        print(f"[mDNS] Resolving {hostname}...")
        ip = socket.gethostbyname(hostname)
        print(f"[mDNS] {hostname} -> {ip}")
        return ip
    except Exception as e:
        print(f"[mDNS] Failed to resolve {hostname}: {e}")
        return hostname  # fallback

# ─── CSV Logger ──────────────────────────────────────────────────────────────
def ensure_log():
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="") as f:
            csv.writer(f).writerow(["timestamp", "event"])

def log_event(event: str):
    ensure_log()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", newline="") as f:
        csv.writer(f).writerow([ts, event])
    print(f"[LOG] {ts} | {event}")

# ─── ESP32 CAR ───────────────────────────────────────────────────────────────
async def car_get(path: str):
    """
    Forward a GET request to the ESP32 car controller and return its JSON.
    Returns {"error": "..."} on any network or HTTP failure so callers
    never have to guard against exceptions individually.
    """
    try:
        r = await http_client.get(f"{ESP32_CAR_URL}{path}", timeout=HTTP_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}

# ─── SNAPSHOT ENGINE ─────────────────────────────────────────────────────────
_snapshot_count = 0

async def capture_snapshot(prefix="snap"):
    global _snapshot_count
    _snapshot_count += 1

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{ts}_{_snapshot_count:04d}.jpg"
    path = SNAPSHOT_DIR / filename

    try:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

        url = f"{ESP32_CAM_URL}/capture_download"
        r = await http_client.get(url, timeout=CAM_TIMEOUT)

        if r.status_code != 200:
            return {"ok": False, "error": f"HTTP {r.status_code}"}

        content = r.content

        if not content.startswith(b"\xff\xd8"):
            return {"ok": False, "error": "Invalid JPEG"}

        path.write_bytes(content)
        size_kb = round(len(content) / 1024, 1)
        log_event(f"Snapshot saved: {filename} ({size_kb} KB)")

        return {
            "ok": True,
            "filename": filename,
            "path": path,
            "size_kb": size_kb,
            "count": _snapshot_count,
        }

    except Exception as e:
        return {"ok": False, "error": str(e)}

async def capture_and_notify(prefix="snap", source="manual", telegram=True):
    result = await capture_snapshot(prefix)

    if not result["ok"]:
        log_event(f"Snapshot FAILED: {result['error']}")
        return result

    if telegram:
        tg = get_telegram()
        if tg:
            await tg.send_photo(
                photo_path=str(result["path"]),
                caption=f"Snapshot #{result['count']} ({source})"
            )

    return result

# ─── AUTO SNAPSHOT ───────────────────────────────────────────────────────────
_auto_task     = None
_auto_active   = False
_auto_interval = 10

async def auto_loop():
    global _auto_active
    while _auto_active:
        await asyncio.sleep(_auto_interval)
        if not _auto_active:
            break
        await capture_and_notify(prefix="auto", source="auto")

def start_auto(interval: int):
    global _auto_task, _auto_active, _auto_interval
    stop_auto()
    _auto_interval = max(2, interval)
    _auto_active   = True
    _auto_task     = asyncio.create_task(auto_loop())

def stop_auto():
    global _auto_task, _auto_active
    _auto_active = False
    if _auto_task:
        _auto_task.cancel()
        _auto_task = None

# ─── APP LIFECYCLE ───────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client, ESP32_CAM_URL, ESP32_CAR_URL
    
    http_client = httpx.AsyncClient(timeout=CAM_TIMEOUT)
    
    # Resolve ESP32 IPs via mDNS if possible, fallback to env or defaults
    try:
        ESP32_CAM_URL = f"http://{socket.gethostbyname(ESP32_CAM_HOST)}"
        log_event(f"Resolved ESP32 CAM via mDNS: {ESP32_CAM_URL}")
    except Exception as e:
        log_event(f"Failed to resolve ESP32 CAM via mDNS: {e}")
        ESP32_CAM_URL = os.getenv("ESP32_CAM_URL")

    try:
        ESP32_CAR_URL = f"http://{socket.gethostbyname(ESP32_CAR_HOST)}"
        log_event(f"Resolved ESP32 CAR via mDNS: {ESP32_CAR_URL}")
    except Exception as e:
        log_event(f"Failed to resolve ESP32 CAR via mDNS: {e}")
        ESP32_CAR_URL = os.getenv("ESP32_CAR_URL")

    SNAPSHOT_DIR.mkdir(exist_ok=True)
    ensure_log()
    log_event("Server started")
    yield
    stop_auto()
    await http_client.aclose()
    log_event("Server stopped")

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if os.path.exists("static"):
    app.mount("/ui", StaticFiles(directory="static", html=True), name="ui")


# ══════════════════════════════════════════════════════════════════════════════
# MOVEMENT ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/move")
async def move(cmd: str = Query(...)):
    """
    Forward a discrete movement command to the ESP32 car controller.

    cmd: forward | backward | left | right | stop

    The ESP32 main.py expects:  GET /move?cmd=<cmd>
    CarController.set_move(cmd) returns False if E-STOP is locked (→ 403).
    """
    cmd = cmd.lower().strip()
    if cmd not in VALID_CMDS:
        raise HTTPException(
            400,
            detail=f"Invalid cmd '{cmd}'. Must be one of: {', '.join(sorted(VALID_CMDS))}",
        )

    res = await car_get(f"/move?cmd={cmd}")

    # Propagate 403 from ESP32 (E-STOP locked) to the frontend
    if isinstance(res, dict) and res.get("ok") is False and "locked" in res.get("error", ""):
        raise HTTPException(403, detail=res["error"])

    # Only log non-trivial commands to avoid flooding the log with 'stop' repeats
    if cmd != "stop":
        log_event(f"Move: {cmd}")
    return res


@app.get("/stop")
async def stop():
    """Hard E-STOP — cuts motors and locks the car controller."""
    res = await car_get("/stop")
    log_event("EMERGENCY STOP")
    return res


@app.get("/resume")
async def resume():
    """Clear E-STOP lock so movement commands are accepted again."""
    res = await car_get("/resume")
    log_event("Resume")
    return res

@app.get("/speed")
async def set_speed(v: int = Query(..., ge=10, le=100)):
    """Set motor speed (10–100). Forwarded to the ESP32 car controller."""
    res = await car_get(f"/speed?v={v}")
    log_event(f"Speed: {v}")
    return res
# ══════════════════════════════════════════════════════════════════════════════
# AUXILIARY ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/light")
async def light(s: int):
    """Toggle the Neopixel strip.  s=1 → on, s=0 → off."""
    res = await car_get(f"/light?s={s}")
    log_event(f"Light {'ON' if s else 'OFF'}")
    return res


@app.get("/status")
async def status():
    """
    Proxy the ESP32 /status endpoint.

    Response shape (from CarController.get_status):
        {
          "distance": float,   cm from HC-SR04
          "stopped":  bool,    True = obstacle forced a stop
          "locked":   bool,    True = E-STOP is active
          "light":    bool,
          "cmd":      str      last accepted movement command
        }
    """
    return await car_get("/status")


# ══════════════════════════════════════════════════════════════════════════════
# SNAPSHOT ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/snapshot")
async def snapshot():
    result = await capture_and_notify()
    if not result["ok"]:
        raise HTTPException(500, result["error"])
    return result


@app.get("/snapshot/auto")
async def snapshot_auto(enable: bool, interval: int = 10):
    if enable:
        start_auto(interval)
        log_event(f"Auto snapshot ON ({interval}s)")
        return {"auto": True, "interval": interval}
    else:
        stop_auto()
        log_event("Auto snapshot OFF")
        return {"auto": False}


@app.get("/snapshot/list")
async def snapshot_list():
    files = sorted(SNAPSHOT_DIR.glob("*.jpg"), reverse=True)
    return [f.name for f in files]


@app.get("/snapshot/download/{filename}")
async def snapshot_download(filename: str):
    path = SNAPSHOT_DIR / filename
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path)

@app.get("/logs/download")
async def logs_download():
    """
    Download the telemetry log CSV file.
    """
    if not os.path.exists(LOG_FILE):
        raise HTTPException(404, detail="Log file not found")

    return FileResponse(
        path=LOG_FILE,
        filename="telemetry.csv",
        media_type="text/csv"
    )

# ══════════════════════════════════════════════════════════════════════════════
# LOG ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/logs")
async def logs(limit: int = 50):
    """Return the last `limit` log entries, most-recent first."""
    ensure_log()
    with open(LOG_FILE) as f:
        rows = list(csv.DictReader(f))
    return {"logs": list(reversed(rows[-limit:]))}


@app.get("/logs/clear")
async def logs_clear():
    """Wipe the telemetry log file and start fresh."""
    with open(LOG_FILE, "w", newline="") as f:
        csv.writer(f).writerow(["timestamp", "event"])
    log_event("Log cleared")
    return {"ok": True}
