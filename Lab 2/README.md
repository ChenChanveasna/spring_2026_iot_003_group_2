1. Project Overview

This project implements an integrated IoT system using an ESP32 and MicroPython. It features a web-based dashboard that allows real-time hardware interaction. Users can control an onboard LED, monitor environmental data (Temperature/Humidity/Distance), and push custom text or sensor readings to an I2C-connected LCD.

2. Learning Outcomes

Deployment of a MicroPython-based asynchronous webserver.

Integration of DHT11 (Temperature) and HC-SR04 (Ultrasonic) sensors.

I2C communication with a 16x2 LCD display.

Bidirectional data flow between a Web UI and physical hardware.

3. Hardware Requirements

ESP32 Dev Board (Flashed with MicroPython)

DHT11 (Temperature/Humidity)

HC-SR04 (Ultrasonic Sensor)

LCD 16x2 with I2C Backpack

LED (External or Onboard GPIO2)

Jumper wires & Breadboard

4. Wiring Diagram

ComponentESP32 PinNoteLEDGPIO 2Series resistor required for external LEDDHT11 DataGPIO 4Pull-up resistor may be neededUltrasonic TriggerGPIO 5OutputUltrasonic EchoGPIO 18Input (Use voltage divider for 3.3V)I2C SDA (LCD)GPIO 21Standard I2C DataI2C SCL (LCD)GPIO 22Standard I2C ClockVCC5V / VINMost LCDs/HC-SR04 require 5VGNDGNDCommon Ground

5. Setup Instructions

Prerequisites

Install Thonny IDE.

Ensure your ESP32 is flashed with the latest MicroPython firmware.

Clone this repository or download the source files.

Installation

Upload Library Files: Upload lcd_api.py and i2c_lcd.py (drivers) to the ESP32 root directory.

Configure Wi-Fi: Open main.py and update the ssid and password variables with your network credentials.

Deploy: Upload main.py to the board and run it.

Access the Server: Note the IP address printed in the Thonny terminal (e.g., 192.168.1.100). Open this IP in any web browser on the same network.

6. Usage Instructions

Web Dashboard Controls

LED Control: Click the ON or OFF buttons to toggle the LED on GPIO2.

Sensor Monitoring: The web page displays real-time Temperature ($^\circ$C) and Distance (cm). The values refresh automatically.

LCD Interaction:

Show Distance: Pressing this button sends the current ultrasonic reading to Line 1 of the LCD.

Show Temp: Pressing this button sends the DHT11 temperature to Line 2 of the LCD.

Custom Text: Type a message in the provided textbox and click Send. The text will appear on the LCD.

Note: If the text is longer than 16 characters, it will automatically scroll.

7. Evidence & Screenshots