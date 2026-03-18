# Smart IoT Parking Management System

## Project Overview
This project implements a **Smart IoT Parking Management System** using **ESP32 with MicroPython**, integrated with multiple sensors, actuators, and IoT platforms.

The system automates parking operations by:
- Detecting incoming vehicles
- Managing parking slot availability
- Controlling entry/exit gates
- Monitoring environmental conditions
- Providing real-time control and monitoring via **Telegram, Web Dashboard, and Blynk**

---

## Objectives
- Design a complete embedded IoT system  
- Integrate hardware with cloud platforms  
- Enable real-time monitoring and automation  
- Apply system-level engineering concepts  
- Develop a scalable and modular architecture  

---

## Hardware Components

| Component | Description |
|----------|------------|
| ESP32 | Main microcontroller (MicroPython) |
| Ultrasonic Sensors | Detect vehicles at entry & exit |
| IR Sensors (x4) | Detect parking slot occupancy |
| Servo Motors (x2) | Control entry & exit gates |
| DHT11 | Temperature & humidity sensor |
| Relay / LED | Parking light control |
| TM1637 Display | Display available slots |
| LCD I2C | Display system status |

---

## IoT Platforms Used

### 1. Telegram Bot
- Remote control and notifications
- Real-time system updates

### 2. Web Dashboard
- Built using **FastAPI**
- Displays:
  - Slot availability
  - Temperature & humidity
  - Gate status
  - Event logs
- Manual control buttons

### 3. Blynk App
- Remote control interface
- Displays:
  - Temperature
  - Slot availability
- Control:
  - Gates
  - Lighting

---

## System Architecture

### Overview
The system consists of 3 main layers:

1. **Hardware Layer (ESP32)**
2. **Communication Layer (MQTT)**
3. **Application Layer (Backend + IoT Apps)**

### Data Flow

![System Architecture](<images/IoT Device Layer.png>)

---

## Software Architecture

### ESP32 (MicroPython)
Handles:
- Sensor readings (IR, Ultrasonic, DHT11)
- Gate control (Servo)
- LED control
- Display updates (TM1637, LCD)
- MQTT communication

### Backend (FastAPI)
Handles:
- MQTT subscription & processing
- State management
- Event logging (CSV)
- Web dashboard API
- Telegram bot integration
- Blynk synchronization

### MQTT Topics
- `smartparking/{site}/{device}/state`
- `smartparking/{site}/{device}/event/...`
- `smartparking/{site}/{device}/control`

---

## Features

### Smart Parking Logic
- Detects vehicles using ultrasonic sensors
- Automatically opens gate if slots available
- Blocks entry when parking is full

### Slot Detection
- IR sensors detect occupancy
- Real-time slot updates
- Displayed on TM1637 & dashboard

### Gate Control
- Automatic (sensor-based)
- Manual via:
  - Telegram
  - Web dashboard
  - Blynk

### Environment Monitoring
- Temperature & humidity via DHT11
- Real-time updates to all platforms

### Smart Features
- Automatic Event Logging
- Generate a Downloadable CSV log 

### Logging System
- All events stored in CSV
- Includes:
  - Parking duration
  - Fee calculation
  - Slot usage

---

## Telegram Bot Commands

| Command | Function |
|--------|---------|
| /status | Show full system status |
| /temp | Show temperature |
| /slots | Show available slots |
| /open_entry | Open entry gate |
| /close_entry | Close entry gate |
| /open_exit | Open exit gate |
| /close_exit | Close exit gate |
| /light_on | Turn light ON |
| /light_off | Turn light OFF |

---

## Web Dashboard Features

- Real-time slot visualization
- Temperature & humidity display
- Gate status monitoring
- Manual control buttons:
  - Open/Close gates
  - LED control
- Event log viewer
- CSV log download

---

## Blynk Features

- Slot counter display
- Temperature display
- Control buttons:
  - Entry gate
  - Exit gate
  - LED

---

## System Workflow

1. Vehicle approaches entry  
2. Ultrasonic sensor detects presence  
3. System checks available slots  
4. If available:
   - Gate opens automatically  
   - Vehicle enters  
5. IR sensor updates slot occupancy  
6. System updates:
   - Displays  
   - Dashboard  
   - Telegram notification  
7. Exit process works similarly  
8. Parking duration & fee are calculated  

---

## Challenges Faced

- Sensor noise and false detection  
- MQTT connection stability  
- Synchronization between multiple platforms  
- Real-time updates across systems  
- Hardware timing & debounce issues  

---

## Future Improvements

- Mobile app instead of Blynk  
- License plate recognition (AI)  
- Payment integration (QR / online payment)  
- Cloud database (instead of CSV)  
- Multi-parking location support  
- Camera-based monitoring system  

---

## Project Structure

/backend

├── main.py (FastAPI + MQTT + Telegram + Blynk)

├── logs/

│ └── parking_log.csv

/esp32

├── main.py (MicroPython logic)

├── hardware.py (sensor & actuator classes)


---

## Video Demonstration

The video includes:
- Project introduction  
- System architecture explanation  
- Workflow demonstration  
- Live hardware demo  
- Telegram interaction  
- Blynk interaction  
- Web dashboard demo  

---

## Conclusion

This project successfully demonstrates a **fully integrated IoT system** combining:
- Embedded hardware
- Cloud communication (MQTT)
- Multi-platform control (Telegram, Web, Blynk)

It showcases real-world applications of **smart automation, IoT integration, and system design**.