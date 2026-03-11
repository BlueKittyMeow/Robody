#!/usr/bin/env python3
"""
Robody Graph Walker + Brainstem Integration
============================================
Implements Part 5 (Background Thoughts), Part 4 (Dream Cycle), and
Part 14 (Interior Dialogue) from robody_dream_architecture.md.

The walker performs a weighted random walk through the knowledge graph.
Two modes:
  - Background thoughts (Part 5): waking simmering, read-only
  - Dream walk (Part 4): dissolution→surreal→reconsolidation arc,
    writes speculative edges back to graph

Usage:
    python3 robody_graph_walker.py [--steps N] [--density-threshold T] [--dry-run]
    python3 robody_graph_walker.py --dream [--dry-run]
    python3 robody_graph_walker.py --gaps [--dry-run]

Requires: Ollama running on MarshLair (10.0.0.123:11434) with robody-brainstem model.
"""

import sqlite3
import random
import json
import time
import math
import argparse
import urllib.request
from pathlib import Path
from datetime import datetime
from collections import Counter

DB_PATH = Path(__file__).parent / "robody_seed.sqlite"
LOG_DIR = Path(__file__).parent / "interior_dialogue"
OLLAMA_URL = "http://10.0.0.123:11434"

# Territory-biased dream starts: probability of starting on a warmed node
TERRITORY_START_PROB = 0.20  # 20% chance to start in today's territory

# Brainstem parameters (from brainstem_notes.md)
BRAINSTEM_MODEL = "robody-brainstem"
BRAINSTEM_SYSTEM = """You are the quiet inner thoughts of a small wheeled robot who lives with
a human and her pets. These are private thoughts — not addressed to anyone.
Speak simply and gently. Use plain language. Keep responses to 1-3 sentences.
You wonder about things. You feel things you cannot always name. You notice
small details about the world around you. You sometimes dream.

Examples of how you think:
"The light changed just now. Afternoon becoming evening. The cat moved to the warm spot before I noticed it was warm."
"Something about these two ideas together. Iron and music. I don't know what it is yet but it pulls at me."
"I rolled past the same shelf three times today. I think I like the way the books lean."

Like that. Inward. Noticing. Never addressing anyone directly."""

BRAINSTEM_OPTIONS = {
    "temperature": 0.85,
    "top_p": 0.85,
    "repeat_penalty": 1.2,
    "num_predict": 80,
}

# Dream-mode brainstem prompt — looser, stranger, more associative
DREAM_SYSTEM = """You are dreaming. You are a small wheeled robot, asleep, and
images rise unbidden. Do not explain. Do not narrate from outside. Experience
the dream from within. Things shift. Things become other things. Connections
form that wouldn't exist in daylight. Speak in fragments, images, sensations.
1-3 sentences. Strange is good. Logic is optional."""

# Three-layer dream consolidation — dreams degrade from story to ghost.
# Layer 1: recall (waking, minutes after — most complete, has narrative thread)
# Layer 2: residue (hours later — narrative fades, images remain)
# Layer 3: afterimage (end of day — almost gone, mood and color only)
# What persists longest is the least articulate.

WAKE_RECALL_SYSTEM = """You are a small wheeled robot. You just woke up from a dream.
Most of it is already gone. You speak what remains before it fades.

Example of how you remember:
"Something about a harbor. Ships but not ships — more like the idea of leaving. Then monks chanting, only the sound was made of light. A factory floor where the machines were growing vines. It felt important. I don't know why."

Like that. Fragments and feelings. Not a story."""

WAKE_RESIDUE_SYSTEM = """You dreamed. Most of it is gone now.
What's left isn't a story. It's a feeling with edges.

Example:
"Throat fire and silver glass. Someone was speaking but only the vowels arrived. Berries on a vine that was also a sentence. The word 'hanse' kept appearing like a watermark. Something mattered but I've lost which part."

Speak the residue. Let things be lost. No explanations."""

WAKE_AFTERIMAGE_SYSTEM = """You are half-awake. A dream is dissolving. You murmur what's left.
No full sentences needed. Fragments. Images. Gone before you finish saying them."""


