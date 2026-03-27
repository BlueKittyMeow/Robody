#!/usr/bin/env python3
"""
motor_server.py — Python 3 motor control daemon for Robody

Listens on a local TCP socket for velocity commands from the ROS node
(which runs in Python 2.7 and can't import MotorKit directly).

Protocol (newline-delimited JSON over TCP 127.0.0.1:9877):
  → {"vx": 0.5, "vy": 0.0, "omega": 0.0}   # velocity command
  ← {"ok": true, "throttles": [fl, fr, rl, rr]}  # ack

Also accepts:
  → {"cmd": "stop"}
  → {"cmd": "status"}
  → {"cmd": "battery"}

Run as a background service:
  python3 ~/catkin_ws/src/robody_drive/scripts/motor_server.py &

Or via systemd (see robody_drive.service).
"""

import sys
import os
import json
import time
import socket
import threading
import signal
import logging

# Allow importing mecanum.py from the same scripts/ directory
_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)
sys.path.insert(0, os.path.expanduser('~/scripts'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [motor_server] %(levelname)s %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('motor_server')

# Socket config
HOST = '127.0.0.1'
PORT = 9877
PIDFILE = '/tmp/motor_server.pid'

# UPS constants (duplicated here to keep motor_server self-contained)
try:
    import smbus2
    _SMBUS = True
except ImportError:
    _SMBUS = False

_UPS_ADDR   = 0x17
_REG_BATT_V = 0x12
_REG_OUT_V  = 0x0E
_REG_BATT_I = 0x1A
_REG_STATUS = 0x1F


class MotorServer:

    def __init__(self):
        self.drive = None
        self._lock = threading.Lock()
        self._running = True
        self._last_cmd_time = time.time()
        self._timeout = 0.8   # stop if no command for this many seconds

        # Init motor drive
        try:
            from mecanum import MecanumDrive
            self.drive = MecanumDrive()
            log.info("MecanumDrive initialized @ I2C 0x60")
        except Exception as e:
            log.error(f"MecanumDrive init failed: {e}")
            log.warning("Running in SIMULATION mode — no motors will turn")

        # Watchdog thread
        self._watchdog = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._watchdog.start()

    # ------------------------------------------------------------------
    # Command dispatch
    # ------------------------------------------------------------------

    def handle(self, data):
        """Parse a command dict and return a response dict."""
        try:
            msg = json.loads(data)
        except json.JSONDecodeError as e:
            return {"ok": False, "error": f"JSON parse error: {e}"}

        # Velocity command
        if "vx" in msg or "vy" in msg or "omega" in msg:
            vx    = float(msg.get("vx",    0.0))
            vy    = float(msg.get("vy",    0.0))
            omega = float(msg.get("omega", 0.0))
            return self._cmd_move(vx, vy, omega)

        # Named commands
        cmd = msg.get("cmd", "")
        if cmd == "stop":
            return self._cmd_stop()
        if cmd == "status":
            return self._cmd_status()
        if cmd == "battery":
            return self._cmd_battery()

        return {"ok": False, "error": f"unknown command: {msg}"}

    def _cmd_move(self, vx, vy, omega):
        with self._lock:
            self._last_cmd_time = time.time()
            if self.drive:
                self.drive.move(vx, vy, omega)
                last = self.drive.get_last_cmd()
            else:
                last = (vx, vy, omega)
        throttles = self._compute_throttles(vx, vy, omega)
        return {"ok": True,
                "throttles": [round(t, 3) for t in throttles],
                "cmd": {"vx": vx, "vy": vy, "omega": omega}}

    def _cmd_stop(self):
        with self._lock:
            if self.drive:
                self.drive.stop()
        return {"ok": True, "cmd": "stop"}

    def _cmd_status(self):
        if self.drive:
            last = self.drive.get_last_cmd()
        else:
            last = (0.0, 0.0, 0.0)
        throttles = self._compute_throttles(*last)
        return {
            "ok":       True,
            "cmd":      {"vx": last[0], "vy": last[1], "omega": last[2]},
            "throttles": [round(t, 3) for t in throttles],
            "sim":      self.drive is None,
            "ts":       time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    def _cmd_battery(self):
        if not _SMBUS:
            return {"ok": False, "error": "smbus2 not available"}
        try:
            bus = smbus2.SMBus(1)
            bv  = bus.read_word_data(_UPS_ADDR, _REG_BATT_V)
            ov  = bus.read_word_data(_UPS_ADDR, _REG_OUT_V)
            bi_raw = bus.read_word_data(_UPS_ADDR, _REG_BATT_I)
            bi  = bi_raw if bi_raw <= 32767 else bi_raw - 65536
            sr1 = bus.read_byte_data(_UPS_ADDR, _REG_STATUS)
            bus.close()
            pct = max(0, min(100, int((bv - 6400) * 100 / (8400 - 6400))))
            return {
                "ok":           True,
                "battery_v_mv": bv,
                "output_v_mv":  ov,
                "battery_i_ma": bi,
                "battery_pct":  pct,
                "charging":     bool(sr1 & 0x04),
                "battery_low":  bool(sr1 & 0x20),
                "ts":           time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Watchdog: stop if no move command for a while
    # ------------------------------------------------------------------

    def _watchdog_loop(self):
        while self._running:
            time.sleep(0.2)
            with self._lock:
                idle = time.time() - self._last_cmd_time
                if idle > self._timeout and self.drive:
                    self.drive.stop()

    # ------------------------------------------------------------------
    # Kinematics (for status reporting)
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_throttles(vx, vy, omega):
        L  = 0.14
        fl =  vx - vy - L * omega
        fr =  vx + vy + L * omega
        rl =  vx + vy - L * omega
        rr =  vx - vy + L * omega
        m  = max(abs(fl), abs(fr), abs(rl), abs(rr), 1.0)
        return (fl/m, fr/m, rl/m, rr/m)

    # ------------------------------------------------------------------
    # TCP server
    # ------------------------------------------------------------------

    def serve(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((HOST, PORT))
            srv.listen(4)
            srv.settimeout(1.0)
            log.info(f"Listening on {HOST}:{PORT}")

            while self._running:
                try:
                    conn, addr = srv.accept()
                except socket.timeout:
                    continue
                threading.Thread(
                    target=self._handle_conn,
                    args=(conn,),
                    daemon=True,
                ).start()

    def _handle_conn(self, conn):
        with conn:
            buf = b""
            while True:
                try:
                    chunk = conn.recv(1024)
                except OSError:
                    break
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if line:
                        resp = self.handle(line.decode("utf-8", errors="replace"))
                        conn.sendall((json.dumps(resp) + "\n").encode())

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def shutdown(self, *_):
        log.info("Shutting down motor server")
        self._running = False
        if self.drive:
            self.drive.stop()
        try:
            os.remove(PIDFILE)
        except FileNotFoundError:
            pass
        sys.exit(0)


def main():
    server = MotorServer()
    signal.signal(signal.SIGTERM, server.shutdown)
    signal.signal(signal.SIGINT,  server.shutdown)

    # Write PID file
    with open(PIDFILE, 'w') as f:
        f.write(str(os.getpid()))
    log.info(f"PID {os.getpid()} written to {PIDFILE}")

    server.serve()


if __name__ == "__main__":
    main()
