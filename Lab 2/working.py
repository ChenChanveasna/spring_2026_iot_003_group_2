import network
import socket
from machine import Pin, I2C, time_pulse_us
import dht
import time
from machine_i2c_lcd import I2cLcd  # Verify if your file is named exactly this
import re

# ==============================
# LED SETUP
# ==============================
led = Pin(2, Pin.OUT)
led.off()

# ==============================
# I2C LCD SETUP
# ==============================
i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=400000)
# Most LCDs use 0x27 or 0x3F address
lcd = I2cLcd(i2c, 0x27, 2, 16)
lcd.putstr("System Ready")

# ==============================
# DHT11 & ULTRASONIC SETUP
# ==============================
dht_sensor = dht.DHT11(Pin(23))
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
print("Connected! IP:", ip)

# ==============================
# HELPER FUNCTIONS
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

def update_lcd_display(text):
    """Handles standard display and long-text scrolling"""
    # URL decoding (fixes spaces and symbols)
    text = text.replace('+', ' ').replace('%20', ' ')
    lcd.clear()
    if len(text) <= 16:
        lcd.putstr(text)
    else:
        # Scrolling logic for long text
        lcd.putstr(text[:16])
        time.sleep(1)
        for i in range(len(text) - 15):
            lcd.move_to(0, 0)
            lcd.putstr(text[i:i+16])
            time.sleep(0.3)

# ==============================
# HTML PAGE
# ==============================
def web_page(temp, hum, dist):
    html = f"""
<html>
<head>
    <title>ESP32 Real-Time Dashboard</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{ font-family: Arial, sans-serif; background: #f3f4f6; text-align: center; padding: 20px; }}
        .container {{ display: flex; justify-content: center; flex-wrap: wrap; gap: 20px; }}
        .card {{ background: white; padding: 20px; width: 260px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }}
        .value {{ font-size: 28px; font-weight: bold; color: #151b54; padding: 10px 0; }}
        .btn {{ width: 170px; height: 45px; font-size: 16px; border: none; border-radius: 8px; cursor: pointer; margin: 8px; color: white; }}
        .button-blue {{ background: #151b54; }}
        .on {{ background: #22c55e; width: 80px; }}
        .off {{ background: #ef4444; width: 80px; }}
        .input-area {{ margin-top: 30px; background: white; padding: 20px; border-radius: 12px; display: inline-block; }}
    </style>
    
    <script>
        // Update sensor values every 3 seconds without refreshing
        setInterval(function() {{
            fetch('/data').then(response => response.text()).then(data => {{
                var parts = data.split(',');
                document.getElementById('temp_val').innerHTML = parts[0] + " C";
                document.getElementById('dist_val').innerHTML = parts[2] + " cm";
            }});
        }}, 3000);

        function sendToLCD() {{
            var msg = document.getElementById("lcd_msg").value;
            fetch("/lcd?msg=" + encodeURIComponent(msg));
            document.getElementById("lcd_msg").value = ""; // Optional: clear box after send
        }}
    </script>
</head>
<body>
    <h1>Real-Time Dashboard</h1>
    <div class="container">
        <div class="card">
            <div>Temperature</div>
            <div id="temp_val" class="value">{temp} C</div>
            <button onclick="fetch('/temp')" class="btn button-blue">Show Temperature</button>
        </div>
        <div class="card">
            <div>Distance</div>
            <div id="dist_val" class="value">{dist} cm</div>
            <button onclick="fetch('/dist')" class="btn button-blue">Show Distance</button>
        </div>
        <div class="card">
            <div>LED Control</div>
            <button onclick="fetch('/on')" class="btn on">ON</button>
            <button onclick="fetch('/off')" class="btn off">OFF</button>
        </div>
    </div>

    <div class="input-area">
        <h3>Send Custom Text to LCD</h3>
        <input type="text" id="lcd_msg" placeholder="Type message...">
        <button onclick="sendToLCD()" class="btn button-blue" style="width: 100px;">Send</button>
    </div>
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
    try:
        conn, addr = s.accept()
        request = conn.recv(1024).decode()
        
        if "GET /favicon.ico" in request:
            conn.close()
            continue
        
        # extract
        match = re.search(r"msg=([^&\s]+)", request)
            
        temp, hum = read_dht()
        dist = read_distance()
        response = web_page(temp, hum, dist)


        # Action Handling
        if "/on" in request:
            led.on()
        elif "/off" in request:
            led.off()
        elif "/temp" in request:
            update_lcd_display(f"Temp: {temp}C")
        elif "/dist" in request:
            update_lcd_display(f"Dist: {dist}cm")
        elif "/lcd?msg=" in request:
            if match:
                # Group(1) contains the text after msg=
                raw_msg = match.group(1)
                
                # Decode URL formatting (+ becomes space, %20 becomes space)
                clean_msg = raw_msg.replace('+', ' ').replace('%20', ' ')
                
                print("Extracted Message:", clean_msg)
                update_lcd_display(clean_msg)
                
            print("payload", clean_msg)
            
        response = web_page(temp, hum, dist)
       
        conn.send("HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n")
        conn.sendall(response)
        conn.close()
        
        time.sleep(3)
        
    except Exception as e:
        print("Error:", e)
