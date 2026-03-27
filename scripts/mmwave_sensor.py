#!/usr/bin/env python3
"""
mmwave_sensor.py — DFRobot C4001 24GHz mmWave Presence Sensor wrapper
SEN0610, I2C address 0x2A (default) or 0x2B (DIP switch alt)

Robody integration: SENSE loop calls sense() which returns a dict.
Human detection works on stationary/sleeping people via micro-movement
(breathing, heartbeat). 12m range, 100°×80° beam.

Usage:
  python3 mmwave_sensor.py          # one-shot read
  python3 mmwave_sensor.py --watch  # continuous loop
"""
import sys
import time
import smbus2
import argparse

# ── Register map ──────────────────────────────────────────────
REG_STATUS          = 0x00
REG_CTRL0           = 0x01
REG_CTRL1           = 0x02
REG_SOFT_VERSION    = 0x03
REG_RESULT_STATUS   = 0x10
REG_RESULT_OBJ_NUM  = 0x10
REG_RESULT_RANGE_L  = 0x11
REG_RESULT_RANGE_H  = 0x12
REG_RESULT_SPEED_L  = 0x13
REG_RESULT_SPEED_H  = 0x14
REG_RESULT_ENERGY_L = 0x15
REG_RESULT_ENERGY_H = 0x16
REG_TRIG_SENSITIVITY= 0x20
REG_KEEP_SENSITIVITY= 0x21
REG_MICRO_MOTION    = 0x26

# Control byte values
CTRL_START  = 0x55
CTRL_STOP   = 0x33
CTRL_RESET  = 0xCC
CTRL_SAVE   = 0x5C   # write to REG_CTRL1

DEFAULT_ADDR = 0x2A
DEFAULT_BUS  = 1


class MmwaveSensor:
    """C4001 24GHz presence sensor, I2C mode."""

    def __init__(self, bus=DEFAULT_BUS, addr=DEFAULT_ADDR):
        self._bus  = smbus2.SMBus(bus)
        self._addr = addr
        self._ok   = False
        self._init()

    def _init(self):
        try:
            v = self._read(REG_SOFT_VERSION, 1)[0]
            self._ok = True
            print(f"[mmwave] C4001 found @ 0x{self._addr:02X}, fw v{v}")
        except OSError:
            print(f"[mmwave] WARNING: C4001 not found at 0x{self._addr:02X}")

    # ── Low-level I/O ─────────────────────────────────────────
    def _read(self, reg, length):
        return self._bus.read_i2c_block_data(self._addr, reg, length)

    def _write(self, reg, data):
        if isinstance(data, int):
            data = [data]
        self._bus.write_i2c_block_data(self._addr, reg, data)

    # ── Config helpers ────────────────────────────────────────
    def start(self):
        self._write(REG_CTRL0, [CTRL_START])
        time.sleep(0.2)

    def stop(self):
        self._write(REG_CTRL0, [CTRL_STOP])
        time.sleep(0.2)

    def set_sensitivity(self, trig=7, keep=7):
        """Trigger and keep sensitivity, 0–9 (higher = more sensitive)."""
        self._write(REG_TRIG_SENSITIVITY, [trig])
        self._write(REG_KEEP_SENSITIVITY, [keep])
        self._write(REG_CTRL1, [CTRL_SAVE])
        time.sleep(0.5)

    def set_micro_motion(self, enabled=True):
        """Enable/disable micro-motion (breathing/heartbeat) detection."""
        self._write(REG_MICRO_MOTION, [1 if enabled else 0])
        self._write(REG_CTRL1, [CTRL_SAVE])
        time.sleep(0.5)

    # ── Primary read ──────────────────────────────────────────
    def sense(self):
        """
        Returns dict:
          present  (bool)   — person detected
          range_m  (float)  — distance in metres (0.0 if absent)
          speed    (float)  — radial speed m/s (signed, 0.0 if absent)
          energy   (int)    — signal energy (0 if absent)
          ok       (bool)   — sensor reachable
        """
        if not self._ok:
            return {"present": False, "range_m": 0.0, "speed": 0.0,
                    "energy": 0, "ok": False}
        try:
            raw = self._read(REG_RESULT_OBJ_NUM, 7)
            present  = bool(raw[0])
            range_cm = raw[1] + raw[2] * 256
            speed_raw= raw[3] + raw[4] * 256
            energy   = raw[5] + raw[6] * 256

            # signed 16-bit (>32768 → negative)
            range_m = ((range_cm - 65536) / 100.0 if range_cm > 32768
                       else range_cm / 100.0)
            speed   = ((speed_raw - 65536) / 100.0 if speed_raw > 32768
                       else speed_raw / 100.0)
            if not present:
                range_m = speed = 0.0
                energy = 0
            return {"present": present, "range_m": range_m,
                    "speed": speed, "energy": energy, "ok": True}
        except OSError as e:
            return {"present": False, "range_m": 0.0, "speed": 0.0,
                    "energy": 0, "ok": False, "error": str(e)}

    def close(self):
        self._bus.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--addr',  type=lambda x: int(x, 0), default=DEFAULT_ADDR)
    ap.add_argument('--bus',   type=int, default=DEFAULT_BUS)
    ap.add_argument('--watch', action='store_true', help='Continuous polling')
    ap.add_argument('--interval', type=float, default=0.5)
    args = ap.parse_args()

    with MmwaveSensor(args.bus, args.addr) as s:
        if args.watch:
            print("Watching... Ctrl-C to stop")
            try:
                while True:
                    d = s.sense()
                    if d['present']:
                        print(f"  PRESENT  range={d['range_m']:.2f}m  "
                              f"speed={d['speed']:+.2f}m/s  energy={d['energy']}")
                    else:
                        print("  absent")
                    time.sleep(args.interval)
            except KeyboardInterrupt:
                pass
        else:
            d = s.sense()
            print(d)


if __name__ == '__main__':
    main()