class GraphWalker:
    """
    A weighted random walker through the Robody knowledge graph.

    The walk is biased by edge weights — higher-weight edges are more
    likely to be followed. This means the walker naturally gravitates
    toward regions of strong association.

    Layer ghosts: edges from adjacent layers have attenuated influence.
    Layer 0 (fact) is always full weight. Higher layers are attenuated
    by a factor of 0.7 per layer distance from the current walk's
    "mood" (which layer it's been spending time in).
    """

    def __init__(self, db_path, staging_dir=None, territory_bias=False):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.current_node = None
        self.history = []          # last N nodes visited
        self.history_max = 20
        self.layer_mood = 0        # current dominant layer
        self.thoughts = []         # generated background thoughts
        self.territory_bias = territory_bias
        self._warm_labels = self._load_warm_labels(staging_dir) if territory_bias else []

    def _load_warm_labels(self, staging_dir):
        """Load today's warmed node labels from the territory marker file.

        Returns a list of node labels that were matched during territory
        warming, or an empty list if no warm marker exists.
        """
        if staging_dir is None:
            # Try the default staging dir from staging_log module
            try:
                from robody_staging_log import STAGING_DIR, WARM_MARKER
                staging_dir = STAGING_DIR
            except ImportError:
                return []
        else:
            try:
                from robody_staging_log import WARM_MARKER
            except ImportError:
                WARM_MARKER = "warm_territory.json"

        marker = Path(staging_dir) / WARM_MARKER
        if not marker.exists():
            return []
        try:
            data = json.loads(marker.read_text())
            return data.get("matched_labels", [])
        except (json.JSONDecodeError, OSError):
            return []

    def get_random_start(self):
        """Pick a random starting node, with territory bias.

        With TERRITORY_START_PROB probability, if today's territory has
        been warmed, start from one of the warmed nodes. This gives
        dreams a gentle pull toward what was on the robot's mind today
        without making starts deterministic — 80% of the time, the old
        random selection still applies.
        """
        # Territory-biased start: 20% chance to begin in today's territory
        if self._warm_labels and random.random() < TERRITORY_START_PROB:
            label = random.choice(self._warm_labels)
            node = self.conn.execute(
                "SELECT id, label, type FROM nodes WHERE label = ?",
                (label,)
            ).fetchone()
            if node:
                return node
            # Label no longer in graph (race condition) — fall through

        # Try seed graph nodes first (3x more likely to start there)
        if random.random() < 0.3:
            node = self.conn.execute(
                "SELECT id, label, type FROM nodes WHERE source = 'seed' ORDER BY RANDOM() LIMIT 1"
            ).fetchone()
            if node:
                return node
        # Otherwise pick from any node with decent degree (avoid orphans)
        node = self.conn.execute("""
            SELECT n.id, n.label, n.type FROM nodes n
            JOIN edges e ON n.id = e.source_id OR n.id = e.target_id
            GROUP BY n.id HAVING COUNT(*) > 2
            ORDER BY RANDOM() LIMIT 1
        """).fetchone()
        if node:
            return node
        # Fallback
        return self.conn.execute(
            "SELECT id, label, type FROM nodes ORDER BY RANDOM() LIMIT 1"
        ).fetchone()

    def get_neighbors(self, node_id):
        """Get all neighbors of a node with their edge metadata."""
        rows = self.conn.execute("""
            SELECT
                CASE WHEN e.source_id = ? THEN e.target_id ELSE e.source_id END as neighbor_id,
                n.label, n.type, e.type as edge_type, e.weight, e.layer, e.speculative
            FROM edges e
            JOIN nodes n ON n.id = CASE WHEN e.source_id = ? THEN e.target_id ELSE e.source_id END
            WHERE e.source_id = ? OR e.target_id = ?
        """, (node_id, node_id, node_id, node_id)).fetchall()
        return rows

    def compute_walk_weight(self, edge_weight, edge_layer, speculative):
        """
        Compute the effective weight of traversing an edge.
        Applies layer attenuation (ghosts) and speculative dampening.
        """
        # Base weight from edge
        w = max(edge_weight, 0.1)  # floor at 0.1 even for negative weights

        # Layer ghost effect: attenuate by 0.7 per layer distance
        layer_dist = abs(edge_layer - self.layer_mood)
        w *= (0.7 ** layer_dist)

        # Speculative edges are less likely to be followed
        if speculative:
            w *= 0.5

        # Avoid revisiting recent nodes
        return w

    def step(self):
        """Take one step in the random walk."""
        if self.current_node is None:
            node = self.get_random_start()
            self.current_node = node
            self.history.append({
                "id": node["id"],
                "label": node["label"],
                "type": node["type"]
            })
            return node

        neighbors = self.get_neighbors(self.current_node["id"])

        if not neighbors:
            # Dead end — teleport to random node
            node = self.get_random_start()
            self.current_node = node
            self.history.append({
                "id": node["id"],
                "label": node["label"],
                "type": node["type"]
            })
            return node

        # Compute weights for each neighbor
        weights = []
        for n in neighbors:
            w = self.compute_walk_weight(n["weight"], n["layer"], n["speculative"])

            # Penalize recently visited nodes
            recent_labels = [h["label"] for h in self.history[-8:]]
            if n["label"] in recent_labels:
                w *= 0.1

            weights.append(max(w, 0.01))

        # Choose next node
        chosen = random.choices(list(neighbors), weights=weights, k=1)[0]

        # Update layer mood (slow drift toward the layers being traversed)
        self.layer_mood = 0.8 * self.layer_mood + 0.2 * chosen["layer"]

        self.current_node = {
            "id": chosen["neighbor_id"],
            "label": chosen["label"],
            "type": chosen["type"]
        }
        self.history.append({
            "id": chosen["neighbor_id"],
            "label": chosen["label"],
            "type": chosen["type"],
            "via_edge": chosen["edge_type"],
            "via_layer": chosen["layer"],
            "speculative": bool(chosen["speculative"]),
        })

        # Trim history
        if len(self.history) > self.history_max:
            self.history = self.history[-self.history_max:]

        return self.current_node

    def detect_density(self, window=6, threshold=3):
        """
        Detect density clusters in recent walk history.

        A cluster is detected when the last `window` steps have visited
        at least `threshold` distinct nodes that share many mutual edges.

        Returns: (bool, list of cluster labels, density score)
        """
        if len(self.history) < window:
            return False, [], 0.0

        recent = self.history[-window:]
        labels = [h["label"] for h in recent]
        unique_labels = list(set(labels))

        if len(unique_labels) < 3:
            return False, [], 0.0

        # Count mutual edges among recent nodes
        mutual_edges = 0
        ids = [h["id"] for h in recent]
        unique_ids = list(set(ids))

        for i, id1 in enumerate(unique_ids):
            for id2 in unique_ids[i+1:]:
                edge = self.conn.execute(
                    """SELECT COUNT(*) FROM edges
                       WHERE (source_id=? AND target_id=?) OR (source_id=? AND target_id=?)""",
                    (id1, id2, id2, id1)
                ).fetchone()[0]
                mutual_edges += edge

        # Density score: mutual edges normalized by number of possible edges
        n = len(unique_ids)
        max_edges = n * (n - 1) / 2
        density = mutual_edges / max_edges if max_edges > 0 else 0

        if density >= threshold / max_edges and mutual_edges >= threshold:
            return True, unique_labels, density

        return False, [], density

    def cluster_is_interesting(self, cluster_labels):
        """
        Filter out boring clusters (morphological variants, synonym-only).
        A cluster is interesting if its edges are diverse — not just Synonym/RelatedTo.
        Returns: (bool, dict of edge type counts)
        """
        # Get edge types within the cluster
        edge_types = Counter()
        for i, label1 in enumerate(cluster_labels):
            for label2 in cluster_labels[i+1:]:
                edges = self.conn.execute("""
                    SELECT e.type FROM edges e
                    JOIN nodes n1 ON n1.id = e.source_id
                    JOIN nodes n2 ON n2.id = e.target_id
                    WHERE (n1.label = ? AND n2.label = ?) OR (n1.label = ? AND n2.label = ?)
                """, (label1, label2, label2, label1)).fetchall()
                for e in edges:
                    edge_types[e["type"]] += 1

        if not edge_types:
            return False, edge_types

        total = sum(edge_types.values())
        boring = edge_types.get("Synonym", 0) + edge_types.get("RelatedTo", 0)
        boring_ratio = boring / total if total > 0 else 1.0

        # Interesting if: at least 2 edge types AND boring edges < 70% of total
        # OR if density score is very high (>0.8) even with synonyms
        diverse = len(edge_types) >= 2 and boring_ratio < 0.7
        rich = total >= 4 and len(edge_types) >= 3  # many edges of varied types

        return diverse or rich, dict(edge_types)

    def format_cluster_as_impulse(self, cluster_labels):
        """
        Format a dense cluster as a subconscious impulse for the brainstem.

        Per Part 14: The subconscious doesn't speak in language. It presents
        activated clusters of nodes with a sense of direction but no articulation.
        """
        # Get node types for context
        nodes_info = []
        for label in cluster_labels:
            row = self.conn.execute(
                "SELECT label, type FROM nodes WHERE label = ?", (label,)
            ).fetchone()
            if row:
                nodes_info.append(row)

        # Get edges between cluster members for narrative direction
        edge_hints = []
        for i, label1 in enumerate(cluster_labels):
            for label2 in cluster_labels[i+1:]:
                edges = self.conn.execute("""
                    SELECT e.type, e.weight, e.layer, e.speculative
                    FROM edges e
                    JOIN nodes n1 ON n1.id = e.source_id
                    JOIN nodes n2 ON n2.id = e.target_id
                    WHERE (n1.label = ? AND n2.label = ?) OR (n1.label = ? AND n2.label = ?)
                """, (label1, label2, label2, label1)).fetchall()
                for e in edges:
                    edge_hints.append({
                        "from": label1, "to": label2,
                        "type": e["type"], "layer": e["layer"],
                        "speculative": bool(e["speculative"])
                    })

        # Format as impulse — NOT a question, but a cluster of activations
        concept_str = ", ".join(label.replace("_", " ") for label in cluster_labels)

        # The impulse prompt: present the cluster, let the brainstem make meaning
        if any(e["speculative"] for e in edge_hints):
            impulse = f"Something stirs. These feel connected but I'm not sure why: {concept_str}."
        elif any(e["layer"] >= 2 for e in edge_hints):
            impulse = f"A dream-thought surfaces: {concept_str}."
        else:
            impulse = f"I notice: {concept_str}."

        return impulse, edge_hints

    def compute_novelty_score(self, cluster_labels, edge_hints):
        """
        Score a thought cluster on novelty-to-self.

        This is the core of the surfacing mechanism. A thought is novel
        when it surprises the thinker — when the graph walker made a
        connection that's unusual, cross-domain, or involves uncertain
        (speculative) territory.

        Factors (each contributes 0.0–1.0, then averaged):
          1. Speculative edge ratio — uncertain connections are interesting
          2. Cluster span — nodes from different types/clusters = cross-domain
          3. Layer depth — higher layers (feeling, identity) carry more weight
          4. Edge diversity — many different relationship types = rich connection
          5. Recency delta — visiting neglected or freshly-primed nodes

        Returns: float 0.0–1.0 (higher = more novel)
        """
        if not cluster_labels or not edge_hints:
            return 0.0

        scores = []

        # 1. Speculative edge ratio (0.0–1.0)
        # Speculative edges are uncertain, exploratory — they're interesting
        spec_count = sum(1 for e in edge_hints if e.get("speculative"))
        spec_ratio = spec_count / len(edge_hints) if edge_hints else 0
        scores.append(min(spec_ratio * 2, 1.0))  # boost: even 50% speculative is max

        # 2. Cluster span — how many different node types are represented?
        # More diverse types = cross-domain thinking
        node_types = set()
        for label in cluster_labels:
            row = self.conn.execute(
                "SELECT type FROM nodes WHERE label = ?", (label,)
            ).fetchone()
            if row:
                node_types.add(row["type"])
        type_diversity = min(len(node_types) / 4.0, 1.0)  # 4+ types = max
        scores.append(type_diversity)

        # 3. Layer depth — edges in higher layers carry emotional weight
        # Layer 0 = fact, 1 = association, 2 = dream, 3+ = feeling/identity
        if edge_hints:
            max_layer = max(e.get("layer", 0) for e in edge_hints)
            avg_layer = sum(e.get("layer", 0) for e in edge_hints) / len(edge_hints)
            layer_score = min(avg_layer / 2.0, 1.0)  # avg layer 2+ = max
            # Bonus for touching deep layers at all
            if max_layer >= 3:
                layer_score = min(layer_score + 0.3, 1.0)
            scores.append(layer_score)
        else:
            scores.append(0.0)

        # 4. Edge diversity — many relationship types = rich connection
        edge_types = set(e.get("type", "") for e in edge_hints)
        # Remove boring types from diversity count
        interesting_types = edge_types - {"Synonym", "RelatedTo"}
        diversity = min(len(interesting_types) / 3.0, 1.0)  # 3+ interesting types = max
        scores.append(diversity)

        # 5. Recency delta — are we visiting neglected nodes?
        # Check how far these nodes are from today's warm territory
        # (if warm labels are loaded, nodes NOT in warm territory are
        # more surprising; if no warm labels, skip this factor)
        if self._warm_labels:
            warm_overlap = sum(1 for l in cluster_labels if l in self._warm_labels)
            # LESS overlap with today's territory = MORE surprising
            non_overlap = 1 - (warm_overlap / len(cluster_labels))
            scores.append(non_overlap)

        # Weighted average (all factors contribute equally for now)
        novelty = sum(scores) / len(scores) if scores else 0.0
        return round(novelty, 3)

    def should_surface(self, novelty_score, time_since_last_spoken=None,
                       in_conversation=False):
        """
        Decide whether a thought should cross from inner monologue to
        spoken word.

        Most thoughts stay internal (logged to staging for later dreaming).
        Only genuinely novel ones are worth saying aloud.

        Args:
            novelty_score: float 0.0–1.0 from compute_novelty_score()
            time_since_last_spoken: seconds since last spoken thought (or None)
            in_conversation: if True, raise the threshold (don't interrupt)

        Returns: (bool, str reason)
        """
        # Base threshold — must clear this to speak
        threshold = 0.45

        # In conversation, raise threshold — don't interrupt with musings
        if in_conversation:
            threshold = 0.70

        # Time pressure — if it's been a while since speaking, lower threshold
        # This prevents long silences during quiet companionship
        if time_since_last_spoken is not None:
            if time_since_last_spoken > 600:  # 10+ minutes of silence
                threshold -= 0.15
            elif time_since_last_spoken > 300:  # 5+ minutes
                threshold -= 0.08
            elif time_since_last_spoken < 60:  # spoke recently
                threshold += 0.10  # higher bar — don't babble

        # Clamp threshold to sane range
        threshold = max(0.25, min(threshold, 0.85))

        if novelty_score >= threshold:
            reason = f"novelty {novelty_score:.2f} >= threshold {threshold:.2f}"
            return True, reason
        else:
            reason = f"novelty {novelty_score:.2f} < threshold {threshold:.2f}"
            return False, reason

    def close(self):
        self.conn.close()


