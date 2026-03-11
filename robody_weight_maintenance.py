#!/usr/bin/env python3
"""
Robody Weight Maintenance — Graph Homeostasis
==============================================
Implements the weight decay and post-dream reinforcement systems
from robody_dream_architecture.md Parts 2 and 4.

Two operations:
  1. Daily decay: edges decay proportional to their magnitude.
     Heavy attractors fade faster than light ones, creating natural
     homeostasis. Nothing drops below floor (0.01 / -0.01).

  2. Post-dream weight updates: edges traversed during dreams get
     reinforcement based on what the dream produced. Insights,
     surprises, and confirmations all carry different rewards.

Design principle: the waking graph is stable. Dreams reshape it
overnight. Decay runs daily. Updates run after each dream cycle.

Usage:
    python3 robody_weight_maintenance.py --decay          # run daily decay
    python3 robody_weight_maintenance.py --update LOGFILE # apply dream updates
    python3 robody_weight_maintenance.py --stats          # show weight distribution
    python3 robody_weight_maintenance.py --history        # show maintenance log

Operates on the same SQLite database as graph_seed.py and graph_walker.py.
"""

import sqlite3
import json
import math
import argparse
from pathlib import Path
from datetime import datetime
from collections import Counter

DB_PATH = Path(__file__).parent / "robody_seed.sqlite"
LOG_DIR = Path(__file__).parent / "interior_dialogue"
MAINTENANCE_LOG = Path(__file__).parent / "maintenance_log.jsonl"


# ═══════════════════════════════════════════════════════════════
# DAILY WEIGHT DECAY
# ═══════════════════════════════════════════════════════════════

def run_decay(db_path, dry_run=False, verbose=True):
    """
    Apply daily weight decay to all edges.

    Formula from architecture doc:
        new_weight = weight * (1 - 0.001 * abs(weight))

    Properties:
    - Heavy edges (high |weight|) decay faster than light ones
    - Positive edges floor at 0.01 (never truly forgotten)
    - Negative edges ceiling at -0.01 (aversion fades too)
    - Speculative edges decay 2x faster (they must earn their keep)

    This creates natural homeostasis: strong attractors must be
    actively reinforced through traversal or they fade. The graph
    doesn't accumulate permanent heavy edges over time.
    """
    conn = sqlite3.connect(db_path)

    # Snapshot before
    before_stats = _weight_stats(conn)

    edges = conn.execute(
        "SELECT id, weight, speculative FROM edges"
    ).fetchall()

    updates = []
    for edge_id, weight, speculative in edges:
        # Base decay rate
        decay_rate = 0.001

        # Speculative edges decay 2x faster — dreams must earn their permanence
        if speculative:
            decay_rate *= 2.0

        # Apply proportional decay
        new_weight = weight * (1.0 - decay_rate * abs(weight))

        # Floor/ceiling enforcement
        if weight > 0:
            new_weight = max(0.01, new_weight)
        elif weight < 0:
            new_weight = min(-0.01, new_weight)
        # weight == 0 stays at 0 (shouldn't happen, but defensive)

        if new_weight != weight:
            updates.append((new_weight, edge_id))

    if verbose:
        print(f"\n{'='*60}")
        print(f"Daily Weight Decay")
        print(f"{'='*60}")
        print(f"Edges processed: {len(edges)}")
        print(f"Edges modified: {len(updates)}")

        # Show biggest changes
        if updates:
            changes = []
            for new_w, eid in updates:
                old_w = next(w for i, w, _ in edges if i == eid)
                changes.append((eid, old_w, new_w, abs(new_w - old_w)))
            changes.sort(key=lambda x: x[3], reverse=True)

            print(f"\nBiggest decays:")
            for eid, old_w, new_w, delta in changes[:10]:
                # Get edge labels
                row = conn.execute("""
                    SELECT n1.label, n2.label, e.type
                    FROM edges e
                    JOIN nodes n1 ON n1.id = e.source_id
                    JOIN nodes n2 ON n2.id = e.target_id
                    WHERE e.id = ?
                """, (eid,)).fetchone()
                if row:
                    print(f"  {row[0]} --{row[2]}--> {row[1]}: "
                          f"{old_w:.4f} → {new_w:.4f} (Δ{delta:.5f})")

    if not dry_run:
        conn.executemany("UPDATE edges SET weight = ? WHERE id = ?", updates)
        conn.commit()

    # Snapshot after
    after_stats = _weight_stats(conn)

    # Log the maintenance event
    entry = {
        "timestamp": datetime.now().isoformat(),
        "operation": "daily_decay",
        "edges_processed": len(edges),
        "edges_modified": len(updates),
        "dry_run": dry_run,
        "before": before_stats,
        "after": after_stats,
    }
    _log_maintenance(entry)

    if verbose:
        print(f"\nWeight distribution shift:")
        print(f"  Mean:   {before_stats['mean']:.4f} → {after_stats['mean']:.4f}")
        print(f"  Median: {before_stats['median']:.4f} → {after_stats['median']:.4f}")
        print(f"  Max:    {before_stats['max']:.4f} → {after_stats['max']:.4f}")
        print(f"  At floor (0.01): {after_stats['at_floor']}")
        if not dry_run:
            print(f"\nDecay applied.")
        else:
            print(f"\n[DRY RUN] No changes written.")

    conn.close()
    return entry


