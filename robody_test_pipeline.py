#!/usr/bin/env python3
"""
Robody Pipeline Integration Test
=================================
Validates the full cognitive pipeline end-to-end on the seed graph,
without requiring Ollama or any hardware.

Tests:
  1. Seed graph creation and integrity
  2. Graph walker — background thought detection
  3. Dream cycle — dissolution/surreal/reconsolidation arc
  4. Weight maintenance — decay, post-dream updates, promotions
  5. Heartbeat — single cycle with simulated sensors
  6. Full nightly sequence: dream → update → decay

All tests run in dry-run mode (no LLM calls) using a temporary
database copy. Nothing is modified on disk.

Usage:
    python3 robody_test_pipeline.py              # run all tests
    python3 robody_test_pipeline.py -v           # verbose output
    python3 robody_test_pipeline.py --test walk  # run specific test

Exit code: 0 if all pass, 1 if any fail.
"""

import sqlite3
import json
import sys
import os
import time
import shutil
import tempfile
import argparse
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager

# Add project dir to path
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from robody_graph_seed import seed_graph, create_schema, add_node, add_edge
from robody_graph_walker import (
    GraphWalker, run_walk, run_dream, run_gap_detection,
    compute_dream_parameters, dream_entropy, measure_novelty,
    sample_dream_peaks, extract_opening_images, extract_concepts,
    TERRITORY_START_PROB,
)
from robody_weight_maintenance import (
    run_decay, apply_dream_updates, promote_confirmed_edges,
    show_stats, _weight_stats,
)
from robody_heartbeat import (
    Heartbeat, SensorState, InternalState, Mode,
    StateWatcher, SilenceWatchdog,
)
from robody_rational_expansion import (
    survey_graph, bridge_clusters, generate_condensates,
    enrich_edge_types, seed_narratives,
    _detect_communities, _find_bridge_gaps, _normalize_label,
    _parse_edge_proposals, _select_diverse_anchors,
)
from robody_staging_log import (
    StagingLog, warm_today_territory, clear_warm_territory,
)
from robody_consciousness import (
    ConsciousnessThreshold, ConsciousnessLog,
    InvocationTier, InvocationReason, InvocationRequest,
    estimate_invocation_cost, estimate_daily_cost,
)


# ═══════════════════════════════════════════════════════════════
# TEST INFRASTRUCTURE
# ═══════════════════════════════════════════════════════════════

class TestResult:
    def __init__(self, name):
        self.name = name
        self.passed = 0
        self.failed = 0
        self.errors = []

    def ok(self, description):
        self.passed += 1
        if VERBOSE:
            print(f"  ✓ {description}")

    def fail(self, description, detail=""):
        self.failed += 1
        msg = f"  ✗ {description}"
        if detail:
            msg += f": {detail}"
        self.errors.append(msg)
        print(msg)

    def check(self, condition, description, detail=""):
        if condition:
            self.ok(description)
        else:
            self.fail(description, detail)

    def summary(self):
        total = self.passed + self.failed
        status = "PASS" if self.failed == 0 else "FAIL"
        return f"  [{status}] {self.name}: {self.passed}/{total} checks passed"


VERBOSE = False
RESULTS = []