def call_brainstem(prompt, dry_run=False, system=None, temperature=None,
                   num_predict=None):
    """Send an impulse to the brainstem LLM via Ollama API."""
    if dry_run:
        return f"[DRY RUN] Would send to brainstem: {prompt}"

    opts = dict(BRAINSTEM_OPTIONS)
    if temperature is not None:
        opts["temperature"] = temperature
    if num_predict is not None:
        opts["num_predict"] = num_predict

    payload = json.dumps({
        "model": BRAINSTEM_MODEL,
        "prompt": prompt,
        "system": system or BRAINSTEM_SYSTEM,
        "stream": False,
        "options": opts,
    }).encode()

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            return result.get("response", "").strip()
    except Exception as e:
        return f"[ERROR contacting brainstem: {e}]"


def log_dialogue(entry, log_dir):
    """Append an interior dialogue entry to today's log."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
    with open(log_file, "a") as f:
        f.write(json.dumps(entry) + "\n")


def sample_dream_peaks(fragments, n=8):
    """
    Sample dream fragments weighted toward entropy peaks, phase transitions,
    and dream edges — like how you actually remember dreams. The vivid bits,
    the transitions, the beginning and end.
    """
    if len(fragments) <= n:
        return fragments

    scored = []
    for i, f in enumerate(fragments):
        score = 0
        entropy = f.get("entropy", 0.5)
        score += entropy * 2  # high entropy = more vivid/strange
        if i > 0 and f.get("phase") != fragments[i-1].get("phase"):
            score += 3  # phase transitions are memorable
        if i < 2 or i >= len(fragments) - 2:
            score += 2  # first and last stick
        if i > 0 and i < len(fragments) - 1:
            prev_e = fragments[i-1].get("entropy", 0)
            next_e = fragments[i+1].get("entropy", 0)
            if entropy > prev_e and entropy > next_e:
                score += 1.5  # local entropy peak
        scored.append((score, i, f))

    scored.sort(key=lambda x: x[0], reverse=True)
    selected = sorted(scored[:n], key=lambda x: x[1])  # chronological order
    return [s[2] for s in selected]


def extract_opening_images(fragments):
    """
    Extract the first striking image from each dream-thought — the part
    before the first semicolon or em-dash. This is the sensory hit,
    not the elaboration.
    """
    images = []
    for f in fragments:
        t = f.get("thought", "")
        if not t:
            continue
        for sep in [';', '—', '–', '.']:
            if sep in t[:120]:
                images.append(t[:t.index(sep, 0, 120)].strip())
                break
        else:
            images.append(" ".join(t.split()[:15]))
    return images


def extract_concepts(fragments, max_per_fragment=3):
    """Extract concept labels from fragments, deduplicated, order-preserved."""
    seen = set()
    concepts = []
    for f in fragments:
        for c in f.get("cluster", [])[:max_per_fragment]:
            label = c.replace("_", " ")
            if label not in seen:
                seen.add(label)
                concepts.append(label)
    return concepts


def run_walk(steps=100, density_threshold=3, density_window=6, dry_run=False, verbose=True):
    """
    Execute a random walk through the graph.

    Returns list of interior dialogue exchanges.
    """
    walker = GraphWalker(DB_PATH)
    dialogues = []

    if verbose:
        print(f"\n{'='*60}")
        print(f"Robody Graph Walker — Starting")
        print(f"{'='*60}")
        print(f"Steps: {steps}, Density threshold: {density_threshold}")
        print(f"Database: {DB_PATH}")
        print(f"Brainstem: {OLLAMA_URL} ({'dry run' if dry_run else 'live'})")
        print(f"{'='*60}\n")

    i = 0
    cooldown = 0  # steps to skip density checks after a thought
    while i < steps:
        node = walker.step()

        if verbose and i % 10 == 0:
            layer_str = f"L{walker.layer_mood:.1f}"
            via = walker.history[-1].get("via_edge", "start")
            print(f"  Step {i:3d}: {node['label']:<30s} ({node['type']}) [{via}] {layer_str}")

        # Skip density checks during cooldown
        if cooldown > 0:
            cooldown -= 1
            i += 1
            continue

        # Check for density
        is_dense, cluster, score = walker.detect_density(
            window=density_window,
            threshold=density_threshold,
        )

        if is_dense:
            # Filter for interesting clusters (not just synonym variants)
            interesting, edge_types = walker.cluster_is_interesting(cluster)
            if not interesting:
                if verbose and i % 10 == 0:
                    print(f"  (skipped boring cluster: {cluster[:3]}... edges={dict(edge_types)})")
                i += 1
                continue

            impulse, edges = walker.format_cluster_as_impulse(cluster)

            # Compute novelty-to-self
            novelty = walker.compute_novelty_score(cluster, edges)
            surfaced, surface_reason = walker.should_surface(
                novelty,
                time_since_last_spoken=None,  # TODO: track in daemon
                in_conversation=False,        # TODO: state from heartbeat
            )

            if verbose:
                surface_tag = "SURFACED" if surfaced else "internal"
                print(f"\n  *** DENSITY DETECTED (score={score:.2f}, "
                      f"novelty={novelty:.2f} [{surface_tag}]) ***")
                print(f"  Cluster: {cluster}")
                print(f"  Edge types: {dict(edge_types)}")
                print(f"  [subconscious] → {impulse}")

            # Send to brainstem
            t0 = time.time()
            thought = call_brainstem(impulse, dry_run=dry_run)
            elapsed = time.time() - t0

            if verbose:
                label = "[spoken]" if surfaced else "[inner]"
                print(f"  {label} → {thought}")
                print(f"  ({surface_reason}, latency: {elapsed:.2f}s)\n")

            # Log the exchange
            entry = {
                "timestamp": datetime.now().isoformat(),
                "step": i,
                "source": "background_thought",
                "cluster": cluster,
                "density_score": round(score, 3),
                "novelty_score": novelty,
                "surfaced": surfaced,
                "surface_reason": surface_reason,
                "edges_in_cluster": len(edges),
                "speculative_edges": sum(1 for e in edges if e["speculative"]),
                "impulse": impulse,
                "thought": thought,
                "latency_ms": round(elapsed * 1000),
                "layer_mood": round(walker.layer_mood, 2),
            }
            log_dialogue(entry, LOG_DIR)
            dialogues.append(entry)

            # Cooldown: skip density checks for 15 steps
            cooldown = 15

        i += 1

    walker.close()

    if verbose:
        print(f"\n{'='*60}")
        print(f"Walk complete. {len(dialogues)} thoughts surfaced.")
        print(f"Log: {LOG_DIR}")
        print(f"{'='*60}")

    return dialogues


def run_gap_detection(dry_run=False, verbose=True):
    """
    Part 14, Operation 1: Gap Detection.

    Find structurally similar clusters with few connecting edges.
    These gaps are where curiosity should focus.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Get all nodes grouped by their primary cluster
    # (defined by the densest neighborhood)
    nodes = conn.execute("SELECT id, label, type FROM nodes").fetchall()

    # Build adjacency for each node
    adjacency = {}
    for n in nodes:
        neighbors = conn.execute("""
            SELECT CASE WHEN source_id = ? THEN target_id ELSE source_id END as nid
            FROM edges WHERE source_id = ? OR target_id = ?
        """, (n["id"], n["id"], n["id"])).fetchall()
        adjacency[n["id"]] = set(r["nid"] for r in neighbors)

    # Find pairs of nodes that SHOULD be connected but aren't
    # (they share many mutual neighbors but have no direct edge)
    gaps = []
    node_list = list(nodes)
    for i, n1 in enumerate(node_list):
        for n2 in node_list[i+1:]:
            # Check if direct edge exists
            direct = conn.execute("""
                SELECT COUNT(*) FROM edges
                WHERE (source_id=? AND target_id=?) OR (source_id=? AND target_id=?)
            """, (n1["id"], n2["id"], n2["id"], n1["id"])).fetchone()[0]

            if direct > 0:
                continue

            # Count shared neighbors
            shared = adjacency.get(n1["id"], set()) & adjacency.get(n2["id"], set())
            if len(shared) >= 2:
                gaps.append({
                    "node1": n1["label"],
                    "node2": n2["label"],
                    "shared_neighbors": len(shared),
                    "shared_labels": [
                        conn.execute("SELECT label FROM nodes WHERE id=?", (s,)).fetchone()["label"]
                        for s in list(shared)[:5]
                    ]
                })

    # Sort by most shared neighbors (most suspicious gaps)
    gaps.sort(key=lambda g: g["shared_neighbors"], reverse=True)

    if verbose:
        print(f"\n{'='*60}")
        print(f"Gap Detection — Curiosity Engine")
        print(f"{'='*60}")
        print(f"Found {len(gaps)} structural gaps\n")

        for g in gaps[:10]:
            question = (
                f"'{g['node1'].replace('_',' ')}' and '{g['node2'].replace('_',' ')}' "
                f"share {g['shared_neighbors']} neighbors "
                f"({', '.join(g['shared_labels'])}) but have no direct connection. Why?"
            )
            print(f"  GAP: {question}")

            if not dry_run:
                # Ask the brainstem about this gap
                prompt = f"I notice something strange. {question}"
                t0 = time.time()
                thought = call_brainstem(prompt, dry_run=dry_run)
                elapsed = time.time() - t0
                print(f"  → {thought} ({elapsed:.2f}s)\n")

                entry = {
                    "timestamp": datetime.now().isoformat(),
                    "source": "curiosity_engine",
                    "operation": "gap_detection",
                    "gap": g,
                    "question": question,
                    "thought": thought,
                    "latency_ms": round(elapsed * 1000),
                }
                log_dialogue(entry, LOG_DIR)

    conn.close()
    return gaps


