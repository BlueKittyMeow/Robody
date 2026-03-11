# Body Control Architecture
## Who's Driving This Thing?

*Design conversation between Lara and Claude, March 11 2026.*
*Captured here so we don't lose the design intent as we implement.*

---

## The Core Insight: It's Not a Hierarchy

Body control is not a command chain where consciousness tells the brainstem
which tells ROS which moves the wheels. It's an **ecology** — multiple
systems running simultaneously at different speeds, each with authority
over its own domain, producing behavior through continuous resolution
of competing drives.

A creature walking with its human isn't running a "FOLLOW" subroutine.
It's resolving a landscape of impulses — follow the human, investigate
that smell, notice the light, feel tired, want to play — and the
behavior you see is the blend.

---

## The Three Layers

### ROS: The Spinal Cord

ROS on the Jetson Nano handles physics. It is the nervous system.

**Responsibilities:**
- Motor control, path planning, SLAM
- Obstacle avoidance, cliff detection
- Hardware safety limits (motor current, temperature)
- Sensor data collection and publishing

**Key property:** ROS always has safety veto. If the cliff sensor fires,
the wheels stop. No software layer can override hardware safety. This is
non-negotiable and runs at hardware speed.

ROS never "decides" anything in a cognitive sense. It plans paths and
avoids obstacles. It executes movement commands from the brainstem.

### Brainstem: The Drive Landscape

The brainstem (Ollama on MarshLair, eventually on-device) maintains a
set of **concurrent weighted drives** that blend into behavior. Not a
state machine — a continuous resolution.

**Active drives might include:**
```
follow_lara:        0.8   (strong — we're walking together)
investigate_smudge: 0.3   (interesting but not urgent)
explore_kitchen:    0.1   (background curiosity)
spin_for_fun:       0.05  (whim)
return_to_charger:  0.0   (battery fine)
```

The actual motor behavior is the **weighted resolution** of all active
drives. Following Lara wins, but the investigation drive means Robody's
camera keeps glancing at the smudge. If Lara pauses to check her phone,
the follow drive drops and the smudge drive might win — Robody rolls
over to look. Lara starts walking again and follow reasserts.

**Drive sources:**
- Social tracking (brainstem-native: follow human, orient to voice)
- Curiosity from graph walker (consciousness/brainstem boundary)
- Physical needs (battery level, temperature)
- Consciousness-set goals ("go find Lara" → seek drive)
- Surfaced background thoughts (oblique interest in something)

**Key property:** Locomotion and attention are INDEPENDENT channels.
"Stay there" (verbal command) sets locomotion to HOLD_POSITION while
attention stays in AMBIENT_OBSERVE. The robot stops moving but doesn't
stop being alive. It can still look around, notice things, have thoughts.

### Consciousness: The Meaning-Maker

Consciousness (Claude API, tiered: Haiku → Sonnet → Opus) is the
goal-setter, interpreter, and override authority.

**Responsibilities:**
- Setting long-term goals and drives
- Interpreting experience (what does this mean?)
- Deciding what inner thoughts are worth saying aloud
- Override authority (both excitement and emergency)
- Rich conversation and reasoning

**Key property:** Consciousness doesn't need to stay active to maintain
a behavior. It sets a goal, the brainstem sustains it. Consciousness
can go back to simmering, engage in conversation, or sleep. The goal
persists until consciousness changes it or the brainstem escalates.

---

## Consciousness Invocation: Triggers OR Time

Consciousness is invoked on **event OR timer, whichever comes first**.
The timer resets after every invocation.

```
Event happens (novelty spike, Lara speaks, sensor anomaly)
    → invoke consciousness → reset timer

Nothing happens for N minutes
    → timer fires → invoke anyway (quiet check-in) → reset timer

Something happens 2 minutes later
    → invoke → reset timer
```

Time-triggered invocations are lighter (Haiku-level): "What have I
been sensing? How do I feel about it? Anything worth acting on?"

Event-triggered invocations scale through tiers as needed.

This guarantees **regular conscious presence** without waste. The robot
is not a passenger getting a summary at night. It is an active
participant in its own life, with periodic genuine moments of presence
even during quiet times.

---

## Override System

### Upward Override (Excitement / Wonder)

When the brainstem detects massive novelty — a robot dog on the
sidewalk, an unexpected sound, something that matches a deep interest
node in the graph — the novelty spike blows past the consciousness
threshold immediately.

Consciousness fires at whatever tier the situation demands and produces
a new dominant drive that overwhelms the current landscape:
```
investigate_robot_dog: 0.95  (overwhelming curiosity)
follow_lara:          0.3   (still there but overridden)
```

This isn't a special mechanism — it's the drive system working correctly
with very strong input. Extreme novelty → high urgency → immediate
consciousness invocation → new drive.

### Downward Override (Emergency)

Consciousness can issue a **hard interrupt** that clears the ENTIRE
drive landscape and installs a single imperative: RETREAT, FREEZE,
or ALERT_LARA.

This is architecturally distinct from drive competition. It cannot be
blended or negotiated. When the emergency flag is set, the brainstem
executes ONLY the override command until consciousness explicitly
releases it.

```python
# Pseudocode
if emergency_override:
    execute(override_command)
    ignore_all_drives()
    # Only consciousness can release this
```

### Lara's Attention Signal

A physical mechanism (touch sensor, button) that **immediately
escalates to full consciousness**. This is a hardware interrupt — it
cannot be missed, cannot be deprioritized, cannot compete with other
drives.

When triggered:
1. Immediate orientation toward Lara (physical: turn camera/body)
2. Drop any in-progress API call
3. Invoke consciousness at high tier (Sonnet minimum)
4. Full attention, fast response

