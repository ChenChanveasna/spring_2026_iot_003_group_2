import network
import urequests
import time

# -------- SETTINGS --------
WIFI_SSID = "Robotic WIFI"
WIFI_PASSWORD = "rbtWIFI@2025"

BOT_TOKEN = "8581995886:AAGQdxkfjMsPULGzmehPmeApgPmqb8N6rgo"
CHAT_ID = "-5172339964"

# -------- WIFI --------
wifi = network.WLAN(network.STA_IF)
wifi.active(True)
wifi.connect(WIFI_SSID, WIFI_PASSWORD)

while not wifi.isconnected():
    time.sleep(1)

print("WiFi connected")

# -------- TELEGRAM --------
URL = "https://api.telegram.org/bot{}/getUpdates".format(BOT_TOKEN)
last_id = 0

# -------- MAIN LOOP --------
while True:
    try:
        r = urequests.get(URL + "?offset={}".format(last_id + 1))
        messages = r.json()["result"]
        r.close()

        for msg in messages:
            last_id = msg["update_id"]
            text = msg["message"]["text"]
            chat_id = msg["message"]["chat"]["id"]

            print("Received message:", text)
    except:
        pass

    time.sleep(2)