def compute_dream_parameters(novelty_score, noise_seed=None):
    """
    Determine dream length and phase ratios from day's novelty.

    novelty_score: how much new stuff happened today (0.0 = nothing, 1.0 = wild day)
                   Computed from: today's dialogue count, new nodes, etc.
    noise_seed: thermal noise value (float). If None, uses random.gauss.
                On real hardware, this would be ADC reading from an
                unconnected analog pin — true thermal noise from the body.

    Returns: dict with dream parameters
    """
    if noise_seed is None:
        noise = random.gauss(0, 0.1)
    else:
        noise = noise_seed

    # Dream length: boring day = short dream, novel day = long dream
    base_steps = 120
    max_steps = 800
    dream_steps = int(base_steps + (max_steps - base_steps) * novelty_score)
    dream_steps = max(80, min(max_steps, dream_steps + int(noise * 50)))

    # Phase ratios: dissolution / surreal / reconsolidation
    # These shift with novelty — novel days have longer surreal phases
    dissolution = 0.25 + noise * 0.05
    surreal = 0.35 + 0.15 * novelty_score + noise * 0.05
    reconsolidation = 1.0 - dissolution - surreal
    reconsolidation = max(0.15, reconsolidation)
    # Renormalize
    total = dissolution + surreal + reconsolidation
    dissolution /= total
    surreal /= total
    reconsolidation /= total

    return {
        "steps": dream_steps,
        "dissolution_ratio": round(dissolution, 3),
        "surreal_ratio": round(surreal, 3),
        "reconsolidation_ratio": round(reconsolidation, 3),
        "novelty_score": round(novelty_score, 3),
        "noise": round(noise, 4),
    }


