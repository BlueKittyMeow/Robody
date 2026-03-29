# Robody Sensor Stack — Dependencies & Integration Notes
*Researched: March 2026 — updated March 29 after successful hardware integration*

---

## Sensors On Order (DFRobot, ordered 2026-03-05)

### 1. DFRobot Gravity mmWave C4001 Presence Sensor — SEN0610

**Purpose:** Primary person-detection modality. 24GHz FMCW radar detects humans by breathing/heartbeat/micro-movement. Works on sleeping/stationary people. Maps to the "mmWave" native channel in the dream somatic layer.

**Hardware**
- I2C address: `0x2A` (default) / `0x2B` (alternate via DIP switch on sensor)
- Both addresses are **free** on Robody's I2C bus (0x17=UPS, 0x60=MotorHAT, 0x70=PCA9685)
- Operates at 3.3–5V; Gravity connector provides 5V from Nano's 5V rail
- I2C logic level: 3.3V compatible (Nano GPIO is 3.3V — fine, no level shifting needed)
- Detection range: 0.3–12m (SEN0610), 100°×80° beam angle

**Python library**
```
git clone https://github.com/DFRobot/DFRobot_C4001
# library is in: python/raspberrypi/
```

**Direct dependencies**
```
smbus       # I2C — see WARNING below
pyserial    # UART mode only (not needed if using I2C)
```

**⚠️ Known Python 3 issues with the official library (confirmed on RPi5, likely same on Nano):**
- Indentation errors throughout (Python 2 spacing not PEP8 compliant)
- `TypeError: 'int' object is not subscriptable` in `motion_detection()` — returns int not list
- Broken class inheritance: `read_reg` / `write_reg` methods not found in subclass
- Recommendation: **do not use the DFRobot library verbatim** — write a thin wrapper
  directly over `smbus2` (we already have it installed) rather than fighting the upstream code

**⚠️ smbus vs smbus2:**
DFRobot library uses `import smbus` (not `import smbus2`). Two options:
- Option A: `sudo apt install python3-smbus` (installs legacy smbus from i2c-tools)
- Option B: Write wrapper using `smbus2` directly (preferred — cleaner, already installed)

**⚠️⚠️ CRITICAL: DIP SWITCHES (learned the hard way, March 29 2026):**
The C4001 has **TWO DIP switches** on the board:
- **Protocol switch**: UART vs I2C. Ships defaulting to UART! If set to UART, the sensor's TX line floods the I2C bus with serial data, creating phantom devices at 30+ addresses and making the Motor HAT unreachable. **Must be set to I2C.**
- **Address switch**: 0x2A (default) vs 0x2B. Set to whichever is free on your bus.
- After flipping DIP switches, **power-cycle the sensor** (unplug and replug from Gravity hub).

**⚠️⚠️ CRITICAL: I2C PROTOCOL — NO BARE READS:**
The C4001 does NOT tolerate bare `read_byte(addr)` or `i2cdetect -r` scans.
It ACKs its address but then holds SDA low indefinitely waiting for a register
byte that never comes. This **locks the entire I2C bus** — all other devices
become unreachable until power cycle or Tegra I2C controller reset.

**Safe approach:** Always use `read_i2c_block_data(0x2A, register, length)`.
For example, to check if the sensor is alive: `read_i2c_block_data(0x2A, 0x00, 1)`.

A `safe-i2cdetect` wrapper and `safe-i2c-scan` utility are deployed on the Nano
to prevent accidental bare scans. See `/usr/local/bin/safe-i2cdetect` and
`/usr/local/bin/safe-i2c-scan`.

**Bus recovery if locked:** Unbind/rebind the Tegra I2C controller:
```bash
echo '7000c400.i2c' | sudo tee /sys/bus/platform/drivers/tegra-i2c/unbind
sleep 1
echo '7000c400.i2c' | sudo tee /sys/bus/platform/drivers/tegra-i2c/bind
```
This only works if the offending device has been physically removed. Otherwise reboot.

