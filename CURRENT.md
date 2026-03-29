# Current Status & Next Steps
*Updated: March 29, 2026 (session 4)*

---

## Where We Are

Robody is ONLINE with full sensor suite. Jetson Nano booted, networked, SSH-accessible, all four I2C devices communicating, camera operational.

### Completed (March 29, session 4)

- **All I2C sensors connected and communicating** — DFRobot Gravity I2C Hub (DFR0759) wired to J41 pins 1(3.3V)/3(SDA)/5(SCL)/6(GND). Full bus verified:
  - 0x17 EP-0245 UPS ✓
  - 0x2A C4001 mmWave Presence ✓
  - 0x60 Motor HAT ✓
  - 0x64 DF2301Q Voice Recognition ✓
- **C4001 DIP switch discovery** — Sensor shipped with protocol DIP set to UART (not I2C). This caused phantom addresses across the entire bus and Motor HAT unreachability. Second DIP selects address (0x2A/0x2B). Both now correctly set. Power cycle required after DIP change.
- **C4001 I2C protocol requirement** — Bare `read_byte()` or `i2cdetect -r` locks the bus permanently. Sensor requires register-addressed block reads: `read_i2c_block_data(0x2A, register, length)`. Safety wrapper deployed.
- **I2C bus safety tools deployed**:
  - `/usr/local/bin/safe-i2cdetect` — blocks bare scans of bus 1, passes through other buses
  - `/usr/local/bin/safe-i2c-scan` — Python utility that safely probes all known devices
  - `~/.bashrc` alias: `i2cdetect → safe-i2cdetect`
- **mmWave live data confirmed** — Presence mode detects humans (breathing/micro-motion). Speed mode returns range (tested 135–283cm), speed (0.17–0.22 m/s fidgeting detected), and signal energy. Possible cat detections at ~283cm.
- **IMX219 camera operational** — Pi Camera v2 at `/dev/video0` via tegra-video. Capture via `gst-launch-1.0 nvarguscamerasrc`. Adjustable gain (16–170) and exposure (13–683709µs). Auto-exposure needs ~10+ frames to converge. `nvgstcapture` doesn't work — use gstreamer directly.
- **Bus recovery procedure documented** — Tegra I2C controller unbind/rebind via sysfs recovers bus after lockup (if offending device removed). Full reboot otherwise.
- **Motor mapping verified** — Physical wheel test confirmed:
  - M1 = Rear Left, M2 = Front Left, M3 = Rear Right, M4 = Front Right
  - All spin forward with positive throttle (no inversions)
  - Updated `scripts/mecanum.py`, `ros/robody_drive/scripts/mecanum.py`, `scripts/motor_test.py`
- **Voice sensor volume** — Was at 0 (silent!). Set to 7 (max). Wake greeting confirmed audible.
- **Camera exposure** — IMX219 auto-exposure converges after ~10+ frames. Manual exposure params: `ispdigitalgainrange`, `gainrange`, `exposuretimerange` on `nvarguscamerasrc`.

### Completed (March 28, session 3)

- **WiFi power management stability fixes** — rtl8723bu driver was going catatonic when idle. Three-layer fix applied:
  - `/etc/modprobe.d/8723bu.conf`: `options 8723bu rtw_power_mgnt=0 rtw_enusbss=0 rtw_ips_mode=0`
  - `/etc/NetworkManager/conf.d/wifi-powersave.conf`: `wifi.powersave = 2`
  - `/etc/udev/rules.d/50-robody-wifi.rules`: USB autosuspend off for Edimax (7392:a611)
