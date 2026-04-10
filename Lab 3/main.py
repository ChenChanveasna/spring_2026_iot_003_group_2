import network
import time
import machine
import urequests as requests
from tm1637 import TM1637

# =====================================================
# CONFIG
# =====================================================
WIFI_SSID = "Robotic WIFI"
WIFI_PASS = "rbtWIFI@2025"

BLYNK_TOKEN = "tEOUu5UtCpPNM7ZgJl1Sxv750Jqu6xmc"
BLYNK_API   = "http://blynk.cloud/external/api"

IR_PIN = 12
SERVO_PIN = 13
TM1637_CLK_PIN = 17
TM1637_DIO_PIN = 16

SERVO_PERIOD = 20      # ms
LOOP_DELAY   = 0.1     # seconds
DEBOUNCE     = 0.05    # seconds

# =====================================================
# HARDWARE SETUP
# =====================================================
ir = machine.Pin(IR_PIN, machine.Pin.IN)
servo = machine.PWM(machine.Pin(SERVO_PIN), freq=50)
tm = TM1637(
    clk_pin=machine.Pin(TM1637_CLK_PIN),
    dio_pin=machine.Pin(TM1637_DIO_PIN),
    brightness=5
)

# =====================================================
# WIFI CONNECT
# =====================================================
wifi = network.WLAN(network.STA_IF)
def connect_wifi():
    wifi.active(True)
    
    if not wifi.isconnected():
        print("Connecting to WiFi...")
        wifi.connect(WIFI_SSID, WIFI_PASS)
        
        # Timeout after 10 seconds so it doesn't hang forever
        timeout = 10
        while not wifi.isconnected() and timeout > 0:
            time.sleep(1)
            timeout -= 1
            
    if wifi.isconnected():
        print("Connected! IP:", wifi.ifconfig()[0])
    else:
        print("Connection failed.")
connect_wifi()

# =====================================================
# HELPER FUNCTIONS
# =====================================================
def safe_request(url):
    try:
        r = requests.get(url)
        data = r.text
        r.close()
        return data
    except:
        print("HTTP error")
        return None

def send_ir_status(status):
    url = f"{BLYNK_API}/update?token={BLYNK_TOKEN}&V0={status}"
    safe_request(url)

def send_count(count):
    url = f"{BLYNK_API}/update?token={BLYNK_TOKEN}&V2={count}"
    safe_request(url)

def read_slider():
    url = f"{BLYNK_API}/get?token={BLYNK_TOKEN}&V1"
    data = safe_request(url)
    if data:
        return int(str(data).strip('[]"{}'))
    return 0

def is_auto_mode():
    url = f"{BLYNK_API}/get?token={BLYNK_TOKEN}&V3"
    data = safe_request(url)
    if data:
        return int(str(data).strip('[]"{}')) == 1
    return False

def angle_to_duty(angle):
    pulse = (angle / 90) + 0.5
    return round((pulse / SERVO_PERIOD) * 1023)

# =====================================================
# STATE VARIABLES
# =====================================================
count = 0
servo.duty(angle_to_duty(0))  # Start at 0 degrees
prev_ir = ir.value()

tm.show_number(0)
print("System ready")

# =====================================================
# MAIN LOOP
# =====================================================
while True:
    if not wifi.isconnected():
        print("WiFi lost. Reconnecting...")
        connect_wifi()
        
    current_ir = ir.value()
    detected = (current_ir == 0)

    # -----------------------------------------
    # Task 1. SEND IR STATUS TO BLYNK
    # -----------------------------------------
    if detected:
        send_ir_status("Detected")
    else:
        send_ir_status("Not%20detected")

    # -----------------------------------------
    # Task 4 – TM1637 Display Integration
    # Count ONLY when: not detected -> detected
    # -----------------------------------------
    if prev_ir == 1 and current_ir == 0:
        time.sleep(DEBOUNCE)
        if ir.value() == 0:   # confirm stable
            count += 1
            print("New object counted:", count)
            tm.show_number(count)
            send_count(count)

    # -----------------------------------------
    # Task 5. Manual Override with BLYNK Switch
    # ----------------------------------------- 
    if is_auto_mode():
        # Task 3 – Automatic IR - Servo Action
        if detected:
            servo.duty(angle_to_duty(90))
        else:
            servo.duty(angle_to_duty(0))
    else:
        # Task 2. Servo Motor Control via BLYNK Slider
        print("Manual")
        angle = read_slider()
        print(angle)
        servo.duty(angle_to_duty(angle))

    # -----------------------------------------
    # UPDATE PREVIOUS STATE
    # -----------------------------------------
    prev_ir = current_ir

    time.sleep(LOOP_DELAY)

