#!/usr/bin/env python3
"""
ups_telemetry.py — 52Pi EP-0245 UPS battery state reader
Reads battery voltage, current, output rail, and status via I2C at 0x17.

Register map from 52Pi wiki (16-bit word reads, little-endian, values in mV/mA):
    0x0E  Output voltage (5V rail to Nano)   mV
    0x10  Input voltage  (USB-C charging)    mV
    0x12  Battery voltage                    mV
    0x14  MCU voltage                        mV
    0x16  Output current (5V rail)           mA
    0x18  Input current  (USB-C)             mA
    0x1A  Battery current (signed: + charge, - discharge)  mA
    0x1C  Temperature                        °C  (8-bit byte)
    0x1F  Status register SR1               flags byte

Battery percentage is calculated from voltage (no direct register available):
    range: 6400mV (empty 2S) – 8400mV (full 2S)

Usage:
    python3 ups_telemetry.py              # single reading
    python3 ups_telemetry.py --watch      # continuous (every 10s)
    python3 ups_telemetry.py --json       # JSON output (for daemon integration)
    python3 ups_telemetry.py --dump       # dump raw registers (diagnostics)
"""

import sys
import time
import json
import argparse

try:
    import smbus2 as smbus_mod
    def open_bus(n): return smbus_mod.SMBus(n)
except ImportError:
    try:
        import smbus as smbus_mod
        def open_bus(n): return smbus_mod.SMBus(n)
    except ImportError:
        print("ERROR: smbus2 or smbus not available.")
        print("  sudo apt install python3-smbus")
        sys.exit(1)

# ------------------------------------------------------------------
# EP-0245 v6 constants  (address confirmed via i2cdetect 2026-03-27)
# ------------------------------------------------------------------
UPS_ADDR = 0x17
I2C_BUS  = 1

# 16-bit word registers (read_word_data, little-endian)
REG_OUT_V    = 0x0E   # Output voltage (5V rail)        mV
REG_IN_V     = 0x10   # Input voltage (USB-C)           mV
REG_BATT_V   = 0x12   # Battery voltage                 mV
REG_MCU_V    = 0x14   # MCU voltage                     mV
REG_OUT_I    = 0x16   # Output current (5V rail)        mA
REG_IN_I     = 0x18   # Input current (USB-C)           mA
REG_BATT_I   = 0x1A   # Battery current (signed)        mA

# 8-bit byte registers
REG_TEMP     = 0x1C   # Temperature                     °C
REG_STATUS   = 0x1F   # Status SR1 flags byte

# Status bit definitions (SR1 at 0x1F)
SR1_BIT_BATT_LOW      = 0x20  # bit5: battery low warning
SR1_BIT_CHARGE_STATUS = 0x04  # bit2: 1=charging, 0=discharging

# Battery voltage range for 2S 18650 pack (2 cells in series)
BATT_FULL_MV  = 8400   # 2 × 4.2V
BATT_EMPTY_MV = 6400   # 2 × 3.2V (safe minimum — don't drain further)
BATT_WARN_MV  = 6800   # ~20% — trigger dock-seek behavior

# USB-C detection threshold (anything below = not connected)
USBC_CONNECTED_MV = 1000


def read_word(bus, reg):
    """Read a 16-bit little-endian word, return as integer."""
    raw = bus.read_word_data(UPS_ADDR, reg)
    return raw


def read_signed_word(bus, reg):
    """Read a 16-bit word and interpret as signed."""
    raw = read_word(bus, reg)
    return raw if raw <= 32767 else raw - 65536


def voltage_to_pct(voltage_mv):
    """
    Estimate battery percentage from voltage (linear approximation).
    Li-ion discharge is nonlinear; this is a rough guide only.
    """
    if voltage_mv >= BATT_FULL_MV:
        return 100
    if voltage_mv <= BATT_EMPTY_MV:
        return 0
    return int((voltage_mv - BATT_EMPTY_MV) / (BATT_FULL_MV - BATT_EMPTY_MV) * 100)


def read_ups(bus):
    """
    Read all key registers from EP-0245 and return a dict.
    Gracefully handles individual register failures.
    """
    result = {
        "timestamp":      time.strftime("%Y-%m-%dT%H:%M:%S"),
        "address":        hex(UPS_ADDR),
        "output_v_mv":    None,   # 5V rail to Nano
        "input_v_mv":     None,   # USB-C input
        "battery_v_mv":   None,   # battery pack voltage
        "battery_pct":    None,   # estimated SOC %
        "battery_i_ma":   None,   # battery current (+charge / -discharge)
        "output_i_ma":    None,   # 5V rail current draw
        "input_i_ma":     None,   # USB-C input current
        "temperature_c":  None,
        "charging":       None,
        "battery_low":    None,
        "usbc_connected": None,
        "status_raw":     None,
        "errors":         [],
    }

    for key, reg, signed in [
        ("output_v_mv",  REG_OUT_V,   False),
        ("input_v_mv",   REG_IN_V,    False),
        ("battery_v_mv", REG_BATT_V,  False),
        ("output_i_ma",  REG_OUT_I,   False),
        ("input_i_ma",   REG_IN_I,    False),
        ("battery_i_ma", REG_BATT_I,  True),
    ]:
        try:
            val = read_signed_word(bus, reg) if signed else read_word(bus, reg)
            result[key] = val
        except Exception as e:
            result["errors"].append(f"{key} (0x{reg:02X}) failed: {e}")

    try:
        result["temperature_c"] = bus.read_byte_data(UPS_ADDR, REG_TEMP)
    except Exception as e:
        result["errors"].append(f"temperature (0x{REG_TEMP:02X}) failed: {e}")

    try:
        sr1 = bus.read_byte_data(UPS_ADDR, REG_STATUS)
        result["status_raw"]  = hex(sr1)
        result["charging"]    = bool(sr1 & SR1_BIT_CHARGE_STATUS)
        result["battery_low"] = bool(sr1 & SR1_BIT_BATT_LOW)
    except Exception as e:
        result["errors"].append(f"status (0x{REG_STATUS:02X}) failed: {e}")

    if result["battery_v_mv"] is not None:
        result["battery_pct"]    = voltage_to_pct(result["battery_v_mv"])
        result["usbc_connected"] = (result["input_v_mv"] or 0) > USBC_CONNECTED_MV

    return result