- **systemd motor service** — `robody-motor.service` created, enabled, and confirmed `active (running)`. Starts `motor_server.py` at boot, restarts on failure. No manual launch needed.
- **UPS software shutdown** — `scripts/ups_poweroff.py` deployed and tested. Writes shutdown countdown to EP-0245 register 0x23 (seconds), then issues `sudo shutdown`. OS halts cleanly; UPS cuts 5V rail after countdown. `--delay N`, `--ups-only`, `--auto-restart`, `--dry-run` flags. Tested: SSH dropped, both IPs went dark.
- **Passwordless sudo for power commands** — `/etc/sudoers.d/robody-power` grants `bluekitty` NOPASSWD for shutdown/poweroff/reboot (required for SSH non-interactive context).
- **Sensor dependencies installed** (when sensors arrive — deps are pre-staged):
  - `python3-smbus` 4.0-2 already present
  - `numpy` 1.13.3 already present
  - `pyserial` already installed
  - DFRobot libraries cloned: `~/lib/DFRobot_C4001/`, `~/lib/DFRobot_DF2301Q/`
- **Sensor wrappers written** (thin smbus2-based, no DFRobot library dependency):
  - `scripts/mmwave_sensor.py` — C4001 (SEN0610) wrapper; `sense()` returns `{present, range_m, speed, energy, ok}`; handles missing hardware gracefully; `--watch` mode
  - `scripts/voice_sensor.py` — DF2301Q (SEN0539-EN) wrapper; `sense()` returns `{cmd_id, ok}`; `play()`, `wake()`, volume/mute config; `--watch`, `--play CMD_ID` flags
- **LocalSend** — Flutter file-sharing app configured. `flutter.ls_quick_save: true` set (auto-accept incoming files). Receives to `~/Downloads/`. Launched with `WAYLAND_DISPLAY=wayland-1 XDG_RUNTIME_DIR=/run/user/1000`.

---

### Completed (March 27, sessions 1–2)

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
- **Kernel updated**: hard shutdown caused kernel update 4.9.253-tegra → 4.9.337-tegra on next boot; rtl8723bu WiFi driver required recompile:
  ```
  git clone https://github.com/lwfinger/rtl8723bu
  cd rtl8723bu
  ln -sf /usr/src/linux-headers-4.9.337-tegra-ubuntu18.04_aarch64/kernel-4.9 /lib/modules/4.9.337-tegra/build
  make ARCH=arm64 -j4 && sudo make install
  sudo modprobe 8723bu
  ```
  Note: headers are at `.../kernel-4.9/` subdirectory, NOT the parent `.../linux-headers-4.9.337-tegra-ubuntu18.04_aarch64/` path.
- **Adafruit library patches applied** (Python 3.6 compatibility — pip-installed files patched in-place, not in git):
  - `adafruit_platformdetect/constants/chips.py` — added `JH71x0 = JH71X0` alias (case mismatch between Blinka 6.15.0 and platformdetect 3.88.0)
  - `adafruit_motor/motor.py` — changed `positive_pwm: PWMOut` / `negative_pwm: PWMOut` to string annotations `"PWMOut"` (Python 3.6 evaluates annotations eagerly; PWMOut not imported)
  - Both patches survive reboots but would need re-applying after `pip install --upgrade`
- **scripts/ written and deployed to ~/scripts/ on Nano:**
  - `motor_test.py` — test each M1–M4 terminal individually, verify wheel direction, optional mecanum demo mode
  - `ups_telemetry.py` — reads live battery/voltage/current/temp from EP-0245 (register map calibrated from live dump: 0x12=battery mV, 0x0E=5V rail, 0x1A=current signed, 0x1F=status). Verified: 53% SOC, 7.46V, 5.15V rail, 27°C
  - `mecanum.py` — MecanumDrive class: move(vx, vy, omega) → wheel throttles; forward/backward/strafe/rotate helpers; normalizes to ±1.0; ready to wrap in ROS node

### Hardware Stack (Assembled)

