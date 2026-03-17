import network
import time
import machine
import ujson
import dht

from umqtt.simple import MQTTClient
from hardware import IR, UltraSonic, Servo, TMDriver, LCD

# =========================
# USER CONFIG
# =========================
WIFI_SSID = "Robotic WIFI"
WIFI_PASSWORD = "rbtWIFI@2025"

BROKER = "broker.hivemq.com"
BROKER_PORT = 1883

SITE_ID = "campusA"
DEVICE_ID = "esp32parking01"
TOPIC_ROOT = "smartparking/{}/{}".format(SITE_ID, DEVICE_ID)

# =========================
# PIN CONFIG
# 2 ultrasonic + 2 servos + 4 IR + LED + DHT11 + TM1637 + LCD
# =========================
ENTRY_TRIG_PIN = 33
ENTRY_ECHO_PIN = 32

EXIT_TRIG_PIN = 5
EXIT_ECHO_PIN = 18

ENTRY_SERVO_PIN = 16
EXIT_SERVO_PIN = 12

IR_SLOT_PINS = {
    "slot1": 14,
    "slot2": 27,
    "slot3": 26,
    "slot4": 25,
}

LED_PIN = 2
DHT_PIN = 4

TM1637_CLK_PIN = 19
TM1637_DIO_PIN = 23
LCD_SCL_PIN = 22
LCD_SDA_PIN = 21

# =========================
# SYSTEM CONFIG
# =========================
ENTRY_DETECT_THRESHOLD_CM = 8
EXIT_DETECT_THRESHOLD_CM = 8
SERVO_OPEN_ANGLE = 80
SERVO_CLOSE_ANGLE = 0

SLOT_DEBOUNCE_MS = 250
ULTRASONIC_DEBOUNCE_MS = 450
ULTRA_NA_RESET_LIMIT = 3

ENTRY_AUTO_CLOSE_MS = 3000
EXIT_AUTO_CLOSE_MS = 3000

HEARTBEAT_INTERVAL_MS = 10000
ENV_PUBLISH_INTERVAL_MS = 5000
LOOP_DELAY_MS = 300

LOCAL_TZ_OFFSET_SECONDS = 7 * 3600
TOTAL_SLOTS = len(IR_SLOT_PINS)

# =========================
# GLOBALS
# =========================
wlan = network.WLAN(network.STA_IF)
mqtt = None
pending_messages = []

last_heartbeat_ms = 0
last_env_publish_ms = 0

last_temp = 0.0
last_humi = 0.0

slot_raw = {}
slot_stable = {}
slot_changed_ms = {}
slot_last_reported = {}

entry_detect_started_ms = None
entry_triggered = False
entry_ultra_na_count = 0
entry_last_presence_sent = None
entry_full_alert_sent = False

exit_detect_started_ms = None
exit_triggered = False
exit_ultra_na_count = 0
exit_last_presence_sent = None

entry_gate_state = {
    "state": "CLOSED",
    "mode": "AUTO",
    "opened_at": 0,
    "auto_close_ms": ENTRY_AUTO_CLOSE_MS,
}

exit_gate_state = {
    "state": "CLOSED",
    "mode": "AUTO",
    "opened_at": 0,
    "auto_close_ms": EXIT_AUTO_CLOSE_MS,
}

# =========================
# HARDWARE OBJECTS
# =========================
entry_ultra = UltraSonic(ENTRY_TRIG_PIN, ENTRY_ECHO_PIN)
exit_ultra = UltraSonic(EXIT_TRIG_PIN, EXIT_ECHO_PIN)
entry_servo = Servo(ENTRY_SERVO_PIN)
exit_servo = Servo(EXIT_SERVO_PIN)
slot_sensors = {name: IR(pin) for name, pin in IR_SLOT_PINS.items()}
led = machine.Pin(LED_PIN, machine.Pin.OUT)
dht_sensor = dht.DHT11(machine.Pin(DHT_PIN))

