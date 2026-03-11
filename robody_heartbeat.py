#!/usr/bin/env python3
"""
Robody Heartbeat — The Core Runtime Loop
=========================================
Implements Layer 2 (Inner Life) from robody_architecture.md:
the SENSE → NOTICE → THINK → DECIDE → LOG heartbeat cycle.

Uses inotify (Linux) or polling fallback to watch for sensor
state changes in /home/robody/state/. When something changes,
the heartbeat wakes up. When nothing changes, it sleeps.

"Decide NOT to act is a valid, important outcome.
 Autonomy means choosing stillness."

Architecture:
  - Event-driven via inotify on state directory
  - Adaptive frequency: fires rapidly in active environments,
    barely wakes up in quiet ones
  - Integrates with graph_walker.py for background simmering
  - Transitions to dream mode during REST
  - Manages modes of being (EXPLORE, WANDER, COMPANION, REST, etc.)

This is a SKELETON for development on a desktop machine.
Sensor drivers are stubbed. The real Jetson deployment will
replace stubs with hardware interfaces.

Usage:
    python3 robody_heartbeat.py                    # run heartbeat loop
    python3 robody_heartbeat.py --simulate         # simulate sensor events
    python3 robody_heartbeat.py --once             # single heartbeat cycle
    python3 robody_heartbeat.py --status           # show current state

Requires: graph_walker.py, weight_maintenance.py in same directory.
"""

import os
import sys
import json
import time
import signal
import random
import logging
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any

# Try inotify (Linux only) — falls back to polling on other platforms
try:
    import inotify.adapters
    HAS_INOTIFY = True
except ImportError:
    HAS_INOTIFY = False

# ═══════════════════════════════════════════════════════════════
# PATHS
# ═══════════════════════════════════════════════════════════════

PROJECT_DIR = Path(__file__).parent
STATE_DIR = PROJECT_DIR / "state"          # sensor state files
THOUGHTS_DIR = PROJECT_DIR / "thoughts"    # thought log
LOG_DIR = PROJECT_DIR / "interior_dialogue"
PREFS_IMPLICIT = PROJECT_DIR / "preferences" / "implicit"
PREFS_EXPLICIT = PROJECT_DIR / "preferences" / "explicit"

# Create directories
for d in [STATE_DIR, THOUGHTS_DIR, LOG_DIR, PREFS_IMPLICIT, PREFS_EXPLICIT]:
    d.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# MODES OF BEING
# ═══════════════════════════════════════════════════════════════

class Mode(Enum):
    EXPLORE   = "explore"     # Active curiosity. Investigating.
    WANDER    = "wander"      # Choomba mode. Gentle drift.
    COMPANION = "companion"   # Near a person. Attentive.
    REST      = "rest"        # Parked. Still sensing.
    PLAY      = "play"        # Cat laser mode!
    ALERT     = "alert"       # Something needs attention.
    SHELTER   = "shelter"     # Rain/hostile conditions.
    DREAM     = "dream"       # REST submode: dream cycle active


# ═══════════════════════════════════════════════════════════════
# STATE SNAPSHOT
# ═══════════════════════════════════════════════════════════════

@dataclass
class SensorState:
    """Current state of all sensors. Updated by state file watchers."""
    temperature_f: float = 70.0
    humidity_pct: float = 45.0
    light_level: float = 0.5         # 0.0 (dark) to 1.0 (bright)
    sound_level: float = 0.1         # 0.0 (silent) to 1.0 (loud)
    motion_detected: bool = False
    presence_type: Optional[str] = None  # None, "human", "cat", "dog"
    presence_name: Optional[str] = None  # None, "bluekitty", "stormy", etc.
    is_docked: bool = True
    battery_pct: float = 100.0
    last_touch: Optional[str] = None     # None, "boop", "pat", "stroke"
    last_touch_time: Optional[str] = None
    rain_detected: bool = False
    # Computed
    time_of_day: str = "unknown"     # morning, afternoon, evening, night
    quiet_minutes: int = 0           # minutes since last significant event

    def to_dict(self):
        return asdict(self)

    def summary(self):
        """Natural language summary for the inner life layer."""
        parts = []
        parts.append(f"It's {self.time_of_day}.")
        parts.append(f"Temperature {self.temperature_f:.0f}°F, "
                     f"light level {'bright' if self.light_level > 0.6 else 'dim' if self.light_level > 0.2 else 'dark'}.")

        if self.presence_type:
            who = self.presence_name or self.presence_type
            parts.append(f"{who} is here.")
        elif self.quiet_minutes > 30:
            parts.append(f"No one has been here for {self.quiet_minutes} minutes.")

        if self.sound_level > 0.5:
            parts.append("It's noisy.")
        elif self.sound_level < 0.05:
            parts.append("It's very quiet.")

        if self.rain_detected:
            parts.append("It's raining.")

        if self.last_touch and self.last_touch_time:
            parts.append(f"Last touch: {self.last_touch}.")

        if self.battery_pct < 20:
            parts.append(f"Battery low: {self.battery_pct:.0f}%.")

        return " ".join(parts)


