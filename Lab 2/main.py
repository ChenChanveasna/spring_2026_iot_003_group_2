import network
import socket
from machine import Pin, I2C, time_pulse_us
import dht
import time
import re
from machine_i2c_lcd import I2cLcd

# ==============================
# LED SETUP
# ==============================
led = Pin(2, Pin.OUT)
led.off()

# ==============================
# I2C LCD SETUP
# ==============================
i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000)
lcd = I2cLcd(i2c, 0x27, 2, 16)
lcd.clear()
lcd.putstr("System Ready")
time.sleep(1)
lcd.clear()

# ==============================
# DHT11 & ULTRASONIC SETUP
# ==============================
dht_sensor = dht.DHT11(Pin(23))
trig = Pin(33, Pin.OUT)
echo = Pin(34, Pin.IN)

# ==============================
# WIFI SETUP (Change if needed)
# ==============================
ssid = "Robotic WIFI"
password = "rbtWIFI@2025"

wifi = network.WLAN(network.STA_IF)
wifi.active(True)
wifi.connect(ssid, password)

print("Connecting to WiFi...")
while not wifi.isconnected():
    time.sleep(1)

ip = wifi.ifconfig()[0]
print("Connected! IP:", ip)

# ==============================
# GLOBAL STATE (IMPORTANT)
# ==============================
temperature = "N/A"
distance = "N/A"
lcd_mode = "sensor"  # or "custom"
scroll_index = 0
last_scroll_time = 0
SCROLL_DELAY = 200  # in ms, adjust speed



# ==============================
# SENSOR FUNCTIONS
# ==============================
def read_dht():
    global temperature
    try:
        dht_sensor.measure()
        temperature = dht_sensor.temperature()
    except:
        temperature = "N/A"

def read_distance():
    global distance
    trig.off()
    time.sleep_us(2)
    trig.on()
    time.sleep_us(10)
    trig.off()
    duration = time_pulse_us(echo, 1, 30000)
    if duration > 0:
        distance = round((duration * 0.0343) / 2, 2)
    else:
        distance = "N/A"

def update_lcd_sensor(text, sensor_mode=None):
    global lcd_mode

    if lcd_mode == "custom":
        return 

    text = text.replace('+', ' ').replace('%20', ' ')

    if sensor_mode == "temp":
        lcd.move_to(0, 1)
        lcd.putstr(" " * 16)
        lcd.move_to(0, 1)
        lcd.putstr(text)

    elif sensor_mode == "dist":
        lcd.move_to(0, 0)
        lcd.putstr(" " * 16)
        lcd.move_to(0, 0)
        lcd.putstr(text)

    
custom_text = ""  # global

def update_lcd_custom(text):
    global custom_text, scroll_index, last_scroll_time, lcd_mode

    lcd_mode = "custom"
    custom_text = text.replace("+", " ").replace("%20", " ")
    scroll_index = 0
    last_scroll_time = time.ticks_ms()

    lcd.clear()
    # Display first 16 chars (initial)
    lcd.putstr(custom_text[:16])

def scroll_custom_text():
    global scroll_index, last_scroll_time

    if lcd_mode != "custom":
        return

    if len(custom_text) <= 16:
        return  # no need to scroll

    now = time.ticks_ms()
    if time.ticks_diff(now, last_scroll_time) < SCROLL_DELAY:
        return

    last_scroll_time = now

    # Add padding for smooth wrap-around
    padded = custom_text + "   "
    view = padded[scroll_index:scroll_index + 16]

    lcd.move_to(0, 0)
    lcd.putstr(view)

    scroll_index = (scroll_index + 1) % len(padded)