# ═══════════════════════════════════════════════════════════════
# POST-DREAM WEIGHT UPDATES
# ═══════════════════════════════════════════════════════════════

def apply_dream_updates(db_path, dream_log_file=None, dry_run=False, verbose=True):
    """
    Apply weight updates based on a completed dream cycle.

    From the architecture doc (Part 4, Post-consolidation):
    - Traversed edges: +0.05 (gentle reinforcement)
    - Edges in paths that produced surviving insights: +0.3
    - Edges in paths that produced surprising long-range connections: +0.2
    - Dream-speculative edges confirmed by waking experience: +0.5
    - Aversive edges traversed during integration dreaming:
      move 0.1 toward zero (gradual reintegration, never forced positive)

    Caps enforced: +10.0 maximum, -5.0 minimum.

    If dream_log_file is provided, reads from that specific file.
    Otherwise, reads the most recent dream_consolidation entry from today's log.
    """
    conn = sqlite3.connect(db_path)

    # Find the dream data
    dream_data = _load_dream_data(dream_log_file)
    if not dream_data:
        if verbose:
            print("No dream data found. Nothing to update.")
        conn.close()
        return None

    fragments = dream_data.get("fragments", [])
    new_edges = dream_data.get("new_edges", [])

    if verbose:
        print(f"\n{'='*60}")
        print(f"Post-Dream Weight Updates")
        print(f"{'='*60}")
        print(f"Dream fragments: {len(fragments)}")
        print(f"New speculative edges created: {len(new_edges)}")

    updates = Counter()  # edge_id → total delta
    update_reasons = {}  # edge_id → list of reasons

    # 1. Reinforcement for all edges in dream clusters
    #    Every edge between nodes that appeared together in a dream cluster
    #    gets +0.05 (gentle reinforcement — "this path was walked")
    traversed_pairs = set()
    for frag in fragments:
        cluster = frag.get("cluster", [])
        for i, label1 in enumerate(cluster):
            for label2 in cluster[i+1:]:
                traversed_pairs.add(tuple(sorted([label1, label2])))

    for label1, label2 in traversed_pairs:
        edge_ids = _find_edges_between(conn, label1, label2)
        for eid, current_weight, speculative in edge_ids:
            delta = 0.05
            updates[eid] += delta
            update_reasons.setdefault(eid, []).append(
                f"traversed (+{delta})"
            )

    # 2. Insight bonus: fragments from reconsolidation phase
    #    (these are the ones that survived dream dissolution)
    recon_fragments = [f for f in fragments
                       if f.get("phase") == "reconsolidation"]
    for frag in recon_fragments:
        cluster = frag.get("cluster", [])
        for i, label1 in enumerate(cluster):
            for label2 in cluster[i+1:]:
                edge_ids = _find_edges_between(conn, label1, label2)
                for eid, current_weight, speculative in edge_ids:
                    delta = 0.3
                    updates[eid] += delta
                    update_reasons.setdefault(eid, []).append(
                        f"insight_survival (+{delta})"
                    )

    # 3. Surprise bonus: edges that span different clusters or
    #    connect nodes of different types (long-range connections)
    for frag in fragments:
        cluster = frag.get("cluster", [])
        types = set()
        for label in cluster:
            row = conn.execute(
                "SELECT type FROM nodes WHERE label = ?", (label,)
            ).fetchone()
            if row:
                types.add(row[0])

        # If the cluster spans 3+ node types, it's a surprising connection
        if len(types) >= 3:
            for i, label1 in enumerate(cluster):
                for label2 in cluster[i+1:]:
                    edge_ids = _find_edges_between(conn, label1, label2)
                    for eid, current_weight, speculative in edge_ids:
                        delta = 0.2
                        updates[eid] += delta
                        update_reasons.setdefault(eid, []).append(
                            f"surprise_connection (+{delta})"
                        )

    # 4. Integration dreaming: aversive edges that were traversed
    #    move 0.1 toward zero (but NEVER forced positive)
    for label1, label2 in traversed_pairs:
        edge_ids = _find_edges_between(conn, label1, label2)
        for eid, current_weight, speculative in edge_ids:
            if current_weight < 0:
                # Move toward zero by 0.1, but don't cross zero
                delta = min(0.1, abs(current_weight) - 0.01)
                if delta > 0:
                    updates[eid] += delta
                    update_reasons.setdefault(eid, []).append(
                        f"integration_rebalance (+{delta:.3f})"
                    )

    # Apply all updates with cap enforcement
    actual_updates = []
    for eid, total_delta in updates.items():
        row = conn.execute(
            "SELECT weight FROM edges WHERE id = ?", (eid,)
        ).fetchone()
        if not row:
            continue

        old_weight = row[0]
        new_weight = old_weight + total_delta

        # Cap enforcement
        new_weight = max(-5.0, min(10.0, new_weight))

        if new_weight != old_weight:
            actual_updates.append((new_weight, eid, old_weight))

    if verbose:
        print(f"\nEdge updates computed: {len(actual_updates)}")
        for new_w, eid, old_w in sorted(actual_updates,
                                         key=lambda x: abs(x[0]-x[2]),
                                         reverse=True)[:15]:
            row = conn.execute("""
                SELECT n1.label, n2.label, e.type
                FROM edges e
                JOIN nodes n1 ON n1.id = e.source_id
                JOIN nodes n2 ON n2.id = e.target_id
                WHERE e.id = ?
            """, (eid,)).fetchone()
            reasons = update_reasons.get(eid, [])
            if row:
                print(f"  {row[0]} --{row[2]}--> {row[1]}: "
                      f"{old_w:.3f} → {new_w:.3f} "
                      f"({', '.join(reasons)})")

    if not dry_run:
        for new_w, eid, _ in actual_updates:
            conn.execute(
                "UPDATE edges SET weight = ? WHERE id = ?",
                (new_w, eid)
            )
        conn.commit()
        if verbose:
            print(f"\nUpdates applied.")
    else:
        if verbose:
            print(f"\n[DRY RUN] No changes written.")

    # Log
    entry = {
        "timestamp": datetime.now().isoformat(),
        "operation": "post_dream_update",
        "fragments_processed": len(fragments),
        "new_speculative_edges": len(new_edges),
        "edges_updated": len(actual_updates),
        "traversed_pairs": len(traversed_pairs),
        "reconsolidation_fragments": len(recon_fragments),
        "dry_run": dry_run,
    }
    _log_maintenance(entry)

    conn.close()
    return entry