tm_display = TMDriver(TM1637_CLK_PIN, TM1637_DIO_PIN, brightness=5)
lcd_display = LCD(LCD_SCL_PIN, LCD_SDA_PIN)

# =========================
# HELPERS
# =========================
def now_iso():
    t = time.time()
    tmv = time.localtime(t)
    return "%04d-%02d-%02d %02d:%02d:%02d" % (
        tmv[0], tmv[1], tmv[2], tmv[3], tmv[4], tmv[5]
    )


def mqtt_topic(suffix):
    return "{}/{}".format(TOPIC_ROOT, suffix)


def occupied_count():
    count = 0
    for slot_name in slot_stable:
        if slot_stable[slot_name]:
            count += 1
    return count


def available_slots():
    return TOTAL_SLOTS - occupied_count()


def publish_event(suffix, payload):
    global mqtt
    try:
        if mqtt is not None:
            mqtt.publish(mqtt_topic(suffix), ujson.dumps(payload))
    except Exception as e:
        print("Publish failed:", e)
        mqtt = None


def build_slots_payload():
    data = {}
    for slot_name in IR_SLOT_PINS:
        data[slot_name] = bool(slot_stable.get(slot_name, False))
    return data


def update_displays():
    slots = available_slots()
    try:
        tm_display.display_number(slots)
    except Exception as e:
        print("TM1637 update failed:", e)

    try:
        line1 = "Welcome!"
        line2 = "Slots: {}/{}".format(slots, TOTAL_SLOTS)
        lcd_display.display_message(line1 + "\n" + line2)
    except Exception as e:
        print("LCD update failed:", e)


def set_led(on_value):
    led.value(1 if on_value else 0)
    publish_event("event/led_state", {
        "ts": now_iso(),
        "led_on": bool(on_value),
        "device_id": DEVICE_ID,
    })


def publish_gate_state(gate_name):
    gate_state = entry_gate_state if gate_name == "entry" else exit_gate_state
    publish_event("event/gate_state", {
        "ts": now_iso(),
        "gate": gate_name,
        "state": gate_state["state"],
        "mode": gate_state["mode"],
        "device_id": DEVICE_ID,
    })


def publish_slot_event(slot_name):
    publish_event("event/slot", {
        "ts": now_iso(),
        "slot": slot_name,
        "occupied": bool(slot_stable.get(slot_name, False)),
        "device_id": DEVICE_ID,
    })


def publish_presence_event(sensor_name, distance_cm, presence):
    global entry_last_presence_sent, exit_last_presence_sent

    presence = bool(presence)
    if sensor_name == "entry_presence":
        if entry_last_presence_sent is presence:
            return
        entry_last_presence_sent = presence
    else:
        if exit_last_presence_sent is presence:
            return
        exit_last_presence_sent = presence

    publish_event("event/{}".format(sensor_name), {
        "ts": now_iso(),
        "sensor": sensor_name,
        "distance_cm": distance_cm,
        "presence": presence,
        "device_id": DEVICE_ID,
    })


def publish_env_event(temp_c, humi):
    publish_event("state", {
        "ts": now_iso(),
        "temperature": float(temp_c),
        "humidity": float(humi),
        "available_slots": available_slots(),
        "slots": build_slots_payload(),
        "entry_gate": entry_gate_state["state"].lower(),
        "exit_gate": exit_gate_state["state"].lower(),
        "entry_gate_mode": entry_gate_state["mode"].lower(),
        "exit_gate_mode": exit_gate_state["mode"].lower(),
        "led_on": bool(led.value()),
        "device_id": DEVICE_ID,
    })


def publish_boot_state():
    publish_gate_state("entry")
    publish_gate_state("exit")
    for slot_name in IR_SLOT_PINS:
        publish_slot_event(slot_name)
    publish_event("event/heartbeat", {
        "ts": now_iso(),
        "ip": wlan.ifconfig()[0] if wlan.isconnected() else None,
        "device_id": DEVICE_ID,
    })
    publish_env_event(last_temp, last_humi)
    update_displays()


