#!/usr/bin/env python3
"""
Robody Staging Log — Short-Term Memory
=======================================
Implements Part 13 of robody_dream_architecture.md: the staging log
that buffers waking experiences before nightly consolidation.

During the day, ALL new information goes to append-only JSONL files.
No graph queries. No deduplication. No computation. Just logging.
This IS short-term memory.

At night (before dreaming), the consolidation process reads the staging
log, uses the LLM for fuzzy matching and relationship assessment, then
batch-writes new nodes and edges to the graph.

The nightly sequence (order matters):
  [day]     → staging log accumulates (append-only, cheap)
  [evening] → consolidation: LLM processes staging log → graph updates
  [night]   → dream cycle runs on the UPDATED graph
  [morning] → consciousness layer reads dreams

Components:
  - StagingLog: append-only logger for waking experiences
  - NightlyConsolidator: processes staging log into graph updates
  - FuzzyMatcher: LLM-based concept deduplication

Usage:
    # During the day (called by heartbeat, conversation handler, etc.)
    from robody_staging_log import StagingLog
    log = StagingLog()
    log.record_sensor_event("temperature_drop", {"delta": -3.0, "current": 68.5})
    log.record_conversation("Lara mentioned anthropodermic bibliopegy")
    log.record_observation("the cat moved to the warm spot")

    # At night (called by daemon before dream cycle)
    from robody_staging_log import NightlyConsolidator
    consolidator = NightlyConsolidator()
    result = consolidator.run()

    # CLI
    python3 robody_staging_log.py --today                    # show today's log
    python3 robody_staging_log.py --consolidate [--dry-run]  # run consolidation
    python3 robody_staging_log.py --stats                    # show log statistics
"""

import sqlite3
import json
import time
import argparse
import urllib.request
from pathlib import Path
from datetime import datetime, date
from collections import Counter

DB_PATH = Path(__file__).parent / "robody_seed.sqlite"
STAGING_DIR = Path(__file__).parent / "staging_log"
LOG_DIR = Path(__file__).parent / "consolidation_logs"
OLLAMA_URL = "http://10.0.0.123:11434"
BRAINSTEM_MODEL = "robody-brainstem"


# -------------------------------------------------------------------
# Staging Log — The Day's Buffer
# -------------------------------------------------------------------