**Status:** `✅ Connected and working (March 29, 2026)`

---

### 2. DFRobot Gravity Voice Recognition Sensor — SEN0539-EN

**Purpose:** Offline, on-chip voice command detection. Zero Jetson compute — all processing on the sensor. Primary voice interaction channel. 121 fixed + 17 custom commands. Built-in speaker for audio feedback.

**Hardware**
- I2C address: `0x64` (fixed)
- Free on Robody's I2C bus — no conflict
- Operates at 3.3–5V; Gravity connector
- UART also supported (9600 baud, `/dev/ttyTHS*` or similar on Nano — not needed for I2C mode)

**Python library**
```
git clone https://github.com/DFRobot/DFRobot_DF2301Q
# library is in: python/raspberrypi/
```

**Direct dependencies**
```
smbus       # I2C — see WARNING below (same as C4001)
numpy       # required by DFRobot_DF2301Q.py
pyserial    # UART mode only (not needed for I2C)
```

**⚠️ smbus vs smbus2:** Same issue as C4001 — uses `import smbus`, not `smbus2`.

**numpy on Jetson Nano Python 3.6:**
```bash
pip3 install numpy --break-system-packages
# or:
sudo apt install python3-numpy
```
Numpy for aarch64/Python 3.6 is available and well-tested. Should install cleanly.

**Note:** Unlike the C4001, the DF2301Q tolerates bare `read_byte()` fine.
It's safe to use `i2cdetect` for this device specifically. The thin wrapper
uses `read_i2c_block_data` for consistency but `read_byte` also works.

**Status:** `✅ Connected and working (March 29, 2026)`

---

### 3. DFRobot Gravity I2C HUB — DFR0759

**Purpose:** Distributes one I2C bus into 8 Gravity-connector ports. Makes physical wiring tidy when daisy-chaining multiple Gravity sensors. Also already ordered.

**Hardware — passive bus splitter**
- This is a **passive hub** (not an active multiplexer like TCA9548A)
- All 8 output ports are wired in parallel to the same SDA/SCL bus
- **No I2C address of its own, no driver or library needed**
- No software interaction required at all — transparent to the OS

**Important implication:** Since it's passive, all devices plugged into it share the same I2C bus and must have unique addresses. With our current devices:

| Device | Address | Conflict? |
|---|---|---|
| EP-0245 UPS | 0x17 | — |
| Motor HAT TB6612 | 0x60 | — |
| PCA9685 all-call | 0x70 | — |
| C4001 mmWave | 0x2A or 0x2B | — |
| DF2301Q Voice | 0x64 | — |

All clear. No conflicts on any planned combination.

**One caveat on bus loading:** Passive hubs increase I2C bus capacitance. With 5 devices, pull-up resistors (usually 4.7kΩ to 3.3V) may need to be lowered if signals get floppy at fast speeds. At 100kHz (standard mode) this is never an issue.

**Status:** `✅ Connected, routing all sensors (March 29, 2026)`

---

## HC-SR04 Ultrasonic Rangefinder (already owned)

*Note: This is NOT I2C — documented here for completeness alongside the I2C sensors.*

- Uses digital GPIO: TRIG (output) + ECHO (input)
- ECHO pin is **5V logic** — requires voltage divider before connecting to Nano's 3.3V GPIO
  - 1kΩ from sensor ECHO → GPIO pin, + 2kΩ from GPIO pin → GND (⅔ divider: 5V → 3.3V)
- Suggested pins: TRIG → GPIO23 (pin 16), ECHO → GPIO24 (pin 18) via divider
- Python library: `RPi.GPIO` style or `Jetson.GPIO` (already installed)
- No additional pip packages needed

---

## Full Planned I2C Bus Map (bus 1, once sensors arrive)