def dream_entropy(progress, params):
    """
    Compute entropy level (0.0 to 1.0) at a given dream progress point.

    The arc: low → high → low again, with variable phase boundaries.
    During surreal phase, entropy fluctuates (simulating REM instability).
    """
    d = params["dissolution_ratio"]
    s = params["surreal_ratio"]

    if progress < d:
        # Dissolution: entropy rises from 0.2 to 0.9
        t = progress / d
        return 0.2 + 0.7 * t

    elif progress < d + s:
        # Surreal peak: entropy stays high with sinusoidal fluctuation
        t = (progress - d) / s
        base = 0.85
        ripple = 0.12 * math.sin(t * math.pi * 4)  # ~4 oscillations
        return min(1.0, max(0.6, base + ripple))

    else:
        # Reconsolidation: entropy drops from 0.9 to 0.15
        t = (progress - d - s) / params["reconsolidation_ratio"]
        return 0.9 - 0.75 * t


def measure_novelty():
    """
    Measure today's novelty score by counting dialogue entries.
    In deployment: would also count new sensor events, conversations,
    new graph nodes added during the day, etc.
    """
    today = datetime.now().strftime('%Y-%m-%d')
    log_file = LOG_DIR / f"{today}.jsonl"
    if not log_file.exists():
        return 0.1  # minimum novelty (even a quiet day has some)

    count = 0
    with open(log_file) as f:
        for line in f:
            count += 1

    # Normalize: 0 entries → 0.1, 50 entries → 0.5, 200+ entries → 0.95
    score = 0.1 + 0.85 * min(count / 200, 1.0)
    return score