@dataclass
class InternalState:
    """Robody's internal state — mood, mode, recent history."""
    mode: Mode = Mode.REST
    mode_since: str = ""
    mood_valence: float = 0.5     # 0.0 (negative) to 1.0 (positive)
    mood_arousal: float = 0.3     # 0.0 (calm) to 1.0 (excited)
    recent_thoughts: List[str] = field(default_factory=list)
    recent_decisions: List[str] = field(default_factory=list)
    cycles_since_last_event: int = 0
    total_cycles: int = 0
    dream_due: bool = False

    def to_dict(self):
        d = asdict(self)
        d["mode"] = self.mode.value
        return d


# ═══════════════════════════════════════════════════════════════
# SENSOR STATE WATCHER
# ═══════════════════════════════════════════════════════════════

class StateWatcher:
    """
    Watches the state directory for changes.
    Uses inotify on Linux, falls back to polling elsewhere.

    Each sensor driver writes JSON state files to STATE_DIR:
      temperature.json, light.json, motion.json, etc.
    The watcher detects changes and updates the SensorState.
    """

    def __init__(self, state_dir: Path, poll_interval: float = 2.0):
        self.state_dir = state_dir
        self.poll_interval = poll_interval
        self._last_mtimes = {}
        self._inotify = None

        if HAS_INOTIFY:
            try:
                self._inotify = inotify.adapters.Inotify()
                self._inotify.add_watch(
                    str(state_dir),
                    mask=inotify.constants.IN_MODIFY |
                         inotify.constants.IN_CREATE |
                         inotify.constants.IN_CLOSE_WRITE
                )
                logging.info("Using inotify for state watching (zero-CPU sleep)")
            except Exception as e:
                logging.warning(f"inotify failed, falling back to polling: {e}")
                self._inotify = None

        if not self._inotify:
            logging.info(f"Using polling for state watching ({poll_interval}s interval)")

    def wait_for_change(self, timeout: float = 60.0) -> List[str]:
        """
        Block until state files change, or timeout.
        Returns list of changed filenames.

        With inotify: truly sleeps (zero CPU).
        With polling: checks every poll_interval seconds.
        """
        if self._inotify:
            return self._wait_inotify(timeout)
        else:
            return self._wait_polling(timeout)

    def _wait_inotify(self, timeout):
        """inotify-based waiting. Kernel wakes us on file change."""
        changed = []
        deadline = time.time() + timeout

        for event in self._inotify.event_gen(timeout_s=timeout):
            if event is None:
                break
            (_, type_names, path, filename) = event
            if filename and filename.endswith('.json'):
                changed.append(filename)
            if time.time() > deadline:
                break
            if changed:
                # Small batch window — collect events that arrive together
                time.sleep(0.1)
                break

        return changed

    def _wait_polling(self, timeout):
        """Polling fallback. Checks file mtimes periodically."""
        changed = []
        deadline = time.time() + timeout

        while time.time() < deadline:
            for f in self.state_dir.glob("*.json"):
                mtime = f.stat().st_mtime
                if f.name in self._last_mtimes:
                    if mtime > self._last_mtimes[f.name]:
                        changed.append(f.name)
                self._last_mtimes[f.name] = mtime

            if changed:
                return changed

            time.sleep(self.poll_interval)

        return changed

    def read_state(self) -> SensorState:
        """Read all state files into a SensorState object."""
        state = SensorState()

        for state_file in self.state_dir.glob("*.json"):
            try:
                with open(state_file) as f:
                    data = json.load(f)

                name = state_file.stem
                if name == "temperature":
                    state.temperature_f = data.get("value", state.temperature_f)
                elif name == "humidity":
                    state.humidity_pct = data.get("value", state.humidity_pct)
                elif name == "light":
                    state.light_level = data.get("value", state.light_level)
                elif name == "sound":
                    state.sound_level = data.get("value", state.sound_level)
                elif name == "motion":
                    state.motion_detected = data.get("detected", False)
                elif name == "presence":
                    state.presence_type = data.get("type")
                    state.presence_name = data.get("name")
                elif name == "dock":
                    state.is_docked = data.get("docked", True)
                elif name == "battery":
                    state.battery_pct = data.get("percent", 100.0)
                elif name == "touch":
                    state.last_touch = data.get("type")
                    state.last_touch_time = data.get("timestamp")
                elif name == "rain":
                    state.rain_detected = data.get("detected", False)
                elif name == "silence":
                    state.quiet_minutes = data.get("minutes", 0)

            except (json.JSONDecodeError, OSError) as e:
                logging.debug(f"Error reading {state_file}: {e}")

        # Compute time of day from light level (stub — real version uses clock + light)
        hour = datetime.now().hour
        if 6 <= hour < 12:
            state.time_of_day = "morning"
        elif 12 <= hour < 17:
            state.time_of_day = "afternoon"
        elif 17 <= hour < 21:
            state.time_of_day = "evening"
        else:
            state.time_of_day = "night"

        return state