def connect_wifi():
    wlan.active(True)
    if wlan.isconnected():
        return

    print("Connecting Wi-Fi...")
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)

    timeout = time.ticks_add(time.ticks_ms(), 15000)
    while not wlan.isconnected():
        if time.ticks_diff(timeout, time.ticks_ms()) <= 0:
            raise RuntimeError("Wi-Fi timeout")
        time.sleep_ms(300)

    print("Wi-Fi connected:", wlan.ifconfig())


def mqtt_callback(topic, msg):
    try:
        pending_messages.append((topic.decode(), msg.decode()))
    except Exception as e:
        print("MQTT callback error:", e)


def connect_mqtt():
    global mqtt
    client_id = "esp32-{}".format(DEVICE_ID)
    mqtt = MQTTClient(client_id=client_id, server=BROKER, port=BROKER_PORT, keepalive=30)
    mqtt.set_callback(mqtt_callback)
    mqtt.connect()
    mqtt.subscribe(mqtt_topic("control"))
    print("MQTT connected")
    publish_boot_state()


def safe_connect():
    global mqtt
    if not wlan.isconnected():
        try:
            connect_wifi()
        except Exception as e:
            print("Wi-Fi reconnect failed:", e)
            return

    if mqtt is None:
        try:
            connect_mqtt()
        except Exception as e:
            print("MQTT reconnect failed:", e)
            mqtt = None


def read_dht():
    global last_temp, last_humi
    try:
        dht_sensor.measure()
        last_temp = dht_sensor.temperature()
        last_humi = dht_sensor.humidity()
        return last_temp, last_humi
    except Exception as e:
        print("DHT read failed:", e)
        return last_temp, last_humi

# =========================
# GATE CONTROL
# =========================
def open_gate(gate_name, mode="AUTO", auto_close_ms=3000):
    gate_state = entry_gate_state if gate_name == "entry" else exit_gate_state
    gate_servo = entry_servo if gate_name == "entry" else exit_servo

    mode = str(mode).upper()
    auto_close_ms = int(auto_close_ms)

    # Ignore duplicate open in same mode; just refresh timer for AUTO
    if gate_state["state"] == "OPEN":
        gate_state["mode"] = mode
        gate_state["opened_at"] = time.ticks_ms()
        gate_state["auto_close_ms"] = auto_close_ms
        publish_gate_state(gate_name)
        publish_env_event(last_temp, last_humi)
        return

    gate_servo.set_angle(SERVO_OPEN_ANGLE)
    time.sleep_ms(300)
    gate_state["state"] = "OPEN"
    gate_state["mode"] = mode
    gate_state["opened_at"] = time.ticks_ms()
    gate_state["auto_close_ms"] = auto_close_ms
    publish_gate_state(gate_name)
    publish_env_event(last_temp, last_humi)


def close_gate(gate_name, next_mode=None):
    gate_state = entry_gate_state if gate_name == "entry" else exit_gate_state
    gate_servo = entry_servo if gate_name == "entry" else exit_servo

    if gate_state["state"] == "CLOSED":
        if next_mode is not None:
            gate_state["mode"] = str(next_mode).upper()
        publish_gate_state(gate_name)
        publish_env_event(last_temp, last_humi)
        return

    gate_servo.set_angle(SERVO_CLOSE_ANGLE)
    time.sleep_ms(300)
    gate_state["state"] = "CLOSED"
    if next_mode is not None:
        gate_state["mode"] = str(next_mode).upper()
    publish_gate_state(gate_name)
    publish_env_event(last_temp, last_humi)


def auto_close_gates():
    now = time.ticks_ms()
    print("ENTRY:", entry_gate_state)
    print("EXIT :", exit_gate_state)

    if entry_gate_state["state"] == "OPEN" and entry_gate_state["mode"] == "AUTO":
        if time.ticks_diff(now, entry_gate_state["opened_at"]) >= entry_gate_state["auto_close_ms"]:
            close_gate("entry", "AUTO")

    if exit_gate_state["state"] == "OPEN" and exit_gate_state["mode"] == "AUTO":
        if time.ticks_diff(now, exit_gate_state["opened_at"]) >= exit_gate_state["auto_close_ms"]:
            close_gate("exit", "AUTO")