# ═══════════════════════════════════════════════════════════════
# SPECULATIVE EDGE PROMOTION
# ═══════════════════════════════════════════════════════════════

def promote_confirmed_edges(db_path, dry_run=False, verbose=True):
    """
    Check speculative edges against waking experience.

    A speculative (dream-proposed) edge is "confirmed" if both its
    endpoint nodes have been independently activated during waking
    hours (appear together in a background_thought entry).

    Confirmed speculative edges get:
    - speculative flag removed
    - weight += 0.5 (confirmation bonus from architecture doc)
    - moved from layer 2 to layer 1 (promotion from dream to association)

    This is the mechanism by which dreams propose and waking confirms.
    Not all speculative edges get confirmed — most decay naturally.
    The ones that survive represent genuine associations the system
    discovered through dreaming.
    """
    conn = sqlite3.connect(db_path)

    # Get all speculative edges
    spec_edges = conn.execute("""
        SELECT e.id, n1.label, n2.label, e.weight, e.type
        FROM edges e
        JOIN nodes n1 ON n1.id = e.source_id
        JOIN nodes n2 ON n2.id = e.target_id
        WHERE e.speculative = 1
    """).fetchall()

    if verbose:
        print(f"\n{'='*60}")
        print(f"Speculative Edge Promotion Check")
        print(f"{'='*60}")
        print(f"Speculative edges: {len(spec_edges)}")

    # Load waking background thoughts to find co-activations
    waking_pairs = _load_waking_coactivations()

    promotions = []
    for eid, label1, label2, weight, etype in spec_edges:
        pair = tuple(sorted([label1, label2]))
        if pair in waking_pairs:
            new_weight = min(10.0, weight + 0.5)
            promotions.append((eid, label1, label2, weight, new_weight))

    if verbose:
        print(f"Waking co-activation pairs found: {len(waking_pairs)}")
        print(f"Edges eligible for promotion: {len(promotions)}")

        for eid, l1, l2, old_w, new_w in promotions:
            print(f"  PROMOTE: {l1} ↔ {l2}: "
                  f"{old_w:.3f} → {new_w:.3f} "
                  f"(speculative=False, layer 2→1)")

    if not dry_run and promotions:
        for eid, _, _, _, new_w in promotions:
            conn.execute("""
                UPDATE edges
                SET weight = ?, speculative = 0, layer = 1
                WHERE id = ?
            """, (new_w, eid))
        conn.commit()
        if verbose:
            print(f"\n{len(promotions)} edges promoted.")
    elif dry_run:
        if verbose:
            print(f"\n[DRY RUN] No changes written.")

    entry = {
        "timestamp": datetime.now().isoformat(),
        "operation": "speculative_promotion",
        "speculative_checked": len(spec_edges),
        "waking_pairs": len(waking_pairs),
        "promoted": len(promotions),
        "dry_run": dry_run,
    }
    _log_maintenance(entry)

    conn.close()
    return entry