```
I2C bus 1  (SDA=pin3, SCL=pin5)
│
├── 0x17  EP-0245 UPS fuel gauge
├── 0x60  Adafruit Motor HAT (TB6612 via PCA9685)
├── 0x64  DF2301Q Voice Recognition Sensor    ← to be connected
├── 0x2A  C4001 mmWave Presence Sensor        ← to be connected
└── 0x70  PCA9685 general call (Motor HAT)
```

All routed through DFR0759 passive hub for tidy wiring.

---

## Installation Record (completed March 29, 2026)

All sensors connected and verified. Here's what was actually done:

```bash
# Dependencies (were already installed during pre-staging)
# python3-smbus 4.0-2, numpy 1.13.3, pyserial, smbus2 all present

# DFRobot libraries cloned for reference (NOT used directly)
# ~/lib/DFRobot_C4001/, ~/lib/DFRobot_DF2301Q/

# Safe bus scan (NEVER use bare i2cdetect -r on bus 1!)
safe-i2c-scan
# 0x17 UPS ✓, 0x2A mmWave ✓, 0x60 Motor HAT ✓, 0x64 Voice ✓

# Test C4001 — MUST use register-addressed read
python3 -c "import smbus2; b=smbus2.SMBus(1); print(b.read_i2c_block_data(0x2A, 0x00, 1))"

# Test DF2301Q — bare read is fine for this device
python3 -c "import smbus2; b=smbus2.SMBus(1); print(hex(b.read_byte(0x64)))"
```

Thin wrappers written using `smbus2` directly: `scripts/mmwave_sensor.py`, `scripts/voice_sensor.py`.

---

## IMX219 Camera (Pi Camera v2, 8MP)

**Hardware**
- CSI connector on Jetson Nano carrier board
- Device: `/dev/video0` via `tegra-video` driver (`vi-output, imx219 8-0010`)
- Sensor modes: 3264×2464@21fps, 3264×1848@28fps, 1920×1080@30fps, 1640×1232@30fps, 1280×720@60fps, 1280×720@120fps
- Adjustable gain (16–170) and exposure (13–683709 µs)

**Capture pipeline (gstreamer)**
```bash
# Single frame, auto-exposure (may be dark — AE needs ~10 frames to settle)
gst-launch-1.0 nvarguscamerasrc num-buffers=1 sensor-id=0 \
  ! 'video/x-raw(memory:NVMM),width=1280,height=720,framerate=21/1' \
  ! nvjpegenc ! filesink location=/tmp/robody_cam.jpg

# Better: capture 30 frames, keep the last (AE converged)
gst-launch-1.0 nvarguscamerasrc num-buffers=30 sensor-id=0 \
  ! 'video/x-raw(memory:NVMM),width=1280,height=720,framerate=21/1' \
  ! nvjpegenc ! multifilesink location=/tmp/robody_cam_%02d.jpg

# Manual exposure (bright indoor):
gst-launch-1.0 nvarguscamerasrc num-buffers=30 sensor-id=0 \
  ispdigitalgainrange='4 4' gainrange='8 8' \
  exposuretimerange='33000000 33000000' \
  ! 'video/x-raw(memory:NVMM),width=1280,height=720,framerate=21/1' \
  ! nvjpegenc ! multifilesink location=/tmp/robody_cam_%02d.jpg
```

**Note:** `nvgstcapture-1.0 --automate` fails with "Capture Pipeline creation failed" on this JetPack. Use `gst-launch-1.0` directly instead.

**Status:** `✅ Working (March 29, 2026)`

---

## Board Revision Note

**TODO:** Determine Jetson Nano developer kit revision (A02 vs B01). Run this when connected:

```bash
cat /proc/device-tree/model
strings /proc/device-tree/compatible
# B01 will show two CSI camera entries
ls /dev/video*    # B01 has /dev/video0 + /dev/video1
```

Relevant for J40 power header wiring (future remote-wake transistor).
A02: J40 is near the HDMI port edge.
B01: J40 is near the micro-USB port edge.
Both have power-on on pins 1–2.
