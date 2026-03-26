# Project Robody: Parts List & Procurement Tracker
*Companion to robody_architecture.md and robody_dream_architecture.md*
*Started: March 3, 2026*

---

## Kit Base

*Originally SparkFun JetBot AI Kit v2.0. Chassis and wheels have been replaced with mecanum wheel platform; motor driver replaced with Adafruit Motor HAT. Several kit components still in use.*

| Item | Source | Price | Status | Notes |
|------|--------|-------|--------|-------|
| SparkFun JetBot AI Kit v2.0 | SparkFun | (owned) | ✅ Have | Base kit — chassis/wheels/motor driver replaced, other components retained |
| Jetson Nano 4GB | (included in kit) | — | ✅ Have | Compute core, flashed with stock JetPack 4.6.1 |
| Leopard Imaging 136 FOV Camera | (included in kit) | — | ✅ Have | |
| SparkFun Qwiic Motor Driver | (included in kit) | — | ⬜ Replaced | Replaced by Adafruit DC+Stepper Motor HAT (TB6612, I2C, 4 channels) |
| OLED Display | (included in kit) | — | ✅ Have | |
| Qwiic pHAT | (included in kit) | — | ✅ Have | |
| Edimax WiFi Adapter | (included in kit) | — | ✅ Have | |
| Eunicell USB Power Bank | (included in kit) | — | ⬜ Replaced | Replaced by 52Pi EP-0245 UPS with 18650 cells |

### Chassis & Drive Train (Modified)

| Item | Source | Price | Status | Notes |
|------|--------|-------|--------|-------|
| Mecanum wheel chassis | (modified from SparkFun kit) | (owned) | ✅ Have | Replaced stock wheels. 4 mecanum wheels with worm-gear drives enabling omnidirectional movement (lateral, diagonal, rotation in place). |
| Adafruit DC+Stepper Motor HAT | B00TIY5JM8 | Amazon/Adafruit | (owned) | ✅ Have | TB6612 chipset, 4 DC motor channels, 1.2A/channel (3A peak), I2C control via PCA9685 PWM. Stacks on Nano GPIO header. Motor power jumpered from GPIO 5V rail (no external motor power supply). |

---

## Power System Upgrade (Autonomous Docking)

The stock Eunicell battery requires manual USB charging. This upgrade adds I2C-monitored 18650 power with magnetic pogo docking for autonomous self-charging.

### Core Power

| Item | SKU | Source | Price | Status | Notes |
|------|-----|--------|-------|--------|-------|
| 52Pi UPS v6 (EP-0245) | EP-0245 | 52Pi | (owned) | ✅ Have | **PRODUCTION UPS.** V1.8 board (2025/6/4). Connects to Jetson Nano via pogo pins on GPIO header. I2C telemetry for battery level monitoring (essential for autonomous recharge docking). USB-C charging input — will be spliced with magnetic pogo breakaway for dock-and-charge. Supports passthrough charging. |
| DFRobot UPS HAT for Jetson Nano | DFR0865 | DFRobot | $49.90 | ✅ Ordered (not using) | Originally ordered but replaced by 52Pi EP-0245 in production build. 5.1V @ 8A, I2C fuel gauge. Keeping as spare/bench supply. |
| Samsung 35E 18650 cells (×6) | INR18650-35E | 18650batterystore.com | $26.50 shipped | ✅ Have | Flat-top unprotected. 3500mAh, 8A continuous, 65mm, 3.6V nominal. 6 cells wired into EP-0245: 2-cell bay + 4-cell expansion bay per 52Pi instructions. |

**Power architecture:** Single power path — 18650s → EP-0245 UPS regulator → 5V via GPIO pogo pins → Jetson Nano → Motor HAT (jumpered from GPIO 5V rail). Motors, compute, and all peripherals draw from the same 5V rail. Autonomous dock charging via USB-C magnetic breakaway connector on the EP-0245's USB-C port. Battery telemetry over I2C enables the AI to monitor charge level and trigger autonomous dock-seek behavior.

**J48 jumper:** Left UNJUMPERED. Power enters via GPIO header pins from UPS, not barrel jack. Micro-USB port remains free for serial console (headless setup).

**GPIO stacking note:** EP-0245 connects via pogo pins (bottom of stack), Motor HAT via standard header (top of stack). Qwiic pHAT may need stacking headers (~$2) to fit in between. Resolve when assembling full stack.

