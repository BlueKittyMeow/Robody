# Robody Sensor Stack — Dependencies & Integration Notes
*Researched: March 2026 — do not install yet, see status flags*

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

**Status:** `📦 Not yet received / 🔴 Not installed`

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

**Status:** `📦 Not yet received / 🔴 Not installed`

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

**Status:** `📦 Not yet received / ✅ No installation needed`

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

## Installation Plan (when sensors arrive)

Do this in order. Don't install yet.

```bash
# 1. Check bus is clean before adding new devices
sudo i2cdetect -y -r 1
# expect: 0x17, 0x60, 0x70 only

# 2. Install smbus (for DFRobot library compatibility)
sudo apt install python3-smbus

# 3. numpy (for DF2301Q)
pip3 install numpy --break-system-packages

# 4. pyserial (in case UART mode ever needed)
pip3 install pyserial --break-system-packages

# 5. Clone DFRobot libraries (to ~/lib/)
mkdir -p ~/lib
git clone https://github.com/DFRobot/DFRobot_C4001 ~/lib/DFRobot_C4001
git clone https://github.com/DFRobot/DFRobot_DF2301Q ~/lib/DFRobot_DF2301Q

# 6. Test C4001 at 0x2A after physical connection
python3 -c "import smbus2; b=smbus2.SMBus(1); print(hex(b.read_byte(0x2A)))"

# 7. Test DF2301Q at 0x64
python3 -c "import smbus2; b=smbus2.SMBus(1); print(hex(b.read_byte(0x64)))"
```

**Then** write thin wrappers using `smbus2` directly rather than patching DFRobot's libraries.

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
