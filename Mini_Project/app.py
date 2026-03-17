import csv
import json
import os
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import requests
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from paho.mqtt import client as mqtt
from pydantic import BaseModel


MQTT_BROKER = os.getenv("MQTT_BROKER", "broker.hivemq.com")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", f"smart-parking-backend-{int(time.time())}")
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")

SITE_ID = os.getenv("SITE_ID", "campusA")
DEVICE_ID = os.getenv("DEVICE_ID", "esp32parking01")
TOPIC_ROOT = f"smartparking/{SITE_ID}/{DEVICE_ID}"

MQTT_TOPIC_STATE = os.getenv("MQTT_TOPIC_STATE", f"{TOPIC_ROOT}/state")
MQTT_TOPIC_EVENTS = os.getenv("MQTT_TOPIC_EVENTS", f"{TOPIC_ROOT}/event/#")
MQTT_TOPIC_CONTROL = os.getenv("MQTT_TOPIC_CONTROL", f"{TOPIC_ROOT}/control")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8581995886:AAGQdxkfjMsPULGzmehPmeApgPmqb8N6rgo")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "-5172339964")
TELEGRAM_ALLOWED_CHAT_ID = os.getenv("TELEGRAM_ALLOWED_CHAT_ID", TELEGRAM_CHAT_ID)

BLYNK_AUTH_TOKEN = os.getenv("BLYNK_AUTH_TOKEN", os.getenv("BLYNK_TOKEN", "yjYZwi6OImUXpgCDxEiQ1Yl-NFK5IiOK"))
BLYNK_BASE_URL = os.getenv("BLYNK_BASE_URL", "https://blynk.cloud/external/api")
BLYNK_POLL_INTERVAL = float(os.getenv("BLYNK_POLL_INTERVAL", "5"))

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
CSV_LOG_FILE = LOG_DIR / "parking_log.csv"

TOTAL_SLOTS = int(os.getenv("TOTAL_SLOTS", "4"))
GENERIC_GATE_NAME = os.getenv("GENERIC_GATE_NAME", "gate")
ENTRY_GATE_NAME = os.getenv("ENTRY_GATE_NAME", "entry_gate")
EXIT_GATE_NAME = os.getenv("EXIT_GATE_NAME", "exit_gate")
LED_NAME = os.getenv("LED_NAME", "led")
TELEGRAM_DEDUPE_WINDOW_SECONDS = float(os.getenv("TELEGRAM_DEDUPE_WINDOW_SECONDS", "8"))


@dataclass
class ParkingState:
    total_slots: int = TOTAL_SLOTS
    available_slots: int = TOTAL_SLOTS
    temperature: float = 0.0
    humidity: float = 0.0
    entry_gate: str = "closed"
    exit_gate: str = "closed"
    led_on: bool = False
    slots: Dict[str, bool] = field(
        default_factory=lambda: {f"slot{i}": False for i in range(1, TOTAL_SLOTS + 1)}
    )
    last_state_update: Optional[str] = None
    last_event: Optional[Dict[str, Any]] = None


class DeviceCommand(BaseModel):
    device: str
    action: str


state = ParkingState()
state_lock = threading.Lock()
event_log = deque(maxlen=150)
parking_sessions: Dict[str, float] = {}
shutdown_flag = threading.Event()


def utc_now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")


def ensure_csv_header() -> None:
    if not CSV_LOG_FILE.exists():
        with CSV_LOG_FILE.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp",
                "event_type",
                "slot",
                "gate",
                "duration_seconds",
                "fee",
                "message",
            ])


def append_csv_log(event: Dict[str, Any]) -> None:
    ensure_csv_header()
    with CSV_LOG_FILE.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                event.get("timestamp", utc_now()),
                event.get("type", "unknown"),
                event.get("slot", ""),
                event.get("gate", ""),
                event.get("duration_seconds", ""),
                event.get("fee", ""),
                event.get("message", ""),
            ]
        )