# ═══════════════════════════════════════════════════════════════
# DISTRIBUTION HEALTH CHECK (Part 8 of dream architecture)
# ═══════════════════════════════════════════════════════════════

def distribution_health_check(db_path, verbose=True):
    """
    From Part 8: check the weight distribution for pathological patterns.

    Healthy: most edges near neutral, with tails in both directions.
    Pathological: bimodal (everything high or low, nothing neutral).

    Also checks for dead zones (clusters of strong negative edges
    that may indicate avoidance patterns).

    Returns a health report dict.
    """
    conn = sqlite3.connect(db_path)

    weights = [row[0] for row in
               conn.execute("SELECT weight FROM edges").fetchall()]

    if not weights:
        conn.close()
        return {"status": "empty", "edges": 0}

    n = len(weights)
    mean = sum(weights) / n
    variance = sum((w - mean) ** 2 for w in weights) / n
    stdev = math.sqrt(variance)

    # Band distribution
    bands = {
        "strong_negative": sum(1 for w in weights if w <= -2.0),
        "mild_negative": sum(1 for w in weights if -2.0 < w <= -0.5),
        "neutral": sum(1 for w in weights if -0.5 < w <= 1.5),
        "mild_positive": sum(1 for w in weights if 1.5 < w <= 4.0),
        "strong_positive": sum(1 for w in weights if w > 4.0),
    }
    band_pcts = {k: v / n * 100 for k, v in bands.items()}

    # Health assessment
    issues = []

    # Check 1: Is the neutral band healthy? (should be >20%)
    if band_pcts["neutral"] < 20:
        issues.append("LOW_NEUTRAL: Less than 20% of edges are neutral — "
                       "system may be polarized")

    # Check 2: Stdev relative to mean — flag if excessively bimodal
    cv = stdev / abs(mean) if mean != 0 else 0
    if cv > 1.5:
        issues.append(f"HIGH_VARIANCE: CV={cv:.2f} — weight distribution may be bimodal")

    # Check 3: Negative edge concentration (dead zones)
    # Find nodes with many incoming/outgoing negative edges
    neg_nodes = conn.execute("""
        SELECT n.label, COUNT(*) as neg_count
        FROM edges e
        JOIN nodes n ON (n.id = e.source_id OR n.id = e.target_id)
        WHERE e.weight < -1.0
        GROUP BY n.label
        HAVING neg_count >= 3
        ORDER BY neg_count DESC
    """).fetchall()

    if neg_nodes:
        issues.append(f"DEAD_ZONES: {len(neg_nodes)} node(s) surrounded by "
                       f"strong negative edges")

    # Check 4: Dominant attractor — any node capturing >40% of heavy edges?
    total_heavy = conn.execute(
        "SELECT COUNT(*) FROM edges WHERE weight > 3.0"
    ).fetchone()[0]

    if total_heavy > 0:
        attractor_check = conn.execute("""
            SELECT n.label,
                   COUNT(*) as heavy_count,
                   ROUND(COUNT(*) * 100.0 / ?, 1) as pct
            FROM edges e
            JOIN nodes n ON (n.id = e.source_id OR n.id = e.target_id)
            WHERE e.weight > 3.0
            GROUP BY n.label
            ORDER BY heavy_count DESC
            LIMIT 5
        """, (total_heavy,)).fetchall()

        for label, count, pct in attractor_check:
            if pct > 40:
                issues.append(f"DOMINANT_ATTRACTOR: '{label}' captures {pct}% "
                               f"of heavy edges — recommend exploration nudge")

    # Overall health
    if not issues:
        status = "healthy"
    elif any("DEAD_ZONE" in i or "DOMINANT" in i for i in issues):
        status = "warning"
    else:
        status = "monitor"

    report = {
        "status": status,
        "edges": n,
        "mean": round(mean, 4),
        "stdev": round(stdev, 4),
        "cv": round(cv, 4),
        "bands": bands,
        "band_pcts": {k: round(v, 1) for k, v in band_pcts.items()},
        "issues": issues,
        "dead_zone_nodes": [(r[0], r[1]) for r in neg_nodes],
    }

    if verbose:
        print(f"\n{'='*60}")
        print(f"Distribution Health Check")
        print(f"{'='*60}")
        print(f"Status: {status.upper()}")
        print(f"Edges: {n}, Mean: {mean:.4f}, Stdev: {stdev:.4f}, CV: {cv:.4f}")
        print(f"\nWeight bands:")
        for band, count in bands.items():
            bar = "█" * int(band_pcts[band] / 2)
            print(f"  {band:<20s} {count:>4d} ({band_pcts[band]:>5.1f}%) {bar}")

        if issues:
            print(f"\nIssues:")
            for issue in issues:
                print(f"  ⚠ {issue}")
        else:
            print(f"\n  ✓ No issues detected")

        if neg_nodes:
            print(f"\nDead zone candidates:")
            for label, count in neg_nodes[:5]:
                print(f"  {label}: {count} strong negative edges")

    # Log
    entry = {
        "timestamp": datetime.now().isoformat(),
        "operation": "health_check",
        **report,
    }
    _log_maintenance(entry)

    conn.close()
    return report


