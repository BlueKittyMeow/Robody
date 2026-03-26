# Current Status & Next Steps
*Updated: March 26, 2026*

---

## Where We Are

JetPack 4.6.1 has been flashed to the Jetson Nano's SD card (stock NVIDIA image, not SparkFun custom). The hardware stack is physically assembled: 52Pi EP-0245 UPS (bottom, pogo pins) → Jetson Nano (middle) → Adafruit Motor HAT (top, needs motor power jumper). Chassis has been modified from the original SparkFun JetBot to mecanum wheels with worm-gear drives for omnidirectional movement. Six Samsung 35E 18650 cells are wired into the EP-0245 (2-cell bay + 4-cell expansion).

Software architecture is complete — all 11 Python modules, 149 tests passing, dream architecture designed and experimentally validated. No hardware integration yet.

---

## Immediate Next Steps (Pre-Boot)

1. **Solder motor power jumper on Motor HAT** — Two short wires from the +5V and GND through-holes on the Motor HAT's power breakout column to the + and − pads of the 5-12V Motor Power screw terminal. This connects motor power to the GPIO 5V rail from the UPS. Strip, insert into screw terminal, solder through-hole side.

2. **Charge 18650 batteries** — Plug USB-C into the EP-0245 and let cells charge to 100% (all four LEDs solid). Can take several hours from empty.

3. **Connect motors to Motor HAT** — Wire four mecanum wheel motors to M1–M4 screw terminals on the Motor HAT. Note which motor maps to which wheel position for later software configuration.

---

## First Boot (Headless Setup)

The EP-0245 powers the Nano via GPIO, leaving the micro-USB port free for serial console. No barrel jack needed. J48 jumper left open.

1. Insert flashed SD card into Jetson Nano
2. Connect micro-USB cable from Nano to laptop
3. Disconnect USB-C charger (run on battery)
4. Power on — EP-0245 feeds 5V to Nano via pogo pins
5. On laptop: `screen /dev/ttyACM0 115200` (or `minicom`)
6. Walk through NVIDIA OOBE over serial (user account, locale, network)
7. Set `sudo nvpmodel -m 1` (5W mode to reduce power draw during setup)
8. Configure WiFi so we can SSH in going forward
9. SSH in from main machine — no more serial cable needed

---

## Post-Boot Software Setup

1. **System updates** — `sudo apt update && sudo apt upgrade`
2. **Enable I2C** — Verify `/dev/i2c-*` devices are present for Motor HAT and UPS telemetry
3. **Install ROS Melodic** — Matching version for Ubuntu 18.04 / JetPack 4.6.x. ROS is the "spinal cord" layer: motor control, path planning, SLAM, obstacle avoidance.
4. **Mecanum wheel ROS packages** — `mecanum_drive` (cmd_vel → individual wheel velocities), nav stack with `holonomic_robot: true`, GMapping + TEB planner for SLAM.
5. **Adafruit Motor HAT library** — `pip3 install adafruit-circuitpython-motorkit`. Test individual motor control over I2C.
6. **EP-0245 I2C telemetry** — Read battery voltage/percentage over I2C for autonomous charge monitoring.
7. **Deploy Robody brainstem** — Initial heartbeat loop, sensor polling, drive landscape.

---

## Hardware Stack (Bottom to Top)

```
┌─────────────────────────┐
│   Adafruit Motor HAT    │  ← TB6612, I2C motor control, 4 channels
│   (GPIO header, top)    │     Motor power jumpered from 5V rail
├─────────────────────────┤
│   Jetson Nano 4GB       │  ← JetPack 4.6.1, compute core
│   (GPIO header, middle) │     micro-USB free for serial console
├─────────────────────────┤
│   52Pi EP-0245 UPS v6   │  ← 6× 18650 cells, 5V regulated output
│   (pogo pins, bottom)   │     USB-C charging, I2C battery telemetry
├─────────────────────────┤
│   Mecanum Wheel Chassis │  ← Omnidirectional: lateral, diagonal, spin
│   (4 motors, worm gear) │     Modified from SparkFun JetBot base
└─────────────────────────┘
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
    └──→ Motor HAT 5V rail (4× mecanum motors)

Charging: USB-C magnetic breakaway → EP-0245 → cells
          (autonomous dock-and-charge, no manual plugging)
```

---

*Previous status: All software modules complete, tests passing. This document tracks the hardware integration phase.*