### Docking Connectors

| Item | SKU | Source | Price | Status | Notes |
|------|-----|--------|-------|--------|-------|
| Adafruit 5-pin Magnetic Pogo Connector | #5359 | Adafruit | $6.95 | 🛒 To order | Male+female pair. Spring-loaded gold-plated pins, neodymium magnets, ~200-400g pull force (motors can overcome for undocking), 100K+ mate cycles. Wiring: 2 pins power, 2 pins ground, 1 pin dock-detect GPIO signal. Doubled power/ground = 4A capacity (need 3A). |
| Adafruit USB-C Vertical Breakout | #5993 | Adafruit | $2.95 | 🛒 To order | CC resistors for 1.5A default negotiation. Nice-to-have — main charging goes through sacrificial cable to HAT's own USB-C port which handles full power negotiation. Horizontal version (#4090) out of stock. |

**Charging wiring plan:** USB-C magnetic breakaway connector spliced inline on the charging cable to the EP-0245's USB-C port. Robot backs up to dock, magnetic pins align and connect, UPS charges via USB-C passthrough while robot continues operating. Robot drives forward to undock — magnetic breakaway disconnects cleanly. No manual plugging ever required.

### Dock Cradle

| Item | Source | Price | Status | Notes |
|------|--------|-------|--------|-------|
| 3D-printed funnel dock cradle | JLCPCB or PCBWay | TBD | 📐 Design pending | Funnel/V-shape: wide opening (~20-25cm) narrowing to JetBot width (~15cm). Back wall holds female pogo connector. Guide walls for ±2cm alignment tolerance, magnets handle final mm. ArUco marker slot on front face. Design STL after JetBot assembled and dimensions measured. |
| ArUco marker (printed) | Self | Free | ✅ Ready | Black-and-white square pattern for OpenCV dock-finding with sub-pixel accuracy + distance/angle estimation. Already on Jetson JetBot image. Print on paper, mount on dock face. |

### Accessories

| Item | Source | Price | Status | Notes |
|------|--------|-------|--------|-------|
| USB-C wall adapter | (owned) | — | ✅ Have | Any decent 5V/3A USB-C adapter. |
| USB-C cable (sacrificial) | (owned) | — | ✅ Have | Cut in half for pogo wiring. |
| Wire + solder | (owned) | — | ✅ Have | For pogo connections. |
| AirTag or NFC sticker | Apple / various | ~$5-30 | 💭 Nice-to-have | Physical locator backup. Not critical for autonomous docking. |

---

## Sensor Expansion

New sensors beyond the JetBot kit and existing inventory, adding new perceptual modalities.

| Item | SKU | Source | Price | Status | Notes |
|------|-----|--------|-------|--------|-------|
| DFRobot Gravity Voice Recognition Sensor | SEN0539-EN | DFRobot | $16.90 | ✅ Ordered 3/5 | Offline voice recognition. Dual built-in mics, 121 fixed + 17 custom voice commands, I2C & UART, built-in speaker. On-chip processing = zero Jetson compute. NOTE: Command classifier only — no raw audio passthrough. |
| DFRobot mmWave C4001 Presence Sensor | SEN0610 | DFRobot | $12.90 | ✅ Ordered 3/5 | 24GHz FMCW radar, 12m range, detects breathing/heartbeat/micro-movements. I2C. 100°×80° beam. Chose 12m over 25m (SEN0609) to avoid detecting through walls. |
| DFRobot Gravity I2C HUB | DFR0759 | DFRobot | $1.50 | ✅ Ordered 3/5 | I2C multiplexer — expands single I2C bus to multiple ports. Needed for: voice sensor, mmWave, OLED, motor driver, UPS HAT fuel gauge. |
| Kinobo Mini USB Microphone | B076BC2Y3W | Amazon | ~$8 | ✅ Ordered 3/5 | Replaces Adafruit #3367 (out of stock). USB dongle, plug-and-play ALSA capture on Linux. Gooseneck adjustable. Environmental audio awareness channel — ambient sound, noise detection, ML input. Separate from SEN0539's command mics. |

---

## Order Summary

### Ordered — DFRobot ($81.20, free shipping) — 2026-03-05

