
## IOT-Section 003-Group 2

# LAB 6: Smart RFID System with Cloud & SD Logging

--- 

## 1. Project Overview
This lab will design and implement a **smart RFID-based attendance system** using
ESP32 and MicroPython (Thonny). The system identifies users, logs attendance locally and remotely, and
provides real-time feedback. The system integrates: 
- **RFID-RC522**
- **SD card**
- **Firestore**
- **a buzzer**

---

## 2. Learning Outcomes (CLO Alignment)

- Integrate SPI-based **RFID sensor (RC522)** with ESP32
- Implement **UID-based identification system**
- Design structured **data storage** (CSV format)
- Store data locally **(SD card)** and remotely **(Firestore)**
- Implement real-time feedback using **buzzer**
- Apply system integration across multiple modules


---

## 3. Hardware Configuration
### Hardware Component
The following hardware components are used in this lab:

1. **ESP32 Development Board**
2. **RFID sensor (RC522)**
3. **Micro SD Card Adapter**
4. **Buzzer**
5. **Jumper wires**
6. **USB cable for ESP32 programming and power**

## Wiring Table

### ESP32 Pin Connections:

| Component        | Component Pin | ESP32 Pin |
|-----------------|--------------|----------|
| RFID Sensor     | SDA          | D16      |
|                 | SCK          | D18      |
|                 | MOSI         | D23      |
|                 | MISO         | D19      |
|                 | GND          | GND      |
|                 | RST          | D22      |
|                 | VCC          | 3.3V     |
| SD Card Adapter | CS           | D13      |
|                 | SCK          | D14      |
|                 | MOSI         | D15      |
|                 | MISO         | D2       |
|                 | VCC          | 5V       |
|                 | GND          | GND      |
| Buzzer          | -            | GND      |
|                 | +            | 5V       |
|                 | S            | D4       |


![Wiring Diagram](...)


---

## 4. Tasks & Evidence

### Task 1: Read UID from RFID card  
Detect card and retrieve its unique ID (UID) 

Evidence:

![Task 1](...)

---

### Task 2: Match UID with student database  
Compare UID with predefined data
- If found -> valid student
- If not -> unknown card 

Evidence: 
[Link to Video](...)
---

### Task 3: Generate current datetime
- Format: YYYY-MM-DD HH:MM:SS

Evidence: 
[Link to Video](...)
---

### Task 4: UID Valid Detection  
If UID is valid:
- Activate buzzer for 0.3 seconds
- Save data to SD card (CSV format):
UID, Name, StudentID, Major, DateTime
- Send data to Firestore 

Evidence: 
[Link to Video](...)
---

### Task 5: UID Invalid Detection
If UID is invalid:
- Activate buzzer for 3 seconds
- Display: "Unknown Card"
- Do not save or send data  

Evidence:

![Screenshot of MIT Interface](...)

Video: [Link to Video](...)
---
 
### Flowchart & Sequence Diagram
![Flowchart](images/Lab_6_Flowchart.png)

---
## 5. Conclusion

...

---