# =========================
# SLOT SENSOR UPDATE
# =========================
def init_slots():
    now = time.ticks_ms()
    for slot_name, sensor in slot_sensors.items():
        occupied = sensor.is_obstacle()
        slot_raw[slot_name] = occupied
        slot_stable[slot_name] = occupied
        slot_last_reported[slot_name] = occupied
        slot_changed_ms[slot_name] = now


def update_slots():
    changed = False
    now = time.ticks_ms()

    for slot_name, sensor in slot_sensors.items():
        raw = sensor.is_obstacle()

        if raw != slot_raw[slot_name]:
            slot_raw[slot_name] = raw
            slot_changed_ms[slot_name] = now

        if raw != slot_stable[slot_name]:
            if time.ticks_diff(now, slot_changed_ms[slot_name]) >= SLOT_DEBOUNCE_MS:
                slot_stable[slot_name] = raw
                publish_slot_event(slot_name)
                changed = True

    if changed:
        publish_env_event(last_temp, last_humi)
        update_displays()

# =========================
# ULTRASONIC LOGIC
# =========================
def update_entry_ultrasonic_presence():
    global entry_detect_started_ms, entry_triggered, entry_ultra_na_count
    global entry_full_alert_sent

    now = time.ticks_ms()

    try:
        entry_distance = entry_ultra.measure_distance()
        print("entry_distance:", entry_distance)

        if entry_distance is None:
            entry_ultra_na_count += 1
            print("Entry ultrasonic N/A count =", entry_ultra_na_count)
            if entry_ultra_na_count >= ULTRA_NA_RESET_LIMIT:
                if entry_detect_started_ms is not None or entry_triggered:
                    publish_presence_event("entry_presence", entry_distance, False)
                entry_detect_started_ms = None
                entry_triggered = False
                entry_full_alert_sent = False
            return

        entry_ultra_na_count = 0
        detected = entry_distance < ENTRY_DETECT_THRESHOLD_CM

        if detected:
            if entry_detect_started_ms is None:
                entry_detect_started_ms = now

            elif (not entry_triggered and
                  time.ticks_diff(now, entry_detect_started_ms) >= ULTRASONIC_DEBOUNCE_MS):
                entry_triggered = True
                publish_presence_event("entry_presence", entry_distance, True)

                if available_slots() > 0:
                    # IMPORTANT: force AUTO here
                    open_gate("entry", "AUTO", ENTRY_AUTO_CLOSE_MS)
                    entry_full_alert_sent = False
                else:
                    if not entry_full_alert_sent:
                        publish_event("event/parking_full", {
                            "ts": now_iso(),
                            "distance_cm": entry_distance,
                            "available_slots": available_slots(),
                            "device_id": DEVICE_ID,
                        })
                        entry_full_alert_sent = True
                    print("Entry blocked: no available slots")

        else:
            if entry_detect_started_ms is not None or entry_triggered:
                publish_presence_event("entry_presence", entry_distance, False)
            entry_detect_started_ms = None
            entry_triggered = False
            entry_full_alert_sent = False

    except Exception as e:
        print("Entry ultrasonic update failed:", e)


