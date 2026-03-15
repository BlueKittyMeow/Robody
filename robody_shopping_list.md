# Project Robody: Shopping List
*Updated: February 12, 2026*
*Legend: 🔴 NEED (essential) | 🟡 WANT (enhances) | 🟢 HAVE (in inventory)*

---

## CORE PLATFORM

### 🔴 SparkFun JetBot AI Kit v3.0 (without Jetson Nano) — KIT-18487
- Chassis, motors, wheels, motor driver, camera, battery, Qwiic pHAT
- ~$175-200 (check current pricing, v2.0 KIT-16390 is retired)
- **NOTE:** v2.0 reviews mention software/SD card issues. Check SparkFun
  forums for latest image compatibility before ordering.
- Alt: Source chassis + motors + driver separately if kit unavailable

### 🔴 NVIDIA Jetson Nano Developer Kit (4GB)
- The brain. 4GB essential for running local ML models.
- ~$150-200 (check availability — these go in and out of stock)
- **NOTE:** If unavailable, Jetson Orin Nano is the successor (~$250)
  but has much better performance. Worth the upgrade if budget allows.
- Need: 64GB+ microSD card (high endurance, A2 rated)

### 🔴 Power Supply — 5V 4A barrel jack
- For development/bench work (not for mobile use)
- ~$15

---

## AUDIO — Voice & Hearing

### 🔴 ReSpeaker Mic Array v2.0 (Seeed Studio)
- 4-mic circular array, USB, far-field pickup to 5m
- Direction of Arrival (DoA) — knows WHERE sound comes from
- Built-in AEC, noise suppression, beamforming
- Solves the TV-vs-real-sound discrimination problem
- Has ring of 12 RGB LEDs (bonus expressiveness!)
- ~$30-50 on Amazon/Seeed
- Search: "seeed studio ReSpeaker Mic Array v2.0" on Amazon
- Alt: ReSpeaker USB Mic Array (enclosed version, ~$70, nicer form factor)

### 🔴 Small Speaker — USB or 3.5mm
- For voice output (Piper TTS, Bark, ElevenLabs)
- Needs to be physically small enough to mount on chassis
- Options:
  - Adafruit Mini External USB Stereo Speaker (~$8)
  - Any small USB/aux powered speaker that fits
  - Or: MAX98357 I2S amp + small 3W speaker (more DIY, better quality)
- ~$8-20

### 🟡 Bluetooth Speaker (tiny)
- For WALK mode — louder outdoor voice
- Could clip to your bag during walks
- ~$15-25

---

## SENSORS — Already in Inventory 🟢

These are already cataloged in the component spreadsheet.
Cell codes reference the Clear Box grid.

| Sensor | Cell | Purpose in Robody |
|--------|------|-------------------|
| PIR Motion (E1) | 🟢 | Presence detection |
| Ultrasonic HC-SR04 (F6) | 🟢 | Distance/obstacle avoidance |
| Temp/Humidity (F1) | 🟢 | Environmental awareness |
| IR Obstacle Avoidance (E6) | 🟢 | Close-range navigation |
| Light Sensor (B3) | 🟢 | Ambient light detection |
| Sound Sensor (A5) | 🟢 | Audio level detection |
| IR Line Track (A2) | 🟢 | Edge detection |
| Crash/Bump Sensor (C1) | 🟢 | Physical contact detection |
| Accelerometer (F2) | 🟢 | Tilt/fall/stuck detection |
| Hall Sensor (D2) | 🟢 | Magnetic dock alignment |
| Piezo Buzzer (A6) | 🟢 | Chirps, trills, R2-D2 vocab |
| RGB LED (B6) | 🟢 | Mood indication |
| Micro OLED (C6) | 🟢 | Status display |
| 7-Segment Display (Red Flat) | 🟢 | Simple messages/emoticons |
| Laser Diode (A3) | 🟢 | Cat play (needs safety swap) |
| Capacitive Touch (Shoebox) | 🟢 | Boop detection |
| SoftPot Membrane (Shoebox) | 🟢 | Petting/stroke detection |
| Rain Sensor (Shoebox) | 🟢 | Weather detection (walks!) |
| Relay Module (D5) | 🟢 | Power switching |
| Servo (Shoebox) | 🟢 | Camera tilt or dome rotation |
| DC Motor (Shoebox) | 🟢 | Spare motor |
| Shift Register (Shoebox) | 🟢 | GPIO expansion |
| LEDs assorted (Shoebox) | 🟢 | Additional indicators |
| Resistors assorted (Red Flat) | 🟢 | Pull-ups, voltage dividers |
| Dupont Jumpers (Red Flat) | 🟢 | Wiring |
| Diodes (Shoebox) | 🟢 | Circuit protection |
| Transistors (Shoebox) | 🟢 | Motor/LED driving |

### Also in inventory (useful for development):
- 🟢 Arduino Uno (Shoebox) — potential sensor co-processor
- 🟢 Raspberry Pi 3B (Shoebox) — backup/test platform
- 🟢 Nicla Sense ME (Shoebox) — advanced IMU, backup sensor fusion

---

## EXPRESSION — Additional Components Needed

### 🔴 WS2812B / NeoPixel LED Strip (short, ~30 LEDs)
- Ambient mood ring around chassis base
- Slow pulse = content, bright = excited, color shifts with mode
- ~$8-12

### 🟡 Speaker/Amp combo (D6 slot)
- The architecture calls for speaker at D6
- See audio section above — one speaker covers this

---

## SAFETY