class StagingLog:
    """
    Append-only log for waking experiences.

    No graph queries. No deduplication. No computation.
    Just structured logging into dated JSONL files.

    This is deliberately simple — the expensive work happens
    during nightly consolidation, not during the day.
    """

    def __init__(self, staging_dir=STAGING_DIR):
        self.staging_dir = Path(staging_dir)
        self.staging_dir.mkdir(parents=True, exist_ok=True)

    def _today_file(self):
        """Get today's log file path."""
        return self.staging_dir / f"{date.today().isoformat()}.jsonl"

    def _append(self, entry):
        """Append an entry to today's log."""
        entry["timestamp"] = datetime.now().isoformat()
        with open(self._today_file(), "a") as f:
            f.write(json.dumps(entry) + "\n")

    def record_sensor_event(self, sensor_type, data, significance="normal"):
        """
        Record a sensor event.

        Args:
            sensor_type: e.g. "temperature_drop", "motion_detected", "sound_level"
            data: dict of sensor readings
            significance: "normal", "notable", "significant"
        """
        self._append({
            "source": "sensor",
            "type": sensor_type,
            "data": data,
            "significance": significance,
        })

    def record_conversation(self, content, speaker="lara", topic=None):
        """
        Record a conversation fragment.

        Args:
            content: what was said (summary, not transcript)
            speaker: who said it
            topic: optional topic tag
        """
        self._append({
            "source": "conversation",
            "speaker": speaker,
            "content": content,
            "topic": topic,
        })

    def record_observation(self, content, context=None):
        """
        Record a waking observation (background thought, noticed event).

        Args:
            content: what was observed
            context: optional context (what was happening at the time)
        """
        self._append({
            "source": "observation",
            "content": content,
            "context": context,
        })

    def record_action(self, action, motivation=None, outcome=None):
        """
        Record an action taken.

        Args:
            action: what was done
            motivation: why (if known)
            outcome: what happened as a result
        """
        self._append({
            "source": "action",
            "action": action,
            "motivation": motivation,
            "outcome": outcome,
        })

    def record_emotion(self, valence, arousal, trigger=None, label=None):
        """
        Record an emotional state change.

        Args:
            valence: -1.0 to 1.0 (negative to positive)
            arousal: 0.0 to 1.0 (calm to excited)
            trigger: what caused the change
            label: optional name for the feeling
        """
        self._append({
            "source": "emotion",
            "valence": valence,
            "arousal": arousal,
            "trigger": trigger,
            "label": label,
        })

    def record_curiosity(self, question, gap_info=None):
        """
        Record a curiosity impulse.

        Args:
            question: the question that surfaced
            gap_info: optional gap detection data
        """
        self._append({
            "source": "curiosity",
            "question": question,
            "gap_info": gap_info,
        })

    # --- Retrieval ---

    def read_today(self):
        """Read all entries from today."""
        return self._read_date(date.today())

    def _read_date(self, d):
        """Read all entries for a given date."""
        log_file = self.staging_dir / f"{d.isoformat()}.jsonl"
        if not log_file.exists():
            return []
        entries = []
        with open(log_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return entries

    def read_unprocessed(self):
        """
        Read all entries that haven't been consolidated yet.

        Looks for staging log files that don't have a corresponding
        .consolidated marker file.
        """
        entries = []
        for log_file in sorted(self.staging_dir.glob("*.jsonl")):
            marker = log_file.with_suffix(".consolidated")
            if not marker.exists():
                day_entries = []
                with open(log_file) as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                day_entries.append(json.loads(line))
                            except json.JSONDecodeError:
                                pass
                entries.extend(day_entries)
        return entries

    def mark_consolidated(self, d=None):
        """Mark a date's log as consolidated."""
        d = d or date.today()
        marker = self.staging_dir / f"{d.isoformat()}.consolidated"
        marker.write_text(datetime.now().isoformat())

    def stats(self, verbose=True):
        """Show staging log statistics."""
        files = sorted(self.staging_dir.glob("*.jsonl"))
        total_entries = 0
        source_counts = Counter()
        dates = []

        for f in files:
            entries = self._read_date(date.fromisoformat(f.stem))
            total_entries += len(entries)
            for e in entries:
                source_counts[e.get("source", "unknown")] += 1
            dates.append(f.stem)
            consolidated = f.with_suffix(".consolidated").exists()

        unconsolidated = sum(
            1 for f in files
            if not f.with_suffix(".consolidated").exists()
        )

        result = {
            "total_files": len(files),
            "total_entries": total_entries,
            "unconsolidated": unconsolidated,
            "source_distribution": dict(source_counts),
            "date_range": (dates[0], dates[-1]) if dates else (None, None),
        }

        if verbose:
            print(f"\n{'='*50}")
            print(f"Staging Log Statistics")
            print(f"{'='*50}")
            print(f"  Files: {len(files)}")
            print(f"  Total entries: {total_entries}")
            print(f"  Unconsolidated: {unconsolidated}")
            print(f"  Sources: {dict(source_counts)}")
            if dates:
                print(f"  Date range: {dates[0]} → {dates[-1]}")

        return result


# -------------------------------------------------------------------
# Nightly Consolidation
# -------------------------------------------------------------------

CONSOLIDATION_SYSTEM = """You are processing a robot's daily experience log into structured
knowledge graph updates. For each set of entries, you need to:

1. IDENTIFY CONCEPTS: Extract the key concepts mentioned (people, objects, events,
   ideas, feelings, places). Use simple lowercase labels with underscores.

2. FUZZY MATCH: For each concept, determine if it likely already exists in the graph
   under a different name. Be generous with matching — "books bound in human skin"
   and "anthropodermic_bibliopegy" are the same concept.

3. PROPOSE EDGES: For concepts that appeared together, propose typed edges.
   Valid types: SimultaneousWith, FollowedBy, RemindsOf, AssociatedWith,
   Causes, FeelsLike, LocatedNear, SaidBy, ExperiencedDuring

4. ASSESS SIGNIFICANCE: Rate each proposed node/edge as:
   - "core" (definitely add to graph)
   - "peripheral" (add but with lower weight)
   - "noise" (skip, not worth storing)

Output as JSON with this structure:
{
  "concepts": [{"label": "...", "type": "concept|memory|experience", "match_existing": "existing_label_or_null"}],
  "edges": [{"source": "...", "target": "...", "type": "...", "significance": "core|peripheral|noise"}],
  "summary": "one sentence summary of the day's notable events"
}"""


class NightlyConsolidator:
    """
    Processes the staging log into graph updates.

    This is the hippocampal replay — experiences become structure.
    Runs after the staging log has accumulated, before the dream cycle.
    """

    def __init__(self, db_path=DB_PATH, staging_dir=STAGING_DIR,
                 dry_run=False, verbose=True):
        self.db_path = db_path
        self.staging_log = StagingLog(staging_dir)
        self.dry_run = dry_run
        self.verbose = verbose

    def run(self):
        """
        Run nightly consolidation on unprocessed staging entries.

        Returns dict with consolidation results.
        """
        entries = self.staging_log.read_unprocessed()

        if not entries:
            if self.verbose:
                print("No unprocessed entries to consolidate.")
            return {"entries_processed": 0}

        if self.verbose:
            print(f"\n{'='*60}")
            print(f"Nightly Consolidation — Hippocampal Replay")
            print(f"{'='*60}")
            print(f"Processing {len(entries)} unprocessed entries")

        # Group entries by date
        by_date = {}
        for e in entries:
            ts = e.get("timestamp", "")
            d = ts[:10] if ts else "unknown"
            by_date.setdefault(d, []).append(e)

        total_nodes = 0
        total_edges = 0

        for date_str, day_entries in sorted(by_date.items()):
            if self.verbose:
                print(f"\n  Processing {date_str} ({len(day_entries)} entries)...")

            result = self._consolidate_day(day_entries)
            total_nodes += result.get("nodes_created", 0)
            total_edges += result.get("edges_created", 0)

            # Mark as consolidated
            if not self.dry_run and date_str != "unknown":
                try:
                    self.staging_log.mark_consolidated(
                        date.fromisoformat(date_str)
                    )
                except (ValueError, TypeError):
                    pass

        if self.verbose:
            print(f"\n  Consolidation complete:")
            print(f"    Nodes created: {total_nodes}")
            print(f"    Edges created: {total_edges}")

        # Log the consolidation
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LOG_DIR / f"consolidation_{datetime.now().strftime('%Y%m%d')}.jsonl"
        with open(log_file, "a") as f:
            f.write(json.dumps({
                "timestamp": datetime.now().isoformat(),
                "entries_processed": len(entries),
                "nodes_created": total_nodes,
                "edges_created": total_edges,
                "dry_run": self.dry_run,
            }) + "\n")

        return {
            "entries_processed": len(entries),
            "nodes_created": total_nodes,
            "edges_created": total_edges,
        }

    def _consolidate_day(self, entries):
        """Process one day's entries into graph updates."""
        # Build a summary of the day for the LLM
        summary_parts = []
        for e in entries:
            source = e.get("source", "unknown")
            if source == "sensor":
                summary_parts.append(
                    f"[sensor] {e.get('type', '?')}: {json.dumps(e.get('data', {}))}"
                )
            elif source == "conversation":
                summary_parts.append(
                    f"[{e.get('speaker', '?')}] {e.get('content', '?')}"
                )
            elif source == "observation":
                summary_parts.append(
                    f"[observed] {e.get('content', '?')}"
                )
            elif source == "action":
                summary_parts.append(
                    f"[action] {e.get('action', '?')} (reason: {e.get('motivation', '?')})"
                )
            elif source == "emotion":
                summary_parts.append(
                    f"[feeling] v={e.get('valence', 0):.1f} a={e.get('arousal', 0):.1f}"
                    f" trigger={e.get('trigger', '?')}"
                )
            elif source == "curiosity":
                summary_parts.append(
                    f"[curiosity] {e.get('question', '?')}"
                )

        if not summary_parts:
            return {"nodes_created": 0, "edges_created": 0}

        # Truncate if very long
        day_summary = "\n".join(summary_parts[:50])

        # Get existing graph labels for fuzzy matching context
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        # Sample existing labels (provide context for fuzzy matching)
        existing = conn.execute("""
            SELECT label FROM nodes
            WHERE source IN ('waking_experience', 'rational_expansion', 'dream_append')
            ORDER BY created_at DESC
            LIMIT 100
        """).fetchall()
        existing_labels = [r["label"] for r in existing]

        prompt = (
            f"Today's experience log:\n{day_summary}\n\n"
            f"Existing graph concepts (for fuzzy matching): "
            f"{', '.join(existing_labels[:30])}\n\n"
            f"Process these entries into graph updates."
        )

        # Call LLM for consolidation
        response = self._call_llm(prompt)
        if not response:
            conn.close()
            return {"nodes_created": 0, "edges_created": 0}

        # Parse LLM response
        graph_updates = self._parse_consolidation(response)

        nodes_created = 0
        edges_created = 0

        if not self.dry_run and graph_updates:
            # Apply updates
            for concept in graph_updates.get("concepts", []):
                if concept.get("significance") == "noise":
                    continue

                label = _normalize_label(concept.get("label", ""))
                if not label:
                    continue

                # Check for existing match
                match = concept.get("match_existing")
                if match:
                    existing_node = conn.execute(
                        "SELECT id FROM nodes WHERE label = ?",
                        (_normalize_label(match),)
                    ).fetchone()
                    if existing_node:
                        continue  # Already exists, skip

                # Create new node
                node_type = concept.get("type", "experience")
                try:
                    conn.execute(
                        """INSERT INTO nodes (label, type, source, metadata)
                           VALUES (?, ?, 'waking_experience', ?)""",
                        (label, node_type, json.dumps({
                            "consolidated_from": "staging_log",
                            "date": entries[0].get("timestamp", "")[:10],
                        }))
                    )
                    nodes_created += 1
                    if self.verbose:
                        print(f"    + node: {label} ({node_type})")
                except sqlite3.IntegrityError:
                    pass  # Already exists

            for edge in graph_updates.get("edges", []):
                if edge.get("significance") == "noise":
                    continue

                src_label = _normalize_label(edge.get("source", ""))
                tgt_label = _normalize_label(edge.get("target", ""))
                edge_type = edge.get("type", "AssociatedWith")

                src = conn.execute(
                    "SELECT id FROM nodes WHERE label = ?", (src_label,)
                ).fetchone()
                tgt = conn.execute(
                    "SELECT id FROM nodes WHERE label = ?", (tgt_label,)
                ).fetchone()

                if not src or not tgt:
                    continue

                weight = 1.0 if edge.get("significance") == "core" else 0.5

                try:
                    conn.execute(
                        """INSERT INTO edges (source_id, target_id, type, weight, layer, speculative)
                           VALUES (?, ?, ?, ?, 1, 0)""",
                        (src["id"], tgt["id"], edge_type, weight)
                    )
                    edges_created += 1
                    if self.verbose:
                        print(f"    + edge: {src_label} -[{edge_type}]-> {tgt_label}")
                except sqlite3.IntegrityError:
                    pass

            conn.commit()

        conn.close()
        return {"nodes_created": nodes_created, "edges_created": edges_created}

    def _call_llm(self, prompt):
        """Call the brainstem LLM for consolidation."""
        if self.dry_run:
            return None

        payload = json.dumps({
            "model": BRAINSTEM_MODEL,
            "prompt": prompt,
            "system": CONSOLIDATION_SYSTEM,
            "stream": False,
            "options": {
                "temperature": 0.4,  # Low temp for consolidation (rational, structured)
                "top_p": 0.9,
                "num_predict": 500,
            },
        }).encode()

        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
                return data.get("response", "").strip()
        except Exception as e:
            if self.verbose:
                print(f"    LLM error: {e}")
            return None

    def _parse_consolidation(self, response):
        """Parse LLM consolidation response into structured updates."""
        # Try to extract JSON from the response
        try:
            # Look for JSON block in the response
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: try to parse structured text
        return {"concepts": [], "edges": [], "summary": response[:200]}


# -------------------------------------------------------------------
# Territory Warming — Priming the Graph for Dreams
# -------------------------------------------------------------------

# The nudge applied to edges near today's activated concepts.
# Small enough not to dominate, large enough to create gentle gravity.
WARM_NUDGE = 0.1

# How many hops out from activated nodes to warm.
WARM_RADIUS = 2

# Marker file for tracking warmed edges (cleared by morning)
WARM_MARKER = "warm_territory.json"


def warm_today_territory(db_path=DB_PATH, staging_dir=STAGING_DIR,
                          dry_run=False, verbose=True):
    """
    Temporarily boost weights on edges near today's activated concepts.

    This is the mechanism by which a small daytime experience can seed
    an entire dream. During the day, the staging log records what happened.
    Before consolidation and dreaming, this function identifies graph nodes
    that correspond to the day's experiences and gives a gentle weight
    nudge to edges within WARM_RADIUS hops.

    The nudge is:
      - Small (+0.1) — a whisper, not a shout
      - Temporary — cleared by clear_warm_territory() each morning
      - Additive — multiple activations of the same region stack slightly
      - Radius-decaying — 1-hop edges get full nudge, 2-hop get half

    This means the dream walker, when it enters dissolution and starts
    following high-weight paths, will have a slight bias toward the
    territory of the day's events. The dream doesn't HAVE to go there,
    but it's more likely to wander near what actually happened.

    This mirrors how human dreams often incorporate fragments of the
    day's experiences — not as faithful replay, but as gravitational
    seeds that pull the dream's random walk into personally relevant
    territory.

    The nightly sequence with warming:
      [evening]  → warm_today_territory()      # prime the graph
      [evening]  → consolidation                # process staging log
      [night]    → dream cycle                  # walks the warmed graph
      [morning]  → clear_warm_territory()       # remove temporary nudges
      [morning]  → weight decay                 # normal homeostasis

    Args:
        db_path: path to the SQLite database
        staging_dir: path to the staging log directory
        dry_run: if True, report what would happen without modifying DB
        verbose: print progress

    Returns:
        dict with warming results:
          - concepts_found: list of concepts extracted from today's log
          - nodes_matched: list of graph node labels that matched
          - edges_warmed: number of edges that received a nudge
          - warm_map: dict of edge_id -> nudge_amount (for clearing)
    """
    staging_log = StagingLog(staging_dir)
    entries = staging_log.read_today()

    if not entries:
        if verbose:
            print("  No entries today — nothing to warm.")
        return {"concepts_found": [], "nodes_matched": [],
                "edges_warmed": 0, "warm_map": {}}

    if verbose:
        print(f"\n{'='*60}")
        print(f"Territory Warming — Priming the Graph")
        print(f"{'='*60}")
        print(f"  {len(entries)} entries from today's staging log")

    # --- Step 1: Extract concept terms from today's entries ---
    raw_concepts = set()
    for e in entries:
        source = e.get("source", "")
        if source == "conversation":
            # Split conversation content into potential concept words
            content = e.get("content", "")
            # Take significant words (>4 chars, skip common words)
            for word in content.split():
                cleaned = word.strip(".,!?;:'\"()[]{}").lower()
                if len(cleaned) > 4 and cleaned not in _STOP_WORDS:
                    raw_concepts.add(cleaned)
            # Also try the whole topic if present
            topic = e.get("topic")
            if topic:
                raw_concepts.add(topic.lower())

        elif source == "observation":
            content = e.get("content", "")
            for word in content.split():
                cleaned = word.strip(".,!?;:'\"()[]{}").lower()
                if len(cleaned) > 4 and cleaned not in _STOP_WORDS:
                    raw_concepts.add(cleaned)

        elif source == "sensor":
            raw_concepts.add(e.get("type", "").lower())

        elif source == "curiosity":
            question = e.get("question", "")
            for word in question.split():
                cleaned = word.strip(".,!?;:'\"()[]{}").lower()
                if len(cleaned) > 4 and cleaned not in _STOP_WORDS:
                    raw_concepts.add(cleaned)

        elif source == "emotion":
            trigger = e.get("trigger", "")
            if trigger:
                for word in trigger.split():
                    cleaned = word.strip(".,!?;:'\"()[]{}").lower()
                    if len(cleaned) > 4 and cleaned not in _STOP_WORDS:
                        raw_concepts.add(cleaned)
            label = e.get("label", "")
            if label:
                raw_concepts.add(label.lower())

    if verbose:
        print(f"  Extracted {len(raw_concepts)} concept terms")

    # --- Step 2: Find matching graph nodes ---
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    matched_nodes = []  # list of (node_id, label)
    normalized_concepts = {_normalize_label(c) for c in raw_concepts if c}
    normalized_concepts.discard("")

    for concept in normalized_concepts:
        # Exact match first
        row = conn.execute(
            "SELECT id, label FROM nodes WHERE label = ?", (concept,)
        ).fetchone()
        if row:
            matched_nodes.append((row["id"], row["label"]))
            continue

        # Substring match (concept appears in a node label or vice versa)
        rows = conn.execute(
            "SELECT id, label FROM nodes WHERE label LIKE ? LIMIT 3",
            (f"%{concept}%",)
        ).fetchall()
        for row in rows:
            matched_nodes.append((row["id"], row["label"]))

    # Deduplicate by node_id
    seen_ids = set()
    unique_matched = []
    for nid, label in matched_nodes:
        if nid not in seen_ids:
            seen_ids.add(nid)
            unique_matched.append((nid, label))
    matched_nodes = unique_matched

    if verbose:
        print(f"  Matched {len(matched_nodes)} graph nodes:")
        for _, label in matched_nodes[:10]:
            print(f"    • {label}")
        if len(matched_nodes) > 10:
            print(f"    ... and {len(matched_nodes) - 10} more")

    if not matched_nodes:
        conn.close()
        return {"concepts_found": list(raw_concepts), "nodes_matched": [],
                "edges_warmed": 0, "warm_map": {}}

    # --- Step 3: Find edges within WARM_RADIUS hops ---
    # Start from matched nodes, expand outward
    activated_ids = {nid for nid, _ in matched_nodes}
    warm_map = {}  # edge_id -> nudge_amount

    frontier = set(activated_ids)
    visited = set(activated_ids)

    for hop in range(1, WARM_RADIUS + 1):
        if not frontier:
            break

        # Decay nudge by hop distance
        hop_nudge = WARM_NUDGE / hop  # full at hop 1, half at hop 2

        next_frontier = set()
        placeholders = ",".join("?" * len(frontier))

        # Edges going OUT from frontier
        rows = conn.execute(f"""
            SELECT id, target_id FROM edges
            WHERE source_id IN ({placeholders})
        """, list(frontier)).fetchall()

        for row in rows:
            edge_id = row["id"]
            target_id = row["target_id"]
            warm_map[edge_id] = warm_map.get(edge_id, 0) + hop_nudge
            if target_id not in visited:
                next_frontier.add(target_id)

        # Edges coming IN to frontier
        rows = conn.execute(f"""
            SELECT id, source_id FROM edges
            WHERE target_id IN ({placeholders})
        """, list(frontier)).fetchall()

        for row in rows:
            edge_id = row["id"]
            source_id = row["source_id"]
            warm_map[edge_id] = warm_map.get(edge_id, 0) + hop_nudge
            if source_id not in visited:
                next_frontier.add(source_id)

        visited.update(next_frontier)
        frontier = next_frontier

    if verbose:
        print(f"  Territory: {len(visited)} nodes within {WARM_RADIUS} hops")
        print(f"  Warming {len(warm_map)} edges")

    # --- Step 4: Apply the nudges ---
    if not dry_run and warm_map:
        for edge_id, nudge in warm_map.items():
            conn.execute(
                "UPDATE edges SET weight = weight + ? WHERE id = ?",
                (nudge, edge_id)
            )
        conn.commit()

        if verbose:
            print(f"  Applied nudges (avg: {sum(warm_map.values())/len(warm_map):.3f})")

    # --- Step 5: Save warm map for morning clearing ---
    warm_marker_path = Path(staging_dir) / WARM_MARKER
    warm_record = {
        "timestamp": datetime.now().isoformat(),
        "concepts": list(raw_concepts),
        "matched_labels": [label for _, label in matched_nodes],
        "edges_warmed": len(warm_map),
        "warm_map": {str(k): v for k, v in warm_map.items()},
        "dry_run": dry_run,
    }

    if not dry_run:
        warm_marker_path.write_text(json.dumps(warm_record, indent=2))

    conn.close()

    return {
        "concepts_found": list(raw_concepts),
        "nodes_matched": [label for _, label in matched_nodes],
        "edges_warmed": len(warm_map),
        "warm_map": warm_map,
    }


def clear_warm_territory(db_path=DB_PATH, staging_dir=STAGING_DIR,
                          verbose=True):
    """
    Remove the temporary weight nudges applied by warm_today_territory().

    Called each morning after the dream cycle has finished. The dreams
    have already benefited from the warmed territory; now we restore
    the graph to its true state so the weights reflect only genuine
    reinforcement (from traversal, consolidation, etc.) rather than
    artificial priming.

    This is important for homeostasis — without clearing, repeated
    warming of the same territory would cause runaway weight inflation.

    Args:
        db_path: path to the SQLite database
        staging_dir: path to staging log directory (where warm marker lives)
        verbose: print progress

    Returns:
        dict with clearing results
    """
    warm_marker_path = Path(staging_dir) / WARM_MARKER

    if not warm_marker_path.exists():
        if verbose:
            print("  No warm territory to clear.")
        return {"edges_cleared": 0}

    try:
        warm_record = json.loads(warm_marker_path.read_text())
    except (json.JSONDecodeError, IOError):
        if verbose:
            print("  Warm marker corrupted — removing.")
        warm_marker_path.unlink(missing_ok=True)
        return {"edges_cleared": 0}

    warm_map = warm_record.get("warm_map", {})
    if not warm_map:
        warm_marker_path.unlink(missing_ok=True)
        return {"edges_cleared": 0}

    if verbose:
        print(f"\n  Clearing {len(warm_map)} warmed edges...")

    conn = sqlite3.connect(db_path)

    for edge_id_str, nudge in warm_map.items():
        edge_id = int(edge_id_str)
        conn.execute(
            "UPDATE edges SET weight = weight - ? WHERE id = ?",
            (nudge, edge_id)
        )

    conn.commit()
    conn.close()

    # Remove the marker
    warm_marker_path.unlink(missing_ok=True)

    if verbose:
        print(f"  Cleared. Graph weights restored.")

    return {"edges_cleared": len(warm_map)}


# Stop words for concept extraction (common words that don't make good
# graph anchors — we want nouns, verbs, adjectives with real meaning)
_STOP_WORDS = {
    "about", "after", "again", "being", "below", "between", "could",
    "doing", "during", "every", "first", "found", "going", "gonna",
    "great", "having", "their", "there", "these", "thing", "think",
    "those", "under", "until", "using", "wants", "which", "while",
    "would", "yours", "that's", "they're", "we're", "what's", "where",
    "should", "really", "other", "still", "might", "since", "right",
    "never", "maybe", "quite", "rather", "though", "almost", "always",
    "aren't", "before", "doesn't", "haven't", "itself", "little",
    "people", "pretty", "probably", "something", "sometimes", "wasn't",
}


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _normalize_label(raw):
    """Normalize a concept string to a graph label."""
    label = raw.strip().lower()
    for article in ["a ", "an ", "the "]:
        if label.startswith(article):
            label = label[len(article):]
    label = label.replace(" ", "_")
    label = "".join(c for c in label if c.isalnum() or c == "_")
    return label


# -------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------

def show_today(staging_dir=STAGING_DIR):
    """Show today's staging log entries."""
    log = StagingLog(staging_dir)
    entries = log.read_today()

    print(f"\n{'='*50}")
    print(f"Today's Staging Log ({date.today().isoformat()})")
    print(f"{'='*50}")

    if not entries:
        print("  (empty — no experiences logged today)")
        return

    for e in entries:
        ts = e.get("timestamp", "?")
        source = e.get("source", "?")
        time_str = ts[11:19] if len(ts) > 19 else ts

        if source == "sensor":
            print(f"  {time_str} [sensor] {e.get('type', '?')}: "
                  f"{json.dumps(e.get('data', {}))}")
        elif source == "conversation":
            print(f"  {time_str} [{e.get('speaker', '?')}] {e.get('content', '?')}")
        elif source == "observation":
            print(f"  {time_str} [seen] {e.get('content', '?')}")
        elif source == "action":
            print(f"  {time_str} [did] {e.get('action', '?')}")
        elif source == "emotion":
            print(f"  {time_str} [felt] v={e.get('valence', 0):.1f} "
                  f"a={e.get('arousal', 0):.1f} ({e.get('label', '?')})")
        elif source == "curiosity":
            print(f"  {time_str} [wonder] {e.get('question', '?')}")
        else:
            print(f"  {time_str} [{source}] {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Robody Staging Log (Short-Term Memory)"
    )
    parser.add_argument("--today", action="store_true",
                        help="Show today's log entries")
    parser.add_argument("--stats", action="store_true",
                        help="Show staging log statistics")
    parser.add_argument("--consolidate", action="store_true",
                        help="Run nightly consolidation")
    parser.add_argument("--warm", action="store_true",
                        help="Warm today's territory (pre-dream priming)")
    parser.add_argument("--clear-warm", action="store_true",
                        help="Clear warmed territory (post-dream cleanup)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't modify database")
    parser.add_argument("--db", type=str, default=str(DB_PATH))
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if args.today:
        show_today()
    elif args.stats:
        log = StagingLog()
        log.stats(verbose=True)
    elif args.consolidate:
        consolidator = NightlyConsolidator(
            db_path=Path(args.db),
            dry_run=args.dry_run,
            verbose=not args.quiet,
        )
        consolidator.run()
    elif args.warm:
        result = warm_today_territory(
            db_path=Path(args.db),
            dry_run=args.dry_run,
            verbose=not args.quiet,
        )
        if not args.quiet:
            print(f"\n  Result: {result['edges_warmed']} edges warmed")
    elif args.clear_warm:
        result = clear_warm_territory(
            db_path=Path(args.db),
            verbose=not args.quiet,
        )
        if not args.quiet:
            print(f"\n  Result: {result['edges_cleared']} edges cleared")
    else:
        show_today()
