import network
import time
from machine import ADC, Pin, I2C   
from umqtt.simple import MQTTClient
import mlx90614
import ujson
import bmp280
import ds3231

# ---------- WIFI ----------
SSID = "Thean Ching"
PASSWORD = "0977303147"

# ---------- MQTT ----------
MQTT_BROKER = "broker.hivemq.com"
CLIENT_ID = "esp32_g2_lab4"
TOPIC = b"/esp32/lab4"
PORT = 1883
KEEPALIVE = 30

# ---------- MQ5 ----------
mq5 = ADC(Pin(33))
mq5.atten(ADC.ATTN_11DB)
mq5.width(ADC.WIDTH_12BIT)

# ---------- MOVING AVERAGE ----------
NUM_READINGS = 5
readings = [0]*NUM_READINGS
index = 0

# ---------- MLX90614 ----------
mlx_i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=100000)
mlx = mlx90614.MLX90614(mlx_i2c)

# ---------- BMP280 ----------
bmp_i2c = I2C(0, scl=Pin(22), sda=Pin(21))
bmp = bmp280.BMP280(bmp_i2c)

# ---------- DS3231 ----------
ds_i2c = I2C(0, scl=Pin(22), sda=Pin(21), freq=100000)
ds = ds3231.DS3231(ds_i2c)

def connect_wifi():
    wifi = network.WLAN(network.STA_IF)
    wifi.active(True)
    wifi.connect(SSID, PASSWORD)

    print("Connecting to WiFi", end="")
    while not wifi.isconnected():
        print(".", end="")
        time.sleep(1)

    print("\nConnected:", wifi.ifconfig())
    
def make_client():
    return MQTTClient(client_id=CLIENT_ID, server=MQTT_BROKER, port=PORT, keepalive=KEEPALIVE)

def mqtt_connect(c):
    time.sleep(0.5)
    c.connect()
    print("Connected to MQTT Broker:", MQTT_BROKER)

def classify_gas(value):

    if value < 2100:
        return "SAFE"
    elif value < 2600:
        return "WARNING"
    else:
        return "DANGER"
    
def fever_detection(temp):
    if temp >= 32.5:
        return 1
    else:
        return 0
    
def format_time(ds_time):
    return "{}-{}-{} {:02d}:{:02d}:{:02d}".format(ds_time[0], ds_time[1], ds_time[2], ds_time[3], ds_time[4], ds_time[5])

# ---------- START ----------
connect_wifi()
client = make_client()

mqtt_connect(client)

# For the sake of submission, we will run all tasks sequentially 5 times in the main loop. 
first_run = True
task1_done = False
task1_count = 0
task2_done = False
task2_count = 0
task3_done = False
task3_count = 0

while True:
    try:
        # Read sensors
        if first_run:
            # Populate initial readings for moving average
            for i in range(NUM_READINGS):
                readings[i] = mq5.read()
                time.sleep(0.5)
            first_run = False
            
        raw = mq5.read()
        temp = mlx.read_object_temp()
        pressure = bmp.pressure / 100
        altitude = bmp.altitude
        time_now = ds.get_time()
        str_time = format_time(time_now)

        readings[index] = raw
        index = (index + 1) % NUM_READINGS

        avg = int(sum(readings) / NUM_READINGS)

        risk = classify_gas(avg)
        fever_flag = fever_detection(temp)
        
        # Below are the print statements for each task. You can uncomment them to see the outputs for each task separately.
        # # Task 1: Show the difference between raw and average readings
        # if not task1_done:
        #     if task1_count == 0:
        #         print("Task 1 - Raw vs Average:")
        #         print("=================================")
        #     print("Raw:", raw, "| Average of last 5 readings:", avg)
        #     time.sleep(0.5)
        #     task1_count += 1
        #     if task1_count >= 5:
        #         task1_done = True
        #     else:
        #         continue

        # # Task 2: Different risk levels based on average reading
        # if not task2_done:
        #     if task2_count == 0:
        #         print("\nTask 2 - Risk Level:")
        #         print("=================================")
        #     print("Average Reading:", avg, "| Risk Level:", risk)
        #     time.sleep(5)
        #     task2_count += 1
        #     if task2_count >= 5:
        #         task2_done = True
        #     else:
        #         continue
        
        # # Task 3: Fever detection based on temperature  
        # if not task3_done:  
        #     if task3_count == 0:
        #         print("\nTask 3 - Fever Detection (>= 32.5°C -> fever_flag = 1, else fever_flag = 0):")
        #         print("=================================")
        #     print("Object Temperature:", round(temp, 2), "C | Fever Flag:", fever_flag)
        #     time.sleep(1)
        #     task3_count += 1
        #     if task3_count >= 5:
        #         task3_done = True
        #     else:
        #         continue

        data = {
            "average": avg,
            "risk_level": risk,
            "temperature": round(temp, 2),
            "fever_flag": fever_flag,
            "pressure": pressure,
            "altitude": altitude,
            "timestamp": str_time
        }
        
        print("Publishing data to MQTT:", data)
        print()
        client.publish(TOPIC, ujson.dumps(data))

        time.sleep(2)

    except OSError as e:
        print("MQTT error:", e)
        time.sleep(3)
        client.connect()