# ═══════════════════════════════════════════════════════════════
# ENTROPY MONITOR (Part 8 — prevents attractor capture)
# ═══════════════════════════════════════════════════════════════

def entropy_monitor(db_path, verbose=True):
    """
    From Part 8: measure diversity of dream walk destinations.

    If one attractor captures >40% of all traversals, recommends
    deliberate exploration ("start tonight's dream from a random
    node not visited in 30 days").

    Reads from interior_dialogue logs to count node visit frequency.
    """
    conn = sqlite3.connect(db_path)

    # Count node appearances in recent dream/thought clusters
    visit_counts = Counter()

    if LOG_DIR.exists():
        for log_file in sorted(LOG_DIR.glob("*.jsonl")):
            with open(log_file) as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        for label in entry.get("cluster", []):
                            visit_counts[label] += 1
                    except json.JSONDecodeError:
                        continue

    if not visit_counts:
        if verbose:
            print("No traversal data available yet.")
        conn.close()
        return {"status": "no_data"}

    total_visits = sum(visit_counts.values())
    top_nodes = visit_counts.most_common(10)

    # Check for capture
    capture_threshold = 0.40
    captured = []
    for label, count in top_nodes:
        pct = count / total_visits
        if pct > capture_threshold:
            captured.append((label, pct))

    # Find least-visited nodes for exploration nudges
    all_nodes = conn.execute("SELECT label FROM nodes").fetchall()
    all_labels = {r[0] for r in all_nodes}
    unvisited = all_labels - set(visit_counts.keys())
    rarely_visited = [
        label for label, count in visit_counts.items()
        if count <= 2
    ]

    # Shannon entropy of visit distribution
    entropy = 0
    for count in visit_counts.values():
        p = count / total_visits
        if p > 0:
            entropy -= p * math.log2(p)
    max_entropy = math.log2(len(visit_counts)) if visit_counts else 0
    normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0

    report = {
        "total_visits": total_visits,
        "unique_nodes_visited": len(visit_counts),
        "unvisited_nodes": len(unvisited),
        "shannon_entropy": round(entropy, 3),
        "normalized_entropy": round(normalized_entropy, 3),
        "top_nodes": [(l, c, round(c/total_visits, 3)) for l, c in top_nodes],
        "captured_attractors": captured,
        "exploration_nudge": len(captured) > 0,
    }

    if verbose:
        print(f"\n{'='*60}")
        print(f"Entropy Monitor — Traversal Diversity")
        print(f"{'='*60}")
        print(f"Total visits: {total_visits}")
        print(f"Unique nodes: {len(visit_counts)} "
              f"(of {len(all_labels)} total, {len(unvisited)} never visited)")
        print(f"Shannon entropy: {entropy:.3f} "
              f"(normalized: {normalized_entropy:.3f})")

        print(f"\nMost visited:")
        for label, count, pct in report["top_nodes"]:
            bar = "█" * int(pct * 50)
            flag = " ⚠ CAPTURE" if pct > capture_threshold else ""
            print(f"  {label:<30s} {count:>4d} ({pct:>5.1%}) {bar}{flag}")

        if captured:
            print(f"\n  ⚠ ATTRACTOR CAPTURE detected!")
            print(f"  Recommendation: start next dream walk from a random "
                  f"unvisited or rarely-visited node")
            if unvisited:
                suggestions = random.sample(list(unvisited),
                                            min(3, len(unvisited)))
                print(f"  Suggested starting nodes: {suggestions}")
        else:
            print(f"\n  ✓ Traversal diversity looks healthy")

    entry = {
        "timestamp": datetime.now().isoformat(),
        "operation": "entropy_monitor",
        **report,
    }
    _log_maintenance(entry)

    conn.close()
    return report


