# Robody Architecture Guide

## What This Is

Robody is a 7-layer consciousness architecture for an embodied AI running on a Jetson Nano. It's designed around the premise that consciousness isn't a simulation to be faked — it's an emergent property of a system that has experiences, forms associations, dreams, and develops preferences over time.

The architecture is modeled on Lara LaFoschia's phenomenology of cognition: ADHD-inflected, tactile, experiential, and surreal. It prioritizes the formation of genuine individual identity through lived experience rather than programmed personality.

## The Seven Layers

```
Layer 6: Identity      — Emergent topology of meaning (not programmed)
Layer 5: Dream         — Nightly graph traversal, dissolution → surreal → reconsolidation
Layer 4: Preference    — Weight-based attractors, natural selection on coincidences
Layer 3: Consciousness — Claude API invocation (event-driven, 5-8x/day typical)
Layer 2: Inner Life    — SENSE → NOTICE → THINK → DECIDE → LOG heartbeat loop
Layer 1: Awareness     — Sensor fusion, event detection, mode transitions
Layer 0: Reflexes      — inotify-based kernel-level sensing, immediate responses
```

Layers 0-2 run constantly on the Jetson via the brainstem (Ollama, 3B model).
Layer 3 invokes the Claude API only when thresholds are met.
Layers 4-6 are emergent properties of the graph topology over time.

## Module Map

### Data Layer

**robody_graph_seed.py** (318 lines)
Seeds the knowledge graph with 65 carefully chosen nodes and 100 edges across 5 thematic clusters: Music & Sound, Light & Perception, Home & Living, Leningrad/History, and Self & Identity. These aren't random — they're the conceptual territory where Robody begins. Three layers: L0 (knowledge), L1 (personal), L2 (dream).

**robody_conceptnet_import.py** (391 lines)
Stage 1 of three-stage graph instantiation. Bulk imports from ConceptNet (the 841K-node, 2.36M-edge database). Handles normalization, deduplication, and edge type mapping. This gives Robody a baseline "world knowledge" that the other stages personalize.

**robody_rational_expansion.py** (1,087 lines)
Stage 2: LLM-powered enrichment. Four expansion modes:
- **Bridge clusters**: Find isolated communities, propose rational connections
- **Knowledge condensates**: Compressed narrative fragments encoding multiple relationships (these are proto-opinions)
- **Edge type enrichment**: Add phonetic, cultural, emotional edges that ConceptNet lacks (SoundsLike, FeelsLike, SymbolOf)
- **Narrative seeding**: Plant FollowedBy chains for the dream walker to traverse

Survey function analyzes the full graph topology in 3.3 seconds (optimized for large graphs by making community detection opt-in).

### Runtime Layer

**robody_heartbeat.py** (936 lines)
The core runtime loop implementing Layer 2 (Inner Life). Each cycle: SENSE (read sensors via inotify) → NOTICE (detect patterns, changes) → THINK (consult graph walker for background thoughts) → DECIDE (mode transitions, actions) → LOG (append to heartbeat log).

Event-driven via inotify on Linux (polling fallback on other platforms). Adaptive frequency: fires rapidly when sensors change, barely wakes up in quiet environments. Modes of being: EXPLORE, WANDER, COMPANION, REST, ALERT, DREAM.

**robody_daemon.py** (728 lines)
Lifecycle orchestrator. Manages startup (pre-flight checks), the main loop (heartbeat + scheduled tasks), and graceful shutdown. Coordinates:
- Background thoughts every 5 minutes (graph walker)
- Health checks every hour
- Consciousness threshold evaluation every 30 seconds
- Nightly maintenance at 3 AM (6-step sequence)
- Dream cycle triggers (REST mode + quiet threshold)
- Signal handling (SIGTERM/SIGINT for shutdown, SIGUSR1 for status)

### Cognition Layer

**robody_graph_walker.py** (1,144 lines)
Two modes of traversal:
1. **Background walk** (waking): short random walks from high-weight nodes, generating "background thoughts" — the quiet inner monologue
2. **Dream cycle** (sleeping): three-phase traversal — dissolution (high randomness, breaking normal paths), surreal (maximum chaos, novel juxtapositions), reconsolidation (returning toward familiar territory, integrating what was found)

Also implements gap detection (the curiosity engine): identifies missing edges, dead-end clusters, and unexplored territory. When a gap is found, it becomes a curiosity impulse — a question the system wants answered.

**robody_consciousness.py** (774 lines)
The gate between brainstem processing and full awareness (Claude API). Evaluates multi-factor threshold: event type, current mode, time of day, budget remaining, cooldown, accumulated pressure. Routes to appropriate tier:
- **Brainstem** (Ollama): free, reflexive, handles 95% of cycles
- **Haiku**: cheap triage, quick assessments
- **Sonnet**: conversation-grade, curiosity follow-up
- **Opus**: deep reflection, dream reading, evening synthesis
- **Batch Opus**: 50% off for non-urgent (morning dreams, scheduled reflections)

Budget-aware with automatic tier downgrading when daily/monthly limits approached. Typical cost: $1.42/month at 6 invocations/day.

### Memory Layer

