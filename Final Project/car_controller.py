"""
car_controller.py — RC Car Control Module
==========================================
Handles all hardware control for the 4WD surveillance car:
  - Motor control (L298N + PWM, explicit differential steering)
  - Ultrasonic obstacle sensing (HC-SR04) with hardware IRQ
  - Distance-based speed scaling (always-on forward safety)
  - Neopixel lighting
  - E-STOP lock / resume state

Pin Map (L298N ↔ ESP32)
-----------------------
  L298N | ESP32 GPIO | Description
  ------|------------|-------------------------------
  IN1   | GPIO 25    | Left motor direction A
  IN2   | GPIO 26    | Left motor direction B
  ENA   | GPIO 32    | Left motor PWM enable   ← MUST remove jumper
  IN3   | GPIO 27    | Right motor direction A
  IN4   | GPIO 14    | Right motor direction B
  ENB   | GPIO 33    | Right motor PWM enable  ← MUST remove jumper

  HC-SR04 | GPIO | Notes
  --------|------|-------------------------------
  TRIG    |  5   | 10µs pulse output
  ECHO    | 18   | Hardware IRQ, rising+falling

  Neopixel | GPIO | Notes
  ---------|------|------
  DATA     |  4   | WS2812B strip, 8 LEDs

CRITICAL wiring note
--------------------
ENA and ENB jumpers on the L298N board MUST be removed before wiring
to GPIO 32/33. With the jumper in place the enable line is hardwired
HIGH (full speed, always on) — PWM does nothing and you cannot control
speed. Remove the jumper, then connect the GPIO.

Turn logic
----------
This module uses EXPLICIT per-side direction control (not a blended
forward+turn formula). Turns are counter-rotation pivots:

  turn_left:  LEFT  motor → reverse  at base_speed × TURN_FACTOR
              RIGHT motor → forward  at base_speed
  turn_right: LEFT  motor → forward  at base_speed
              RIGHT motor → reverse  at base_speed × TURN_FACTOR

Why counter-rotation and not arc turns?
  Arc turns (both sides forward, one reduced) need ~0.6 × base_speed
  on the inner wheel to overcome static friction on carpet/hard floors.
  Below that threshold the inner wheel stalls and the car lurches
  unpredictably. Counter-rotation gives a clear ~41% duty differential
  that clears friction reliably on any surface. The turn is sharper but
  consistent and controllable.

Hardware IRQ safety
-------------------
The HC-SR04 ECHO pin is attached to a hardware interrupt (IRQ) that
fires on every rising and falling edge. The ISR:
  1. Records rising-edge timestamp
  2. On falling edge: computes distance and updates self._distance
  3. If distance ≤ DIST_FULL_STOP AND car is moving forward → cuts
     both PWM channels to 0 immediately, at the hardware level,
     regardless of what the main loop is doing.

The polling path in update() is a secondary/redundant read that keeps
self._distance fresh for the /status endpoint.

Usage in main.py
----------------
    from car_controller import CarController
    car = CarController()
    car.update()     # call every main loop tick (~10ms)
"""

import time
from machine import Pin, PWM
import neopixel


# ── PWM Constants ─────────────────────────────────────────────────────────────
PWM_FREQ    = 1000    # 1 kHz — good L298N balance: low heat, smooth control
MAX_DUTY    = 1023    # ESP32 MicroPython 10-bit PWM range (0–1023)
TURN_FACTOR = 0.45    # Inner-wheel fraction during turns
#
# Tuning guide:
#   base_speed  0.60–0.75  → safe starting range for most hobby motors
#   base_speed  > 0.90     → needs good battery and well-matched motors
#   TURN_FACTOR 0.30–0.35  → sharper/tighter pivot
#   TURN_FACTOR 0.55–0.65  → gentler arc (better at high speed)
#
# Why TURN_FACTOR = 0.45:
#   Outer wheel:  0.70 × 1023 ≈ duty 716
#   Inner wheel:  0.70 × 0.45 × 1023 ≈ duty 322  (~46%)
#   Most hobby DC motors need ≥ 25% duty to overcome static friction.
#   0.45 clears that threshold reliably. Below 0.30 the inner wheel
#   often stalls, causing unpredictable lurching.


