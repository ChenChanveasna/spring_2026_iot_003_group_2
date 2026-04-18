import machine
import time
import dht
from tm1637 import TM1637
from machine_i2c_lcd import I2cLcd


class DHT11:
    def __init__(self, pin):
        self.sensor = dht.DHT11(machine.Pin(pin))

    def read(self):
        try:
            self.sensor.measure()
            return self.sensor.temperature(), self.sensor.humidity()
        except OSError:
            return None, None


class IR:
    def __init__(self, pin):
        self.ir = machine.Pin(pin, machine.Pin.IN)
        self.start_time = None

    def is_obstacle(self):
        return self.ir.value() == 0  # active low

    def time_spent(self, start_time, end_time):
        return time.ticks_diff(end_time, start_time) / 1000


class UltraSonic:
    def __init__(self, trig_pin, echo_pin):
        self.trig = machine.Pin(trig_pin, machine.Pin.OUT)
        self.echo = machine.Pin(echo_pin, machine.Pin.IN)

    def measure_distance(self):
        self.trig.off()
        time.sleep_us(2)
        self.trig.on()
        time.sleep_us(10)
        self.trig.off()

        try:
            duration = machine.time_pulse_us(self.echo, 1, 30000)
            if duration > 0:
                return round((duration * 0.0343) / 2, 2)
            return None
        except Exception:
            return None

    def detect_car(self, threshold_cm=20):
        distance = self.measure_distance()
        return distance is not None and distance < threshold_cm


class Servo:
    def __init__(self, pin):
        self.servo = machine.PWM(machine.Pin(pin), freq=50)

    def set_angle(self, angle):
        duty = int((angle / 180) * 102 + 26)
        self.servo.duty(duty)


class TMDriver:
    def __init__(self, clk_pin, dio_pin, brightness=5):
        self.clk = machine.Pin(clk_pin, machine.Pin.OUT)
        self.dio = machine.Pin(dio_pin, machine.Pin.OUT)
        self.brightness = brightness
        self.tm = TM1637(
            clk_pin=self.clk,
            dio_pin=self.dio,
            brightness=self.brightness
        )

    def display_number(self, number):
        try:
            self.tm.show_number(number)
        except Exception:
            pass


class LCD:
    def __init__(self, scl_pin, sda_pin, freq=400000, i2c_id=0, address=0x27):
        self.i2c = machine.I2C(
            i2c_id,
            scl=machine.Pin(scl_pin),
            sda=machine.Pin(sda_pin),
            freq=freq
        )
        self.lcd = I2cLcd(self.i2c, address, 2, 16)
        self.lcd.clear()
        self.lcd.putstr("System Ready!!")
        time.sleep(2)
        self.lcd.clear()

    def display_message(self, message):
        self.lcd.clear()
        self.lcd.putstr(message[:32])

    def clear(self):
        self.lcd.clear()