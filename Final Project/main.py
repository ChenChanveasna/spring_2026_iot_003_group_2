import network
import socket
import time
import json

from car_controller import CarController

# ─── WiFi & mDNS Configuration ───────────────────────────────────────────────
WIFI_SSID      = "Robotic WIFI"
WIFI_PASS      = "rbtWIFI@2025"

# mDNS hostname — device reachable at http://<MDNS_HOSTNAME>.local/
# Rules: lowercase, digits, hyphens only. No spaces. Max 32 chars.
MDNS_HOSTNAME  = "car4wd"

SERVER_PORT     = 80
RECV_TIMEOUT_S  = 0.05   # 50ms — max wait per HTTP request read


# ─── Initialise CarController ─────────────────────────────────────────────────
# Pin defaults match the wiring table in car_controller.py.
# Override here if your wiring differs, e.g.:
#   car = CarController(in1=25, in2=26, ena=32, ...)
car = CarController(
    in1=25, in2=26, ena=32,
    in3=27, in4=14, enb=33,
    trig=5, echo=18,
    neo_pin=13, neo_num=24,
)


# ══════════════════════════════════════════════════════════════════════════════
# HTTP HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def parse_query(path: str) -> dict:
    """
    Extract query-string parameters from a URL path string.

    '/move?cmd=forward'  →  {'cmd': 'forward'}
    '/status'            →  {}
    """
    params = {}
    if "?" in path:
        _, qs = path.split("?", 1)
        for pair in qs.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                params[k.strip()] = v.strip()
    return params