def compact_state_text() -> str:
    with state_lock:
        occupied = [name for name, busy in state.slots.items() if busy]
        free = [name for name, busy in state.slots.items() if not busy]
        return (
            "🚗 Smart Parking Status\n"
            f"Available slots: {state.available_slots}/{state.total_slots}\n"
            f"Temperature: {state.temperature:.1f}°C\n"
            f"Humidity: {state.humidity:.1f}%\n"
            f"Entry gate: {state.entry_gate}\n"
            f"Exit gate: {state.exit_gate}\n"
            f"LED: {'on' if state.led_on else 'off'}\n"
            f"Occupied: {', '.join(occupied) if occupied else 'None'}\n"
            f"Free: {', '.join(free) if free else 'None'}"
        )


class TelegramBridge:
    def __init__(self, bot_token: str, default_chat_id: str, allowed_chat_id: str):
        self.bot_token = (bot_token or "").strip()
        self.default_chat_id = str(default_chat_id or "").strip()
        self.allowed_chat_id = str(allowed_chat_id or "").strip()
        self.enabled = bool(self.bot_token)
        self.last_update_id = 0
        self.session = requests.Session()
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else ""

    def send_message(self, text: str, chat_id: Optional[str] = None) -> None:
        if not self.enabled:
            return
        target_chat_id = str(chat_id or self.default_chat_id or "").strip()
        if not target_chat_id:
            return
        try:
            self.session.post(
                f"{self.base_url}/sendMessage",
                json={"chat_id": target_chat_id, "text": text},
                timeout=15,
            )
        except requests.RequestException:
            pass

    def get_updates(self) -> list:
        if not self.enabled:
            return []
        try:
            response = self.session.get(
                f"{self.base_url}/getUpdates",
                params={
                    "timeout": 20,
                    "offset": self.last_update_id + 1,
                    "allowed_updates": json.dumps(["message"]),
                },
                timeout=30,
            )
            data = response.json()
            if not data.get("ok"):
                return []
            return data.get("result", [])
        except (requests.RequestException, ValueError):
            return []

    def handle_command(self, chat_id: str, text: str, mqtt_bridge: "MqttBridge") -> None:
        cmd = (text or "").strip().lower()
        if not cmd:
            return
        if self.allowed_chat_id and str(chat_id) != self.allowed_chat_id:
            self.send_message("Unauthorized chat ID.", chat_id=chat_id)
            return

        if cmd in ("/start", "/help"):
            self.send_message(
                "Smart Parking Bot Commands:\n"
                "/status - Current parking status\n"
                "/temp - Current temperature\n"
                "/slots - Available parking slots\n"
                "/open_entry - Open entry gate\n"
                "/close_entry - Close entry gate\n"
                "/open_exit - Open exit gate\n"
                "/close_exit - Close exit gate\n"
                "/light_on - Turn LED on\n"
                "/light_off - Turn LED off",
                chat_id=chat_id,
            )
            return

        if cmd == "/status":
            self.send_message(compact_state_text(), chat_id=chat_id)
            return
        if cmd == "/temp":
            self.send_message(f"Current temperature: {state.temperature:.1f} °C", chat_id=chat_id)
            return
        if cmd == "/slots":
            self.send_message(f"Available slots: {state.available_slots}/{state.total_slots}", chat_id=chat_id)
            return

        command_map = {
            "/open_entry": (ENTRY_GATE_NAME, "open"),
            "/close_entry": (ENTRY_GATE_NAME, "close"),
            "/open_exit": (EXIT_GATE_NAME, "open"),
            "/close_exit": (EXIT_GATE_NAME, "close"),
            "/light_on": (LED_NAME, "on"),
            "/light_off": (LED_NAME, "off"),
        }
        if cmd in command_map:
            device, action = command_map[cmd]
            mqtt_bridge.publish_control(device=device, action=action, source="telegram")
            self.send_message(f"Sent command: {device} -> {action}", chat_id=chat_id)
            return

        self.send_message("Unknown command. Send /help to see available commands.", chat_id=chat_id)

    def run_polling(self, mqtt_bridge: "MqttBridge") -> None:
        if not self.enabled:
            print("Telegram disabled: TELEGRAM_BOT_TOKEN is missing")
            return
        print("Telegram polling started")
        while not shutdown_flag.is_set():
            updates = self.get_updates()
            for item in updates:
                self.last_update_id = max(self.last_update_id, item.get("update_id", 0))
                message = item.get("message", {})
                chat_id = str(message.get("chat", {}).get("id", "")).strip()
                text = message.get("text", "")
                if chat_id and text and text.startswith("/"):
                    self.handle_command(chat_id, text, mqtt_bridge)