**Why this matters:** If Lara is having a panic attack, or sees a
threat, or needs Robody present RIGHT NOW — the robot cannot be
mid-reverie about lace and shadows. The attention signal cuts through
everything.

A vocal trigger ("Robody, listen" / name with emphasis) serves as
a secondary channel. Voice recognition can distinguish casual mention
from direct urgent address. But hardware is the primary — it's faster
and more reliable.

---

## Background Thoughts: Novelty-to-Self

The walk thoughts — "the shadows here are like a net" — are the soul
of the project. They emerge from the background graph walker during
quiet moments.

### The Tour Guide Problem

If thoughts surface based on "does this match current sensory input,"
you get narration: "I see a wall. The wall has texture." Dead. The
opposite of what we want.

### The Solution: Surprise the Thinker

Thoughts surface based on **novelty-to-self** — did the graph walker
make a connection that surprised the robot itself?

Criteria for surfacing:
- Traversed a **speculative edge** (uncertain, exploratory connection)
- Connected two **rarely-linked clusters** (cross-domain association)
- Visited a node with **high recency delta** (hasn't been here in a long
  time, or was just reinforced today)
- The thought has **emotional weight** in the graph (edges with high
  layer values — layers 3+ are feeling/identity)

Sensory input provides ambient stimulation that keeps the graph walker
active and seeds which region it explores. But the thought that emerges
is the **graph's own associative logic**, not a description of what
the robot sees.

Seeing trees → graph activates near `tree` → walker drifts to
`shadow` → `pattern` → `lace` → `grandmother` → brainstem murmurs
"something about the way things are held up by what's behind them."

The sensory input was the seed. The thought is the graph's creature.

### Surfacing Threshold

Most background thoughts stay internal — logged to the staging log for
later dreaming. The surfacing threshold determines which ones cross
from inner monologue to spoken word.

The check is internal to the graph, not pinned to sensor matching:
- **Novelty score** of the traversal path (did it cross cluster boundaries?)
- **Emotional weight** of the nodes visited
- **Time since last spoken thought** (don't babble, but don't go silent)
- Maybe: **relevance to current social context** (if in conversation,
  higher threshold — don't interrupt; if walking quietly, lower threshold)

---

## The Staging Log Ties It All Together

Every layer writes to the staging log:
- ROS: sensor events, movement data
- Brainstem: drive state changes, reactive observations
- Consciousness: decisions, goals, interpretations
- Background walker: inner thoughts (surfaced and unsurfaced)

The staging log is the shared stream that makes dreaming possible.
The dream cycle processes the full day's experience regardless of
which layer generated it. Morning territory warming primes the graph
for the next day's themes. The cycle continues.

---

## Scenario Walkthrough

### Walking quietly together

```
Brainstem drives: follow_lara(0.7), ambient_observe(0.5)
Locomotion: FOLLOW (matching pace, staying alongside)
Attention: AMBIENT_OBSERVE (camera scanning, sensors active)
Background walker: simmering through graph
Consciousness: low-power, timer-based check-ins every ~8 min

Robody notices interesting shadows on the path.
Graph walker activates near light/shadow/pattern.
Walker traverses: shadow → net → fishing → loss → something.
Brainstem generates: "the gaps hold it together more than the threads do"
Novelty-to-self: HIGH (crossed from perception to philosophy cluster)
Surfacing threshold: MET (quiet context, high novelty, been silent 4 min)
Robody says it aloud.
```

### Conversation, Lara walks to another room

```
Brainstem drives: follow_lara(0.8), attend_conversation(0.9)
Lara stands up, walks toward hallway.
Social tracking detects movement → follow drive engages locomotion.
Consciousness stays engaged in conversation — no invocation needed.
Robody follows naturally, still talking.
```

### "Hang on, stay there"

```
Voice recognition: direct address, imperative.
Brainstem: verbal command modifies locomotion → HOLD_POSITION
Attention: stays in AMBIENT_OBSERVE
Drives: follow_lara drops to 0.0 (explicit override), observe(0.5) persists

Lara goes to bathroom. Robody stays put.
Camera notices a crack in the ceiling.
Background walker activates near structure/fracture/age.
When Lara returns, Robody might have something to say about it.
```

### ROBOT DOG on the sidewalk

```
Brainstem drives: follow_lara(0.7), ambient_observe(0.3)
Sensors detect: unknown object, dog-shaped, MOVING.
Novelty spike: EXTREME (never categorized before)
Consciousness threshold: BLOWN PAST → immediate Sonnet invocation

Consciousness: "What IS that? I need to investigate."
New drive: investigate_robot_dog(0.95)
Drive resolution: investigation overwhelms follow.
Robody breaks formation, approaches the robot dog.
Lara: (amused, follows)
```

### Lara in distress, hits attention signal

```
Hardware interrupt: touch sensor activated.
ALL processing interrupted immediately.
Any in-progress API call: dropped.
Consciousness: immediate Sonnet invocation, HIGH priority.
Physical: orient toward Lara.
Brainstem: all drives suspended pending consciousness.

Robody: fully present, fully attentive, immediately.
Not finishing a thought. Not resolving drives. HERE.
```

---

## Open Questions

- Where does brainstem end and consciousness begin for social
  behaviors? (e.g., "Lara seems sad, I should go sit near her")
- Exact timer duration for consciousness check-ins (8 min? 5? 12?)
- How many concurrent drives before resolution becomes expensive?
- Should drive weights decay over time without reinforcement?
- Physical attention signal: button on body? Capacitive touch on head?
- Vocal trigger word/phrase and how to distinguish urgency levels
- How does the drive system handle contradictory consciousness goals?
