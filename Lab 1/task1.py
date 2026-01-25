import network
import time
import machine
import dht


print("Starting Task 1: DHT Sensor Readings")
dht_sensor = dht.DHT11(machine.Pin(33))

count = 1
while True:
    dht_sensor.measure()
    temp = dht_sensor.temperature()
    hum = dht_sensor.humidity()
    print(f"Temp: {temp:.2f} C | Hum: {hum:.2f} %")
    time.sleep(2)
    
    if count == 3:
        print("Task 1 completed after 3 readings.")
        break
    count += 1