def update_exit_ultrasonic_presence():
    global exit_detect_started_ms, exit_triggered, exit_ultra_na_count

    now = time.ticks_ms()

    try:
        exit_distance = exit_ultra.measure_distance()
        print("exit_distance:", exit_distance)

        if exit_distance is None:
            exit_ultra_na_count += 1
            print("Exit ultrasonic N/A count =", exit_ultra_na_count)
            if exit_ultra_na_count >= ULTRA_NA_RESET_LIMIT:
                exit_detect_started_ms = None
                exit_triggered = False
            return

        exit_ultra_na_count = 0
        detected = exit_distance < EXIT_DETECT_THRESHOLD_CM

        if detected:
            if exit_detect_started_ms is None:
                exit_detect_started_ms = now
            elif (not exit_triggered and
                  time.ticks_diff(now, exit_detect_started_ms) >= ULTRASONIC_DEBOUNCE_MS):
                exit_triggered = True
                publish_presence_event("exit_presence", exit_distance, True)
                open_gate("exit", "AUTO", EXIT_AUTO_CLOSE_MS)
        else:
            if exit_detect_started_ms is not None or exit_triggered:
                publish_presence_event("exit_presence", exit_distance, False)
            exit_detect_started_ms = None
            exit_triggered = False

    except Exception as e:
        print("Exit ultrasonic update failed:", e)


def publish_env_if_due():
    global last_env_publish_ms
    now = time.ticks_ms()

    if time.ticks_diff(now, last_env_publish_ms) < ENV_PUBLISH_INTERVAL_MS:
        return

    last_env_publish_ms = now
    temp_c, humi = read_dht()
    publish_env_event(temp_c, humi)

# =========================
# MQTT COMMANDS
# =========================
def handle_command(topic, payload_text):
    try:
        payload = ujson.loads(payload_text)
    except Exception:
        print("Bad MQTT JSON:", payload_text)
        return

    if not topic.endswith("/control"):
        return

    device = payload.get("device")
    action = payload.get("action")
    source = str(payload.get("source", "dashboard")).lower()
    mode = str(payload.get("mode", "MANUAL")).upper()
    auto_close_ms = int(payload.get("auto_close_ms", 3000))

    # FORCE BLYNK GATE COMMANDS TO AUTO
    if source == "blynk" and device in ("entry_gate", "exit_gate", "gate"):
        mode = "AUTO"

    # keep compatibility if generic "gate" is ever used
    if device == "gate":
        if action == "open":
            open_gate("entry", mode, auto_close_ms)
        elif action == "close":
            close_gate("entry", "AUTO" if source == "blynk" else mode)
        return

    if device == "entry_gate":
        if action == "open":
            open_gate("entry", mode, auto_close_ms)
        elif action == "close":
            close_gate("entry", "AUTO" if source == "blynk" else "AUTO")
        return

    if device == "exit_gate":
        if action == "open":
            open_gate("exit", mode, auto_close_ms)
        elif action == "close":
            close_gate("exit", "AUTO" if source == "blynk" else "AUTO")
        return

    if device == "led":
        if action == "on":
            set_led(True)
            publish_env_event(last_temp, last_humi)
        elif action == "off":
            set_led(False)
            publish_env_event(last_temp, last_humi)
        return

    print("Unknown control device:", device)


def process_mqtt():
    global mqtt
    try:
        if mqtt is not None:
            mqtt.check_msg()
    except Exception as e:
        print("MQTT check failed:", e)
        mqtt = None
        return

    while pending_messages:
        topic, msg = pending_messages.pop(0)
        handle_command(topic, msg)


def heartbeat_if_due():
    global last_heartbeat_ms
    now = time.ticks_ms()

    if time.ticks_diff(now, last_heartbeat_ms) < HEARTBEAT_INTERVAL_MS:
        return

    last_heartbeat_ms = now
    publish_event("event/heartbeat", {
        "ts": now_iso(),
        "ip": wlan.ifconfig()[0] if wlan.isconnected() else None,
        "device_id": DEVICE_ID,
    })


def boot():
    read_dht()
    entry_servo.set_angle(SERVO_CLOSE_ANGLE)
    exit_servo.set_angle(SERVO_CLOSE_ANGLE)
    set_led(False)
    init_slots()
    update_displays()


def main():
    boot()
    while True:
        safe_connect()

        if wlan.isconnected():
            update_slots()
            update_entry_ultrasonic_presence()
            update_exit_ultrasonic_presence()
            process_mqtt()
            auto_close_gates()
            heartbeat_if_due()
            publish_env_if_due()

        time.sleep_ms(LOOP_DELAY_MS)


main()