# ==============================
# HTML PAGE
# ==============================
def web_page():
    html = """
<html>
<head>
    <title>ESP32 Sensor Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; background: #f3f4f6; text-align: center; padding: 20px; }
        .container { display: flex; justify-content: center; flex-wrap: wrap; gap: 20px; }
        .card { background: white; padding: 20px; width: 260px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
        .label { color: #555; margin-bottom: 8px; }
        .value { font-size: 24px; font-weight: bold; padding-bottom: 12px; }
        .btn { width: 80px; height: 45px; font-size: 16px; border: none; border-radius: 8px; cursor: pointer; margin: 8px; color: white; }
        .on { background: #22c55e; }
        .off { background: #ef4444; }
        .button-blue { background: #151b54; }
        .input-area { margin-top: 30px; background: white; padding: 20px; border-radius: 12px; display: inline-block; }
        input[type=text] { padding: 10px; width: 200px; border-radius: 5px; border: 1px solid #ccc; }
    </style>
</head>
<body>
    <h1>ESP32 Sensor Dashboard</h1>
    <div class="container">
        <div class="card">
            <div class="label">Temperature</div>
            <div class="value" id="temp">-- C</div>
            <a href="/temp"><button class="btn button-blue">Show Temp</button></a>
        </div>
        <div class="card">
            <div class="label">Distance</div>
            <div class="value" id="dist">-- cm</div>
            <a href="/dist"><button class="btn button-blue">Show Dist</button></a>
        </div>
        <div class="card">
            <div class="label">LED Control</div>
            <div>
                <a href="/on"><button class="btn on">ON</button></a>
                <a href="/off"><button class="btn off">OFF</button></a>
            </div>
        </div>
    </div>

    <div class="input-area">
        <h3>Send Custom Text to LCD</h3>
        <form action="/lcd">
            <input type="text" name="msg" placeholder="Enter message...">
            <button type="submit" class="btn button-blue" style="width: 100px;">Send</button>
        </form>
    </div>

    <script>
        async function fetchSensorData() {
            try {
                const response = await fetch('/data');
                const data = await response.json();
                document.getElementById('temp').innerText = data.temp + " C";
                document.getElementById('dist').innerText = data.dist + " cm";
            } catch (err) {
                console.log("Error fetching sensor data:", err);
            }
        }
        setInterval(fetchSensorData, 2000); // Update every 2 seconds
        window.onload = fetchSensorData;
    </script>
</body>
</html>
"""
    return html

# ==============================
# WEB SERVER SETUP
# ==============================
addr = socket.getaddrinfo("0.0.0.0", 8080)[0][-1]
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(addr)
s.listen(1)

print("Web server running...")

# ==============================
# MAIN LOOP
# ==============================
while True:
    conn, addr = s.accept()
    request = conn.recv(1024).decode()
    
    scroll_custom_text()

    if "favicon.ico" in request:
        conn.close()
        continue

    # --- Always refresh sensor cache ---
    read_dht()
    read_distance()

    # --- LED ---
    if "/on" in request:
        led.on()
    elif "/off" in request:
        led.off()

    # --- LCD BUTTONS ---
    elif "/temp" in request:
        lcd_mode = "sensor"
        update_lcd_sensor("Temp: {}C".format(temperature), sensor_mode="temp")

    elif "/dist" in request:
        lcd_mode = "sensor"
        update_lcd_sensor("Dist: {}cm".format(distance), sensor_mode="dist")

    # --- CUSTOM LCD TEXT (ROBUST REGEX) ---
    if request.startswith("GET /lcd"):
        request_line = request.split("\r\n")[0]
        match = re.search(r"/lcd\?msg=([^ ]+)", request_line)
        if match:
            raw_msg = match.group(1)
            msg = raw_msg.replace("+", " ").replace("%20", " ")

            lcd_mode = "custom"
            update_lcd_custom(msg)



    # --- DATA ENDPOINT (WEB ONLY) ---
    if "/data" in request:
        payload = '{{"temp":"{}","dist":"{}"}}'.format(
            temperature, distance
        )
        conn.send("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n")
        conn.send(payload.encode())
    else:
        conn.send("HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n")
        conn.send(web_page().encode())

    conn.close()