```
                  ┌── IMX219 Camera (front) ──── CSI port 0
                  │
┌─────────────────┴───────┐
│   Adafruit Motor HAT    │  ← TB6612, I2C @ 0x60, 4 channels
│   (GPIO header, top)    │     Motor power: 5V rail jumper SOLDERED ✓
├─────────────────────────┤
│   Jetson Nano 4GB       │  ← JetPack 4.6.1, Ubuntu 18.04, Python 3.6
│   (GPIO header, middle) │     192.168.1.166 (WiFi) / .165 (eth)
├─────────────────┬───────┤
│   52Pi EP-0245  │ J41 pins 1/3/5/6 → DFR0759 Gravity I2C Hub
│   UPS v6        │   ├── C4001 mmWave Presence  @ 0x2A (front-right)
│   I2C @ 0x17    │   └── DF2301Q Voice Recog    @ 0x64
├─────────────────┴───────┤
│   Mecanum Wheel Chassis │  ← Omnidirectional: lateral, diagonal, spin
│   (4 motors, worm gear) │     Modified from SparkFun JetBot base
└─────────────────────────┘
```

---

## Immediate Next Steps

### Hardware (Lara)

1. ~~Solder motor power jumper~~ — DONE (5V/GND wires to Motor HAT screw terminal)
2. ~~Wire motors to Motor HAT~~ — DONE (M1=FL, M2=FR, M3=RL, M4=RR — all four verified spinning)

### Software (Claude)

1. ~~Motor test script~~ — Done (`scripts/motor_test.py`) — all 4 motors: ✓ OK
2. ~~UPS telemetry script~~ — Done (`scripts/ups_telemetry.py`)
3. ~~Mecanum kinematics~~ — Done (`scripts/mecanum.py`)
4. ~~ROS mecanum node~~ — Done (`ros/robody_drive/` catkin package, built and running)
   - `motor_server.py` (Python 3, TCP 9877) — MecanumDrive initialized @ I2C 0x60 ✓
   - `mecanum_drive_node.py` (Python 2.7 rospy) — `/cmd_vel` → TCP socket bridge
   - `drive.launch` — starts both nodes with respawn
   - catkin workspace: `~/catkin_ws/src/robody_drive/`, sourced in `~/.bashrc`
5. ~~On-boot motor service~~ — Done (`robody-motor.service` systemd unit, enabled ✓)
6. ~~UPS software shutdown~~ — Done (`scripts/ups_poweroff.py`, tested ✓)
7. ~~Sensor wrappers~~ — Done (`scripts/mmwave_sensor.py`, `scripts/voice_sensor.py`)
8. ~~Wire sensors~~ — Done (March 29). Gravity hub connected via female DuPont to J41 pins 1/3/5/6. Both sensors communicating.
9. ~~Camera verified~~ — Done (March 29). IMX219 at `/dev/video0`, captures via gstreamer.
10. **Deploy Robody heartbeat** — Get the core SENSE→NOTICE→THINK→DECIDE→LOG loop running on the Nano
11. **System updates** — `apt upgrade` on Nano (was attempted earlier but timed out)
12. **Rear camera** — Second camera cable arriving tomorrow; connect to second CSI port
13. **mmWave calibration** — Presence mode range values may be inaccurate (reported 283cm when physically closer). Speed mode gives better range data. Investigate detection range settings and calibration.

---

## Connection Reference

```
# SSH (passwordless from MysteryOfGlass)
ssh bluekitty@192.168.1.166

# Check motor HAT
python3 -c "from adafruit_motorkit import MotorKit; kit = MotorKit(); print('OK')"

# Check I2C devices — SAFE method (NEVER use bare i2cdetect on bus 1!)
safe-i2c-scan

# ROS
source /opt/ros/melodic/setup.bash
source ~/catkin_ws/devel/setup.bash   # (already in ~/.bashrc)
rosversion -d    # should print "melodic"
roslaunch robody_drive drive.launch   # start full mecanum drive stack
# motor_server alone (Python 3, no ROS needed):
python3 ~/catkin_ws/src/robody_drive/scripts/motor_server.py &

# Power mode
sudo nvpmodel -q   # 1 = 5W mode

# UPS shutdown (clean OS halt + UPS power cut after N seconds)
python3 ~/scripts/ups_poweroff.py --delay 45
python3 ~/scripts/ups_poweroff.py --dry-run   # show registers without acting

# Motor service (systemd, starts at boot)
sudo systemctl status robody-motor
sudo journalctl -u robody-motor -f

# LocalSend (file sharing from phone/MysteryOfGlass)
# Launch if not running:
WAYLAND_DISPLAY=wayland-1 XDG_RUNTIME_DIR=/run/user/1000 nohup /usr/local/localsend_app/localsend_app &
# Prefs: ~/.local/share/org.localsend.localsend_app/shared_preferences.json
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
    └──→ Motor HAT 5V rail (4× mecanum motors) [JUMPER SOLDERED ✓]

Charging: USB-C magnetic breakaway → EP-0245 → cells
          (autonomous dock-and-charge, no manual plugging)
```