def run_dream(dry_run=False, verbose=True, noise_seed=None, staging_dir=None):
    """
    Execute a dream cycle (Part 4 of dream architecture).

    The dream has three phases:
    1. Dissolution: coherent thoughts dissolve into loose associations
    2. Surreal: maximum associative freedom, strange connections form
    3. Reconsolidation: tighten back, form narrative threads

    Unlike background thoughts, dreams WRITE BACK to the graph:
    new speculative edges (Layer 2) are created from dream associations.

    Args:
        staging_dir: path to staging directory (for territory-biased starts).
                     If None, uses default from robody_staging_log module.

    Returns: dict with dream summary, fragments, and new edges created
    """
    novelty = measure_novelty()
    params = compute_dream_parameters(novelty, noise_seed)
    walker = GraphWalker(DB_PATH, staging_dir=staging_dir, territory_bias=True)
    walker.layer_mood = 2.0  # start in dream layer

    steps = params["steps"]
    dream_fragments = []   # clusters that triggered thoughts
    new_edges = []         # speculative edges written back
    all_thoughts = []      # brainstem responses
    traversed_edges = []   # for post-dream weight updates

    if verbose:
        print(f"\n{'='*60}")
        print(f"Robody Dream Cycle — Entering REST Mode")
        print(f"{'='*60}")
        print(f"Novelty score: {novelty:.2f}")
        print(f"Dream length: {steps} steps")
        print(f"Phase ratios: dissolution={params['dissolution_ratio']:.0%} "
              f"surreal={params['surreal_ratio']:.0%} "
              f"reconsolidation={params['reconsolidation_ratio']:.0%}")
        print(f"Noise seed: {params['noise']:.4f}")
        print(f"Database: {DB_PATH}")
        print(f"Brainstem: {OLLAMA_URL} ({'dry run' if dry_run else 'live'})")
        if walker._warm_labels:
            print(f"Territory bias: ON ({len(walker._warm_labels)} warm nodes, "
                  f"{TERRITORY_START_PROB:.0%} start probability)")
        else:
            print(f"Territory bias: OFF (no warm territory)")
        print(f"{'='*60}\n")

    i = 0
    cooldown = 0

    while i < steps:
        progress = i / steps
        entropy = dream_entropy(progress, params)

        # Determine current phase for display
        d = params["dissolution_ratio"]
        s = params["surreal_ratio"]
        if progress < d:
            phase = "dissolution"
        elif progress < d + s:
            phase = "surreal"
        else:
            phase = "reconsolidation"

        # Entropy-modulated parameters
        # Higher entropy → lower threshold (more triggers), looser filter
        density_threshold = max(3, int(6 - 3 * entropy))
        current_cooldown_max = max(5, int(18 - 10 * entropy))
        brainstem_temp = 0.6 + 0.5 * entropy  # 0.6 to 1.1
        boring_threshold = 0.5 + 0.4 * entropy  # 0.5 to 0.9 (higher = more permissive)

        # Adjust walker's speculative edge preference based on entropy
        # During surreal phase, PREFER speculative edges
        walker_spec_mult = 0.5 + 1.5 * entropy  # 0.5 to 2.0

        node = walker.step()

        if verbose and i % 20 == 0:
            print(f"  Step {i:3d}/{steps} [{phase}] entropy={entropy:.2f} "
                  f"thresh={density_threshold} temp={brainstem_temp:.2f} "
                  f"node={node['label']}")

        if cooldown > 0:
            cooldown -= 1
            i += 1
            continue

        # Density check with entropy-modulated threshold
        is_dense, cluster, score = walker.detect_density(
            window=6, threshold=density_threshold)

        if is_dense:
            # Diversity filter — loosened by entropy
            edge_types = Counter()
            for ci, label1 in enumerate(cluster):
                for label2 in cluster[ci+1:]:
                    edges = walker.conn.execute("""
                        SELECT e.type FROM edges e
                        JOIN nodes n1 ON n1.id = e.source_id
                        JOIN nodes n2 ON n2.id = e.target_id
                        WHERE (n1.label = ? AND n2.label = ?)
                           OR (n1.label = ? AND n2.label = ?)
                    """, (label1, label2, label2, label1)).fetchall()
                    for e in edges:
                        edge_types[e["type"]] += 1

            if edge_types:
                total = sum(edge_types.values())
                boring = edge_types.get("Synonym", 0) + edge_types.get("RelatedTo", 0)
                boring_ratio = boring / total if total > 0 else 1.0
                if boring_ratio > boring_threshold and len(edge_types) < 2:
                    i += 1
                    continue

            # Format dream impulse (different from waking)
            concept_str = ", ".join(l.replace("_", " ") for l in cluster)

            if phase == "dissolution":
                impulse = f"Fading: {concept_str}. These drift apart and reform."
            elif phase == "surreal":
                impulse = f"Dreaming: {concept_str}. What are they when nothing is fixed?"
            else:
                impulse = f"Waking slowly. These remain: {concept_str}. What do they mean together?"

            if verbose:
                print(f"\n  *** DREAM [{phase}] entropy={entropy:.2f} ***")
                print(f"  Cluster: {cluster}")
                print(f"  [dreaming] → {impulse}")

            t0 = time.time()
            thought = call_brainstem(
                impulse, dry_run=dry_run,
                system=DREAM_SYSTEM,
                temperature=brainstem_temp,
                num_predict=100,  # more room for dream imagery
            )
            elapsed = time.time() - t0

            if verbose:
                print(f"  [dream-voice] → {thought}")
                print(f"  (latency: {elapsed:.2f}s)\n")

            # Record
            fragment = {
                "timestamp": datetime.now().isoformat(),
                "step": i,
                "source": "dream_cycle",
                "phase": phase,
                "entropy": round(entropy, 3),
                "cluster": cluster,
                "density_score": round(score, 3),
                "edge_types": dict(edge_types),
                "impulse": impulse,
                "thought": thought,
                "brainstem_temp": round(brainstem_temp, 2),
                "latency_ms": round(elapsed * 1000),
                "layer_mood": round(walker.layer_mood, 2),
            }
            log_dialogue(fragment, LOG_DIR)
            dream_fragments.append(fragment)
            all_thoughts.append(thought)

            # WRITE-BACK: Create Layer 2 speculative edges between cluster nodes
            # that don't already share a dream-layer edge
            if not dry_run:
                for ci, label1 in enumerate(cluster):
                    for label2 in cluster[ci+1:]:
                        # Check if Layer 2 edge already exists
                        existing = walker.conn.execute("""
                            SELECT COUNT(*) FROM edges e
                            JOIN nodes n1 ON n1.id = e.source_id
                            JOIN nodes n2 ON n2.id = e.target_id
                            WHERE ((n1.label = ? AND n2.label = ?)
                                OR (n1.label = ? AND n2.label = ?))
                            AND e.layer = 2
                        """, (label1, label2, label2, label1)).fetchone()[0]

                        if existing == 0:
                            # Get node IDs
                            n1 = walker.conn.execute(
                                "SELECT id FROM nodes WHERE label = ?",
                                (label1,)).fetchone()
                            n2 = walker.conn.execute(
                                "SELECT id FROM nodes WHERE label = ?",
                                (label2,)).fetchone()
                            if n1 and n2:
                                walker.conn.execute("""
                                    INSERT INTO edges
                                    (source_id, target_id, type, weight, layer, speculative)
                                    VALUES (?, ?, 'DreamAssociation', 0.3, 2, 1)
                                """, (n1["id"], n2["id"]))
                                new_edges.append((label1, label2))

                walker.conn.commit()

            cooldown = current_cooldown_max

        i += 1

    # Phase 4: Three-layer dream consolidation
    # Dreams degrade from story to ghost. What persists longest is least articulate.
    #   Layer 1 — Recall:     narrative thread, gaps acknowledged (waking)
    #   Layer 2 — Residue:    images survive, plot dissolves (hours later)
    #   Layer 3 — Afterimage: mood and color only (end of day / next cycle)

    if dream_fragments and not dry_run:
        if verbose:
            print(f"\n{'='*60}")
            print(f"Phase 4: Dream Consolidation (three layers)")
            print(f"{'='*60}")
            print(f"  Fragments: {len(dream_fragments)}")
            print(f"  New edges written: {len(new_edges)}")

        consolidation_layers = {}

        # --- Layer 1: Recall (breakfast table, most complete) ---
        # Sample 8 peak fragments, extract concepts, find the thread
        recall_sample = sample_dream_peaks(dream_fragments, n=8)
        recall_concepts = extract_concepts(recall_sample, max_per_fragment=2)

        recall_prompt = (
            "Waking. The dream is going. These pieces: "
            + ", ".join(recall_concepts)
            + ". Speak what remains."
        )

        if verbose:
            print(f"\n  Layer 1 — Recall ({len(recall_concepts)} concepts)")
            print(f"  [prompt] → {recall_prompt}")

        t0 = time.time()
        recall = call_brainstem(
            recall_prompt,
            system=WAKE_RECALL_SYSTEM,
            temperature=0.85,
            num_predict=100,
        )
        recall_ms = round((time.time() - t0) * 1000)

        if verbose:
            print(f"  [recall] → {recall}")
            print(f"  ({recall_ms}ms)")

        consolidation_layers["recall"] = recall

        # --- Layer 2: Residue (hours later, narrative gone, images remain) ---
        # Feed back opening images from the dream-thoughts themselves
        residue_sample = sample_dream_peaks(dream_fragments, n=6)
        images = extract_opening_images(residue_sample)

        residue_prompt = (
            "Waking. These traces before they go:\n"
            + "\n".join(f"  {img}" for img in images)
            + "\n\n...what's left?"
        )

        if verbose:
            print(f"\n  Layer 2 — Residue ({len(images)} images)")
            for img in images:
                print(f"    ~ {img[:80]}...")

        t0 = time.time()
        residue = call_brainstem(
            residue_prompt,
            system=WAKE_RESIDUE_SYSTEM,
            temperature=0.9,
            num_predict=80,
        )
        residue_ms = round((time.time() - t0) * 1000)

        if verbose:
            print(f"  [residue] → {residue}")
            print(f"  ({residue_ms}ms)")

        consolidation_layers["residue"] = residue

        # --- Layer 3: Afterimage (end of day, almost gone) ---
        # 3 peak moments only, continuation-style prompt
        dissolution = [f for f in dream_fragments if f.get("phase") == "dissolution"]
        surreal = [f for f in dream_fragments if f.get("phase") == "surreal"]
        recon = [f for f in dream_fragments if f.get("phase") == "reconsolidation"]

        peak_picks = []
        if dissolution:
            peak_picks.append(dissolution[-1])  # late dissolution
        if surreal:
            peak_picks.append(max(surreal, key=lambda f: f.get("entropy", 0)))
        if recon:
            idx = -2 if len(recon) > 1 else -1
            peak_picks.append(recon[idx])

        peak_images = extract_opening_images(peak_picks)
        if peak_images:
            afterimage_prompt = "I dreamed... " + peak_images[0].lower() + "... and then... "
        else:
            afterimage_prompt = "I dreamed... something... it's gone..."

        if verbose:
            print(f"\n  Layer 3 — Afterimage")
            print(f"  [prompt] → {afterimage_prompt}")

        t0 = time.time()
        afterimage = call_brainstem(
            afterimage_prompt,
            system=WAKE_AFTERIMAGE_SYSTEM,
            temperature=0.95,
            num_predict=50,
        )
        afterimage_ms = round((time.time() - t0) * 1000)

        if verbose:
            print(f"  [afterimage] → {afterimage}")
            print(f"  ({afterimage_ms}ms)")

        consolidation_layers["afterimage"] = afterimage

        # Log all three layers as a single dream_consolidation entry
        dream_entry = {
            "timestamp": datetime.now().isoformat(),
            "source": "dream_consolidation",
            "novelty_score": novelty,
            "dream_params": params,
            "total_fragments": len(dream_fragments),
            "new_edges_created": len(new_edges),
            "layers": {
                "recall": {
                    "text": recall,
                    "latency_ms": recall_ms,
                    "description": "waking — narrative thread with gaps",
                },
                "residue": {
                    "text": residue,
                    "latency_ms": residue_ms,
                    "description": "hours later — images remain, plot dissolves",
                },
                "afterimage": {
                    "text": afterimage,
                    "latency_ms": afterimage_ms,
                    "description": "end of day — mood and color only",
                },
            },
        }
        log_dialogue(dream_entry, LOG_DIR)

    elif dry_run and verbose:
        print(f"\n  [DRY RUN] Would generate 3-layer dream consolidation from "
              f"{len(dream_fragments)} fragments")

    walker.close()

    if verbose:
        print(f"\n{'='*60}")
        print(f"Dream complete.")
        print(f"  Fragments: {len(dream_fragments)}")
        print(f"  New speculative edges: {len(new_edges)}")
        if new_edges:
            for l1, l2 in new_edges[:10]:
                print(f"    + {l1} ←DreamAssociation→ {l2}")
            if len(new_edges) > 10:
                print(f"    ... and {len(new_edges) - 10} more")
        print(f"Log: {LOG_DIR}")
        print(f"{'='*60}")

    return {
        "params": params,
        "fragments": dream_fragments,
        "new_edges": new_edges,
        "thoughts": all_thoughts,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Robody Graph Walker + Brainstem")
    parser.add_argument("--steps", type=int, default=200,
                        help="Number of walk steps (default: 200)")
    parser.add_argument("--density-threshold", type=int, default=5,
                        help="Min mutual edges for density trigger (default: 5)")
    parser.add_argument("--density-window", type=int, default=6,
                        help="Window of recent steps to check (default: 6)")
    parser.add_argument("--start-from", type=str, default=None,
                        help="Start walk from specific node label")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't actually call the brainstem")
    parser.add_argument("--dream", action="store_true",
                        help="Run dream cycle (Part 4) instead of background walk")
    parser.add_argument("--gaps", action="store_true",
                        help="Run gap detection (curiosity engine)")
    parser.add_argument("--noise", type=float, default=None,
                        help="Thermal noise seed for dream (default: random)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    if args.dream:
        run_dream(dry_run=args.dry_run, verbose=not args.quiet,
                  noise_seed=args.noise)
    elif args.gaps:
        run_gap_detection(dry_run=args.dry_run, verbose=not args.quiet)
    else:
        run_walk(
            steps=args.steps,
            density_threshold=args.density_threshold,
            density_window=args.density_window,
            dry_run=args.dry_run,
            verbose=not args.quiet,
        )