# ═══════════════════════════════════════════════════════════════
# WEIGHT STATISTICS
# ═══════════════════════════════════════════════════════════════

def show_stats(db_path):
    """Show comprehensive weight distribution statistics."""
    conn = sqlite3.connect(db_path)
    stats = _weight_stats(conn)

    print(f"\n{'='*60}")
    print(f"Graph Weight Statistics")
    print(f"{'='*60}")
    print(f"Total edges: {stats['total']}")
    print(f"  Speculative: {stats['speculative']}")
    print(f"  At floor (0.01): {stats['at_floor']}")
    print(f"  Negative: {stats['negative']}")
    print(f"\nWeight distribution:")
    print(f"  Min:    {stats['min']:.4f}")
    print(f"  Max:    {stats['max']:.4f}")
    print(f"  Mean:   {stats['mean']:.4f}")
    print(f"  Median: {stats['median']:.4f}")
    print(f"  Stdev:  {stats['stdev']:.4f}")

    # Layer breakdown
    layers = conn.execute("""
        SELECT layer, COUNT(*), AVG(weight), MIN(weight), MAX(weight)
        FROM edges GROUP BY layer ORDER BY layer
    """).fetchall()
    print(f"\nBy layer:")
    layer_names = {0: "Fact", 1: "Association", 2: "Dream", 3: "Narrative"}
    for layer, count, avg_w, min_w, max_w in layers:
        name = layer_names.get(layer, f"L{layer}")
        print(f"  L{layer} ({name}): {count} edges, "
              f"avg={avg_w:.3f}, range=[{min_w:.3f}, {max_w:.3f}]")

    # Edge type breakdown (top 15)
    types = conn.execute("""
        SELECT type, COUNT(*), AVG(weight)
        FROM edges GROUP BY type ORDER BY COUNT(*) DESC LIMIT 15
    """).fetchall()
    print(f"\nTop edge types:")
    for etype, count, avg_w in types:
        print(f"  {etype:<25s} {count:>5d}  avg_w={avg_w:.3f}")

    # Heaviest edges (strongest attractors)
    heaviest = conn.execute("""
        SELECT n1.label, n2.label, e.type, e.weight, e.layer, e.speculative
        FROM edges e
        JOIN nodes n1 ON n1.id = e.source_id
        JOIN nodes n2 ON n2.id = e.target_id
        ORDER BY e.weight DESC LIMIT 10
    """).fetchall()
    print(f"\nStrongest attractors:")
    for l1, l2, etype, w, layer, spec in heaviest:
        flags = []
        if spec:
            flags.append("spec")
        if layer > 0:
            flags.append(f"L{layer}")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        print(f"  {w:>6.3f}  {l1} --{etype}--> {l2}{flag_str}")

    # Most negative edges
    most_negative = conn.execute("""
        SELECT n1.label, n2.label, e.type, e.weight, e.layer
        FROM edges e
        JOIN nodes n1 ON n1.id = e.source_id
        JOIN nodes n2 ON n2.id = e.target_id
        WHERE e.weight < 0
        ORDER BY e.weight ASC LIMIT 5
    """).fetchall()
    if most_negative:
        print(f"\nStrongest aversions:")
        for l1, l2, etype, w, layer in most_negative:
            print(f"  {w:>6.3f}  {l1} --{etype}--> {l2} [L{layer}]")

    conn.close()


