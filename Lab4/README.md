
## IOT-Section 003-Group 2

# LAB 4: Multi-Sensor IoT Monitoring with Grafana Dashboard

--- 

## 1. Project Overview
This lab will design and implement a multi-sensor IoT monitoring system using
ESP32 and MicroPython (Thonny). The system integrates MLX90614 (body temperature),
MQ-5 (gas sensor), BMP280 (room temperature, pressure, altitude), and DS3231 (RTC).
Students must implement edge logic processing before sending data to Node-RED, where it
will be stored in InfluxDB and visualized in Grafana.

---

## 2. Learning Outcomes (CLO Alignment)
• Integrate multiple I2C and analog sensors with ESP32.
• Implement moving average filtering for noisy sensor signals.
• Create rule-based classification logic at the edge.
• Structure JSON packets for IoT transmission.
• Store time-series data in InfluxDB.
• Design dashboards using Grafana.

---

## 3. Hardware Configuration
### Hardware Component


### Wiring Table

**ESP32 Pin Connections:**

| Component         | Component Pin    | ESP32 Pin |
| :---------------- | :--------------- | :-------- |
| TM1637 Display    | CLK              | **D17**   |
|                   | DIO              | **D16**   |
|                   | VCC              | **5V**    |
|                   | GND              | **GND**   |
| Servo Motor       | Signal (Yellow)  | **D13**   |
|                   | 5V (Red)         | **5V**    |
|                   | GND (Brown)      | **GND**   |
| IP Sensor         | OUT              | **D12**   |
|                   | GND              | **GND**   |
|                   | VCC              | **VCC**   |




---

## 4. Tasks & Evidence

### Task 1: Gas Filtering (Moving Average)


Evidence: 

---

### Task 2: Gas Risk Classification

 
Evidence: 

---

### Task 3: Fever Detection Logic

Evidence:

---

### Task 4: Pressure & Altitude Monitoring (Grafana)

  
Evidence: 


Evidence: 

---

### Flowchart & Sequence Diagram
![Flowchart](./images/Gemini_Generated_Image_7zs22z7zs22z7zs2.png)


---

## 5. Conclusion