---

## Known Issues / Notes

- **Python 3.6 on JetPack 4.6.1**: Latest Adafruit/Jetson.GPIO packages use features unavailable in 3.6. Libraries pinned to compatible versions. May need to upgrade Python or use virtualenv for newer packages later.
- **WiFi driver compiled from source**: rtl8723bu not in stock kernel. Module persisted in /etc/modules. **Kernel updated 4.9.253→4.9.337 after hard shutdown** — driver was recompiled. Will need recompile again on any future kernel update. Headers path is `linux-headers-<ver>-ubuntu18.04_aarch64/kernel-4.9/` (note the `kernel-4.9/` subdirectory for the build symlink target).
- **WiFi power management**: rtl8723bu drops connection when idle unless power saving is disabled. Three config files in place (modprobe options, NetworkManager, udev). If WiFi goes catatonic: `sudo rmmod 8723bu && sudo modprobe 8723bu` to recover without reboot.
- **WiFi hardware**: Edimax EW-7611ULB (rtl8723bu) is marginal. Consider upgrading to TP-Link Archer T2U Nano (RTL8811AU) or MT7612U-based adapter. Task in Pin and Paper.
- **No Wake on LAN**: Jetson Nano does not support WoL after full power-off. J40 header (pins 1&2) is the physical power button — could be driven by a transistor/relay for remote wake. Auto-restart via UPS register 0x1D bit0 also possible (re-applies power when USB-C reconnects).
- **UPS shutdown is one-way**: After `ups_poweroff.py`, Robody cannot power itself back on without physical button press or J40 transistor hack. Plan: WiFi-connected button motor for remote power-on.
- **Adafruit library patches**: Two pip-installed library files needed patching for Python 3.6 (see Completed section above). These will be lost on `pip upgrade` of the affected packages — re-apply if MotorKit breaks after upgrade.
- **Serial console**: USB gadget mode (ttyACM0) only works when barrel jack power is used with J48 jumpered. With GPIO power from UPS, micro-USB does NOT expose serial. Use SSH for all remote access.
- **Disk space**: 15GB free on 32GB card. Monitor carefully when installing additional packages.
- **C4001 mmWave I2C protocol**: NEVER use bare `read_byte()`, `i2cdetect -r`, or any address-only I2C transaction with the C4001. It holds SDA low and locks the entire bus. Always use `read_i2c_block_data(0x2A, register, length)`. Safety wrapper `safe-i2cdetect` is aliased in `~/.bashrc`. Bus recovery: unbind/rebind `7000c400.i2c` via sysfs, or reboot.
- **C4001 DIP switches**: Ships with protocol DIP set to UART. Must be flipped to I2C. Power cycle after any DIP change. Second DIP selects address 0x2A/0x2B.
- **Camera auto-exposure**: IMX219 via `nvarguscamerasrc` needs ~10+ frames for auto-exposure to converge. Single-frame captures will be very dark. Capture 30 frames and use the last one, or set manual exposure/gain.

---

*Software architecture (all 11 Python modules, 149 tests) is complete and waiting for hardware integration. This document tracks the bring-up phase.*