| Item | Price | Notes |
|------|-------|-------|
| UPS HAT (DFR0865) | $49.90 | Not using in production — replaced by 52Pi EP-0245. Keeping as spare. |
| Voice Recognition Sensor (SEN0539-EN) | $16.90 | |
| mmWave Presence Sensor (SEN0610) | $12.90 | |
| I2C HUB (DFR0759) | $1.50 | |
| **Total** | **$81.20** | |

### Ordered — Amazon Prime — 2026-03-05

| Item | Price |
|------|-------|
| Kinobo Mini USB Microphone (B076BC2Y3W) | ~$8.00 |

### Ordered — 18650batterystore.com — 2026-03-03

| Item | Price |
|------|-------|
| 6× Samsung 35E 18650 cells | $26.50 shipped |

### Ordered — Adafruit ($34.80 + $6.36 shipping) — 2026-03-05

| Item | Price |
|------|-------|
| 5-pin Magnetic Pogo Connector (#5359) | $6.95 |
| NeoPixel RGBW Strip 1m, 30 LED/m (#2508) | $17.95 |
| MAX98357A I2S 3W Amp Breakout (#3006) | $5.95 |
| Mono Enclosed Speaker 3W 4Ω (#3351) | $3.95 |
| Shipping (USPS Ground Advantage) | $6.36 |
| **Total** | **$41.16** |

### Deferred — Order Later

| Item | Source | Price | Notes |
|------|--------|-------|-------|
| USB-C Vertical Breakout (#5993) | Adafruit | $2.95 | Nice-to-have, not needed — charging goes through sacrificial cable. |
| 74AHCT125 Level Shifter (#1787) | Adafruit | $1.50 | Only if NeoPixel strip flickers at 3.3V data. Try without first. |
| Class 2 Laser Module (<1mW) | Amazon | ~$3-8 | Adafruit doesn't sell Class 2. Replace Keyes laser for eye-safe cat play. |

### Grand Total: ~$156.86

---

## Existing Inventory (Relevant to Robody)

Full inventory in Google Sheets "Components Inventory" (3 tabs: Clear Box, Red Flat, Red Shoebox).

Key items already owned and allocated to Robody — see robody_dream_architecture.md Part 16 for full sensor mapping with phenomenological functions:

**Touch/Vibration:** Tilt/vibrate, crash/knock, capacitive touch, SoftPot, tactile buttons
**Temperature:** Temp/humidity (F1), analog temp ×2, digital temp, TMP36
**Light:** TEMT6000, analog light, LDR, IR line track
**Sound:** Sound sensor MK, passive speaker, buzzer, speaker amp
**Spatial:** PIR motion, reed switch, ultrasonic HC-SR04, accelerometer ADXL345
**Air Quality:** MQ-2 smoke/VOC, MQ-3 alcohol
**Magnetic:** Hall sensor A3144
**Output:** RGB LED, LED strip, micro OLED, 7-segment display, laser diode
**Actuators:** Micro servo, DC motor, relay
**Compute:** Raspberry Pi 3B, Arduino Uno, Nicla Sense ME, Promicro ATmega

---

## Future Considerations (Not Yet Spec'd)

- **Samsung S22 Ultra as face/display** (owned, WiFi-only) — 6.8" AMOLED, 1440×3088. Serve a React web app over local WiFi, phone opens it in fullscreen. WebSocket connection to Robody backend for real-time state updates. Display could mix generated images (via ComfyUI on MarshLair), Giphy pulls for reactive moments, and layered UI elements (mood colors, text, particles). AMOLED burn-in consideration: favor dark backgrounds with moving elements, periodic subtle shifts. Needs: wake lock (Android dev settings or wrapper app), permanent USB-C power, mount solution. The phone is just a gorgeous dumb screen — all logic server-side, swappable for any browser-capable device.
- **Stacking headers** (~$2) — if EP-0245 + Motor HAT + Qwiic pHAT won't all fit on GPIO simultaneously
- **Clear dome** — protective enclosure, pet-hair defense, aesthetic. 3D print / vacuum form / commercial source TBD
- **GPS module** — for Walk Mode outdoor navigation (see robody_architecture.md)
- **ReSpeaker or similar** — directional audio array for TV discrimination (see architecture addendum)
- **Bumper ring** — furniture/toe protection for mecanum chassis
- **SuperCollider on Jetson** — real-time synthesis engine (research pending)

---

*This document tracks procurement only. For design philosophy, see robody_architecture.md.
For cognitive architecture, see robody_dream_architecture.md.*

💚