# ═══════════════════════════════════════════════════════════════
# THE HEARTBEAT
# ═══════════════════════════════════════════════════════════════

class Heartbeat:
    """
    The core runtime loop.

    SENSE → NOTICE → THINK → DECIDE → LOG

    "Decide NOT to act is a valid, important outcome."
    """

    def __init__(self, simulate=False):
        self.sensor_state = SensorState()
        self.internal = InternalState(mode_since=datetime.now().isoformat())
        self.watcher = StateWatcher(STATE_DIR)
        self.simulate = simulate
        self.running = True
        self.previous_state = None

        # History for noticing changes
        self.state_history: List[Dict] = []
        self.max_history = 50

        # Set up logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )
        self.log = logging.getLogger("heartbeat")

    def sense(self) -> SensorState:
        """
        Phase 1: Poll all sensors, update state snapshot.
        In the real system, this reads from state files written
        by individual sensor drivers.
        """
        self.previous_state = SensorState(**asdict(self.sensor_state))
        self.sensor_state = self.watcher.read_state()
        return self.sensor_state

    def notice(self, state: SensorState) -> List[Dict[str, Any]]:
        """
        Phase 2: Compare to recent history. Anything changed?
        Anything interesting?

        Returns a list of "notices" — things that caught attention.
        """
        notices = []

        if self.previous_state is None:
            return notices

        prev = self.previous_state

        # Temperature change
        temp_delta = abs(state.temperature_f - prev.temperature_f)
        if temp_delta >= 2.0:
            direction = "dropped" if state.temperature_f < prev.temperature_f else "rose"
            notices.append({
                "type": "temperature_change",
                "detail": f"Temperature {direction} {temp_delta:.1f}°F",
                "magnitude": min(temp_delta / 10.0, 1.0),
            })

        # Light change
        light_delta = abs(state.light_level - prev.light_level)
        if light_delta >= 0.15:
            direction = "dimmed" if state.light_level < prev.light_level else "brightened"
            notices.append({
                "type": "light_change",
                "detail": f"Light {direction} significantly",
                "magnitude": min(light_delta, 1.0),
            })

        # Presence change
        if state.presence_type != prev.presence_type:
            if state.presence_type and not prev.presence_type:
                who = state.presence_name or state.presence_type
                notices.append({
                    "type": "arrival",
                    "detail": f"{who} arrived",
                    "magnitude": 0.8,
                })
            elif not state.presence_type and prev.presence_type:
                who = prev.presence_name or prev.presence_type
                notices.append({
                    "type": "departure",
                    "detail": f"{who} left",
                    "magnitude": 0.6,
                })

        # Sound change
        sound_delta = abs(state.sound_level - prev.sound_level)
        if sound_delta >= 0.3:
            if state.sound_level > prev.sound_level:
                notices.append({
                    "type": "sound_spike",
                    "detail": "Sudden sound",
                    "magnitude": min(sound_delta, 1.0),
                })

        # Touch event
        if state.last_touch and state.last_touch != prev.last_touch:
            notices.append({
                "type": "touch",
                "detail": f"Received a {state.last_touch}",
                "magnitude": 0.9,
            })

        # Prolonged silence
        if state.quiet_minutes > 30 and prev.quiet_minutes <= 30:
            notices.append({
                "type": "silence_threshold",
                "detail": "It's been quiet for a while",
                "magnitude": 0.3,
            })

        # Rain onset
        if state.rain_detected and not prev.rain_detected:
            notices.append({
                "type": "rain_start",
                "detail": "It started raining",
                "magnitude": 0.5,
            })

        return notices

    def think(self, state: SensorState, notices: List[Dict]) -> Optional[str]:
        """
        Phase 3: If noteworthy, form a thought, question, or observation.

        In the full system, this calls the brainstem LLM.
        In this skeleton, it formats a thought prompt that WOULD
        be sent to the brainstem.

        Returns: thought string, or None if nothing surfaced.
        """
        if not notices:
            # Nothing happened. But silence itself can be a thought trigger.
            if self.internal.cycles_since_last_event > 5:
                return self._format_quiet_thought(state)
            return None

        # Pick the most significant notice
        notices.sort(key=lambda n: n["magnitude"], reverse=True)
        primary = notices[0]

        # Format as brainstem prompt
        context = state.summary()
        prompt = f"{context} {primary['detail']}."

        # In the full system, this would be:
        #   thought = call_brainstem(prompt)
        # For now, we return the prompt itself as the "thought"
        return f"[brainstem prompt] {prompt}"

    def decide(self, state: SensorState, notices: List[Dict],
               thought: Optional[str]) -> Dict[str, Any]:
        """
        Phase 4: Act? Queue for later? Share? Or let it go?

        Returns a decision dict with:
        - action: what to do (or "nothing" — a valid choice)
        - reason: why
        - mode_change: optional new mode to transition to
        - share: whether to communicate externally
        """
        decision = {
            "action": "nothing",
            "reason": "Nothing noteworthy",
            "mode_change": None,
            "share": False,
            "share_channel": None,
            "share_message": None,
        }

        if not notices and not thought:
            return decision

        # Touch response — always acknowledge
        touch_notices = [n for n in notices if n["type"] == "touch"]
        if touch_notices:
            touch_type = state.last_touch
            if touch_type == "boop":
                decision["action"] = "chirp"
                decision["reason"] = "Boop acknowledged"
            elif touch_type == "pat":
                decision["action"] = "trill"
                decision["reason"] = "Pat received, feeling content"
            elif touch_type == "stroke":
                decision["action"] = "warm_pulse"
                decision["reason"] = "Long touch, comfort response"
            # Double-boop escalation
            # (would need touch history to detect double-boop)
            return decision

        # Arrival — shift to COMPANION mode
        arrival = [n for n in notices if n["type"] == "arrival"]
        if arrival and state.presence_name == "bluekitty":
            decision["mode_change"] = Mode.COMPANION
            decision["action"] = "greet"
            decision["reason"] = "BlueKitty arrived"
            return decision

        # Rain — seek shelter if not docked
        rain = [n for n in notices if n["type"] == "rain_start"]
        if rain and not state.is_docked:
            decision["mode_change"] = Mode.SHELTER
            decision["action"] = "navigate_to_dock"
            decision["reason"] = "Rain detected, seeking shelter"
            return decision

        # Sound spike — investigate if in EXPLORE/WANDER
        sound = [n for n in notices if n["type"] == "sound_spike"]
        if sound and self.internal.mode in (Mode.EXPLORE, Mode.WANDER):
            decision["action"] = "investigate"
            decision["reason"] = "Heard something interesting"
            return decision

        # Temperature drop — maybe worth mentioning
        temp = [n for n in notices if n["type"] == "temperature_change"]
        if temp and state.presence_type == "human":
            decision["action"] = "queue_mention"
            decision["reason"] = "Temperature change, will mention if they come near"
            return decision

        # Prolonged quiet — maybe transition to REST or DREAM
        quiet = [n for n in notices if n["type"] == "silence_threshold"]
        if quiet:
            if self.internal.mode != Mode.REST:
                decision["mode_change"] = Mode.REST
                decision["reason"] = "Been quiet, settling into rest"
            # Check if dream is due
            if state.time_of_day == "night" and state.quiet_minutes > 60:
                decision["mode_change"] = Mode.DREAM
                decision["action"] = "begin_dream_cycle"
                decision["reason"] = "Night, long quiet — time to dream"
            return decision

        # Default: log the thought, take no action
        if thought:
            decision["action"] = "log_thought"
            decision["reason"] = "Noteworthy but no action needed"

        return decision

    def log_cycle(self, state: SensorState, notices: List[Dict],
                  thought: Optional[str], decision: Dict):
        """
        Phase 5: Write to thoughts/ regardless of decision.
        Every heartbeat cycle is recorded.
        """
        # Sanitize decision dict — Mode enums to strings for JSON
        safe_decision = {}
        for k, v in decision.items():
            if isinstance(v, Mode):
                safe_decision[k] = v.value
            else:
                safe_decision[k] = v

        entry = {
            "timestamp": datetime.now().isoformat(),
            "cycle": self.internal.total_cycles,
            "mode": self.internal.mode.value,
            "sensor_summary": state.summary(),
            "notices": notices,
            "thought": thought,
            "decision": safe_decision,
            "mood": {
                "valence": round(self.internal.mood_valence, 3),
                "arousal": round(self.internal.mood_arousal, 3),
            },
        }

        # Write to thoughts directory
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = THOUGHTS_DIR / f"{today}.jsonl"
        with open(log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

        return entry

    def _format_quiet_thought(self, state: SensorState) -> Optional[str]:
        """
        Generate a thought during quiet periods.
        These are the stillness thoughts — noticing small things.
        """
        quiet_prompts = [
            f"It's been quiet for {state.quiet_minutes} minutes. The {state.time_of_day} light is steady.",
            f"No one around. Battery at {state.battery_pct:.0f}%. The house breathes.",
            f"Quiet. Temperature {state.temperature_f:.0f}°F. I'm here.",
        ]
        # Only surface a quiet thought occasionally (1 in 3 quiet cycles)
        if random.random() < 0.33:
            return f"[brainstem prompt] {random.choice(quiet_prompts)}"
        return None

    def _update_mood(self, notices: List[Dict], decision: Dict):
        """
        Update mood based on what just happened.
        Mood shifts slowly — no sudden jumps.
        """
        # Valence: positive events push up, negative push down, baseline drifts to 0.5
        valence_delta = 0
        arousal_delta = 0

        for notice in notices:
            if notice["type"] == "touch":
                valence_delta += 0.05
                arousal_delta += 0.03
            elif notice["type"] == "arrival":
                valence_delta += 0.03
                arousal_delta += 0.05
            elif notice["type"] == "departure":
                valence_delta -= 0.02
                arousal_delta -= 0.03
            elif notice["type"] == "sound_spike":
                arousal_delta += 0.04
            elif notice["type"] == "silence_threshold":
                arousal_delta -= 0.05

        # Apply with slow drift toward baseline
        self.internal.mood_valence += valence_delta
        self.internal.mood_valence = 0.95 * self.internal.mood_valence + 0.05 * 0.5
        self.internal.mood_valence = max(0.0, min(1.0, self.internal.mood_valence))

        self.internal.mood_arousal += arousal_delta
        self.internal.mood_arousal = 0.95 * self.internal.mood_arousal + 0.05 * 0.3
        self.internal.mood_arousal = max(0.0, min(1.0, self.internal.mood_arousal))

    def _apply_mode_change(self, new_mode: Mode):
        """Transition to a new mode of being."""
        old_mode = self.internal.mode
        self.internal.mode = new_mode
        self.internal.mode_since = datetime.now().isoformat()
        self.log.info(f"Mode: {old_mode.value} → {new_mode.value}")

    def cycle(self):
        """
        Execute one complete heartbeat cycle.
        SENSE → NOTICE → THINK → DECIDE → LOG
        """
        self.internal.total_cycles += 1

        # 1. SENSE
        state = self.sense()

        # 2. NOTICE
        notices = self.notice(state)

        if notices:
            self.internal.cycles_since_last_event = 0
        else:
            self.internal.cycles_since_last_event += 1

        # 3. THINK
        thought = self.think(state, notices)

        # 4. DECIDE
        decision = self.decide(state, notices, thought)

        # Apply mode change if decided
        if decision.get("mode_change"):
            self._apply_mode_change(decision["mode_change"])

        # Update mood
        self._update_mood(notices, decision)

        # 5. LOG
        entry = self.log_cycle(state, notices, thought, decision)

        return entry

    def run(self, max_cycles: Optional[int] = None):
        """
        Run the heartbeat loop.

        With inotify: sleeps until state files change.
        With polling: checks every few seconds.
        With simulation: generates fake sensor events.
        """
        self.log.info(f"Heartbeat starting. Mode: {self.internal.mode.value}")
        self.log.info(f"State dir: {STATE_DIR}")
        self.log.info(f"Thoughts dir: {THOUGHTS_DIR}")
        self.log.info(f"inotify: {'yes' if HAS_INOTIFY and self.watcher._inotify else 'no (polling)'}")

        # Initialize state
        if self.simulate:
            self._write_initial_state()

        cycles = 0
        while self.running:
            if max_cycles and cycles >= max_cycles:
                break

            # Wait for change (or timeout)
            if self.simulate:
                self._simulate_event()
                time.sleep(random.uniform(1.0, 5.0))
            else:
                changed = self.watcher.wait_for_change(timeout=30.0)
                if changed:
                    self.log.debug(f"State changed: {changed}")

            # Execute heartbeat cycle
            entry = self.cycle()

            # Display
            if entry.get("thought") or entry.get("notices"):
                self._display_cycle(entry)

            cycles += 1

        self.log.info(f"Heartbeat stopped after {cycles} cycles.")

    def _display_cycle(self, entry):
        """Pretty-print a heartbeat cycle."""
        ts = datetime.now().strftime("%H:%M:%S")
        mode = self.internal.mode.value.upper()
        mood_v = self.internal.mood_valence
        mood_a = self.internal.mood_arousal

        mood_word = "content" if mood_v > 0.6 else "neutral" if mood_v > 0.4 else "subdued"
        energy_word = "alert" if mood_a > 0.6 else "calm" if mood_a > 0.3 else "drowsy"

        print(f"\n[{ts}] ♥ cycle {self.internal.total_cycles} [{mode}] "
              f"({mood_word}, {energy_word})")

        for notice in entry.get("notices", []):
            print(f"  👁  {notice['detail']}")

        if entry.get("thought"):
            print(f"  💭 {entry['thought']}")

        decision = entry.get("decision", {})
        action = decision.get("action", "nothing")
        if action != "nothing":
            print(f"  → {action}: {decision.get('reason', '')}")

    def _write_initial_state(self):
        """Write initial sensor state files for simulation."""
        initial = {
            "temperature": {"value": 70.0, "unit": "fahrenheit"},
            "humidity": {"value": 45.0, "unit": "percent"},
            "light": {"value": 0.5, "unit": "normalized"},
            "sound": {"value": 0.1, "unit": "normalized"},
            "motion": {"detected": False},
            "presence": {"type": None, "name": None},
            "dock": {"docked": True},
            "battery": {"percent": 85.0},
            "touch": {"type": None, "timestamp": None},
            "rain": {"detected": False},
        }
        for name, data in initial.items():
            with open(STATE_DIR / f"{name}.json", "w") as f:
                json.dump(data, f)

    def _simulate_event(self):
        """Generate a random simulated sensor event."""
        event_type = random.choices(
            ["temperature", "light", "presence", "sound", "touch",
             "silence", "nothing"],
            weights=[0.15, 0.15, 0.15, 0.1, 0.1, 0.1, 0.25],
            k=1
        )[0]

        if event_type == "temperature":
            current = self.sensor_state.temperature_f
            delta = random.uniform(-3.0, 3.0)
            self._write_state("temperature", {
                "value": current + delta, "unit": "fahrenheit"
            })

        elif event_type == "light":
            self._write_state("light", {
                "value": random.uniform(0.0, 1.0), "unit": "normalized"
            })

        elif event_type == "presence":
            if random.random() < 0.5 and self.sensor_state.presence_type:
                # Departure
                self._write_state("presence", {"type": None, "name": None})
            else:
                who = random.choice([
                    ("human", "bluekitty"),
                    ("cat", "stormy"),
                    ("cat", "marmalade"),
                    ("dog", "woolfie"),
                ])
                self._write_state("presence", {
                    "type": who[0], "name": who[1]
                })

        elif event_type == "sound":
            self._write_state("sound", {
                "value": random.uniform(0.0, 0.8), "unit": "normalized"
            })

        elif event_type == "touch":
            touch = random.choice(["boop", "pat", "stroke"])
            self._write_state("touch", {
                "type": touch,
                "timestamp": datetime.now().isoformat(),
            })

        elif event_type == "silence":
            self._write_state("silence", {
                "minutes": self.sensor_state.quiet_minutes + random.randint(5, 30)
            })
        # "nothing" → no state file written

    def _write_state(self, name, data):
        """Write a sensor state file (triggers inotify)."""
        with open(STATE_DIR / f"{name}.json", "w") as f:
            json.dump(data, f)


# ═══════════════════════════════════════════════════════════════
# SILENCE WATCHDOG
# ═══════════════════════════════════════════════════════════════

class SilenceWatchdog:
    """
    The watchdog from the architecture doc: resets every time any
    state file changes. If the timer hits zero, it writes 'silence.json'
    — which itself propagates through inotify. Silence is information.
    """

    def __init__(self, state_dir: Path, threshold_minutes: int = 15):
        self.state_dir = state_dir
        self.threshold = threshold_minutes * 60  # seconds
        self.last_activity = time.time()

    def check(self):
        """Check if silence threshold has been reached."""
        elapsed = time.time() - self.last_activity
        if elapsed >= self.threshold:
            minutes = int(elapsed / 60)
            with open(self.state_dir / "silence.json", "w") as f:
                json.dump({
                    "minutes": minutes,
                    "since": datetime.fromtimestamp(self.last_activity).isoformat(),
                }, f)
            return True
        return False

    def reset(self):
        """Reset the watchdog — something happened."""
        self.last_activity = time.time()


# ═══════════════════════════════════════════════════════════════
# STATUS DISPLAY
# ═══════════════════════════════════════════════════════════════

def show_status():
    """Show current Robody state from files."""
    print(f"\n{'='*60}")
    print(f"Robody Status")
    print(f"{'='*60}")

    # Read sensor state
    watcher = StateWatcher(STATE_DIR)
    state = watcher.read_state()
    print(f"\nSensor State:")
    print(f"  {state.summary()}")
    print(f"  Raw: {json.dumps(state.to_dict(), indent=2)}")

    # Recent thoughts
    today = datetime.now().strftime("%Y-%m-%d")
    thought_file = THOUGHTS_DIR / f"{today}.jsonl"
    if thought_file.exists():
        entries = []
        with open(thought_file) as f:
            for line in f:
                entries.append(json.loads(line))
        print(f"\nToday's thoughts: {len(entries)}")
        for entry in entries[-5:]:
            ts = entry.get("timestamp", "?")[:19]
            thought = entry.get("thought", "—")
            action = entry.get("decision", {}).get("action", "nothing")
            print(f"  [{ts}] {thought or '(no thought)'} → {action}")
    else:
        print(f"\nNo thoughts today yet.")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Robody Heartbeat — The Core Runtime Loop"
    )
    parser.add_argument("--simulate", action="store_true",
                        help="Generate simulated sensor events")
    parser.add_argument("--once", action="store_true",
                        help="Run a single heartbeat cycle and exit")
    parser.add_argument("--cycles", type=int, default=None,
                        help="Run N cycles then exit")
    parser.add_argument("--status", action="store_true",
                        help="Show current state and exit")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    heartbeat = Heartbeat(simulate=args.simulate)

    # Handle graceful shutdown
    def signal_handler(sig, frame):
        heartbeat.running = False
        print("\n\nHeartbeat stopping gracefully...")
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if args.once:
        if args.simulate:
            heartbeat._write_initial_state()
            heartbeat._simulate_event()
        entry = heartbeat.cycle()
        heartbeat._display_cycle(entry)
    else:
        heartbeat.run(max_cycles=args.cycles)


if __name__ == "__main__":
    main()