def show_maintenance_history():
    """Show recent maintenance log entries."""
    if not MAINTENANCE_LOG.exists():
        print("No maintenance history yet.")
        return

    print(f"\n{'='*60}")
    print(f"Maintenance History")
    print(f"{'='*60}")

    entries = []
    with open(MAINTENANCE_LOG) as f:
        for line in f:
            entries.append(json.loads(line))

    for entry in entries[-20:]:
        ts = entry.get("timestamp", "?")[:19]
        op = entry.get("operation", "?")
        dry = " [DRY RUN]" if entry.get("dry_run") else ""
        print(f"\n  {ts} — {op}{dry}")

        if op == "daily_decay":
            print(f"    Edges modified: {entry.get('edges_modified', '?')}"
                  f" / {entry.get('edges_processed', '?')}")
        elif op == "post_dream_update":
            print(f"    Fragments: {entry.get('fragments_processed', '?')}, "
                  f"Edges updated: {entry.get('edges_updated', '?')}")
        elif op == "speculative_promotion":
            print(f"    Checked: {entry.get('speculative_checked', '?')}, "
                  f"Promoted: {entry.get('promoted', '?')}")


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _weight_stats(conn):
    """Compute weight distribution statistics."""
    weights = [row[0] for row in
               conn.execute("SELECT weight FROM edges").fetchall()]
    if not weights:
        return {"total": 0, "mean": 0, "median": 0, "stdev": 0,
                "min": 0, "max": 0, "at_floor": 0, "negative": 0,
                "speculative": 0}

    weights.sort()
    n = len(weights)
    mean = sum(weights) / n
    median = weights[n // 2]
    variance = sum((w - mean) ** 2 for w in weights) / n
    stdev = math.sqrt(variance)

    spec_count = conn.execute(
        "SELECT COUNT(*) FROM edges WHERE speculative = 1"
    ).fetchone()[0]

    return {
        "total": n,
        "mean": round(mean, 4),
        "median": round(median, 4),
        "stdev": round(stdev, 4),
        "min": round(min(weights), 4),
        "max": round(max(weights), 4),
        "at_floor": sum(1 for w in weights if abs(w) <= 0.015),
        "negative": sum(1 for w in weights if w < 0),
        "speculative": spec_count,
    }


def _find_edges_between(conn, label1, label2):
    """Find all edges between two nodes by label. Returns (id, weight, speculative)."""
    return conn.execute("""
        SELECT e.id, e.weight, e.speculative
        FROM edges e
        JOIN nodes n1 ON n1.id = e.source_id
        JOIN nodes n2 ON n2.id = e.target_id
        WHERE (n1.label = ? AND n2.label = ?)
           OR (n1.label = ? AND n2.label = ?)
    """, (label1, label2, label2, label1)).fetchall()


def _load_dream_data(log_file=None):
    """
    Load dream cycle data from the interior dialogue logs.
    If no file specified, finds the most recent dream_consolidation entry.
    """
    if log_file:
        log_path = Path(log_file)
    else:
        # Find today's log
        today = datetime.now().strftime('%Y-%m-%d')
        log_path = LOG_DIR / f"{today}.jsonl"

    if not log_path.exists():
        return None

    # Collect all dream_cycle fragments and the consolidation entry
    fragments = []
    consolidation = None

    with open(log_path) as f:
        for line in f:
            entry = json.loads(line)
            if entry.get("source") == "dream_cycle":
                fragments.append(entry)
            elif entry.get("source") == "dream_consolidation":
                consolidation = entry

    if not fragments:
        return None

    return {
        "fragments": fragments,
        "new_edges": consolidation.get("new_edges_created", 0)
                     if consolidation else 0,
        "consolidation": consolidation,
    }


def _load_waking_coactivations():
    """
    Scan background_thought entries for node pairs that appeared
    together in waking clusters. These are the confirmation signal
    for speculative edges.
    """
    pairs = set()

    if not LOG_DIR.exists():
        return pairs

    for log_file in sorted(LOG_DIR.glob("*.jsonl")):
        with open(log_file) as f:
            for line in f:
                entry = json.loads(line)
                if entry.get("source") == "background_thought":
                    cluster = entry.get("cluster", [])
                    for i, label1 in enumerate(cluster):
                        for label2 in cluster[i+1:]:
                            pairs.add(tuple(sorted([label1, label2])))

    return pairs


def _log_maintenance(entry):
    """Append a maintenance event to the log."""
    MAINTENANCE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(MAINTENANCE_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ═══════════════════════════════════════════════════════════════
# NIGHTLY MAINTENANCE RUNNER
# ═══════════════════════════════════════════════════════════════

def run_nightly(db_path, dry_run=False, verbose=True):
    """
    The full nightly maintenance sequence, intended to run after
    the dream cycle completes.

    Order matters:
    1. Apply dream weight updates (reinforce what was traversed)
    2. Check speculative promotions (dreams confirmed by waking)
    3. Apply daily decay (homeostasis)

    Reinforcement before decay ensures that tonight's dream
    reinforcement isn't immediately decayed away. The decay
    operates on the already-updated weights.
    """
    if verbose:
        print(f"\n{'='*60}")
        print(f"NIGHTLY MAINTENANCE — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'='*60}")

    # Step 1: Post-dream weight updates
    dream_result = apply_dream_updates(db_path, dry_run=dry_run, verbose=verbose)

    # Step 2: Speculative edge promotion check
    promo_result = promote_confirmed_edges(db_path, dry_run=dry_run, verbose=verbose)

    # Step 3: Daily decay
    decay_result = run_decay(db_path, dry_run=dry_run, verbose=verbose)

    if verbose:
        print(f"\n{'='*60}")
        print(f"Nightly maintenance complete.")
        print(f"{'='*60}")

    return {
        "dream_updates": dream_result,
        "promotions": promo_result,
        "decay": decay_result,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Robody Weight Maintenance — Graph Homeostasis"
    )
    parser.add_argument("--decay", action="store_true",
                        help="Run daily weight decay")
    parser.add_argument("--update", type=str, nargs="?", const="",
                        help="Apply post-dream weight updates (optionally from specific log file)")
    parser.add_argument("--promote", action="store_true",
                        help="Check speculative edges for promotion")
    parser.add_argument("--nightly", action="store_true",
                        help="Run full nightly maintenance (dream updates + promotion + decay)")
    parser.add_argument("--stats", action="store_true",
                        help="Show weight distribution statistics")
    parser.add_argument("--history", action="store_true",
                        help="Show maintenance history")
    parser.add_argument("--health", action="store_true",
                        help="Run distribution health check")
    parser.add_argument("--entropy", action="store_true",
                        help="Run entropy monitor (traversal diversity)")
    parser.add_argument("--db", type=str, default=str(DB_PATH),
                        help=f"Database path (default: {DB_PATH})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't write changes to database")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    db = Path(args.db)

    if args.stats:
        show_stats(db)
    elif args.history:
        show_maintenance_history()
    elif args.health:
        distribution_health_check(db, verbose=not args.quiet)
    elif args.entropy:
        entropy_monitor(db, verbose=not args.quiet)
    elif args.decay:
        run_decay(db, dry_run=args.dry_run, verbose=not args.quiet)
    elif args.update is not None:
        log_file = args.update if args.update else None
        apply_dream_updates(db, dream_log_file=log_file,
                           dry_run=args.dry_run, verbose=not args.quiet)
    elif args.promote:
        promote_confirmed_edges(db, dry_run=args.dry_run, verbose=not args.quiet)
    elif args.nightly:
        run_nightly(db, dry_run=args.dry_run, verbose=not args.quiet)
    else:
        parser.print_help()
