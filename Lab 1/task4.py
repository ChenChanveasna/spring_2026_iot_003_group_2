import network
import time
import urequests
import machine
import dht
import json

# ===================== WIFI =====================
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Connecting to Wi-Fi...")
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        timeout = 10
        while not wlan.isconnected() and timeout > 0:
            time.sleep(1)
            timeout -= 1
    print("Wi-Fi status:", wlan.isconnected())
    return wlan
        
# ===================== TELEGRAM =====================
def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text
    }
    try:
        r = urequests.post(url, json=payload)
        print("Message Sent\nTelegram status:", r.status_code)
        r.close()
    except Exception as e:
        print("Telegram error:", e)

def get_updates():
    global last_update_id
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={last_update_id + 1}"
    try:
        r = urequests.get(url)
        data = r.json()
        r.close()
        if data["ok"]:
            return data["result"]
    except Exception as e:
        print("Update error:", e)
    return []

# ===================== MAIN =====================
def main():
    # ===================== CONFIG =====================
    global WIFI_SSID
    WIFI_SSID = "Robotic WIFI"
    global WIFI_PASSWORD
    WIFI_PASSWORD = "rbtWIFI@2025"

    global BOT_TOKEN
    BOT_TOKEN = "8581995886:AAGQdxkfjMsPULGzmehPmeApgPmqb8N6rgo"
    global CHAT_ID
    CHAT_ID = -5172339964

    TEMP_THRESHOLD = 30.0
    SAMPLE_INTERVAL = 5  # seconds

    # ===================== HARDWARE =====================
    dht_sensor = dht.DHT11(machine.Pin(33))
    relay = machine.Pin(5, machine.Pin.OUT)
    relay.value(0)  # relay OFF at start

    # ===================== GLOBAL STATE =====================
    relay_state = False
    global last_update_id
    last_update_id = 0
    

    wlan = connect_wifi()
    while True:
        # ---------- Ensure Wi-Fi is connected ----------
        if not wlan.isconnected():
            connect_wifi()

        # ---------- Read DHT ----------
        try:
            dht_sensor.measure()
            temp = dht_sensor.temperature()
            hum = dht_sensor.humidity()
            print(f"Temp: {temp:.2f} C | Hum: {hum:.2f} %")
        except OSError:
            print("DHT read error, skipping cycle")
            time.sleep(SAMPLE_INTERVAL)
            continue

        # ---------- Telegram Commands ----------
        updates = get_updates()
        for msg in updates:
            last_update_id = msg["update_id"]
            msg_content = msg.get("message")
            
            if not msg_content:
                continue
            
            text = msg_content.get("text", "")
            chat_id = msg_content["chat"]["id"]
            
            if chat_id != CHAT_ID:
                continue

            if text == "/status":
                state = "ON" if relay_state else "OFF"
                send_message(
                    f"Temperature: {temp:.2f} C\n"
                    f"Humidity: {hum:.2f} %\n"
                    f"Relay: {state}"
                )

            elif text.strip() == "/on":
                relay.value(1)
                relay_state = True
                send_message("Relay turned ON")

            elif text == "/off":
                relay.value(0)
                relay_state = False
                send_message("Relay turned OFF")

        # ---------- Temperature Logic ----------
        if temp >= TEMP_THRESHOLD and not relay_state:
            send_message(f"ALERT: Temperature exceeded 30 C! Send /on to activate relay.\nCurrent Temperature: {temp:.2f}C")

        if temp < TEMP_THRESHOLD and relay_state:
            relay.value(0)
            relay_state = False
            send_message(f"Temperature normalized.\nCurrent Temperature: {temp:.2f}C\nRelay auto-OFF.")

        time.sleep(SAMPLE_INTERVAL)
        
if __name__ == "__main__":
    main()
