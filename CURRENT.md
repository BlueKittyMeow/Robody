# Current Status & Next Steps
*Updated: March 27, 2026*

---

## Where We Are

Robody is ONLINE. Jetson Nano booted, networked, and SSH-accessible from MysteryOfGlass.

### Completed (March 27)

- JetPack 4.6.1 flashed to 32GB SD card (first card was corrupt, reflashed to new card)
- OOBE completed via HDMI + keyboard (headless serial requires barrel jack power; USB gadget mode not available when powered via GPIO)
- WiFi connected: Edimax EW-7611ULB driver (rtl8723bu) compiled from source and installed, persists across reboots via /etc/modules
- SSH: passwordless from MysteryOfGlass, IP 192.168.1.166 (WiFi) / 192.168.1.165 (eth)
- Power mode: 5W (`nvpmodel -m 1`)
- I2C verified: Motor HAT @ 0x60, UPS fuel gauge @ 0x17
- ROS Melodic installed (ros-base + 79 packages, sourced in bashrc)
- Adafruit MotorKit library installed and loading (pinned for Python 3.6 compatibility: Jetson.GPIO 2.0.21, busdevice 5.1.1, motorkit 1.6.4, pca9685 3.4.4, motor 3.4.3, register 1.9.8, dataclasses backport)
- smbus2 installed for UPS I2C telemetry
- Robody added to Hearth config as monitored machine
- **scripts/ written and deployed to ~/scripts/ on Nano:**
  - `motor_test.py` — test each M1–M4 terminal individually, verify wheel direction, optional mecanum demo mode
  - `ups_telemetry.py` — reads live battery/voltage/current/temp from EP-0245 (register map calibrated from live dump: 0x12=battery mV, 0x0E=5V rail, 0x1A=current signed, 0x1F=status). Verified: 53% SOC, 7.46V, 5.15V rail, 27°C
  - `mecanum.py` — MecanumDrive class: move(vx, vy, omega) → wheel throttles; forward/backward/strafe/rotate helpers; normalizes to ±1.0; ready to wrap in ROS node

### Hardware Stack (Assembled)

```
┌─────────────────────────┐
│   Adafruit Motor HAT    │  ← TB6612, I2C @ 0x60, 4 channels
│   (GPIO header, top)    │     Motor power: NEEDS JUMPER from 5V rail
├─────────────────────────┤
│   Jetson Nano 4GB       │  ← JetPack 4.6.1, Ubuntu 18.04, Python 3.6
│   (GPIO header, middle) │     192.168.1.166 (WiFi) / .165 (eth)
├─────────────────────────┤
│   52Pi EP-0245 UPS v6   │  ← 6× 18650 cells, I2C fuel gauge @ 0x17
│   (pogo pins, bottom)   │     USB-C charging, passthrough capable
├─────────────────────────┤
│   Mecanum Wheel Chassis │  ← Omnidirectional: lateral, diagonal, spin
│   (4 motors, worm gear) │     Modified from SparkFun JetBot base
└─────────────────────────┘
```

---

## Immediate Next Steps

### Hardware (Lara)

1. **Solder motor power jumper** — Two short wires from +5V and GND through-holes to the + and − of the Motor HAT's 5-12V power screw terminal
2. **Wire motors to Motor HAT** — Connect four mecanum motors to M1–M4 screw terminals. Note which motor maps to which wheel position

### Software (Claude)

1. ~~Motor test script~~ — Done (`scripts/motor_test.py`)
2. ~~UPS telemetry script~~ — Done (`scripts/ups_telemetry.py`)
3. ~~Mecanum kinematics~~ — Done (`scripts/mecanum.py`)
4. **ROS mecanum node** — ROS node wrapping MecanumDrive to accept geometry_msgs/Twist
5. **Deploy Robody heartbeat** — Get the core SENSE→NOTICE→THINK→DECIDE→LOG loop running on the Nano
6. **System updates** — `apt upgrade` on Nano (was attempted earlier but timed out)

---

## Connection Reference

```
# SSH (passwordless from MysteryOfGlass)
ssh bluekitty@192.168.1.166

# Check motor HAT
python3 -c "from adafruit_motorkit import MotorKit; kit = MotorKit(); print('OK')"

# Check I2C devices
sudo i2cdetect -y -r 1

# ROS
source /opt/ros/melodic/setup.bash
rosversion -d    # should print "melodic"

# Power mode
sudo nvpmodel -q   # 1 = 5W mode
```

---

## Power Architecture

```
18650 cells (6×, 7.4V nominal)
    │
    ▼
EP-0245 UPS regulator → 5V
    │
    ├──→ Jetson Nano (compute, camera, WiFi, sensors)
    │
    └──→ Motor HAT 5V rail (4× mecanum motors) [NEEDS SOLDER JUMPER]

Charging: USB-C magnetic breakaway → EP-0245 → cells
          (autonomous dock-and-charge, no manual plugging)
```

---

## Known Issues / Notes

- **Python 3.6 on JetPack 4.6.1**: Latest Adafruit/Jetson.GPIO packages use features unavailable in 3.6. Libraries pinned to compatible versions. May need to upgrade Python or use virtualenv for newer packages later.
- **WiFi driver compiled from source**: rtl8723bu not in stock kernel. Module persisted in /etc/modules. If kernel updates, driver needs recompile.
- **Serial console**: USB gadget mode (ttyACM0) only works when barrel jack power is used with J48 jumpered. With GPIO power from UPS, micro-USB does NOT expose serial. Use SSH for all remote access.
- **Disk space**: 15GB free on 32GB card. Monitor carefully when installing additional packages.

---

*Software architecture (all 11 Python modules, 149 tests) is complete and waiting for hardware integration. This document tracks the bring-up phase.*
