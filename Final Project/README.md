# Remote Controlled Surveillance Car System  
**Report**

---

## 1. Introduction

### Overview  
This project presents a **remote-controlled surveillance car system** built using an ESP32-based architecture. It integrates mobility, real-time video streaming, obstacle detection, and remote monitoring into a unified platform.

### Problem Statement  
Many environments are difficult, unsafe, or inefficient for direct human access. Industrial inspection sites, disaster zones, and remote areas expose personnel to significant risks and operational challenges. At the same time, existing surveillance and monitoring solutions are often expensive and not easily accessible for widespread use. As a result, there is a clear need for an affordable, remotely operated system capable of navigating such environments while providing real-time video monitoring.

### Proposed Solution  
To address this need, this project proposes a **low-cost IoT-based remote-controlled surveillance car** that combines mobility, live video streaming, and remote accessibility. The system leverages an **ESP32-based architecture** to enable:
- Real-time video transmission via an onboard camera (ESP32-CAM)
- Remote navigation and control through a web-based interface
- Obstacle-aware movement using distance sensing for safer operation
- Lightweight and scalable communication via a FastAPI backend

This solution provides a practical and accessible approach to remote monitoring, reducing human risk while maintaining situational awareness in challenging environments.

### [Link to Video](https://youtu.be/26dmMD6e5S0)

---

## 2. Hardware Components and Pin Configuration

### Hardware Components

| Component              | Purpose                                      |
|----------------------|----------------------------------------------|
| ESP32 (Main)         | Motor control and sensor processing          |
| ESP32-CAM            | Video streaming and image capture            |
| L298N Motor Driver   | Controls DC motors                           |
| DC Motors (x4)       | Vehicle movement                             |
| HC-SR04 Ultrasonic   | Distance measurement for obstacle detection  |
| WS2812B Neopixel     | Visual status indication                     |
| Power Supply         | Provides power to system components          |

---

### Pin Configuration (ESP32)

| Function                  | GPIO Pin |
|---------------------------|----------|
| Motor IN1 (Left)          | 25       |
| Motor IN2 (Left)          | 26       |
| Motor ENA (PWM)           | 32       |
| Motor IN3 (Right)         | 27       |
| Motor IN4 (Right)         | 14       |
| Motor ENB (PWM)           | 33       |
| Ultrasonic TRIG           | 5        |
| Ultrasonic ECHO           | 18       |
| Neopixel Data             | 13       |

---

## 3. Setup Guide

### 3.1 Environment Setup

1. (Optional) Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate   # Linux/macOS
venv\Scripts\activate      # Windows
```
2. Install dependencies:

```
pip install -r requirements.txt
```

---

### 3.2 Configuration

Create a `.env` file based on `.env.example`.

Key configurations:

- **ESP32 Hosts**

```
ESP32_CAR_HOST=car4wd.localESP32_CAM_HOST=esp32cam.local
```

- **Telegram Bot Setup**

```
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id
```

---

### 3.3 ESP32-CAM Setup

1. Install ESP32 board support in Arduino IDE:
    - Add board URL:  
        `https://dl.espressif.com/dl/package_esp32_index.json`
2. Select board:
    - **AI Thinker ESP32-CAM**
3. Configure:
    - Flash mode: QIO
    - Partition scheme: Huge APP

4. Configure WiFi and System Parameters

Open the **CameraWebServer.ino** and update:
```
const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";
```

If applicable, also configure:

mDNS hostname
Motor speed defaults
Sensor thresholds for obstacle detection

5. Upload code from:

```
CameraWebServer/
```

### 3.4 ESP32-CAM Setup

1. Configure WiFi and System Parameters

Open the ESP32 car controller code and update:
```
const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";
```
2. Upload Project Files

Upload the following files to the ESP32:

main.py → Entry point
car_controller.py → Core control logic
Using Thonny IDE

---

## 4. Usage Instructions

### Start Backend Server

```
uvicorn app:app --reload
```

---
### Access Web Dashboard

```
http://localhost:8000/ui/index.html
```

---
### Main Features

#### Movement Control

- Forward, backward, left, right, stop
- Controlled via REST API and web UI
#### Camera Streaming
- Real-time feed from ESP32-CAM
- Snapshot capture capability
#### Sensor Monitoring
- Ultrasonic sensor provides distance data
- Used for obstacle-aware movement
#### Notifications
- Telegram alerts (if enabled)
- Event-based updates (e.g., obstacle detection)
---
## 5. How the System Works

### 5.1 System Architecture

![System Architecture](./images/final_project_sys-architecture.png)
---

### 5.2 Flowchart

![Flowchart](./images/Flowchart.png)
---

### 5.3 Software Architecture

#### Components
1. **ESP32 Car Controller**
    - Handles motor control and sensor input
    - Runs a lightweight HTTP server
    - Executes movement commands
2. **ESP32-CAM**
    - Streams video over HTTP
    - Captures snapshots
3. **FastAPI Backend**
    - Acts as middleware between UI and hardware
    - Sends HTTP requests to ESP32 devices
    - Logs telemetry data
    - Handles notifications
4. **Web Interface**
    - Provides user control dashboard
    - Displays camera feed and system status

---

### REST API Overview

|Endpoint|Method|Description|
|---|---|---|
|`/move`|GET|Control movement (`cmd`)|
|`/speed`|GET|Adjust motor speed|
|`/status`|GET|Retrieve system status|
|`/snapshot`|GET|Capture image from camera|
|`/telemetry`|GET|Retrieve logged data|

---
### Logic Flow

1. User sends command via UI
2. FastAPI backend processes request
3. Backend forwards request to ESP32
4. ESP32 executes command via `CarController`
5. Sensor feedback adjusts behavior (e.g., obstacle stop)
6. Telemetry is logged and optionally sent via Telegram

---
## 6–8. Design Decisions, Challenges & Limitations, Future Improvements

### Design Decisions

- **Separation of Concerns**
    - ESP32 handles real-time control
    - Backend handles orchestration and logging
- **HTTP-Based Communication**
    - Simple and lightweight for IoT integration
- **Safety Mechanism**
    - Distance-based speed scaling and auto-stop
- **Modular Design**
    - Components can be independently upgraded

---
### Challenges & Limitations

- **Network Dependency**
    - System relies on stable WiFi connectivity
- **Latency**
    - HTTP communication introduces slight delays
- **Limited Processing Power**
    - ESP32 constraints affect advanced autonomy
- **Camera Performance**
    - ESP32-CAM has limited resolution and frame rate
- **Obstacle Detection Scope**
    - Single ultrasonic sensor limits field of view

---
### Future Improvements

- Implement **multi-sensor fusion** (e.g., IR + ultrasonic)
- Add **autonomous navigation algorithms**
- Upgrade to **WebSocket for real-time control**
- Improve **video streaming quality**
- Add **mobile application interface**
- Integrate **AI-based object detection**
- Enhance **security (authentication & encryption)**

---
## 9. Conclusion

This project successfully demonstrates a **low-cost, IoT-enabled surveillance vehicle** that integrates mobility, sensing, and real-time monitoring.

Key achievements include:
- Functional remote control system
- Real-time video streaming
- Obstacle-aware safety mechanism
- Backend-driven telemetry and notifications

The project highlights the practical integration of **embedded systems and web technologies**, offering a strong foundation for future enhancements in robotics and IoT surveillance applications.