class CarController:
    """
    All-in-one RC car hardware controller.

    Default GPIO assignments match the pin map in the module header.
    Every pin can be overridden in __init__ to match different wiring.
    """

    # ── Distance safety thresholds (cm) ───────────────────────────────────
    DIST_FULL_SPEED = 50    # ≥ this → scale = 1.0  (unrestricted)
    DIST_FULL_STOP  = 10    # ≤ this → scale = 0.0  (hard stop, forward only)
    # Linear ramp between the two thresholds

    # ── Polling interval for the software sensor path (ms) ────────────────
    SENSOR_POLL_MS  = 80

    # ── Neopixel colours ──────────────────────────────────────────────────
    COLOR_ON  = (200, 180, 100)   # warm white
    COLOR_OFF = (0, 0, 0)

    # ─────────────────────────────────────────────────────────────────────

    def __init__(self,
                 # Left motor (L298N channel A)
                 in1=25, in2=26, ena=32,
                 # Right motor (L298N channel B)
                 in3=27, in4=14, enb=33,
                 # Ultrasonic HC-SR04
                 trig=5, echo=18,
                 # Neopixel WS2812B
                 neo_pin=13, neo_num=16,
                 # Motor Speed Tuning
                 base_speed=0.70):
        """
        Initialise all hardware. GPIO numbers can be overridden to match
        your specific wiring.
        """

        # ── Left motor direction pins (digital output) ─────────────────────
        self._in1 = Pin(in1, Pin.OUT)
        self._in2 = Pin(in2, Pin.OUT)

        # ── Left motor PWM enable pin ──────────────────────────────────────
        # duty=0 at init → motor off until first command
        self._ena = PWM(Pin(ena), freq=PWM_FREQ, duty=0)

        # ── Right motor direction pins (digital output) ────────────────────
        self._in3 = Pin(in3, Pin.OUT)
        self._in4 = Pin(in4, Pin.OUT)

        # ── Right motor PWM enable pin ─────────────────────────────────────
        self._enb = PWM(Pin(enb), freq=PWM_FREQ, duty=0)

        # Set base speed for movement commands (0.0–1.0)
        self._base_speed = max(0.0, min(1.0, base_speed))
        
        # ── Ultrasonic trigger (output) ────────────────────────────────────
        self._trig = Pin(trig, Pin.OUT)
        self._trig.value(0)

        # ── Ultrasonic echo (input + hardware IRQ) ─────────────────────────
        self._echo = Pin(echo, Pin.IN)
        self._echo_start_us = 0    # rising-edge timestamp (µs)

        # Attach IRQ — fires on BOTH edges to time the full pulse width.
        # The handler _echo_irq is responsible for the hardware safety cut.
        self._echo.irq(
            trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING,
            handler=self._echo_irq,
        )

        # ── Neopixel strip ────────────────────────────────────────────────
        self._np      = neopixel.NeoPixel(Pin(neo_pin), neo_num)
        self._neo_num = neo_num

        # ── Car state ─────────────────────────────────────────────────────
        self._cmd      = 'stop'   # last movement command string
        self._locked   = False    # True = E-STOP active, ignores set_move()
        self._distance = 55.0     # cm — updated by IRQ and polling
        self._stopped  = False    # True when obstacle scale forces a stop
        self._light    = False

        # ── Polling timer ─────────────────────────────────────────────────
        self._last_poll_ms = 0

        # Safe startup state
        self.stop_all()
        print("[CarController] Initialised — ECHO IRQ active on GPIO{}".format(echo))

    # ══════════════════════════════════════════════════════════════════════
    # set_base_speed is a tuning parameter for movement commands. 
    # It does NOT affect the obstacle speed scaling — 
    # that is always applied on top of the base speed.
    # ══════════════════════════════════════════════════════════════════════ 
    def set_base_speed(self, base_speed: float):
        """Set the base speed for movement commands (0.0–1.0)."""
        self._base_speed = max(0.0, min(1.0, base_speed))

    # ══════════════════════════════════════════════════════════════════════
    # HARDWARE IRQ  — runs outside the main loop at hardware level
    # ══════════════════════════════════════════════════════════════════════

    def _echo_irq(self, pin):
        """
        Hardware interrupt handler for the HC-SR04 ECHO pin.

        Fires on every rising AND falling edge, independent of the main
        loop — including during HTTP recv(), time.sleep(), etc.

        Rising edge  → record pulse start time
        Falling edge → compute distance, update self._distance,
                       cut PWM immediately if critically close + moving fwd

        ISR constraints (MicroPython)
        ------------------------------
        - Must execute quickly (< ~50µs ideally)
        - NO memory allocation (no lists, dicts, f-strings)
        - NO blocking calls
        - Integer arithmetic preferred (avoids GC pressure)
        - Direct register writes for the emergency motor cut
        """
        if pin.value():
            # ── Rising edge: pulse has started ────────────────────────────
            self._echo_start_us = time.ticks_us()
        else:
            # ── Falling edge: pulse has ended ─────────────────────────────
            duration = time.ticks_diff(time.ticks_us(), self._echo_start_us)

            # Guard: discard noise / missed rising-edge artefacts
            if duration <= 0 or duration > 30000:
                return

            # distance_cm = (duration_µs / 2) / 29.1
            # Integer form avoids float allocation in ISR:
            #   dist × 10 = (duration × 10) // 58
            dist_x10 = (duration * 10) // 58       # tenths of a cm
            self._distance = dist_x10 / 10.0        # float OK on falling edge

            # ── Hardware-level emergency stop ──────────────────────────────
            # Cut PWM directly — do NOT wait for update() or handle_request().
            # This makes obstacle braking truly real-time.
            # Only applies to forward motion (sensor faces forward only).
            if self._distance <= self.DIST_FULL_STOP and self._cmd in ('forward',):
                self._ena.duty(0)
                self._enb.duty(0)


    # ══════════════════════════════════════════════════════════════════════
    # PRIVATE MOTOR HELPERS
    # ══════════════════════════════════════════════════════════════════════

    @staticmethod
    def _pct_to_duty(speed_pct: float) -> int:
        """Convert 0.0–1.0 speed percentage to 0–1023 PWM duty."""
        return int(max(0.0, min(1.0, speed_pct)) * MAX_DUTY)

    def _set_left(self, forward: bool, speed_pct: float):
        """
        Set left motor direction and speed independently.

        forward=True  → IN1=HIGH, IN2=LOW  (forward rotation)
        forward=False → IN1=LOW,  IN2=HIGH (reverse rotation)
        speed_pct     → 0.0 – 1.0
        """
        if forward:
            self._in1.value(1)
            self._in2.value(0)
        else:
            self._in1.value(0)
            self._in2.value(1)
        self._ena.duty(self._pct_to_duty(speed_pct))

    def _set_right(self, forward: bool, speed_pct: float):
        """
        Set right motor direction and speed independently.

        forward=True  → IN3=HIGH, IN4=LOW  (forward rotation)
        forward=False → IN3=LOW,  IN4=HIGH (reverse rotation)
        speed_pct     → 0.0 – 1.0
        """
        if forward:
            self._in3.value(1)
            self._in4.value(0)
        else:
            self._in3.value(0)
            self._in4.value(1)
        self._enb.duty(self._pct_to_duty(speed_pct))

    def _apply_obstacle_scale(self, scale: float):
        """
        Re-apply the current command with an obstacle speed scale.
        Called by update() after computing the distance-based scale.

        scale = 1.0 → full BASE_SPEED
        scale = 0.0 → motors off (obstacle too close)

        Only forward motion is scaled — reverse and turns are
        unaffected because the HC-SR04 faces forward only.
        """
        cmd = self._cmd

        if cmd == 'forward':
            spd = self._base_speed * scale
            # Both forward, scaled
            self._in1.value(1); self._in2.value(0)
            self._in3.value(1); self._in4.value(0)
            self._ena.duty(self._pct_to_duty(spd))
            self._enb.duty(self._pct_to_duty(spd))

        elif cmd == 'backward':
            # Reverse: no obstacle scaling (sensor faces front)
            self._in1.value(0); self._in2.value(1)
            self._in3.value(0); self._in4.value(1)
            self._ena.duty(self._pct_to_duty(self._base_speed))
            self._enb.duty(self._pct_to_duty(self._base_speed))

        elif cmd == 'left':
            # Counter-rotation pivot left (no obstacle scaling on turns)
            # Left  → reverse at base_speed * TURN_FACTOR
            # Right → forward at base_speed
            self._set_left(forward=False, speed_pct=self._base_speed * TURN_FACTOR)
            self._set_right(forward=True,  speed_pct=self._base_speed)

        elif cmd == 'right':
            # Counter-rotation pivot right
            # Left  → forward at base_speed
            # Right → reverse at base_speed * TURN_FACTOR
            self._set_left(forward=True,  speed_pct=self._base_speed)
            self._set_right(forward=False, speed_pct=self._base_speed * TURN_FACTOR)

        else:  # 'stop' or unknown
            self.stop_all()


    # ══════════════════════════════════════════════════════════════════════
    # PUBLIC API  — called by main.py
    # ══════════════════════════════════════════════════════════════════════

    def set_move(self, cmd: str) -> bool:
        """
        Set the desired movement command.

        cmd: 'forward' | 'backward' | 'left' | 'right' | 'stop'

        Returns False (and ignores the command) if E-STOP is locked.
        The command is stored; actual motor output is applied on the
        next update() call (with up-to-date obstacle scaling).
        """
        if self._locked:
            return False
        valid = ('forward', 'backward', 'left', 'right', 'stop')
        if cmd not in valid:
            return False
        self._cmd = cmd
        return True

    def emergency_stop(self):
        """
        Hard stop: cut motors immediately and LOCK all movement commands.
        Only resume() clears the lock.
        """
        self._cmd    = 'stop'
        self._locked = True
        self.stop_all()

    def resume(self):
        """
        Clear E-STOP lock. Car stays stationary until next set_move().
        """
        self._locked = False
        self._cmd    = 'stop'

    def set_light(self, on: bool):
        """Turn Neopixel strip on (warm white) or off."""
        self._light = bool(on)
        color = self.COLOR_ON if self._light else self.COLOR_OFF
        for i in range(self._neo_num):
            self._np[i] = color
        self._np.write()

    def update(self):
        """
        Call every main loop iteration (~every 10ms).

        1. Trigger a new ultrasonic pulse every SENSOR_POLL_MS (80ms).
           Result is captured asynchronously by _echo_irq.
        2. Compute obstacle speed scale from self._distance.
        3. Apply motor outputs with scale (respects E-STOP lock).

        The ECHO IRQ independently cuts PWM on imminent collision,
        even when update() is delayed by HTTP handling.
        """
        now = time.ticks_ms()

        # ── Trigger new ultrasonic pulse (rate-limited to 80ms) ───────────
        if time.ticks_diff(now, self._last_poll_ms) >= self.SENSOR_POLL_MS:
            self._trigger_pulse()
            self._last_poll_ms = now

        # ── Compute obstacle safety scale ─────────────────────────────────
        scale = self._speed_scale(self._distance)

        # ── Track obstacle-forced stop flag ───────────────────────────────
        self._stopped = (scale == 0.0 and self._cmd == 'forward')

        # ── Apply motor outputs ───────────────────────────────────────────
        if self._locked:
            self.stop_all()
        else:
            self._apply_obstacle_scale(scale)

    def stop_all(self):
        """
        Cut power to both motors immediately.
        Floats direction pins and zeros PWM duty.
        Does NOT set E-STOP lock (use emergency_stop() for that).
        """
        self._in1.value(0); self._in2.value(0)
        self._in3.value(0); self._in4.value(0)
        self._ena.duty(0)
        self._enb.duty(0)

    def cleanup(self):
        """Deinit PWM timers — call on exit to release hardware resources."""
        self.stop_all()
        self._ena.deinit()
        self._enb.deinit()

    # ── Read-only state (for /status endpoint) ────────────────────────────

    @property
    def distance(self) -> float:
        return self._distance

    @property
    def stopped(self) -> bool:
        return self._stopped

    @property
    def locked(self) -> bool:
        return self._locked

    @property
    def light(self) -> bool:
        return self._light

    @property
    def cmd(self) -> str:
        return self._cmd

    def get_status(self) -> dict:
        """Full state snapshot for the /status JSON endpoint."""
        return {
            "distance": self._distance,
            "stopped":  self._stopped,
            "locked":   self._locked,
            "light":    self._light,
            "cmd":      self._cmd,
            "speed":    self._base_speed * 100,
        }


    # ══════════════════════════════════════════════════════════════════════
    # PRIVATE SENSOR HELPERS
    # ══════════════════════════════════════════════════════════════════════

    def _trigger_pulse(self):
        """
        Fire a 10µs HIGH pulse on TRIG to start a new HC-SR04 cycle.
        The ECHO IRQ captures the result asynchronously.
        """
        self._trig.value(0)
        time.sleep_us(2)
        self._trig.value(1)
        time.sleep_us(10)
        self._trig.value(0)

    def _speed_scale(self, distance: float) -> float:
        """
        Map obstacle distance to a speed multiplier [0.0 – 1.0].

        ≥ DIST_FULL_SPEED (50 cm) → 1.0  (full speed allowed)
        ≤ DIST_FULL_STOP  (10 cm) → 0.0  (forward motion blocked)
        Between                   → linear interpolation

        Formula: clamp((d - STOP) / (FULL - STOP), 0.0, 1.0)
        """
        scale = (distance - self.DIST_FULL_STOP) / float(
            self.DIST_FULL_SPEED - self.DIST_FULL_STOP
        )
        return max(0.0, min(1.0, scale))