def print_human(data):
    """Pretty-print UPS status for terminal use."""
    bv    = data.get("battery_v_mv")
    bi    = data.get("battery_i_ma")
    ov    = data.get("output_v_mv")
    oi    = data.get("output_i_ma")
    iv    = data.get("input_v_mv")
    pct   = data.get("battery_pct")
    chg   = data.get("charging")
    low   = data.get("battery_low")
    usbc  = data.get("usbc_connected")
    temp  = data.get("temperature_c")

    # Battery bar
    bar_width = 20
    if pct is not None:
        filled   = int(bar_width * pct / 100)
        bar_char = "█"
        if low:
            bar_char = "▓"
        bar = "[" + bar_char * filled + "░" * (bar_width - filled) + "]"
        warn = "  ⚠ LOW" if low else ""
        pct_str = f"{bar} {pct}%{warn}"
    else:
        pct_str = "  [unknown]"

    print(f"\n  52Pi EP-0245 UPS — {data['timestamp']}")
    print(f"  {'─' * 42}")
    print(f"  Battery:  {pct_str}")

    if bv is not None:
        print(f"  Pack:     {bv/1000:.3f} V", end="")
        if bi is not None:
            direction = "↑ charging" if bi > 50 else ("↓ discharging" if bi < -50 else "idle")
            print(f"   {abs(bi)} mA ({direction})", end="")
        print()

    if ov is not None:
        print(f"  5V rail:  {ov/1000:.3f} V", end="")
        if oi is not None:
            print(f"   {oi} mA  ({oi/1000*ov/1000:.2f} W est.)", end="")
        print()

    if iv is not None:
        usbc_str = f"{iv/1000:.2f} V  (connected)" if usbc else "not connected"
        print(f"  USB-C:    {usbc_str}")

    if chg is not None:
        print(f"  Charging: {'Yes ↑' if chg else 'No (discharging)'}")

    if temp is not None:
        print(f"  Temp:     {temp} °C")

    if data.get("errors"):
        print(f"\n  Warnings:")
        for err in data["errors"]:
            print(f"    ⚠  {err}")

    print()


def dump_registers(bus):
    """Read all registers 0x0E–0x2C and print raw values (for debugging)."""
    print(f"\n  Register dump — EP-0245 @ {hex(UPS_ADDR)}")
    print(f"  {'─' * 44}")
    labels = {
        0x0E: "Output voltage (5V rail) mV",
        0x10: "Input voltage (USB-C)    mV",
        0x12: "Battery voltage          mV",
        0x14: "MCU voltage              mV",
        0x16: "Output current           mA",
        0x18: "Input current            mA",
        0x1A: "Battery current (signed) mA",
        0x1C: "Temperature              °C  [byte]",
        0x1F: "Status SR1              flags [byte]",
    }
    for reg in range(0x0E, 0x2D, 2):
        label = labels.get(reg, "")
        try:
            if reg in (0x1C, 0x1F):
                val = bus.read_byte_data(UPS_ADDR, reg)
                print(f"  0x{reg:02X} [{label}]: {val} (0x{val:02X}  0b{val:08b})")
            else:
                val = read_word(bus, reg)
                signed = val if val <= 32767 else val - 65536
                print(f"  0x{reg:02X} [{label}]: {val}  signed={signed}")
        except Exception as e:
            print(f"  0x{reg:02X}: ERROR ({e})")
    print()


def main():
    parser = argparse.ArgumentParser(description="52Pi EP-0245 UPS telemetry")
    parser.add_argument("--watch",    action="store_true", help="Continuous poll")
    parser.add_argument("--interval", type=int, default=10, help="Watch interval (s)")
    parser.add_argument("--json",     action="store_true", help="Output as JSON")
    parser.add_argument("--dump",     action="store_true", help="Dump raw registers")
    args = parser.parse_args()

    try:
        bus = open_bus(I2C_BUS)
    except Exception as e:
        print(f"ERROR: Cannot open I2C bus {I2C_BUS}: {e}")
        sys.exit(1)

    if args.dump:
        dump_registers(bus)
        bus.close()
        return

    try:
        if args.watch:
            print(f"  Watching UPS (every {args.interval}s). Ctrl+C to stop.")
            while True:
                data = read_ups(bus)
                if args.json:
                    print(json.dumps(data))
                else:
                    print_human(data)
                time.sleep(args.interval)
        else:
            data = read_ups(bus)
            if args.json:
                print(json.dumps(data, indent=2))
            else:
                print_human(data)
    except KeyboardInterrupt:
        print("\n  Stopped.")
    finally:
        bus.close()


if __name__ == "__main__":
    main()
