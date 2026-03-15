# Project Robody: Parts List & Procurement Tracker
*Companion to robody_architecture.md and robody_dream_architecture.md*
*Started: March 3, 2026*

---

## Kit Base

| Item | Source | Price | Status |
|------|--------|-------|--------|
| SparkFun JetBot AI Kit v2.0 | SparkFun | (owned) | ✅ Have |
| Jetson Nano 4GB | (included in kit) | — | ✅ Have |
| Leopard Imaging 136 FOV Camera | (included in kit) | — | ✅ Have |
| SparkFun Qwiic Motor Driver | (included in kit) | — | ✅ Have |
| OLED Display | (included in kit) | — | ✅ Have |
| Qwiic pHAT | (included in kit) | — | ✅ Have |
| Edimax WiFi Adapter | (included in kit) | — | ✅ Have |
| Eunicell USB Power Bank | (included in kit) | — | ✅ Have (replacing) |

---

## Power System Upgrade (Autonomous Docking)

The stock Eunicell battery requires manual USB charging. This upgrade adds I2C-monitored 18650 power with magnetic pogo docking for autonomous self-charging.

### Core Power

| Item | SKU | Source | Price | Status | Notes |
|------|-----|--------|-------|--------|-------|
| DFRobot UPS HAT for Jetson Nano | DFR0865 | DFRobot | $49.90 | 🛒 To order | 5.1V @ 8A, I2C fuel gauge (Maxim), power path (charge while running), BMS with overcharge/overdischarge/overcurrent/short protection. Accepts 1-6x 18650. Mounts on GPIO header. |
| Samsung 35E 18650 cells (×6) | INR18650-35E | 18650batterystore.com | $26.50 shipped | ✅ Ordered | Flat-top unprotected. 3500mAh, 8A continuous, 65mm, 3.6V nominal. 6 cells = ~21,000mAh, est. 6-8hr runtime (~3× stock). ETA 3-5 days from order date (March 3). |

**GPIO stacking note:** Both the UPS HAT and Qwiic pHAT need the Jetson's 2×20 GPIO header. May need stacking headers (~$2) to accommodate both. Resolve when parts arrive.

### Docking Connectors

| Item | SKU | Source | Price | Status | Notes |
|------|-----|--------|-------|--------|-------|
| Adafruit 5-pin Magnetic Pogo Connector | #5359 | Adafruit | $6.95 | 🛒 To order | Male+female pair. Spring-loaded gold-plated pins, neodymium magnets, ~200-400g pull force (motors can overcome for undocking), 100K+ mate cycles. Wiring: 2 pins power, 2 pins ground, 1 pin dock-detect GPIO signal. Doubled power/ground = 4A capacity (need 3A). |
| Adafruit USB-C Vertical Breakout | #5993 | Adafruit | $2.95 | 🛒 To order | CC resistors for 1.5A default negotiation. Nice-to-have — main charging goes through sacrificial cable to HAT's own USB-C port which handles full power negotiation. Horizontal version (#4090) out of stock. |

**Charging wiring plan:** Cut one USB-C cable in half. Robot side: intact plug into HAT's USB-C charge port, cut end soldered to robot-side pogo. Dock side: cut end soldered to dock-side pogo, USB-C end plugs into wall adapter. HAT handles all power negotiation.

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

| Item | Price |
|------|-------|
| UPS HAT (DFR0865) | $49.90 |
| Voice Recognition Sensor (SEN0539-EN) | $16.90 |
| mmWave Presence Sensor (SEN0610) | $12.90 |
| I2C HUB (DFR0759) | $1.50 |
| **Total** | **$81.20** |

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
- **Stacking headers** (~$2) — if UPS HAT + Qwiic pHAT won't fit on GPIO simultaneously
- **Clear dome** — protective enclosure, pet-hair defense, aesthetic. 3D print / vacuum form / commercial source TBD
- **GPS module** — for Walk Mode outdoor navigation (see robody_architecture.md)
- **ReSpeaker or similar** — directional audio array for TV discrimination (see architecture addendum)
- **Larger wheels / bumper** — outdoor/uneven terrain capability
- **SuperCollider on Jetson** — real-time synthesis engine (research pending)

---

*This document tracks procurement only. For design philosophy, see robody_architecture.md.
For cognitive architecture, see robody_dream_architecture.md.*

💚