telegram_bridge = TelegramBridge(
    bot_token=TELEGRAM_BOT_TOKEN,
    default_chat_id=TELEGRAM_CHAT_ID,
    allowed_chat_id=TELEGRAM_ALLOWED_CHAT_ID,
)


class BlynkBridge:
    STATUS_PINS = ("V0", "V1", "V2", "V3", "V4", "V5")
    COMMAND_PINS = ("V3","V6", "V7", "V8", "V9")

    def __init__(self, auth_token: str, base_url: str, poll_interval: float):
        self.auth_token = (auth_token or "").strip()
        self.base_url = base_url.rstrip("/")
        self.poll_interval = poll_interval
        self.enabled = bool(self.auth_token)
        self.session = requests.Session()

        # Only command pins are tracked as inputs now
        self.last_input_values = {pin: "0" for pin in self.COMMAND_PINS}
        self.last_pushed_state = None
        self.lock = threading.Lock()

    def update_pin(self, pin: str, value: Any) -> None:
        if not self.enabled:
            return
        try:
            self.session.get(
                f"{self.base_url}/update",
                params={"token": self.auth_token, pin: value},
                timeout=10,
            )
        except requests.RequestException:
            pass

    def get_pin(self, pin: str) -> Optional[str]:
        if not self.enabled:
            return None
        try:
            response = self.session.get(
                f"{self.base_url}/get",
                params={"token": self.auth_token, pin: ""},
                timeout=10,
            )
            if response.ok:
                value = response.text.strip()
                if value.startswith("[") and value.endswith("]"):
                    try:
                        data = json.loads(value)
                        if data:
                            return str(data[0]).strip()
                    except Exception:
                        pass
                return value.strip().strip('"')
        except requests.RequestException:
            pass
        return None

    def reset_command_pin(self, pin: str) -> None:
        # Make push buttons behave as one-shot commands
        self.update_pin(pin, 0)
        self.last_input_values[pin] = "0"

    def build_signature(self) -> Dict[str, Any]:
        with state_lock:
            return {
                "V0": round(float(state.temperature), 1),
                "V1": round(float(state.humidity), 1),
                "V2": int(state.available_slots),
                "V3": 1 if state.led_on else 0,
                "V4": str(state.entry_gate).lower(),   # "open" / "close"
                "V5": str(state.exit_gate).lower(),    # "open" / "close"
            }

    def push_state(self, force: bool = False) -> None:
        if not self.enabled:
            return
        signature = self.build_signature()
        with self.lock:
            if not force and signature == self.last_pushed_state:
                return
            self.last_pushed_state = dict(signature)

        for pin, value in signature.items():
            print(f"Pushing to Blynk: {pin} = {value}")
            self.update_pin(pin, value)

    def poll_inputs(self, mqtt_bridge: "MqttBridge") -> None:
        if not self.enabled:
            return

        current = {pin: self.get_pin(pin) for pin in self.COMMAND_PINS}
        for pin, value in current.items():
            if value is None:
                current[pin] = self.last_input_values.get(pin, "0")

        command_map = {
            "V3": ("led", "on"),
            "V6": (ENTRY_GATE_NAME, "open"),
            "V7": (ENTRY_GATE_NAME, "close"),
            "V8": (EXIT_GATE_NAME, "open"),
            "V9": (EXIT_GATE_NAME, "close"),
        }

        for pin, pair in command_map.items():
            device, action = pair
            old_value = self.last_input_values.get(pin, "0")
            new_value = str(current.get(pin, "0"))
            print("[Debug] - Polling Blynk pin:", pin, "old_value=", old_value, "new_value=", new_value)

            # Only fire on rising edge: 0 -> 1
            if old_value != "1" and new_value == "1":
                mqtt_bridge.publish_control(
                    device=device,
                    action=action,
                    source="blynk",
                    mode="AUTO",
                    auto_close_ms=3000,
                )
                self.reset_command_pin(pin)
            else:
                self.last_input_values[pin] = new_value

    def run(self, mqtt_bridge: "MqttBridge") -> None:
        if not self.enabled:
            print("Blynk disabled: BLYNK_AUTH_TOKEN is missing")
            return
        print("Blynk bridge started")
        self.push_state(force=True)

        # make sure all command pins are reset at startup
        for pin in self.COMMAND_PINS:
            self.update_pin(pin, 0)
            self.last_input_values[pin] = "0"

        while not shutdown_flag.is_set():
            self.poll_inputs(mqtt_bridge)
            self.push_state()
            time.sleep(self.poll_interval)


