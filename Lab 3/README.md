## IOT-Section 003-Group 2

# LAB 3: IoT Smart Gate Control with Blynk, IR Sensor, Servo Motor, and TM1637

--- 

## 1. Project Overview
This Project implements an ESP32-based IoT system using MicroPythonand the Blynk platform. 
The system integrates an IR sensor for object detection, a servo motor forphysical actuation, and a TM1637 7-segment display for real-time local feedback.

---

## 2. Learning Outcomes (CLO Alignment)
- Integrate multiple sensors and actuators into a single IoT system using ESP32.
- Use Blynk to remotely control hardware and visualize system status.
- Implement automatic and manual control logic based on sensor input and cloud commands.
- Display system status and numerical data using a TM1637 7-segment display.
- Document system wiring, logic flow, and IoT behavior clearly.

---

## 3. Hardware Configuration
### Hardware Component
* ESP32 Dev Board
* TM1637 4-Digit Display
* Servo Motor (SG90)
* IR Obstacle Avoidance Sensor
* Jumper Wires

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

![Wiring Diagram](Images/image.png)


---

## 4. Tasks & Evidence

### Task 1: IR Sensor Reading

**Evidence:**

---

### Task 2: Servo Motor Control via Blynk

**Evidence:**

---

### Task 3: Automatic IR - Servo Action

**Evidence:**

---

### Task: 4 TM1637 Display Integration

**Evidence:**

---

### Task 5: Manual Override Mode

**Evidence:**

---

## 7. Conclusion
This project emphasizes interaction between sensors, actuators, cloud-based control, and localdisplay, reinforcing event-driven and IoT system design concepts.
