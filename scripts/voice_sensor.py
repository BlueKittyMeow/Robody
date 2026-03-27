#!/usr/bin/env python3
"""
voice_sensor.py — DFRobot DF2301Q Voice Recognition Sensor wrapper
SEN0539-EN, I2C address 0x64 (fixed)

Offline voice recognition, zero Jetson compute. 121 fixed commands
+ 17 user-trainable. Built-in speaker for audio feedback.

Robody integration: SENSE loop calls sense() which returns a dict.
play(cmd_id) speaks an audio response directly from the sensor.

Selected command IDs (English firmware):
  1  = "Hello"            wake word
  2  = "Turn on the light"
  5  = "Turn on"
  6  = "Turn off"
  102 = "Robody" (custom wake word — needs training)
  See: https://wiki.dfrobot.com/SKU_SEN0539-EN for full list

Usage:
  python3 voice_sensor.py           # one-shot read (0 = no command)
  python3 voice_sensor.py --watch   # continuous listen
  python3 voice_sensor.py --play 1  # speak command ID 1
"""
import sys
import time
import smbus2
import argparse

DEFAULT_ADDR = 0x64
DEFAULT_BUS  = 1

# Register addresses
REG_CMDID       = 0x02   # read: last recognised command ID (0 = none)
REG_PLAY_CMDID  = 0x03   # write: speak audio for this command ID
REG_MUTE        = 0x04   # write: 1=mute, 0=unmute
REG_VOLUME      = 0x05   # write: volume 1–7
REG_WAKE_TIME   = 0x06   # read/write: wake-up duration 0–255s


class VoiceSensor:
    """DF2301Q offline voice recognition sensor, I2C mode."""

    def __init__(self, bus=DEFAULT_BUS, addr=DEFAULT_ADDR):
        self._bus  = smbus2.SMBus(bus)
        self._addr = addr
        self._ok   = False
        self._init()

    def _init(self):
        try:
            self._bus.read_byte(self._addr)
            self._ok = True
            print(f"[voice] DF2301Q found @ 0x{self._addr:02X}")
        except OSError:
            print(f"[voice] WARNING: DF2301Q not found at 0x{self._addr:02X}")

    # ── Low-level I/O ─────────────────────────────────────────
    def _read_reg(self, reg):
        data = self._bus.read_i2c_block_data(self._addr, reg, 1)
        return data[0]

    def _write_reg(self, reg, value):
        self._bus.write_i2c_block_data(self._addr, reg, [value & 0xFF])

    # ── Config ────────────────────────────────────────────────
    def set_volume(self, vol):
        """Set speaker volume 1–7."""
        self._write_reg(REG_VOLUME, max(1, min(7, vol)))

    def set_mute(self, muted=True):
        """Mute (True) or unmute (False) the speaker."""
        self._write_reg(REG_MUTE, 1 if muted else 0)

    def set_wake_time(self, seconds):
        """Set how long sensor stays awake after wake word (0–255s)."""
        self._write_reg(REG_WAKE_TIME, seconds & 0xFF)

    def get_wake_time(self):
        return self._read_reg(REG_WAKE_TIME)

    # ── Primary read ──────────────────────────────────────────
    def get_cmd_id(self):
        """
        Poll for latest recognised command. Returns int:
          0   = no new command
          1–N = command ID
        Sensor clears to 0 after read.
        """
        if not self._ok:
            return 0
        time.sleep(0.05)   # sensor needs small gap between polls
        try:
            return self._read_reg(REG_CMDID)
        except OSError:
            return 0

    def sense(self):
        """
        Returns dict for SENSE loop:
          cmd_id  (int)   — 0 = silence, >0 = recognised command
          ok      (bool)  — sensor reachable
        """
        cmd_id = self.get_cmd_id()
        return {"cmd_id": cmd_id, "ok": self._ok}

    def play(self, cmd_id):
        """Speak the audio phrase associated with command ID cmd_id."""
        if not self._ok:
            return
        self._write_reg(REG_PLAY_CMDID, cmd_id)
        time.sleep(1)   # give speaker time to finish

    def wake(self):
        """Force sensor into wake-up state (same as speaking wake word)."""
        self.play(1)   # cmd_id 1 triggers wake in I2C mode

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
    ap.add_argument('--watch', action='store_true', help='Continuous listen loop')
    ap.add_argument('--play',  type=int, metavar='CMD_ID', help='Speak a command ID')
    ap.add_argument('--volume', type=int, default=None)
    args = ap.parse_args()

    with VoiceSensor(args.bus, args.addr) as v:
        if args.volume is not None:
            v.set_volume(args.volume)
            print(f"Volume set to {args.volume}")

        if args.play is not None:
            print(f"Playing cmd_id {args.play}...")
            v.play(args.play)

        elif args.watch:
            print("Listening... Ctrl-C to stop")
            try:
                while True:
                    d = v.sense()
                    if d['cmd_id']:
                        print(f"  COMMAND: ID {d['cmd_id']}")
                    time.sleep(0.1)
            except KeyboardInterrupt:
                pass
        else:
            d = v.sense()
            print(d)


if __name__ == '__main__':
    main()
