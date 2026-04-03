
import network
import socket
from machine import Pin, PWM, I2C
import tcs34725
import time
import neopixel

# Initialize I2C for color sensor
i2c = I2C(scl=Pin(22), sda=Pin(21))
sensor = tcs34725.TCS34725(i2c)

# Initialize NeoPixel
np = neopixel.NeoPixel(Pin(23), 24)  # 1 NeoPixel on pin 4

# Motor direction pins
IN1 = Pin(27, Pin.OUT)
IN2 = Pin(26, Pin.OUT)

# PWM pin for speed control
ENA = PWM(Pin(14))
ENA.freq(1000)
ENA.duty(0) # Start at 0

mode = "manual"  # Default mode is manual
latest_color = "None"

# Motor control functions
def forward(speed_val):
    IN1.value(1)
    IN2.value(0)
    ENA.duty(speed_val)

def backward(speed_val):
    IN1.value(0)
    IN2.value(1)
    ENA.duty(speed_val)
    
def stop():
    IN1.value(0)
    IN2.value(0)
    ENA.duty(0)
    
# TSC34725 color sensor functions
def read_color():
    r, g, b, c = sensor.read_raw()
    if c < 800:
        return "None"
    print(f"Raw Color Data: \n R = {r}\n G = {g}\n B = {b}")
    return classify_color(r, g, b)
    
def classify_color(r, g, b):
    if r > g and r > b:
        return "Red"
    elif g > r and g > b:
        return "Green"
    elif b > r and b > g:
        return "Blue"
    else:
        return "None"
    
def set_neopixel_color(r, g, b):
    """ Set the NeoPixel color based on RGB values (0-255) (Static)"""
    for i in range(24):
        np[i] = (r, g, b)
    np.write()
    

ssid = "Robotic WIFI"
password = "rbtWIFI@2025"

# Connect to WiFi
wifi = network.WLAN(network.STA_IF)
wifi.active(True)
wifi.connect(ssid, password)

print("Connecting", end="")
timeout = 0
while not wifi.isconnected() and timeout < 20:
    print(".", end="")
    time.sleep(0.5)
    timeout += 1

if wifi.isconnected():
    print("\nConnected!")
    print("ESP32 IP:", wifi.ifconfig()[0])
else:
    print("\nWiFi connection failed!")

# ==== Web Server ====
addr = ('0.0.0.0', 80)
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(addr)
server.listen(5)

print("Server running on port 80...")


while True:
    try: 
        if mode == "auto":
            current_speed = 0
            if latest_color == "Red":
                current_speed = 1000
                set_neopixel_color(255, 0, 0)# Red for Red
            elif latest_color == "Green":
                current_speed = 850
                set_neopixel_color(0, 255, 0) # Green for Green
            elif latest_color == "Blue":
                current_speed = 700
                set_neopixel_color(0, 0, 255) # Blue for Blue
                
            forward(current_speed)
            time.sleep(1)
              
        client, addr = server.accept()
        request = client.recv(1024).decode()
         
        response_msg = "OK"
        
        latest_color = read_color()
        print("Detected Color:", latest_color)
    
        
        if "GET /color" in request:
            response_msg = latest_color
            
        elif "GET /set_color" in request:
            try:
                # Extract '255, 0, 0' from 'GET /set_color?value=255,0,0 HTTP/1.1'
                mode = "manual"  # Switch to manual mode when a color is set manually
                print(request)
                val_str = request.split("value=")[1].split(" ")[0]
                print(val_str)
                rgb_list = val_str.replace('%22', '').split(',')
                print("rgblist:",rgb_list)
                print(rgb_list[0])
                print(type(rgb_list[0]))
                
                # Convert to integer
                r = int(rgb_list[0])
                g = int(rgb_list[1])
                b = int(rgb_list[2])
                
                print(f"Received color set request: R={r}, G={g}, B={b}")
                set_neopixel_color(r, g, b)
                response_msg = f"NeoPixel color set to R={r}, G={g}, B={b}"
                
            except Exception as e:
                print("Error parsing color:", e)
                r, g, b = 0, 0, 0  # Default to off on error
                set_neopixel_color(r, g, b)


        elif "GET /forward" in request:
            mode = "manual"  # Switch to manual mode when a movement command is received
            forward(current_speed)
            response_msg = "Moving Forward"

        elif "GET /backward" in request:
            mode = "manual"  # Switch to manual mode when a movement command is received
            backward(current_speed)
            response_msg = "Moving Backward"

        elif "GET /stop" in request:
            mode = "manual"  # Switch to manual mode when a movement command is received
            stop()
            response_msg = "Stopped"
            
        elif "GET /mode" in request:
            try:
                # Expecting /mode?value=auto or /mode?value=manual
                val_str = request.split("value=")[1].split(" ")[0]
                mode = val_str
                response_msg = f"Mode switched to {mode}"
                print(response_msg)
            except:
                response_msg = "Error switching mode"

        elif "GET /speed" in request:
            mode = "manual"  # Switch to manual mode when a speed command is received
            try:
                val_str = request.split("value=")[1].split(" ")[0]
                current_speed = int(float(val_str))
                response_msg = f"Manual speed set to {current_speed}"
            except Exception as e:
                print("Error parsing speed:", e)
            else:
                response_msg = "Cannot change speed manually in Auto Mode"
        
        # HTTP Response Header
        client.send("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\r\n")
        client.send(response_msg)
        client.close()
        
    except Exception as e:
        print("Server error:", e)
        if 'client' in locals():
            client.close()