def send_response(conn, body: str, status: int = 200):
    """Send a minimal HTTP/1.1 JSON response and close the connection."""
    status_text = "OK" if status == 200 else (
        "Bad Request" if status == 400 else
        "Forbidden"   if status == 403 else
        "Not Found"   if status == 404 else "Error"
    )
    header = (
        "HTTP/1.1 {} {}\r\n"
        "Content-Type: application/json\r\n"
        "Access-Control-Allow-Origin: *\r\n"
        "Content-Length: {}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).format(status, status_text, len(body))
    conn.sendall(header + body)


# ══════════════════════════════════════════════════════════════════════════════
# REQUEST ROUTER
# ══════════════════════════════════════════════════════════════════════════════

def handle_request(conn):
    """
    Parse one HTTP request and dispatch to the correct handler.

    The socket already has a 50ms recv timeout set by the main loop.
    If the client stalls, recv() raises OSError which is caught below.

    Endpoint summary
    ----------------
    /move?cmd=<cmd>   Set movement command (forward/backward/left/right/stop)
    /stop             Emergency stop + lock
    /resume           Clear E-STOP lock
    /light?s=<0|1>    Neopixel on/off
    /status           Full state JSON
    """
    try:
        raw = conn.recv(1024)
        if not raw:
            return
        request = raw.decode()

        lines = request.split("\r\n")
        if not lines:
            return

        parts = lines[0].split(" ")
        if len(parts) < 2:
            return

        path   = parts[1]
        params = parse_query(path)

        # ── Speed ─────────────────────────────────────────
        if path.startswith("/speed"):
            v = params.get("v", "").strip()
            if not v.isdigit() or not (0 <= int(v) <= 100):
                send_response(
                    conn,
                    '{"error":"invalid speed — use 0–100"}',
                    400,
                )
                return
            car.set_base_speed(float(int(v)/100))
            send_response(conn, '{"ok":true,"msg":"speed set"}')
        # ── /move?cmd=<forward|backward|left|right|stop> ──────────────────
        if path.startswith("/move"):
            cmd = params.get("cmd", "").lower()
            if cmd not in ("forward", "backward", "left", "right", "stop"):
                send_response(
                    conn,
                    '{"error":"invalid cmd — use forward/backward/left/right/stop"}',
                    400,
                )
                return

            if car.set_move(cmd):
                send_response(
                    conn,
                    '{{"ok":true,"cmd":"{}"}}'.format(cmd),
                )
            else:
                send_response(
                    conn,
                    '{"ok":false,"error":"controls locked — E-STOP active"}',
                    403,
                )

        # ── /stop — hard E-STOP, locks all controls ───────────────────────
        elif path.startswith("/stop"):
            car.emergency_stop()
            send_response(conn, '{"ok":true,"msg":"emergency stop — controls locked"}')

        # ── /resume — clear E-STOP lock ───────────────────────────────────
        elif path.startswith("/resume"):
            car.resume()
            send_response(conn, '{"ok":true,"msg":"controls resumed"}')

        # ── /light?s=<0|1> ────────────────────────────────────────────────
        elif path.startswith("/light"):
            on = (params.get("s", "0") == "1")
            car.set_light(on)
            send_response(
                conn,
                '{{"ok":true,"light":{}}}'.format("true" if on else "false"),
            )

        # ── /status ───────────────────────────────────────────────────────
        elif path.startswith("/status"):
            send_response(conn, json.dumps(car.get_status()))

        # ── unknown endpoint ──────────────────────────────────────────────
        else:
            send_response(conn, '{"error":"unknown endpoint"}', 404)

    except OSError:
        # recv() timed out (50ms) or client disconnected — safe to ignore
        pass
    except Exception as e:
        print("[HTTP] Handler error:", e)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# WiFi + mDNS
# ══════════════════════════════════════════════════════════════════════════════

def connect_wifi() -> bool:
    """
    Connect to WiFi and register the mDNS hostname.

    dhcp_hostname must be set BEFORE wlan.connect() — the ESP32 WiFi
    stack announces it during the DHCP exchange.

    Returns True on success, False if connection times out (10 seconds).
    """
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    # Set mDNS hostname while interface is active, before connecting
    try:
        wlan.config(dhcp_hostname=MDNS_HOSTNAME)
        print("[mDNS] Hostname set to: {}.local".format(MDNS_HOSTNAME))
    except Exception as e:
        print("[mDNS] WARNING — dhcp_hostname not supported:", e)
        print("[mDNS] Upgrade MicroPython to v1.19+ for mDNS support")

    if wlan.isconnected():
        ip = wlan.ifconfig()[0]
        print("[WiFi] Already connected. IP: {}  mDNS: {}.local".format(
            ip, MDNS_HOSTNAME))
        return True

    print("[WiFi] Connecting to:", WIFI_SSID)
    wlan.connect(WIFI_SSID, WIFI_PASS)

    for _ in range(20):          # wait up to 10 seconds (20 × 0.5s)
        if wlan.isconnected():
            ip = wlan.ifconfig()[0]
            print("[WiFi] Connected!")
            print("       IP address : {}".format(ip))
            print("       mDNS name  : {}.local".format(MDNS_HOSTNAME))
            print("       Control at : http://{}.local/status".format(MDNS_HOSTNAME))
            return True
        time.sleep(0.5)

    print("[WiFi] Connection FAILED — check SSID/password")
    return False


# ══════════════════════════════════════════════════════════════════════════════
# MAIN LOOP
# ══════════════════════════════════════════════════════════════════════════════

def main():
    if not connect_wifi():
        print("[FATAL] No WiFi — halting.")
        return

    # ── Non-blocking TCP server socket ────────────────────────────────────
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("", SERVER_PORT))
    server.listen(3)
    server.setblocking(False)       # accept() returns immediately if no client

    print("[Server] Listening on port {}".format(SERVER_PORT))
    print("[Ready]  http://{}.local/status".format(MDNS_HOSTNAME))

    while True:
        # ── 1. Update car: trigger sensor + compute scale + apply PWM ─────
        #    CarController.update() self-rate-limits the ultrasonic trigger
        #    to 80ms. The ECHO IRQ handles the emergency cut independently.
        car.update()

        # ── 2. Accept one HTTP connection if available (non-blocking) ──────
        try:
            conn, addr = server.accept()
            conn.settimeout(RECV_TIMEOUT_S)   # 50ms cap on slow clients
            handle_request(conn)
        except OSError:
            pass    # No connection waiting — normal, continue loop

        # ── 3. Yield to keep the ESP32 watchdog timer satisfied ───────────
        time.sleep_ms(5)


main()