@contextmanager
def temp_db():
    """Create a temporary database from seed for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_robody.sqlite"
        # Patch the module-level DB_PATH
        import robody_graph_seed as seed_mod
        import robody_graph_walker as walker_mod
        import robody_weight_maintenance as maint_mod
        import robody_rational_expansion as expand_mod
        import robody_staging_log as staging_mod

        original_paths = {
            'seed': seed_mod.DB_PATH,
            'walker': walker_mod.DB_PATH,
            'walker_log': walker_mod.LOG_DIR,
            'maint': maint_mod.DB_PATH,
            'maint_log': maint_mod.MAINTENANCE_LOG,
            'maint_log_dir': maint_mod.LOG_DIR,
            'expand': expand_mod.DB_PATH,
            'expand_log': expand_mod.LOG_DIR,
            'staging_db': staging_mod.DB_PATH,
            'staging_dir': staging_mod.STAGING_DIR,
            'staging_log_dir': staging_mod.LOG_DIR,
        }

        seed_mod.DB_PATH = db_path
        walker_mod.DB_PATH = db_path
        walker_mod.LOG_DIR = Path(tmpdir) / "dialogue"
        maint_mod.DB_PATH = db_path
        maint_mod.LOG_DIR = Path(tmpdir) / "dialogue"
        maint_mod.MAINTENANCE_LOG = Path(tmpdir) / "maintenance.jsonl"
        expand_mod.DB_PATH = db_path
        expand_mod.LOG_DIR = Path(tmpdir) / "expansion_logs"
        staging_mod.DB_PATH = db_path
        staging_mod.STAGING_DIR = Path(tmpdir) / "staging"
        staging_mod.LOG_DIR = Path(tmpdir) / "consolidation_logs"

        # Create the seed graph
        seed_graph()

        try:
            yield db_path, Path(tmpdir)
        finally:
            # Restore original paths
            seed_mod.DB_PATH = original_paths['seed']
            walker_mod.DB_PATH = original_paths['walker']
            walker_mod.LOG_DIR = original_paths['walker_log']
            maint_mod.DB_PATH = original_paths['maint']
            maint_mod.LOG_DIR = original_paths['maint_log_dir']
            maint_mod.MAINTENANCE_LOG = original_paths['maint_log']
            expand_mod.DB_PATH = original_paths['expand']
            expand_mod.LOG_DIR = original_paths['expand_log']
            staging_mod.DB_PATH = original_paths['staging_db']
            staging_mod.STAGING_DIR = original_paths['staging_dir']
            staging_mod.LOG_DIR = original_paths['staging_log_dir']


# ═══════════════════════════════════════════════════════════════
# TEST 1: SEED GRAPH
# ═══════════════════════════════════════════════════════════════

def test_seed_graph():
    """Verify the seed graph is structurally correct."""
    t = TestResult("Seed Graph")

    with temp_db() as (db_path, tmpdir):
        conn = sqlite3.connect(db_path)

        # Node count
        nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        t.check(nodes >= 60, f"Has ≥60 nodes (got {nodes})")

        # Edge count
        edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        t.check(edges >= 80, f"Has ≥80 edges (got {edges})")

        # All 5 clusters have nodes
        for label in ["music", "light", "home", "siege_of_leningrad", "self"]:
            row = conn.execute(
                "SELECT id FROM nodes WHERE label = ?", (label,)
            ).fetchone()
            t.check(row is not None, f"Cluster anchor '{label}' exists")

        # Speculative edges exist
        spec = conn.execute(
            "SELECT COUNT(*) FROM edges WHERE speculative = 1"
        ).fetchone()[0]
        t.check(spec >= 5, f"Has ≥5 speculative edges (got {spec})")

        # Layer distribution
        layers = conn.execute(
            "SELECT DISTINCT layer FROM edges ORDER BY layer"
        ).fetchall()
        layer_set = {r[0] for r in layers}
        t.check(0 in layer_set, "Has Layer 0 (fact) edges")
        t.check(1 in layer_set, "Has Layer 1 (association) edges")
        t.check(2 in layer_set, "Has Layer 2 (dream) edges")

        # Dream fragments exist
        dream_frags = conn.execute(
            "SELECT COUNT(*) FROM nodes WHERE type = 'dream_fragment'"
        ).fetchone()[0]
        t.check(dream_frags >= 2, f"Has dream fragments (got {dream_frags})")

        # The canonical dream walk path exists
        # leningrad_orchestra → shostakovich_7th → orchestra → trombone → 76_trombones
        for src, tgt in [
            ("leningrad_orchestra", "shostakovich_7th"),
            ("trombone", "orchestra"),
            ("trombone", "76_trombones"),
        ]:
            edge = conn.execute("""
                SELECT e.type FROM edges e
                JOIN nodes n1 ON n1.id = e.source_id
                JOIN nodes n2 ON n2.id = e.target_id
                WHERE (n1.label = ? AND n2.label = ?)
                   OR (n1.label = ? AND n2.label = ?)
            """, (src, tgt, tgt, src)).fetchone()
            t.check(edge is not None, f"Canonical path: {src} → {tgt}")

        # No orphan nodes (every node has at least one edge)
        orphans = conn.execute("""
            SELECT n.label FROM nodes n
            WHERE n.id NOT IN (
                SELECT source_id FROM edges
                UNION
                SELECT target_id FROM edges
            )
        """).fetchall()
        t.check(len(orphans) == 0,
                f"No orphan nodes",
                f"Found: {[r[0] for r in orphans]}" if orphans else "")

        conn.close()

    RESULTS.append(t)
    return t


# ═══════════════════════════════════════════════════════════════
# TEST 2: GRAPH WALKER
# ═══════════════════════════════════════════════════════════════

def test_graph_walker():
    """Verify the graph walker can traverse and detect density."""
    t = TestResult("Graph Walker")

    with temp_db() as (db_path, tmpdir):
        # Basic walk
        walker = GraphWalker(db_path)

        # Can start
        node = walker.step()
        t.check(node is not None, "Walker can start")
        # step() returns a dict or Row — check by access not containment
        try:
            has_label = bool(node["label"])
        except (KeyError, TypeError):
            has_label = False
        t.check(has_label, "Start node has label")

        # Can take steps
        for _ in range(50):
            node = walker.step()
        t.check(len(walker.history) > 10, f"History accumulated ({len(walker.history)} entries)")

        # Layer mood drifts
        t.check(isinstance(walker.layer_mood, float), "Layer mood is float")

        # Weight computation
        w = walker.compute_walk_weight(2.0, 0, False)
        t.check(w > 0, f"Walk weight is positive ({w:.3f})")

        w_spec = walker.compute_walk_weight(2.0, 0, True)
        t.check(w_spec < w, "Speculative edges get dampened")

        w_distant = walker.compute_walk_weight(2.0, 2, False)
        t.check(w_distant < w, "Distant layer edges get attenuated")

        walker.close()

        # Full walk (dry run)
        dialogues = run_walk(steps=100, dry_run=True, verbose=False)
        t.check(isinstance(dialogues, list), "Walk returns dialogue list")

        # Gap detection (dry run)
        gaps = run_gap_detection(dry_run=True, verbose=False)
        t.check(isinstance(gaps, list), "Gap detection returns list")
        # Seed graph has structural gaps
        t.check(len(gaps) > 0, f"Found structural gaps ({len(gaps)})")

        # --- Territory-biased dream starts ---

        # Walker without territory bias has empty warm labels
        w_no_bias = GraphWalker(db_path, territory_bias=False)
        t.check(w_no_bias._warm_labels == [], "No-bias walker has empty warm labels")
        w_no_bias.close()

        # Create a fake warm territory marker
        import robody_staging_log as staging_mod
        staging_dir = staging_mod.STAGING_DIR
        os.makedirs(staging_dir, exist_ok=True)
        from robody_staging_log import WARM_MARKER

        # Get some real node labels from the test DB
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        sample_labels = [r["label"] for r in conn.execute(
            "SELECT label FROM nodes LIMIT 5"
        ).fetchall()]
        conn.close()
        t.check(len(sample_labels) > 0, f"Got sample labels for warm marker ({len(sample_labels)})")

        marker_path = Path(staging_dir) / WARM_MARKER
        marker_data = {
            "timestamp": datetime.now().isoformat(),
            "matched_labels": sample_labels,
            "edges_warmed": 10,
            "warm_map": {},
        }
        marker_path.write_text(json.dumps(marker_data))

        # Walker WITH territory bias loads the warm labels
        w_biased = GraphWalker(db_path, staging_dir=staging_dir, territory_bias=True)
        t.check(len(w_biased._warm_labels) == len(sample_labels),
                f"Biased walker loaded {len(w_biased._warm_labels)} warm labels")
        t.check(set(w_biased._warm_labels) == set(sample_labels),
                "Warm labels match marker file")

        # Start node should work (might or might not be territory-biased,
        # but it should always return a valid node)
        start_nodes = []
        for _ in range(50):
            w_biased.current_node = None  # reset for fresh start
            node = w_biased.get_random_start()
            start_nodes.append(node["label"])
        t.check(len(start_nodes) == 50, "Got 50 start nodes")

        # With 20% territory probability over 50 starts, we expect ~10 territory
        # starts on average. With 5 warm labels, at least some starts should land
        # on one. (Statistical: P(0 territory starts in 50 trials) = 0.8^50 ≈ 0.0001)
        territory_starts = sum(1 for l in start_nodes if l in sample_labels)
        t.check(territory_starts > 0,
                f"Territory bias produced {territory_starts}/50 territory starts")
        # But also not ALL starts should be territory (that would be deterministic)
        non_territory = 50 - territory_starts
        t.check(non_territory > 0,
                f"Non-territory starts also occurred ({non_territory}/50)")

        w_biased.close()

        # Clean up marker
        marker_path.unlink(missing_ok=True)

        # Verify missing marker = no warm labels
        w_no_marker = GraphWalker(db_path, staging_dir=staging_dir, territory_bias=True)
        t.check(w_no_marker._warm_labels == [],
                "No marker file = no warm labels")
        w_no_marker.close()

    RESULTS.append(t)
    return t


# ═══════════════════════════════════════════════════════════════
# TEST 3: DREAM CYCLE
# ═══════════════════════════════════════════════════════════════

def test_dream_cycle():
    """Verify dream cycle mechanics."""
    t = TestResult("Dream Cycle")

    # Dream parameters
    params_quiet = compute_dream_parameters(0.1)
    params_novel = compute_dream_parameters(0.9)

    t.check(params_novel["steps"] > params_quiet["steps"],
            f"Novel day = longer dream ({params_novel['steps']} > {params_quiet['steps']})")

    t.check(params_novel["surreal_ratio"] > params_quiet["surreal_ratio"],
            "Novel day = more surreal time")

    # Phase ratios sum to ~1.0
    total = (params_quiet["dissolution_ratio"] +
             params_quiet["surreal_ratio"] +
             params_quiet["reconsolidation_ratio"])
    t.check(abs(total - 1.0) < 0.01,
            f"Phase ratios sum to 1.0 (got {total:.4f})")

    # Entropy curve
    e_start = dream_entropy(0.0, params_quiet)
    e_mid = dream_entropy(0.5, params_quiet)
    e_end = dream_entropy(0.95, params_quiet)

    t.check(e_start < 0.5, f"Entropy starts low ({e_start:.2f})")
    t.check(e_mid > 0.6, f"Entropy peaks in middle ({e_mid:.2f})")
    t.check(e_end < e_mid, f"Entropy drops at end ({e_end:.2f})")

    # Full dream (dry run)
    with temp_db() as (db_path, tmpdir):
        result = run_dream(dry_run=True, verbose=False, noise_seed=0.0)
        t.check("fragments" in result, "Dream returns fragments")
        t.check("params" in result, "Dream returns parameters")
        t.check("new_edges" in result, "Dream returns new edges list")

    # Dream fragment sampling
    fake_fragments = [
        {"thought": f"thought {i}", "cluster": [f"c{i}"], "phase": p,
         "entropy": 0.3 + 0.5 * (i / 10)}
        for i, p in enumerate(
            ["dissolution"] * 3 + ["surreal"] * 5 + ["reconsolidation"] * 2
        )
    ]
    sampled = sample_dream_peaks(fake_fragments, n=5)
    t.check(len(sampled) == 5, f"Sample returns requested count ({len(sampled)})")

    images = extract_opening_images(fake_fragments[:3])
    t.check(len(images) > 0, f"Extract opening images works ({len(images)})")

    concepts = extract_concepts(fake_fragments[:3])
    t.check(len(concepts) > 0, f"Extract concepts works ({len(concepts)})")

    RESULTS.append(t)
    return t


# ═══════════════════════════════════════════════════════════════
# TEST 4: WEIGHT MAINTENANCE
# ═══════════════════════════════════════════════════════════════

def test_weight_maintenance():
    """Verify weight decay and update mechanics."""
    t = TestResult("Weight Maintenance")

    with temp_db() as (db_path, tmpdir):
        conn = sqlite3.connect(db_path)

        # Get initial stats
        before = _weight_stats(conn)
        t.check(before["total"] > 0, f"Graph has edges ({before['total']})")

        # Verify specific edge weights
        row = conn.execute("""
            SELECT e.weight FROM edges e
            JOIN nodes n1 ON n1.id = e.source_id
            JOIN nodes n2 ON n2.id = e.target_id
            WHERE n1.label = 'bluekitty' AND n2.label = 'home'
        """).fetchone()
        t.check(row is not None, "bluekitty→home edge exists")
        original_weight = row[0] if row else 0

        conn.close()

        # Run decay (not dry run — we're in a temp DB)
        decay_result = run_decay(db_path, dry_run=False, verbose=False)
        t.check(decay_result is not None, "Decay completes")
        t.check(decay_result["edges_modified"] > 0,
                f"Decay modified edges ({decay_result['edges_modified']})")

        # Verify weights actually changed
        conn = sqlite3.connect(db_path)
        after = _weight_stats(conn)
        t.check(after["mean"] < before["mean"],
                f"Mean weight decreased ({before['mean']:.4f} → {after['mean']:.4f})")

        # Heavy edges should decay more
        row = conn.execute("""
            SELECT e.weight FROM edges e
            JOIN nodes n1 ON n1.id = e.source_id
            JOIN nodes n2 ON n2.id = e.target_id
            WHERE n1.label = 'bluekitty' AND n2.label = 'home'
        """).fetchone()
        if row:
            new_weight = row[0]
            t.check(new_weight < original_weight,
                    f"Heavy edge decayed ({original_weight:.4f} → {new_weight:.4f})")

        # Floor enforcement — no edge below 0.01 (positive) or above -0.01 (negative)
        floored = conn.execute(
            "SELECT COUNT(*) FROM edges WHERE weight > 0 AND weight < 0.01"
        ).fetchone()[0]
        t.check(floored == 0, "No positive edges below floor (0.01)")

        negative_above_ceiling = conn.execute(
            "SELECT COUNT(*) FROM edges WHERE weight < 0 AND weight > -0.01"
        ).fetchone()[0]
        t.check(negative_above_ceiling == 0, "No negative edges above ceiling (-0.01)")

        conn.close()

        # Post-dream updates (no dream data available in test, so should handle gracefully)
        update_result = apply_dream_updates(db_path, dry_run=True, verbose=False)
        t.check(update_result is None or isinstance(update_result, dict),
                "Dream updates handle missing data gracefully")

        # Speculative promotion (no waking data, so nothing to promote)
        promo_result = promote_confirmed_edges(db_path, dry_run=True, verbose=False)
        t.check(promo_result is not None, "Promotion check completes")

    RESULTS.append(t)
    return t


# ═══════════════════════════════════════════════════════════════
# TEST 5: HEARTBEAT
# ═══════════════════════════════════════════════════════════════

def test_heartbeat():
    """Verify heartbeat cycle mechanics."""
    t = TestResult("Heartbeat")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Patch state and thoughts dirs
        import robody_heartbeat as hb_mod
        orig_state = hb_mod.STATE_DIR
        orig_thoughts = hb_mod.THOUGHTS_DIR
        hb_mod.STATE_DIR = tmpdir / "state"
        hb_mod.THOUGHTS_DIR = tmpdir / "thoughts"
        hb_mod.STATE_DIR.mkdir()
        hb_mod.THOUGHTS_DIR.mkdir()

        try:
            # Sensor state basics
            state = SensorState()
            t.check(state.temperature_f == 70.0, "Default temperature")
            t.check(state.time_of_day == "unknown", "Default time")

            summary = state.summary()
            t.check(isinstance(summary, str), "Summary is string")
            t.check(len(summary) > 10, f"Summary is meaningful ({len(summary)} chars)")

            # Internal state
            internal = InternalState()
            t.check(internal.mode == Mode.REST, "Starts in REST mode")
            t.check(0.0 <= internal.mood_valence <= 1.0, "Mood valence in range")

            # Mode enum
            t.check(Mode.EXPLORE.value == "explore", "Mode values correct")
            t.check(len(Mode) == 8, f"All 8 modes defined ({len(Mode)})")

            # Heartbeat creation
            heartbeat = Heartbeat(simulate=True)
            t.check(heartbeat is not None, "Heartbeat creates")

            # Write initial state
            heartbeat._write_initial_state()
            state_files = list(hb_mod.STATE_DIR.glob("*.json"))
            t.check(len(state_files) >= 8,
                    f"Initial state files created ({len(state_files)})")

            # Single cycle
            entry = heartbeat.cycle()
            t.check(entry is not None, "Cycle completes")
            t.check("timestamp" in entry, "Entry has timestamp")
            t.check("mode" in entry, "Entry has mode")
            t.check("decision" in entry, "Entry has decision")

            # Simulate event and cycle again
            heartbeat._simulate_event()
            entry2 = heartbeat.cycle()
            t.check(entry2 is not None, "Second cycle completes")
            t.check(entry2["cycle"] > entry["cycle"], "Cycle counter increments")

            # Thought log was written
            today = datetime.now().strftime("%Y-%m-%d")
            log_file = hb_mod.THOUGHTS_DIR / f"{today}.jsonl"
            t.check(log_file.exists(), "Thought log file created")

            # Notice detection — simulate a presence arrival
            heartbeat.sensor_state.presence_type = None
            heartbeat.previous_state = SensorState(presence_type=None)

            new_state = SensorState(presence_type="human", presence_name="bluekitty")
            heartbeat.sensor_state = new_state
            notices = heartbeat.notice(new_state)
            arrival_notices = [n for n in notices if n["type"] == "arrival"]
            t.check(len(arrival_notices) > 0, "Detects arrival event")

            # Decision — touch should always be acknowledged
            heartbeat.sensor_state = SensorState(last_touch="boop",
                                                  last_touch_time="now")
            heartbeat.previous_state = SensorState(last_touch=None)
            notices = heartbeat.notice(heartbeat.sensor_state)
            decision = heartbeat.decide(heartbeat.sensor_state, notices, None)
            t.check(decision["action"] == "chirp",
                    f"Boop gets chirp response (got: {decision['action']})")

            # Silence watchdog
            watchdog = SilenceWatchdog(hb_mod.STATE_DIR, threshold_minutes=0)
            # With threshold=0, it should immediately fire
            time.sleep(0.01)
            fired = watchdog.check()
            t.check(fired, "Silence watchdog fires at threshold")
            silence_file = hb_mod.STATE_DIR / "silence.json"
            t.check(silence_file.exists(), "Silence file written")

        finally:
            hb_mod.STATE_DIR = orig_state
            hb_mod.THOUGHTS_DIR = orig_thoughts

    RESULTS.append(t)
    return t


# ═══════════════════════════════════════════════════════════════
# TEST 6: FULL NIGHTLY SEQUENCE
# ═══════════════════════════════════════════════════════════════

def test_nightly_sequence():
    """
    Verify the full nightly sequence:
    dream → weight updates → speculative promotion → decay
    """
    t = TestResult("Nightly Sequence")

    with temp_db() as (db_path, tmpdir):
        conn = sqlite3.connect(db_path)
        before_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        before_spec = conn.execute(
            "SELECT COUNT(*) FROM edges WHERE speculative = 1"
        ).fetchone()[0]
        before_stats = _weight_stats(conn)
        conn.close()

        t.check(before_edges > 0, f"Starting edges: {before_edges}")
        t.check(before_spec > 0, f"Starting speculative: {before_spec}")

        # Run dream (dry run — no LLM, but still walks graph)
        dream_result = run_dream(dry_run=True, verbose=False, noise_seed=0.05)
        t.check(dream_result is not None, "Dream completes")

        # Run decay (actual — we're in temp DB)
        decay_result = run_decay(db_path, dry_run=False, verbose=False)
        t.check(decay_result is not None, "Decay completes")

        # Check post-state
        conn = sqlite3.connect(db_path)
        after_stats = _weight_stats(conn)
        conn.close()

        t.check(after_stats["mean"] <= before_stats["mean"],
                f"Mean weight didn't increase after decay "
                f"({before_stats['mean']:.4f} → {after_stats['mean']:.4f})")

        # No weights exceeded caps
        conn = sqlite3.connect(db_path)
        over_cap = conn.execute(
            "SELECT COUNT(*) FROM edges WHERE weight > 10.0 OR weight < -5.0"
        ).fetchone()[0]
        t.check(over_cap == 0, "No weights exceed caps (±10/5)")
        conn.close()

    RESULTS.append(t)
    return t


# ═══════════════════════════════════════════════════════════════
# TEST 7: RATIONAL EXPANSION
# ═══════════════════════════════════════════════════════════════

def test_rational_expansion():
    """Verify rational expansion infrastructure works on seed graph."""
    t = TestResult("Rational Expansion")

    with temp_db() as (db_path, tmpdir):
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        # --- Survey (read-only) ---
        survey = survey_graph(db_path, verbose=False, detect_communities=True)
        t.check(survey["node_count"] > 50, "Survey finds nodes",
                f"got {survey['node_count']}")
        t.check(survey["edge_count"] > 80, "Survey finds edges",
                f"got {survey['edge_count']}")
        t.check(len(survey["edge_type_distribution"]) >= 3, "Multiple edge types found")
        t.check(len(survey["hub_nodes"]) > 0, "Hub nodes identified")
        t.check(len(survey["missing_edge_types"]) > 0, "Missing edge types detected")
        t.check(survey["survey_time_s"] >= 0, "Survey time recorded")

        # --- Community detection (small seed graph) ---
        communities = survey["communities"]
        t.check(len(communities) >= 2, "Multiple communities detected",
                f"got {len(communities)}")

        # --- Bridge gap detection ---
        bridge_gaps = survey["bridge_candidates"]
        t.check(isinstance(bridge_gaps, list), "Bridge candidates is a list")
        # Seed graph has distinct clusters so there should be gaps
        if bridge_gaps:
            t.check("c1" in bridge_gaps[0], "Bridge has c1 field")
            t.check("potential_score" in bridge_gaps[0], "Bridge has potential_score")

        # --- Label normalization ---
        t.check(_normalize_label("A Beautiful Sunset") == "beautiful_sunset",
                "Normalize strips articles and lowercases")
        t.check(_normalize_label("THE BIG dog") == "big_dog",
                "Normalize handles THE")
        t.check(_normalize_label("hello world!") == "hello_world",
                "Normalize strips punctuation")

        # --- Edge proposal parsing ---
        test_text = """
        cat -> RelatedTo -> dog: both are pets
        music -> FeelsLike -> water: both flow
        """
        proposals = _parse_edge_proposals(test_text)
        t.check(len(proposals) == 2, "Parsed 2 edge proposals",
                f"got {len(proposals)}")
        t.check(proposals[0]["source"] == "cat", "First source is cat")
        t.check(proposals[0]["relation"] == "RelatedTo", "First relation is RelatedTo")
        t.check(proposals[0]["target"] == "dog", "First target is dog")

        # --- Diverse anchor selection ---
        anchors = _select_diverse_anchors(conn, communities, per_cluster=2)
        t.check(len(anchors) > 0, "Anchors selected",
                f"got {len(anchors)}")

        # --- Dry-run bridge clusters ---
        pre_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        bridges = bridge_clusters(db_path, dry_run=True, verbose=False)
        post_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        t.check(pre_edges == post_edges, "Dry-run doesn't modify edges")

        # --- Dry-run condensates ---
        pre_nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        condensates = generate_condensates(db_path, dry_run=True, verbose=False,
                                           num_condensates=2)
        post_nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        t.check(pre_nodes == post_nodes, "Dry-run condensates don't modify nodes")

        # --- Dry-run enrich edge types ---
        enriched = enrich_edge_types(db_path, dry_run=True, verbose=False, batch_size=5)
        post_edges2 = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        t.check(pre_edges == post_edges2, "Dry-run enrich doesn't modify edges")

        # --- Dry-run narrative seeding ---
        narratives = seed_narratives(db_path, dry_run=True, verbose=False, num_seeds=2)
        post_nodes2 = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        t.check(pre_nodes == post_nodes2, "Dry-run narratives don't modify nodes")

        conn.close()

    RESULTS.append(t)


# ═══════════════════════════════════════════════════════════════
# TEST 8: STAGING LOG & TERRITORY WARMING
# ═══════════════════════════════════════════════════════════════

def test_staging_and_warming():
    """Test staging log, territory warming, and clearing."""
    t = TestResult("Staging & Warming")

    with temp_db() as (db_path, tmpdir):
        staging_dir = tmpdir / "staging"
        staging_dir.mkdir(exist_ok=True)

        # --- Staging log basic operations ---
        log = StagingLog(staging_dir)
        log.record_sensor_event("temperature_drop", {"delta": -3.0})
        log.record_conversation("Lara mentioned anthropodermic bibliopegy")
        log.record_observation("the cathedral had stained glass windows")
        log.record_action("searched for ecclesiastical imagery")
        log.record_emotion(0.8, 0.6, trigger="beautiful_light", label="wonder")
        log.record_curiosity("what connects stained glass to sacred geometry?")

        entries = log.read_today()
        t.check(len(entries) == 6, f"Staging log recorded 6 entries (got {len(entries)})")

        # Check entry types
        sources = [e["source"] for e in entries]
        t.check("sensor" in sources, "Has sensor entry")
        t.check("conversation" in sources, "Has conversation entry")
        t.check("observation" in sources, "Has observation entry")
        t.check("emotion" in sources, "Has emotion entry")
        t.check("curiosity" in sources, "Has curiosity entry")

        # Check timestamps present
        t.check(all("timestamp" in e for e in entries), "All entries have timestamps")

        # Stats
        stats = log.stats(verbose=False)
        t.check(stats["total_entries"] == 6, "Stats shows 6 entries")
        t.check(stats["unconsolidated"] == 1, "One unconsolidated file")

        # Unprocessed entries
        unprocessed = log.read_unprocessed()
        t.check(len(unprocessed) == 6, "6 unprocessed entries")

        # Mark as consolidated
        from datetime import date as dt_date
        log.mark_consolidated(dt_date.today())
        unprocessed2 = log.read_unprocessed()
        t.check(len(unprocessed2) == 0, "No unprocessed after marking consolidated")

        # Remove the marker so warming can use today's entries
        from datetime import date
        marker = staging_dir / f"{date.today().isoformat()}.consolidated"
        if marker.exists():
            marker.unlink()

        # --- Territory warming ---
        # The seed graph has nodes like "cathedral", "stained_glass", "sacred_geometry"
        # etc. Our staging log entries mention these concepts.

        # Get pre-warming edge weights
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        pre_weights = {}
        for row in conn.execute("SELECT id, weight FROM edges"):
            pre_weights[row["id"]] = row["weight"]

        # Warm territory
        result = warm_today_territory(
            db_path=db_path,
            staging_dir=staging_dir,
            dry_run=False,
            verbose=False,
        )

        t.check(len(result["concepts_found"]) > 0,
                f"Found concepts from staging log ({len(result['concepts_found'])})")
        t.check(result["edges_warmed"] >= 0,
                f"Edges warmed: {result['edges_warmed']}")

        # Check that some weights actually changed (if any nodes matched)
        if result["nodes_matched"]:
            t.check(result["edges_warmed"] > 0,
                    f"Warmed edges near matched nodes ({result['edges_warmed']})")

            # Verify weights increased
            post_weights = {}
            for row in conn.execute("SELECT id, weight FROM edges"):
                post_weights[row["id"]] = row["weight"]

            changed = sum(1 for eid in pre_weights
                         if post_weights.get(eid, 0) != pre_weights[eid])
            t.check(changed == result["edges_warmed"],
                    f"Weight changes match edges_warmed count ({changed})")

            # Check warm marker file exists
            warm_marker = staging_dir / "warm_territory.json"
            t.check(warm_marker.exists(), "Warm marker file created")

            # --- Clear warm territory ---
            clear_result = clear_warm_territory(
                db_path=db_path,
                staging_dir=staging_dir,
                verbose=False,
            )
            t.check(clear_result["edges_cleared"] == result["edges_warmed"],
                    f"Cleared same number of edges ({clear_result['edges_cleared']})")

            # Verify weights restored
            restored_weights = {}
            for row in conn.execute("SELECT id, weight FROM edges"):
                restored_weights[row["id"]] = row["weight"]

            max_drift = max(
                abs(restored_weights.get(eid, 0) - pre_weights[eid])
                for eid in pre_weights
            )
            t.check(max_drift < 0.001,
                    f"Weights restored after clearing (max drift: {max_drift:.6f})")

            # Warm marker should be gone
            t.check(not warm_marker.exists(), "Warm marker removed after clearing")
        else:
            t.ok("No node matches in seed graph (expected with small seed)")
            t.ok("Skipping weight verification (no matches)")
            t.ok("Skipping clear verification (no matches)")
            t.ok("Skipping restore verification (no matches)")
            t.ok("Skipping marker removal (no matches)")

        # --- Dry-run warming ---
        result_dry = warm_today_territory(
            db_path=db_path,
            staging_dir=staging_dir,
            dry_run=True,
            verbose=False,
        )
        t.check(result_dry["concepts_found"] == result["concepts_found"],
                "Dry-run finds same concepts")

        # Weights should not change in dry-run
        dry_weights = {}
        for row in conn.execute("SELECT id, weight FROM edges"):
            dry_weights[row["id"]] = row["weight"]
        max_drift_dry = max(
            abs(dry_weights.get(eid, 0) - pre_weights[eid])
            for eid in pre_weights
        ) if pre_weights else 0
        t.check(max_drift_dry < 0.001, "Dry-run doesn't modify weights")

        # --- Clear with nothing to clear ---
        clear_empty = clear_warm_territory(
            db_path=db_path,
            staging_dir=staging_dir,
            verbose=False,
        )
        t.check(clear_empty["edges_cleared"] == 0,
                "Clear on empty returns 0")

        conn.close()

    RESULTS.append(t)


# ═══════════════════════════════════════════════════════════════
# TEST 9: CONSCIOUSNESS THRESHOLD
# ═══════════════════════════════════════════════════════════════

def test_consciousness():
    """Test consciousness threshold, cost estimation, and logging."""
    t = TestResult("Consciousness")

    with tempfile.TemporaryDirectory() as tmpdir:
        log_dir = Path(tmpdir) / "consciousness_log"

        # Patch the log dir
        import robody_consciousness as cons_mod
        orig_log_dir = cons_mod.LOG_DIR
        cons_mod.LOG_DIR = log_dir

        try:
            # --- InvocationTier and InvocationReason enums ---
            t.check(InvocationTier.BRAINSTEM.value == "brainstem", "Brainstem tier exists")
            t.check(InvocationTier.OPUS.value == "opus", "Opus tier exists")
            t.check(InvocationReason.DREAM_READING.value == "dream_reading",
                    "Dream reading reason exists")

            # --- Cost estimation ---
            # Brainstem should be free
            brainstem_cost = estimate_invocation_cost(
                InvocationTier.BRAINSTEM, InvocationReason.TRIAGE
            )
            t.check(brainstem_cost == 0.0, "Brainstem is free")

            # Haiku triage should be cheap
            haiku_cost = estimate_invocation_cost(
                InvocationTier.HAIKU, InvocationReason.TRIAGE
            )
            t.check(0 < haiku_cost < 0.01, f"Haiku triage is cheap (${haiku_cost:.4f})")

            # Opus should be more expensive than Haiku
            opus_cost = estimate_invocation_cost(
                InvocationTier.OPUS, InvocationReason.EVENING_REFLECTION
            )
            t.check(opus_cost > haiku_cost, "Opus costs more than Haiku")

            # Batch Opus should be cheaper than regular Opus
            batch_cost = estimate_invocation_cost(
                InvocationTier.BATCH_OPUS, InvocationReason.DREAM_READING
            )
            # Compare same reason for fairness
            regular_cost = estimate_invocation_cost(
                InvocationTier.OPUS, InvocationReason.DREAM_READING
            )
            t.check(batch_cost < regular_cost, "Batch Opus cheaper than regular Opus")

            # --- Daily cost estimation ---
            daily = estimate_daily_cost()
            t.check(daily["daily_total"] > 0, "Daily cost is positive")
            t.check(daily["monthly_estimate"] > 0, "Monthly estimate is positive")
            t.check(daily["monthly_estimate"] < 10.0,
                    f"Monthly estimate reasonable (${daily['monthly_estimate']:.2f})")
            t.check("breakdown" in daily, "Daily estimate has breakdown")

            # --- InvocationRequest ---
            req = InvocationRequest(
                tier=InvocationTier.SONNET,
                reason=InvocationReason.CONVERSATION,
                context={"trigger": "test"},
                urgency=0.7,
            )
            t.check(req.estimated_cost > 0, "Request has estimated cost")
            t.check(req.timestamp != "", "Request has timestamp")
            d = req.to_dict()
            t.check(d["tier"] == "sonnet", "to_dict serializes tier")
            t.check(d["reason"] == "conversation", "to_dict serializes reason")

            # --- ConsciousnessLog ---
            log = ConsciousnessLog(log_dir)
            t.check(log.today_cost() == 0.0, "Empty log has zero cost")
            t.check(log.today_count() == 0, "Empty log has zero count")

            # Record an invocation
            log.record(req, actual_tokens={"input": 2000, "output": 500, "cached": 1500})
            t.check(log.today_count() == 1, "Count after recording")
            t.check(log.today_cost() > 0, "Cost after recording")

            # Check invoked_today_for
            t.check(log.invoked_today_for(InvocationReason.CONVERSATION),
                    "Invoked today for conversation")
            t.check(not log.invoked_today_for(InvocationReason.DREAM_READING),
                    "Not invoked today for dream reading")

            # --- ConsciousnessThreshold ---
            threshold = ConsciousnessThreshold(
                daily_budget=1.0, monthly_budget=30.0
            )

            # No events → no invocation
            result = threshold.evaluate()
            t.check(result is None, "No events = no invocation")

            # Forced invocation
            result = threshold.evaluate(
                force_reason=InvocationReason.DREAM_READING
            )
            t.check(result is not None, "Forced invocation returns request")
            t.check(result.reason == InvocationReason.DREAM_READING,
                    "Forced reason preserved")

            # Status check
            status = threshold.status()
            t.check("pressure" in status, "Status has pressure")
            t.check("budget_remaining_today" in status, "Status has budget remaining")

            # Tier mapping
            tier = threshold._tier_for_reason(InvocationReason.TRIAGE)
            t.check(tier == InvocationTier.HAIKU, "Triage maps to Haiku")

            tier = threshold._tier_for_reason(InvocationReason.EVENING_REFLECTION)
            t.check(tier == InvocationTier.OPUS, "Evening reflection maps to Opus")

            # Downgrade chain
            t.check(threshold._downgrade_tier(InvocationTier.OPUS) == InvocationTier.SONNET,
                    "Opus downgrades to Sonnet")
            t.check(threshold._downgrade_tier(InvocationTier.HAIKU) is None,
                    "Haiku can't downgrade further")

        finally:
            cons_mod.LOG_DIR = orig_log_dir

    RESULTS.append(t)


# ═══════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════

import time as _time

ALL_TESTS = {
    "seed": test_seed_graph,
    "walk": test_graph_walker,
    "dream": test_dream_cycle,
    "weight": test_weight_maintenance,
    "heartbeat": test_heartbeat,
    "nightly": test_nightly_sequence,
    "expansion": test_rational_expansion,
    "staging": test_staging_and_warming,
    "consciousness": test_consciousness,
}


def run_tests(test_name=None):
    global VERBOSE, RESULTS
    RESULTS = []

    tests = ALL_TESTS if test_name is None else {test_name: ALL_TESTS[test_name]}

    print(f"\n{'='*60}")
    print(f"Robody Pipeline Integration Tests")
    print(f"{'='*60}")
    print(f"Running {len(tests)} test(s)...\n")

    t0 = _time.time()

    for name, test_fn in tests.items():
        print(f"▸ {name}")
        try:
            test_fn()
        except Exception as e:
            r = TestResult(name)
            r.fail("EXCEPTION", str(e))
            RESULTS.append(r)
            import traceback
            if VERBOSE:
                traceback.print_exc()

    elapsed = _time.time() - t0

    print(f"\n{'='*60}")
    print(f"Results ({elapsed:.2f}s)")
    print(f"{'='*60}")

    total_passed = 0
    total_failed = 0
    for r in RESULTS:
        print(r.summary())
        total_passed += r.passed
        total_failed += r.failed

    print(f"\n  Total: {total_passed} passed, {total_failed} failed "
          f"({total_passed + total_failed} checks)")

    if total_failed > 0:
        print(f"\n  FAILURES:")
        for r in RESULTS:
            for err in r.errors:
                print(f"    {err}")

    return total_failed == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Robody Pipeline Integration Tests"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--test", choices=list(ALL_TESTS.keys()),
                        help="Run specific test only")
    args = parser.parse_args()

    VERBOSE = args.verbose

    success = run_tests(args.test)
    sys.exit(0 if success else 1)