blynk_bridge = BlynkBridge(
    auth_token=BLYNK_AUTH_TOKEN,
    base_url=BLYNK_BASE_URL,
    poll_interval=BLYNK_POLL_INTERVAL,
)


class MqttBridge:
    def __init__(self) -> None:
        self.client = mqtt.Client(client_id=MQTT_CLIENT_ID, clean_session=True)
        if MQTT_USERNAME:
            self.client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        self.connected = False
        self.telegram_last_sent: Dict[str, float] = {}

    def connect(self) -> None:
        self.client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        self.client.loop_start()

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    def on_connect(self, client, userdata, flags, rc):
        self.connected = rc == 0
        print(f"MQTT connected={self.connected}, rc={rc}")
        client.subscribe(MQTT_TOPIC_STATE)
        client.subscribe(MQTT_TOPIC_EVENTS)

    def on_disconnect(self, client, userdata, rc):
        self.connected = False
        print(f"MQTT disconnected, rc={rc}")

    def on_message(self, client, userdata, msg):
        raw = msg.payload.decode("utf-8", errors="ignore")
        print("MQTT RX:", msg.topic, raw)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"message": raw}

        if msg.topic == MQTT_TOPIC_STATE:
            self.process_state(payload)
        elif msg.topic.startswith(f"{TOPIC_ROOT}/event/"):
            self.process_event(payload, msg.topic)

    def process_state(self, payload: Dict[str, Any]) -> None:
        with state_lock:
            slots = payload.get("slots") or {}
            for key in list(state.slots.keys()):
                if key in slots:
                    state.slots[key] = bool(slots[key])
            computed_available = state.total_slots - sum(1 for busy in state.slots.values() if busy)
            state.available_slots = int(payload.get("available_slots", computed_available))
            state.temperature = float(payload.get("temperature", state.temperature or 0.0))
            state.humidity = float(payload.get("humidity", state.humidity or 0.0))
            if payload.get("entry_gate"):
                state.entry_gate = str(payload["entry_gate"]).lower()
            if payload.get("exit_gate"):
                state.exit_gate = str(payload["exit_gate"]).lower()
            if "led_on" in payload:
                state.led_on = bool(payload.get("led_on"))
            state.last_state_update = utc_now()
        blynk_bridge.push_state()

    def normalize_event(self, payload: Dict[str, Any], topic: str) -> Dict[str, Any]:
        payload = dict(payload)
        payload.setdefault("timestamp", payload.get("ts", utc_now()))

        if topic.endswith("/event/slot"):
            slot_name = str(payload.get("slot", "")).lower().strip()
            if not slot_name.startswith("slot"):
                slot_name = f"slot{slot_name}" if slot_name else "slot1"
            occupied = bool(payload.get("occupied", False))
            payload["slot"] = slot_name
            payload["type"] = "parking_started" if occupied else "parking_finished"
            payload.setdefault("message", f"{slot_name} occupied" if occupied else f"{slot_name} freed")
            return payload

        if topic.endswith("/event/gate_state"):
            gate = str(payload.get("gate", "entry")).lower().strip()
            gate_state = str(payload.get("state", "closed")).lower().strip()
            payload["gate"] = gate
            payload["type"] = f"{gate}_gate_opened" if gate_state == "open" else f"{gate}_gate_closed"
            payload.setdefault("message", f"{gate.capitalize()} gate {gate_state}")
            return payload

        if topic.endswith("/event/entry_presence"):
            presence = bool(payload.get("presence", False))
            distance_cm = payload.get("distance_cm")
            payload["type"] = "vehicle_at_entry" if presence else "entry_clear"
            payload.setdefault(
                "message",
                f"Vehicle detected at entry ({distance_cm} cm)" if presence else "Entry area clear",
            )
            return payload

        if topic.endswith("/event/exit_presence"):
            presence = bool(payload.get("presence", False))
            distance_cm = payload.get("distance_cm")
            payload["type"] = "vehicle_at_exit" if presence else "exit_clear"
            payload.setdefault(
                "message",
                f"Vehicle detected at exit ({distance_cm} cm)" if presence else "Exit area clear",
            )
            return payload

        if topic.endswith("/event/parking_full"):
            distance_cm = payload.get("distance_cm")
            available = payload.get("available_slots", state.available_slots)
            payload["type"] = "parking_full"
            payload.setdefault(
                "message",
                f"Parking full. Vehicle waiting at entry ({distance_cm} cm). Available slots: {available}",
            )
            return payload

        if topic.endswith("/event/led_state"):
            led_on = bool(payload.get("led_on", False))
            payload["type"] = "led_changed"
            payload.setdefault("message", "LED turned on" if led_on else "LED turned off")
            return payload

        if topic.endswith("/event/heartbeat"):
            payload["type"] = "heartbeat"
            payload.setdefault("message", "Heartbeat")
            return payload

        payload.setdefault("type", "unknown")
        return payload

    def should_send_telegram(self, payload: Dict[str, Any]) -> bool:
        event_type = payload.get("type", "unknown")
        if event_type in {
            "heartbeat",
            "led_changed",
            "entry_clear",
            "exit_clear",
            "entry_gate_closed",
            "exit_gate_closed",
        }:
            return False

        signature = "|".join(
            [
                str(event_type),
                str(payload.get("slot", "")),
                str(payload.get("gate", "")),
                str(payload.get("message", "")),
            ]
        )
        now_ts = time.time()
        last_ts = self.telegram_last_sent.get(signature, 0.0)
        if now_ts - last_ts < TELEGRAM_DEDUPE_WINDOW_SECONDS:
            return False
        self.telegram_last_sent[signature] = now_ts
        return True

    def process_event(self, payload: Dict[str, Any], topic: str) -> None:
        payload = self.normalize_event(payload, topic)
        event_type = payload.get("type", "unknown")
        slot = payload.get("slot")

        if event_type == "parking_started" and slot:
            parking_sessions[slot] = time.time()
        elif event_type == "parking_finished" and slot:
            started_at = parking_sessions.pop(slot, None)
            if started_at is not None:
                duration_seconds = int(time.time() - started_at)
                fee = (duration_seconds // 10) * 1000
                payload.setdefault("duration_seconds", duration_seconds)
                payload.setdefault("duration_minutes", round(duration_seconds / 60.0, 2))
                payload.setdefault("fee", fee)
                payload["message"] = f"{slot} freed | Duration: {duration_seconds}s | Fee: {fee} Riel"

        with state_lock:
            state.last_event = payload
            if slot in state.slots and event_type == "parking_started":
                state.slots[slot] = True
            elif slot in state.slots and event_type == "parking_finished":
                state.slots[slot] = False

            state.available_slots = state.total_slots - sum(1 for busy in state.slots.values() if busy)

            if event_type == "entry_gate_opened":
                state.entry_gate = "open"
            elif event_type == "entry_gate_closed":
                state.entry_gate = "closed"
            elif event_type == "exit_gate_opened":
                state.exit_gate = "open"
            elif event_type == "exit_gate_closed":
                state.exit_gate = "closed"
            elif event_type == "led_changed":
                state.led_on = bool(payload.get("led_on"))

        event_log.appendleft(payload)
        append_csv_log(payload)
        blynk_bridge.push_state()

        if self.should_send_telegram(payload):
            telegram_bridge.send_message(self.format_event_message(payload))

    def format_event_message(self, payload: Dict[str, Any]) -> str:
        event_type = payload.get("type", "event")
        slot = payload.get("slot")

        if payload.get("message"):
            prefix = {
                "vehicle_at_entry": "🚘",
                "vehicle_at_exit": "🚘",
                "parking_started": "🅿️",
                "parking_finished": "✅",
                "entry_gate_opened": "🟢",
                "exit_gate_opened": "🟢",
                "parking_full": "🚫",
            }.get(event_type, "📢")
            return f"{prefix} {payload['message']}"

        if event_type == "vehicle_at_entry":
            return "🚘 Vehicle detected at entry gate"
        if event_type == "vehicle_at_exit":
            return "🚘 Vehicle detected at exit gate"
        if event_type == "parking_started" and slot:
            return f"🅿️ {slot} occupied"
        if event_type == "parking_finished" and slot:
            return f"✅ {slot} freed"
        if event_type == "entry_gate_opened":
            return "🟢 Entry gate opened"
        if event_type == "exit_gate_opened":
            return "🟢 Exit gate opened"
        if event_type == "parking_full":
            return "🚫 Parking full. Vehicle detected at entry gate"
        return f"📢 Event: {event_type}"

    def publish_control(
    self,
    device: str,
    action: str,
    source: str = "dashboard",
    mode: str | None = None,
    auto_close_ms: int | None = None,
    ) -> None:
        payload = {
            "device": device,
            "action": action,
            "source": source,
            "timestamp": utc_now(),
        }

        if mode is not None:
            payload["mode"] = mode
        if auto_close_ms is not None:
            payload["auto_close_ms"] = int(auto_close_ms)

        print("Publishing control command:", payload)
        self.client.publish(MQTT_TOPIC_CONTROL, json.dumps(payload), qos=0, retain=False)


mqtt_bridge = MqttBridge()
app = FastAPI(title="Smart Parking IoT")


@app.on_event("startup")
def startup_event() -> None:
    ensure_csv_header()
    mqtt_bridge.connect()
    threading.Thread(target=telegram_bridge.run_polling, args=(mqtt_bridge,), daemon=True).start()
    threading.Thread(target=blynk_bridge.run, args=(mqtt_bridge,), daemon=True).start()


@app.on_event("shutdown")
def shutdown_event_handler() -> None:
    shutdown_flag.set()
    mqtt_bridge.stop()


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    return """
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>Smart Parking Dashboard</title>
  <script src=\"https://cdn.tailwindcss.com\"></script>
</head>
<body class=\"bg-slate-950 text-white min-h-screen\">
  <div class=\"max-w-7xl mx-auto p-6\">
    <div class=\"flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-8\">
      <div>
        <h1 class=\"text-3xl font-bold\">Smart Parking Dashboard</h1>
        <p class=\"text-slate-300\">FastAPI + MQTT + Telegram + Blynk</p>
      </div>
      <div class=\"bg-slate-900 rounded-2xl px-4 py-3 shadow-lg border border-slate-800\">
        <p class=\"text-sm text-slate-400\">Last update</p>
        <p id=\"lastUpdate\" class=\"font-medium\">Waiting for data...</p>
      </div>
    </div>

    <div class=\"grid md:grid-cols-6 gap-4 mb-6\">
      <div class=\"bg-emerald-600 rounded-2xl p-5 shadow-lg\">
        <p class=\"text-sm opacity-90\">Available Slots</p>
        <p id=\"availableSlots\" class=\"text-4xl font-bold mt-2\">-</p>
      </div>
      <div class=\"bg-sky-700 rounded-2xl p-5 shadow-lg\">
        <p class=\"text-sm opacity-90\">Temperature</p>
        <p id=\"temperature\" class=\"text-4xl font-bold mt-2\">-</p>
      </div>
      <div class=\"bg-indigo-700 rounded-2xl p-5 shadow-lg\">
        <p class=\"text-sm opacity-90\">Humidity</p>
        <p id=\"humidity\" class=\"text-4xl font-bold mt-2\">-</p>
      </div>
      <div class=\"bg-amber-600 rounded-2xl p-5 shadow-lg\">
        <p class=\"text-sm opacity-90\">Total Slots</p>
        <p id=\"totalSlots\" class=\"text-4xl font-bold mt-2\">-</p>
      </div>
      <div class=\"bg-fuchsia-700 rounded-2xl p-5 shadow-lg\">
        <p class=\"text-sm opacity-90\">Entry Gate</p>
        <p id=\"entryGateCard\" class=\"text-3xl font-bold mt-2\">-</p>
      </div>
      <div class=\"bg-cyan-700 rounded-2xl p-5 shadow-lg\">
        <p class=\"text-sm opacity-90\">Exit Gate</p>
        <p id=\"exitGateCard\" class=\"text-3xl font-bold mt-2\">-</p>
      </div>
    </div>

    <div class=\"grid lg:grid-cols-3 gap-6\">
      <div class=\"lg:col-span-2 bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-lg\">
        <div class=\"flex items-center justify-between mb-4\">
          <h2 class=\"text-xl font-semibold\">Parking Slots</h2>
          <div class=\"text-sm text-slate-400\">Green = free, Red = occupied</div>
        </div>
        <div id=\"slotGrid\" class=\"grid grid-cols-2 md:grid-cols-4 gap-4\"></div>
      </div>

      <div class=\"bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-lg\">
        <h2 class=\"text-xl font-semibold mb-4\">Controls</h2>
        <div class=\"space-y-3\">
          <button onclick=\"sendCommand('entry_gate','open')\" class=\"w-full bg-emerald-600 hover:bg-emerald-500 rounded-xl p-3 font-semibold\">Open Entry Gate</button>
          <button onclick=\"sendCommand('entry_gate','close')\" class=\"w-full bg-red-600 hover:bg-red-500 rounded-xl p-3 font-semibold\">Close Entry Gate</button>
          <button onclick=\"sendCommand('exit_gate','open')\" class=\"w-full bg-cyan-600 hover:bg-cyan-500 rounded-xl p-3 font-semibold\">Open Exit Gate</button>
          <button onclick=\"sendCommand('exit_gate','close')\" class=\"w-full bg-orange-600 hover:bg-orange-500 rounded-xl p-3 font-semibold\">Close Exit Gate</button>
          <button onclick=\"sendCommand('led','on')\" class=\"w-full bg-yellow-400 hover:bg-yellow-300 text-black rounded-xl p-3 font-semibold\">LED On</button>
          <button onclick=\"sendCommand('led','off')\" class=\"w-full bg-slate-400 hover:bg-slate-300 text-black rounded-xl p-3 font-semibold\">LED Off</button>
          <button onclick="downloadCsvLog()" class="w-full bg-blue-600 hover:bg-blue-500 rounded-xl p-3 font-semibold">Download CSV Log</button>
        </div>
        <div class=\"mt-6 text-sm text-slate-300 space-y-1\">
          <p><span class=\"font-semibold\">Entry gate:</span> <span id=\"entryGate\">-</span></p>
          <p><span class=\"font-semibold\">Exit gate:</span> <span id=\"exitGate\">-</span></p>
          <p><span class=\"font-semibold\">LED:</span> <span id=\"ledState\">-</span></p>
        </div>
      </div>
    </div>

    <div class=\"mt-6 bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-lg\">
      <h2 class=\"text-xl font-semibold mb-4\">Recent Events</h2>
      <div id=\"eventList\" class=\"space-y-3 text-sm\"></div>
    </div>
  </div>

  <script>
    async function loadState() {
      const stateRes = await fetch('/api/state');
      const state = await stateRes.json();

      document.getElementById('availableSlots').textContent = state.available_slots;
      document.getElementById('temperature').textContent = `${state.temperature.toFixed(1)} °C`;
      document.getElementById('humidity').textContent = `${state.humidity.toFixed(1)} %`;
      document.getElementById('totalSlots').textContent = state.total_slots;
      document.getElementById('entryGate').textContent = state.entry_gate;
      document.getElementById('exitGate').textContent = state.exit_gate;
      document.getElementById('entryGateCard').textContent = state.entry_gate.toUpperCase();
      document.getElementById('exitGateCard').textContent = state.exit_gate.toUpperCase();
      document.getElementById('ledState').textContent = state.led_on ? 'ON' : 'OFF';
      document.getElementById('lastUpdate').textContent = state.last_state_update || 'No update yet';

      const slotGrid = document.getElementById('slotGrid');
      slotGrid.innerHTML = '';
      Object.entries(state.slots).forEach(([slot, occupied]) => {
        const card = document.createElement('div');
        card.className = `rounded-2xl p-5 text-center font-semibold shadow-lg ${occupied ? 'bg-red-600' : 'bg-emerald-600'}`;
        card.innerHTML = `<div class=\"text-lg\">${slot.toUpperCase()}</div><div class=\"text-sm mt-2\">${occupied ? 'Occupied' : 'Free'}</div>`;
        slotGrid.appendChild(card);
      });

      const eventsRes = await fetch('/api/events');
      const events = await eventsRes.json();
      const eventList = document.getElementById('eventList');
      eventList.innerHTML = '';
      events.forEach((event) => {
        const item = document.createElement('div');
        item.className = 'rounded-xl bg-slate-800 p-4 border border-slate-700';
        const body = event.message || event.type;
        item.innerHTML = `<div class=\"text-slate-400\">${event.timestamp || ''}</div><div class=\"mt-1\">${body}</div>`;
        eventList.appendChild(item);
      });
    }

    async function sendCommand(device, action) {
      const res = await fetch('/api/control', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({device, action})
      });
      const text = await res.text();
      console.log('status:', res.status);
      console.log('response:', text);
      await loadState();
    }

    function downloadCsvLog() {
      window.location.href = '/api/logs/csv';
    }

    loadState();
    setInterval(loadState, 3000);
  </script>
</body>
</html>
    """


@app.get("/api/state")
def get_state() -> Dict[str, Any]:
    with state_lock:
        return asdict(state)


@app.get("/api/events")
def get_events() -> list:
    return list(event_log)


@app.get("/api/logs/csv")
def download_csv_log():
    ensure_csv_header()
    return FileResponse(
        path=str(CSV_LOG_FILE),
        media_type="text/csv",
        filename="parking_log.csv",
    )


@app.post("/api/control")
def control_device(command: DeviceCommand) -> Dict[str, str]:
    device = command.device.strip().lower()
    action = command.action.strip().lower()

    valid_devices = {GENERIC_GATE_NAME, ENTRY_GATE_NAME, EXIT_GATE_NAME, LED_NAME}
    if device not in valid_devices:
        raise HTTPException(status_code=400, detail="Invalid device name")

    if device in {GENERIC_GATE_NAME, ENTRY_GATE_NAME, EXIT_GATE_NAME}:
        allowed_actions = {"open", "close"}
    else:
        allowed_actions = {"on", "off"}

    if action not in allowed_actions:
        raise HTTPException(status_code=400, detail="Invalid action")

    mqtt_bridge.publish_control(device=device, action=action, source="dashboard")
    return {"status": "ok", "device": device, "action": action}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