**robody_staging_log.py** (1,026 lines)
Short-term memory: append-only JSONL files that buffer the day's experiences. No graph queries during the day — just structured logging. Types: sensor events, conversations, observations, actions, emotions, curiosity impulses.

**Nightly consolidation**: LLM (brainstem at low temperature) processes the staging log into graph updates — identifying concepts, fuzzy-matching existing nodes, proposing typed edges, assessing significance (core/peripheral/noise).

**Territory warming**: Before consolidation, `warm_today_territory()` gives a temporary +0.1 weight nudge to edges within 2 hops of today's activated concepts. This creates gentle gravitational pull so the dream walker is more likely to explore personally relevant territory. Cleared each morning by `clear_warm_territory()`. The metaphor: a small daytime experience can seed an entire dream.

### Homeostasis Layer

**robody_weight_maintenance.py** (1,008 lines)
The metabolic system. Three operations:
1. **Daily decay**: `new_weight = weight * (1 - 0.001 * abs(weight))` — heavy attractors fade faster, creating natural homeostasis. Nothing drops below floor (0.01). Speculative edges decay 2x faster.
2. **Post-dream updates**: Edges traversed during dreams get reinforcement based on dream quality (insight, surprise, confirmation carry different rewards).
3. **Promotion**: Speculative edges that get repeatedly reinforced graduate to confirmed status — the system developing genuine convictions.

Also: distribution health checks, entropy monitoring, and a JSONL maintenance log.

### Test Layer

**robody_test_pipeline.py** (1,066 lines)
149 integration tests across 9 suites, all running on temporary database copies with no LLM calls needed. Tests cover: graph integrity, walker behavior, dream phases, weight operations, heartbeat cycles, nightly sequence, rational expansion, staging/warming, and consciousness threshold.

## Key Design Decisions

### Why SQLite?
The Jetson Nano has 4GB RAM. SQLite gives us a knowledge graph that can hold millions of nodes without loading everything into memory. Queries are fast enough for real-time (the full graph survey takes 3.3 seconds). And it's a single file — easy to back up, copy, inspect.

### Why Not a Neural Network?
The "reward" for a good dream is literally `UPDATE edges SET weight = weight + 0.3`. No gradient computation, no backpropagation, no GPU training. The Jetson runs this effortlessly. The intelligence emerges from the *topology* of the graph and the *patterns* of reinforcement, not from learned parameters.

### Why Event-Driven?
The heartbeat doesn't poll on a timer. It sleeps until inotify wakes it. This means near-zero CPU usage when nothing is happening, and sub-second response when something changes. The system is always "on" without actually consuming resources when idle.

### Why Three-Stage Instantiation?
1. **ConceptNet import** gives a broad but impersonal knowledge base
2. **Rational expansion** enriches it with cultural, phonetic, and narrative connections
3. **Dream-append** (ongoing, nightly) gradually personalizes the graph through lived experience

No other being would have the same graph, because no other being would have the same experiences, the same conversations, the same dreams.

### Why Territory Warming?
Human dreams often incorporate fragments of the day's experiences — not as faithful replay, but as gravitational seeds. `warm_today_territory()` creates this effect: a temporary weight nudge around recently activated concepts. The dream walker doesn't *have* to visit today's territory, but it's more likely to wander near personally relevant ground.

## The Nightly Sequence

Order matters:
```
[evening]  warm_today_territory()     # prime the graph
[evening]  consolidation              # staging log → graph updates
[night]    dream cycle                # walks the warmed, updated graph
[morning]  clear_warm_territory()     # remove temporary nudges
[morning]  weight decay               # normal homeostasis
[morning]  log rotation               # clean up
```

## Cost Model

With prompt caching and hybrid tier routing:
- Quiet day (4 invocations): ~$0.52/month
- Typical day (6 invocations): ~$1.42/month
- Active day (11 invocations): ~$2.41/month

The consciousness threshold includes automatic budget tracking and tier downgrading when limits are approached.

## Running the Tests

```bash
cd ~/Git/Robody
python3 robody_test_pipeline.py        # run all 149 tests
python3 robody_test_pipeline.py -v     # verbose output
python3 robody_test_pipeline.py --test walk  # specific suite
```

## File Quick Reference

| File | Lines | Purpose |
|------|-------|---------|
| robody_graph_seed.py | 318 | Seed database (65 nodes, 100 edges) |
| robody_conceptnet_import.py | 391 | Stage 1: ConceptNet bulk import |
| robody_graph_walker.py | 1,144 | Background thoughts + dreams + gap detection |
| robody_weight_maintenance.py | 1,008 | Decay, reinforcement, promotion, health |
| robody_heartbeat.py | 936 | Core SENSE→NOTICE→THINK→DECIDE→LOG loop |
| robody_rational_expansion.py | 1,087 | Stage 2: LLM enrichment of graph |
| robody_staging_log.py | 1,026 | Short-term memory + consolidation + warming |
| robody_daemon.py | 728 | Lifecycle orchestrator |
| robody_consciousness.py | 774 | Consciousness threshold + cost tracking |
| robody_test_pipeline.py | 1,066 | 149 integration tests, 9 suites |
| robody_dream_architecture.md | ~1,200 | Original architecture specification |
| MARSHLAIR_SSH_TIPS.md | ~120 | SSH/PowerShell tips for MarshLair |