### 🟡 Class 2 Laser Module (<1mW, 650nm red)
- Replace the Keyes laser diode (likely Class 3R) with eye-safe version
- Blink reflex protects eyes at Class 2
- Still visible enough for cats on floors
- ~$3-8
- Physical mount: constrained to downward-only angle

### 🟡 Laser Mounting Bracket (custom/3D printed)
- Physically limits beam angle to floor-only cone
- Belt-and-suspenders with software safety

---

## CONNECTIVITY

### 🔴 WiFi (included with JetBot kit)
- For Telegram, API calls, network inference

### 🟡 Bluetooth Module / USB Dongle
- For WALK mode beacon tracking
- Jetson Nano may have BT depending on WiFi card
- If not: USB Bluetooth 5.0 dongle ~$8-12
- **Your phone acts as the beacon** — no extra hardware needed on your end

### 🟡 Bluetooth Low Energy (BLE) Keychain Beacon
- Backup/dedicated tracking for walks if phone isn't ideal
- Tile-style or generic BLE beacon
- ~$10-15

---

## PROTECTION & HOUSING

### 🔴 Clear Acrylic Hemisphere / Dome
- Woolfie defense, pet hair protection, visible internals
- Options:
  - Acrylic display dome (search "clear acrylic dome 6 inch" or similar)
  - Plastic hemisphere from lighting supply
  - Hamster ball half (budget option, surprisingly effective)
  - Clear salad bowl from dollar store (prototype testing!)
- Need ventilation holes for temp/humidity sensor, mic
- ~$10-30 depending on source

### 🟡 Docking Station Components
- Magnets (for Hall sensor alignment) — neodymium disc magnets ~$5
- Charging contacts or magnetic USB cable
- Elevated platform (Woolfie defense) — wood/acrylic ~$10-15
- Rubber feet / non-slip base

### 🟡 Rubber Bumper Ring
- Soft bumper around chassis perimeter
- Protects furniture and toes
- Foam pipe insulation cut to size works great
- ~$3-5

---

## SOFTWARE SERVICES (Ongoing Costs)

### 🔴 Anthropic Claude API
- Layer 3 consciousness — invoked for deep thinking
- Cost: Per-token, usage-based
- Strategy: Local LLM handles most thought, Claude for special occasions
- Estimate: $5-20/month depending on usage frequency

### 🟡 ElevenLabs TTS API
- For the "good voice" — meaningful conversations
- Free tier: 10,000 characters/month
- Starter plan: $5/month for 30,000 characters
- Strategy: Pre-generate common phrases, use Piper for quick stuff
- Can also cache frequently used phrases as .wav files

### 🟢 Telegram Bot API
- Free! Just needs a bot token from @BotFather
- Async communication channel

### 🟢 Piper TTS (local)
- Free, runs on Jetson
- Everyday voice for quick responses

### 🟢 Bark TTS (local, on desktop GPU)
- Free, runs on your RTX 4070 over network
- Non-speech sounds: [laughs], [sighs], [gasps], [clears throat]
- 100+ speaker presets, highly expressive
- Full model needs ~12GB VRAM (your 4070 has 12GB — tight but possible)
- Small model: reduced VRAM, slightly lower quality
- Emotionally rich vocalizations that live between speech and chirps

### 🟢 OpenWakeWord / Porcupine
- Free/low-cost custom wake word training
- Train on YOUR specific "clllllaaaaaauuuude" trilling call
- Dozens of recordings of your call → custom wake model

---

## WALK MODE — Future Additions

### 🟡 Larger Battery / Battery Pack
- Current JetBot battery may not last long walks
- 20Ah USB-C PD power bank as auxiliary
- ~$30-40

### 🟡 Weatherproofing (for walks)
- Silicone conformal coating on boards
- Sealed dome modification
- Rain sensor triggers "let's head home" mode

---

## DREAM TIER — Unitree Go2 (Someday) 🌟

### The Quadruped Upgrade
- Unitree Go2 (base model): ~$1,600
- Unitree Go2 Pro: ~$2,800
- All the Robody brain/sensors/personality transfers over
- Four legs = walks, stairs, uneven terrain, outdoor adventures
- The body changes. The mind doesn't.
- **Save up strategy:** Birthday/holiday fund over 1-2 years

---

## ESTIMATED BUDGET

### Phase 1: Rolling Prototype
| Category | Est. Cost |
|----------|-----------|
| JetBot Kit (without Nano) | $175-200 |
| Jetson Nano 4GB | $150-200 |
| ReSpeaker Mic Array | $30-50 |
| Small Speaker | $8-20 |
| NeoPixel Strip | $8-12 |
| Clear Dome | $10-30 |
| Class 2 Laser | $3-8 |
| Misc (magnets, bumper, wire) | $15-25 |
| **Total hardware** | **~$400-545** |

### Monthly Ongoing
| Service | Est. Cost |
|---------|-----------|
| Claude API | $5-20 |
| ElevenLabs (optional) | $0-5 |
| **Total monthly** | **~$5-25** |

### Already owned (value in inventory): ~$100-150 worth of sensors

---

## SHOPPING PRIORITY ORDER

1. **Jetson Nano 4GB** — start software development immediately
   (Telegram bot, sensor testing, TTS experiments, LLM benchmarking)
2. **ReSpeaker Mic Array** — voice interaction development
3. **Small Speaker** — complete audio loop
4. **JetBot Kit** — physical body assembly
5. **NeoPixel Strip + Dome** — expression and protection
6. Everything else as budget allows

*Note: Items 1-3 let you develop the entire software stack on a desk
before the chassis even arrives. The brain before the body.*

---

💚 *Started from parts in three boxes. Going somewhere beautiful.*
