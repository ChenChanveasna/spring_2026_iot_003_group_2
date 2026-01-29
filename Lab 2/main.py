import network
import socket
from machine import Pin, time_pulse_us
import dht
import time

# ==============================
# LED SETUP
# ==============================
led = Pin(2, Pin.OUT)
led.off()

# ==============================
# DHT11 SETUP
# ==============================
dht_sensor = dht.DHT11(Pin(23))

# ==============================
# ULTRASONIC SETUP
# ==============================
trig = Pin(33, Pin.OUT)
echo = Pin(34, Pin.IN)

# ==============================
# WIFI SETUP
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
print("Connected!")
print("ESP32 IP address:", ip)

# ==============================
# WEB SERVER SETUP
# ==============================
addr = socket.getaddrinfo("0.0.0.0", 8080)[0][-1]
s = socket.socket()
s.bind(addr)
s.listen(1)

print("Web server running...")

# ==============================
# SENSOR FUNCTIONS
# ==============================
def read_dht():
    try:
        dht_sensor.measure()
        return dht_sensor.temperature(), dht_sensor.humidity()
    except:
        return "N/A", "N/A"

def read_distance():
    trig.off()
    time.sleep_us(2)
    trig.on()
    time.sleep_us(10)
    trig.off()

    duration = time_pulse_us(echo, 1, 30000)
    distance = (duration * 0.0343) / 2
    return round(distance, 2)

# ==============================
# HTML PAGE
# ==============================
def web_page(temp, hum, dist):
    html = f"""
<html>
<head>
    <title>ESP32 Sensor Dashboard</title>
    <meta http-equiv="refresh" content="2">
    <style>
        body {{
            font-family: Arial, sans-serif;
            background: #f3f4f6;
            text-align: center;
            padding: 20px;
        }}

        h1 {{
            margin-bottom: 30px;
        }}

        .container {{
            display: flex;
            justify-content: center;
            flex-wrap: wrap;
            gap: 20px;
        }}

        .card {{
            background: white;
            padding: 20px;
            width: 260px;
            border-radius: 12px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.1);
            font-size: 18px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }}

        .label {{
            color: #555;
            margin-bottom: 8px;
        }}

        .value {{
            font-size: 24px;
            font-weight: bold;
            padding-bottom: 12px;
        }}

        .btn {{
            width: 110px;
            height: 45px;
            font-size: 18px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            margin: 8px;
        }}

        .on {{
            background: #22c55e;
            color: white;
        }}

        .off {{
            background: #ef4444;
            color: white;
        }}

        .button {{
            background:#151b54;
            color:white;
            width: 170px;
        }}
    </style>
</head>

<body>
    <h1>ESP32 Sensor Dashboard</h1>

    <div class="container">

        <div class="card">
            <div class="label">Temperature</div>
            <div class="value">{temp} C</div>
            <a href="/temp"><button class="btn button">Show Temperature</button></a>
        </div>

        <div class="card">
            <div class="label">Distance</div>
            <div class="value">{dist} cm</div>
            <a href="/dist"><button class="btn button">Show Distance</button></a>
        </div>

        <div class="card">
            <div class="label">LED Control</div>
            <a href="/on"><button class="btn on">ON</button></a>
            <a href="/off"><button class="btn off">OFF</button></a>
        </div>

    </div>
</body>
</html>
"""
    return html
 

# ==============================
# MAIN LOOP
# ==============================
while True:
    conn, addr = s.accept()
    request = conn.recv(1024).decode()

    if "/on" in request:
        led.on()

    if "/off" in request:
        led.off()

    temp, hum = read_dht()
    dist = read_distance()

    response = web_page(temp, hum, dist)

    conn.send("HTTP/1.1 200 OK\r\n")
    conn.send("Content-Type: text/html\r\n")
    conn.send("Connection: close\r\n\r\n")
    conn.sendall(response)
    conn.close()
