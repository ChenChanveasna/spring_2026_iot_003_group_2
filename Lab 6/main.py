from machine import Pin, SPI
from mfrc522 import MFRC522
import time
import datetime
import os
import sdcard
import urequests
import network

# HARDCODE VALID STUDENT IDS
VALID_STUDENT = {
    "25481138180145": {
        "name": "Hanto",
        "studentID": "2024089",
        "major": "Cybersecurity"
    },
    "3020511918117": {
        "name": "Sna",
        "studentID": "2024023",
        "major": "Cybersecurity"
    }
}

# WIFI CONFIG
SSID = "Robotic WIFI"
PASSWORD = "rbtWIFI@2025"

# Initialize RFID reader
rfid_spi = SPI(1, baudrate=1000000, polarity=0, phase=0,
        sck=Pin(18), mosi=Pin(23), miso=Pin(19))

rfid_rdr = MFRC522(spi=rfid_spi, gpioRst=Pin(22), gpioCs=Pin(16))

# Initialize SD card
sd_spi = SPI(1, baudrate=1000000,
        sck=Pin(14), mosi=Pin(15), miso=Pin(2))

cs = Pin(13)
sd = sdcard.SDCard(sd_spi, cs)
vfs = os.VfsFat(sd)
try:
    os.mount(vfs, "/sd")
    print("SD card mounted successfully.")
except Exception as e:
    print("Failed to mount SD card:", e)

# Initialize Buzzer
buzzer = Pin(4, Pin.OUT)

# Google FIREBASE CONFIG
PROJECT_ID = "firestore-ID"
URL ="https://firestore.googleapis.com/v1/projects/{}/databases/(default)/documents/rfid_logs".format(PROJECT_ID)

def main():
    """ Main loop to read RFID tags and log attendance. """
    connect_wifi()
    while True:
        is_online = connect_wifi()
        uid = read_rfid()
        if uid:
            if uid in VALID_STUDENT:
                student_info = VALID_STUDENT[uid]
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                payload = {
                    "uid": uid,
                    "name": student_info["name"],
                    "studentID": student_info["studentID"],
                    "major": student_info["major"],
                    "time": timestamp
                }
                
                # Log the attendance data
                write_to_sd_card(payload)
                activate_buzzer(0.3)
                
                # Check if WiFi is connected before sending to Firestore
                if is_online:
                    send_to_firestore(payload)
                else:
                    print("Error: Offline - Log saved to SD only.")
                    
            else:
                print("Invalid UID:", uid)
                activate_buzzer(3)
            time.sleep(2)  # Delay to prevent multiple reads of the same tag
            
        else:
            print("No RFID tag detected.")
                
        # Small sleep to keep the ESP32 stable
        time.sleep(0.1)

# Helper Functions
def connect_wifi() -> bool:
    """ Connects to WiFi. Retries if disconnected. """
    wifi = network.WLAN(network.STA_IF)
    if wifi.isconnected():
        return True
    print("WiFi is not Connected. Connecting to WiFi", end="")
    wifi.active(True)
    wifi.connect(SSID, PASSWORD)
    
    max_wait = 10  # seconds
    while not wifi.isconnected() and max_wait > 0:
        print(".", end="")
        time.sleep(1)
        max_wait -= 1

    if wifi.isconnected():
        print("\nConnected:", wifi.ifconfig())
    else:
        print("\nFailed to connect to WiFi")
        return False
    
def read_rfid() -> str | None:
    """ Reads RFID tag and returns the UID as a string. Returns None if no tag is detected."""
    (stat, tag_type) = rdr.request(rdr.REQIDL)
    if stat == rdr.OK:
        (stat, uid) = rdr.anticoll()
        if stat == rdr.OK:
            return "".join([str(i) for i in uid])
    return None

def write_to_sd_card(payload: dict) -> None:
    """ Writes data to the SD card. """
    try:
        # Extract date from timestamp for filename
        date_str = payload["time"].split(" ")[0].replace("-", "_")
        with open(f"/sd/attendance_{date_str}.csv", "a") as f:
            f.write(f"{payload['uid']},{payload['name']},{payload['studentID']},{payload['major']},{payload['time']}\n")
        print("Data written to SD card successfully.")
    except Exception as e:
        print("Failed to write to SD card:", e)

def read_from_sd_card(date_str: str) -> str | None:
    """ Reads data from the SD card for a specific date. """
    try:
        with open(f"/sd/attendance_{date_str}.csv", "r") as f:
            data = f.read()
        print("Data read from SD card successfully.")
        return data
    except Exception as e:
        print("Failed to read from SD card:", e)
        return None

def activate_buzzer(seconds: float) -> None:
    """ Buzzes the buzzer to indicate a successful/failed scan. """
    buzzer.value(1)
    time.sleep(seconds)
    buzzer.value(0)

def send_to_firestore(payload: dict) -> None:
    """ Sends data to Google Firestore."""
    res = None
    data = {
        "fields": {
            "uid": {"stringValue": payload["uid"]},
            "name": {"stringValue": payload["name"]},
            "studentID": {"stringValue": payload["studentID"]},
            "major": {"stringValue": payload["major"]},
            "time": {"stringValue": payload["time"]},
        }
    }
 
    try:
        res = urequests.post(URL, json=data)
        print("Sent:", res.text)
        res.close()
    except Exception as e:
        print("Error sending:", e)
    finally:
        if res:
            res.close()

if __name__ == "__main__":
    main()