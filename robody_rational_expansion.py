#!/usr/bin/env python3
"""
Robody Rational Expansion — Stage 2 Instantiation
==================================================
Reviews the ConceptNet-seeded graph and enriches it with structured
knowledge condensates: compressed fragments encoding relationships,
surprises, and missing connections that the impersonal substrate lacks.

This is Stage 2 of the three-stage instantiation described in
robody_dream_architecture.md Part 3:
  Stage 1: ConceptNet import (common-sense knowledge substrate) ✓
  Stage 2: Rational expansion (LLM enrichment) ← THIS MODULE
  Stage 3: Dream-append (speculative edges from dreaming)

The expansion uses Claude (consciousness layer) at normal temperature
to generate rational, structured, deliberate connections. This is
"parental DNA" — the gaps Claude chooses to fill shape which dream
paths are possible later.

Expansion modes:
  1. Cluster bridging — find isolated clusters and propose connections
  2. Knowledge condensates — generate compressed relationship fragments
  3. Missing edge types — add phonetic, cultural, personal edges that
     ConceptNet lacks entirely
  4. Narrative seeding — plant fragments that enable story-like traversals

Usage:
    python3 robody_rational_expansion.py [--db PATH] [--mode MODE] [--dry-run]
    python3 robody_rational_expansion.py --survey     # analyze graph topology first
    python3 robody_rational_expansion.py --condense   # generate knowledge condensates
    python3 robody_rational_expansion.py --bridge      # bridge isolated clusters
    python3 robody_rational_expansion.py --enrich      # add missing edge types

Requires: Ollama running on MarshLair (10.0.0.123:11434) with robody-brainstem model,
          OR Claude API access for higher-quality expansion.
"""

import sqlite3
import json
import time
import random
import argparse
import urllib.request
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

DB_PATH = Path(__file__).parent / "robody_seed.sqlite"
LOG_DIR = Path(__file__).parent / "expansion_logs"
OLLAMA_URL = "http://10.0.0.123:11434"
BRAINSTEM_MODEL = "robody-brainstem"

# -------------------------------------------------------------------
# LLM interface (same pattern as graph_walker, shared infrastructure)
# -------------------------------------------------------------------

EXPANSION_SYSTEM = """You are helping build the foundational knowledge of a small wheeled
robot who will develop its own personality and interests over time. Your task is to
identify connections between concepts that a common-sense database misses.

You think carefully and precisely. You notice:
- Cultural connections (a song associated with a place, a film that references an idea)
- Phonetic similarities (words that sound alike and create associative bridges)
- Emotional resonances (concepts that feel similar despite being unrelated)
- Narrative connections (things that appear together in stories, myths, history)
- Sensory links (things that share textures, sounds, temperatures, colors)

When you propose a connection, state it as:
SOURCE -> RELATION_TYPE -> TARGET: brief reason

Keep reasons to one sentence. Be specific, not vague."""

CONDENSATE_SYSTEM = """You are generating knowledge condensates — compressed fragments that
encode surprising relationships and facts. Each condensate should be a single paragraph
that links several concepts together through a narrative thread.

Good condensates:
- Encode MULTIPLE relationships in a single coherent fragment
- Include at least one surprising or non-obvious connection
- Are grounded in real knowledge (historical, scientific, cultural)
- Create potential for dream-walks to find interesting paths

Example: "The orchestra that performed during the siege of Leningrad played
Shostakovich's 7th Symphony; broadcast on loudspeakers toward German lines;
some soldiers later said it was the moment they knew they would lose. Music
as weapon, as survival, as defiance."

Generate condensates that are true, specific, and rich with traversable connections."""


def call_llm(prompt, system=EXPANSION_SYSTEM, temperature=0.7, max_tokens=200,
             dry_run=False, verbose=False):
    """Call the brainstem LLM via Ollama."""
    if dry_run:
        return f"[DRY RUN] Would generate for: {prompt[:80]}..."

    payload = json.dumps({
        "model": BRAINSTEM_MODEL,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {
            "temperature": temperature,
            "top_p": 0.9,
            "repeat_penalty": 1.15,
            "num_predict": max_tokens,
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
        if verbose:
            print(f"  LLM call failed: {e}")
        return None


# -------------------------------------------------------------------
# Graph topology analysis
# -------------------------------------------------------------------

def survey_graph(db_path=DB_PATH, verbose=True, detect_communities=False):
    """
    Analyze graph topology to identify expansion opportunities.

    For large graphs (100k+ nodes), community detection is skipped by default
    since label propagation is O(nodes * edges * iterations). Use
    detect_communities=True on smaller graphs or sampled subsets.

    Returns a dict with:
    - cluster_info: detected communities and their characteristics
    - bridge_candidates: pairs of clusters with few inter-connections
    - missing_edge_types: edge types absent from the graph
    - hub_nodes: highest-degree nodes (potential expansion anchors)
    - leaf_nodes: degree-1 nodes (potential dead ends needing enrichment)
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    t0 = time.time()

    # Basic stats
    node_count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

    # Auto-skip community detection on large graphs
    large_graph = node_count > 50_000
    if large_graph and detect_communities:
        if verbose:
            print(f"  WARNING: {node_count:,} nodes — community detection will be slow")

    # Node type distribution
    type_dist = dict(conn.execute(
        "SELECT type, COUNT(*) FROM nodes GROUP BY type ORDER BY COUNT(*) DESC"
    ).fetchall())

    # Edge type distribution
    edge_types = dict(conn.execute(
        "SELECT type, COUNT(*) FROM edges GROUP BY type ORDER BY COUNT(*) DESC"
    ).fetchall())

    # Source distribution
    source_dist = dict(conn.execute(
        "SELECT source, COUNT(*) FROM nodes GROUP BY source ORDER BY COUNT(*) DESC"
    ).fetchall())

    # Degree distribution (top hubs) — use pre-computed counts for speed
    # For large graphs, compute degree from edge counts per node
    hub_query = """
        SELECT n.id, n.label, n.type,
               (SELECT COUNT(*) FROM edges e WHERE e.source_id = n.id OR e.target_id = n.id) as degree
        FROM nodes n
        ORDER BY degree DESC
        LIMIT 50
    """
    hubs = [dict(r) for r in conn.execute(hub_query).fetchall()]

    # Leaf nodes (degree 1) — sample for large graphs
    leaf_limit = 100
    leaf_query = """
        SELECT n.id, n.label, n.type,
               (SELECT COUNT(*) FROM edges e WHERE e.source_id = n.id OR e.target_id = n.id) as degree
        FROM nodes n
        WHERE (SELECT COUNT(*) FROM edges e WHERE e.source_id = n.id OR e.target_id = n.id) = 1
        LIMIT ?
    """
    leaves = [dict(r) for r in conn.execute(leaf_query, (leaf_limit,)).fetchall()]
    # Also get total leaf count
    leaf_total_query = """
        SELECT COUNT(*) FROM nodes n
        WHERE (SELECT COUNT(*) FROM edges e WHERE e.source_id = n.id OR e.target_id = n.id) = 1
    """
    leaf_total = conn.execute(leaf_total_query).fetchone()[0]

    # Orphan nodes (degree 0)
    orphan_query = """
        SELECT n.id, n.label, n.type
        FROM nodes n
        WHERE NOT EXISTS (SELECT 1 FROM edges e WHERE e.source_id = n.id OR e.target_id = n.id)
    """
    orphans = [dict(r) for r in conn.execute(orphan_query).fetchall()]

    # Missing edge types from the architecture spec
    spec_edge_types = {
        "RelatedTo", "IsA", "PartOf", "HasProperty", "DefinedAs", "SymbolOf",
        "Causes", "CausesDesire", "MotivatedByGoal", "UsedFor", "CreatedBy",
        "LocatedNear", "AtLocation", "CoLocatedWith",
        "SimultaneousWith", "FollowedBy", "DuringSameEra",
        "SoundsLike", "RhymesWith", "ContainsWord",
        "AssociatedWith", "AppearsWith", "ReferencedIn",
        "RemindsOf", "ExperiencedDuring", "LearnedFrom", "SaidBy",
        "FeelsLike", "OppositeMoodOf", "EvokedBy",
        "ContainedIn", "LayeredWith", "OverlaysOnto",
    }
    present_types = set(edge_types.keys())
    missing_types = spec_edge_types - present_types

    # Community detection (only on small graphs or when explicitly requested)
    communities = {}
    bridge_candidates = []
    if detect_communities and not large_graph:
        communities = _detect_communities(conn)
        bridge_candidates = _find_bridge_gaps(conn, communities)

    # For large graphs, use source-based clustering as a fast proxy
    source_clusters = {}
    if large_graph:
        for src in source_dist:
            sample = conn.execute(
                "SELECT id, label, type FROM nodes WHERE source = ? ORDER BY RANDOM() LIMIT 20",
                (src,)
            ).fetchall()
            source_clusters[src] = [dict(r) for r in sample]

    elapsed = time.time() - t0
    conn.close()

    result = {
        "node_count": node_count,
        "edge_count": edge_count,
        "type_distribution": type_dist,
        "edge_type_distribution": edge_types,
        "source_distribution": source_dist,
        "hub_nodes": hubs[:20],
        "leaf_nodes": leaves,
        "leaf_total": leaf_total,
        "orphan_nodes": orphans,
        "missing_edge_types": sorted(missing_types),
        "communities": communities,
        "source_clusters": source_clusters,
        "bridge_candidates": bridge_candidates,
        "survey_time_s": round(elapsed, 1),
    }

    if verbose:
        print(f"\n{'='*60}")
        print(f"Robody Graph Survey — Expansion Opportunity Analysis")
        print(f"{'='*60}")
        print(f"\nGraph: {node_count:,} nodes, {edge_count:,} edges")
        print(f"Survey time: {elapsed:.1f}s")
        print(f"\nNode types: {type_dist}")
        print(f"Sources: {source_dist}")

        print(f"\nTop 10 edge types:")
        for etype, count in sorted(edge_types.items(), key=lambda x: -x[1])[:10]:
            print(f"  {etype:<30s} {count:>8,}")

        print(f"\nMissing edge types ({len(missing_types)} from architecture spec):")
        for mt in sorted(missing_types):
            print(f"  {mt}")

        print(f"\nTop 10 hub nodes:")
        for h in hubs[:10]:
            print(f"  {h['label']:<30s} degree={h['degree']}")

        print(f"\nLeaf nodes (degree 1): {leaf_total:,} total (showing {len(leaves)})")
        if leaves:
            for lf in leaves[:10]:
                print(f"  {lf['label']}")
            if len(leaves) > 10:
                print(f"  ... and {leaf_total - 10:,} more")

        print(f"\nOrphan nodes (degree 0): {len(orphans)}")
        for o in orphans[:10]:
            print(f"  {o['label']}")

        if communities:
            print(f"\nCommunities detected: {len(communities)}")
            for cid, members in sorted(communities.items(), key=lambda x: -len(x[1]))[:10]:
                sample = [m["label"] for m in members[:5]]
                print(f"  Cluster {cid} ({len(members)} nodes): {', '.join(sample)}...")

            print(f"\nBridge candidates: {len(bridge_candidates)}")
            for bc in bridge_candidates[:10]:
                print(f"  Cluster {bc['c1']} ↔ Cluster {bc['c2']}: "
                      f"{bc['existing_bridges']} bridges, "
                      f"potential={bc['potential_score']:.2f}")
        elif large_graph:
            print(f"\nSource-based clusters (community detection skipped for {node_count:,} nodes):")
            for src, sample in source_clusters.items():
                labels = [s["label"] for s in sample[:5]]
                print(f"  {src}: {', '.join(labels)}...")

    return result


def _detect_communities(conn, max_iterations=20):
    """
    Simple label propagation community detection.
    No external deps — just SQL and Python.
    """
    # Initialize each node with its own community
    nodes = conn.execute("SELECT id, label, type FROM nodes").fetchall()
    community = {n["id"]: n["id"] for n in nodes}

    # Build adjacency with weights
    edges = conn.execute(
        "SELECT source_id, target_id, weight FROM edges WHERE weight > 0"
    ).fetchall()

    adjacency = defaultdict(list)
    for e in edges:
        adjacency[e["source_id"]].append((e["target_id"], e["weight"]))
        adjacency[e["target_id"]].append((e["source_id"], e["weight"]))

    # Iterate: each node adopts the most common community among neighbors
    node_ids = list(community.keys())
    for iteration in range(max_iterations):
        changed = 0
        random.shuffle(node_ids)
        for nid in node_ids:
            neighbors = adjacency.get(nid, [])
            if not neighbors:
                continue

            # Weighted vote
            votes = Counter()
            for neighbor_id, weight in neighbors:
                votes[community[neighbor_id]] += max(weight, 0.01)

            best = votes.most_common(1)[0][0]
            if community[nid] != best:
                community[nid] = best
                changed += 1

        if changed == 0:
            break

    # Group nodes by community
    groups = defaultdict(list)
    node_map = {n["id"]: dict(n) for n in nodes}
    for nid, cid in community.items():
        if nid in node_map:
            groups[cid].append(node_map[nid])

    # Filter to communities with 2+ members, renumber
    result = {}
    for i, (cid, members) in enumerate(
        sorted(groups.items(), key=lambda x: -len(x[1]))
    ):
        if len(members) >= 2:
            result[i] = members

    return result


def _find_bridge_gaps(conn, communities, min_size=3):
    """Find pairs of communities with few connecting edges."""
    # Build community membership lookup
    node_to_community = {}
    for cid, members in communities.items():
        for m in members:
            node_to_community[m["id"]] = cid

    # Count inter-community edges
    inter_edges = Counter()
    edges = conn.execute("SELECT source_id, target_id FROM edges").fetchall()
    for e in edges:
        c1 = node_to_community.get(e["source_id"])
        c2 = node_to_community.get(e["target_id"])
        if c1 is not None and c2 is not None and c1 != c2:
            pair = (min(c1, c2), max(c1, c2))
            inter_edges[pair] += 1

    # Score: communities that are large but have few bridges
    candidates = []
    large_communities = {cid: m for cid, m in communities.items() if len(m) >= min_size}
    cids = sorted(large_communities.keys())

    for i, c1 in enumerate(cids):
        for c2 in cids[i+1:]:
            pair = (min(c1, c2), max(c1, c2))
            bridges = inter_edges.get(pair, 0)
            size_product = len(large_communities[c1]) * len(large_communities[c2])
            # Potential score: large communities with few bridges score higher
            potential = size_product / (bridges + 1)
            candidates.append({
                "c1": c1, "c2": c2,
                "c1_size": len(large_communities[c1]),
                "c2_size": len(large_communities[c2]),
                "existing_bridges": bridges,
                "potential_score": potential,
            })

    candidates.sort(key=lambda x: -x["potential_score"])
    return candidates


# -------------------------------------------------------------------
# Expansion Mode 1: Cluster Bridging
# -------------------------------------------------------------------

def bridge_clusters(db_path=DB_PATH, dry_run=False, verbose=True, max_bridges=20):
    """
    Find isolated clusters and propose rational connections between them.

    Uses the LLM to generate plausible connections between concepts in
    different clusters that should logically be related but aren't.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    communities = _detect_communities(conn)
    bridge_gaps = _find_bridge_gaps(conn, communities)

    if verbose:
        print(f"\n{'='*60}")
        print(f"Rational Expansion — Cluster Bridging")
        print(f"{'='*60}")
        print(f"Found {len(bridge_gaps)} cluster pairs to consider")

    bridges_created = 0

    for gap in bridge_gaps[:max_bridges]:
        c1_members = communities.get(gap["c1"], [])
        c2_members = communities.get(gap["c2"], [])

        if not c1_members or not c2_members:
            continue

        # Sample representative nodes from each cluster
        c1_sample = random.sample(c1_members, min(5, len(c1_members)))
        c2_sample = random.sample(c2_members, min(5, len(c2_members)))

        c1_labels = [m["label"].replace("_", " ") for m in c1_sample]
        c2_labels = [m["label"].replace("_", " ") for m in c2_sample]

        prompt = (
            f"Two groups of concepts have no connections between them:\n"
            f"Group A: {', '.join(c1_labels)}\n"
            f"Group B: {', '.join(c2_labels)}\n\n"
            f"Propose 1-3 specific connections between concepts from "
            f"Group A and Group B. Use this format:\n"
            f"CONCEPT_A -> RELATION -> CONCEPT_B: reason\n\n"
            f"Valid relations: RelatedTo, Causes, SymbolOf, FeelsLike, "
            f"AssociatedWith, RemindsOf, SoundsLike, LocatedNear, UsedFor"
        )

        if verbose:
            print(f"\n  Bridging Cluster {gap['c1']} ↔ Cluster {gap['c2']}:")
            print(f"    A: {', '.join(c1_labels)}")
            print(f"    B: {', '.join(c2_labels)}")

        response = call_llm(prompt, temperature=0.6, max_tokens=300, dry_run=dry_run)
        if not response:
            continue

        if verbose:
            print(f"    LLM: {response[:200]}")

        # Parse response for edges
        proposed_edges = _parse_edge_proposals(response)

        for edge in proposed_edges:
            src_label = _normalize_label(edge["source"])
            tgt_label = _normalize_label(edge["target"])
            rel_type = edge["relation"]

            # Look up nodes
            src = conn.execute(
                "SELECT id FROM nodes WHERE label = ?", (src_label,)
            ).fetchone()
            tgt = conn.execute(
                "SELECT id FROM nodes WHERE label = ?", (tgt_label,)
            ).fetchone()

            if not src or not tgt:
                if verbose:
                    print(f"    SKIP (node not found): {src_label} -> {tgt_label}")
                continue

            if not dry_run:
                try:
                    conn.execute(
                        """INSERT INTO edges (source_id, target_id, type, weight, layer, speculative)
                           VALUES (?, ?, ?, 0.8, 1, 0)""",
                        (src["id"], tgt["id"], rel_type)
                    )
                    bridges_created += 1
                    if verbose:
                        print(f"    ✓ {src_label} -[{rel_type}]-> {tgt_label} (weight 0.8, layer 1)")
                except sqlite3.IntegrityError:
                    if verbose:
                        print(f"    DUPE: {src_label} -[{rel_type}]-> {tgt_label}")

    if not dry_run:
        conn.commit()

    conn.close()

    if verbose:
        print(f"\n  Bridges created: {bridges_created}")

    return bridges_created


# -------------------------------------------------------------------
# Expansion Mode 2: Knowledge Condensates
# -------------------------------------------------------------------

def generate_condensates(db_path=DB_PATH, dry_run=False, verbose=True,
                         num_condensates=10, anchor_count=3):
    """
    Generate knowledge condensates — compressed narrative fragments
    that encode multiple relationships and surprise connections.

    Each condensate becomes a 'knowledge' node with edges to the
    concepts it references. These create rich traversal paths for
    future dream walks.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Find interesting anchor points: high-degree nodes from different clusters
    communities = _detect_communities(conn)
    anchors = _select_diverse_anchors(conn, communities, anchor_count)

    if verbose:
        print(f"\n{'='*60}")
        print(f"Rational Expansion — Knowledge Condensates")
        print(f"{'='*60}")

    condensates_created = 0

    for _ in range(num_condensates):
        # Pick 3-5 seed concepts, mixing clusters
        seeds = random.sample(anchors, min(random.randint(3, 5), len(anchors)))
        seed_labels = [s["label"].replace("_", " ") for s in seeds]

        prompt = (
            f"Generate a knowledge condensate connecting these concepts: "
            f"{', '.join(seed_labels)}.\n\n"
            f"A knowledge condensate is a single paragraph (3-5 sentences) that "
            f"weaves these concepts together through REAL facts, history, science, "
            f"or culture. Include at least one surprising or non-obvious connection.\n\n"
            f"End with a one-line summary of the key relationship."
        )

        if verbose:
            print(f"\n  Seeds: {', '.join(seed_labels)}")

        response = call_llm(
            prompt, system=CONDENSATE_SYSTEM,
            temperature=0.7, max_tokens=400,
            dry_run=dry_run, verbose=verbose
        )
        if not response:
            continue

        if verbose:
            print(f"  Condensate: {response[:200]}...")

        if dry_run:
            continue

        # Create a knowledge node for the condensate
        condensate_label = f"condensate_{int(time.time())}_{random.randint(0, 999)}"
        try:
            cur = conn.execute(
                """INSERT INTO nodes (label, type, source, metadata)
                   VALUES (?, 'knowledge', 'rational_expansion', ?)""",
                (condensate_label, json.dumps({
                    "text": response,
                    "seed_concepts": seed_labels,
                    "created": datetime.now().isoformat(),
                }))
            )
            condensate_id = cur.lastrowid

            # Link to seed concepts
            for seed in seeds:
                try:
                    conn.execute(
                        """INSERT INTO edges (source_id, target_id, type, weight, layer, speculative)
                           VALUES (?, ?, 'EncondensedFrom', 1.5, 1, 0)""",
                        (condensate_id, seed["id"])
                    )
                except sqlite3.IntegrityError:
                    pass

            condensates_created += 1
            if verbose:
                print(f"  ✓ Created {condensate_label} linked to {len(seeds)} concepts")

        except sqlite3.IntegrityError as e:
            if verbose:
                print(f"  ERROR creating condensate: {e}")

    if not dry_run:
        conn.commit()
    conn.close()

    if verbose:
        print(f"\n  Condensates created: {condensates_created}")

    return condensates_created


def _select_diverse_anchors(conn, communities, per_cluster=3):
    """Pick high-degree nodes from diverse clusters."""
    anchors = []
    for cid, members in sorted(communities.items(), key=lambda x: -len(x[1])):
        if len(members) < 3:
            continue
        # Get degree for each member
        member_ids = [m["id"] for m in members]
        if not member_ids:
            continue
        placeholders = ",".join("?" * len(member_ids))
        degrees = conn.execute(f"""
            SELECT n.id, n.label, n.type, COUNT(e.id) as degree
            FROM nodes n
            LEFT JOIN edges e ON n.id = e.source_id OR n.id = e.target_id
            WHERE n.id IN ({placeholders})
            GROUP BY n.id
            ORDER BY degree DESC
            LIMIT ?
        """, member_ids + [per_cluster]).fetchall()
        anchors.extend([dict(d) for d in degrees])

    return anchors


# -------------------------------------------------------------------
# Expansion Mode 3: Missing Edge Types
# -------------------------------------------------------------------

def enrich_edge_types(db_path=DB_PATH, dry_run=False, verbose=True, batch_size=20):
    """
    Add edge types that ConceptNet completely lacks:
    phonetic, cultural, emotional, personal, temporal connections.

    ConceptNet is great for semantic/causal edges but has no:
    - SoundsLike / RhymesWith (phonetic)
    - AssociatedWith / ReferencedIn (cultural)
    - FeelsLike / EvokedBy (emotional)
    - SimultaneousWith / DuringSameEra (temporal)

    These are exactly the edge types that make dream walks interesting.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get a sample of high-degree concept nodes
    concepts = conn.execute("""
        SELECT n.id, n.label, n.type, COUNT(e.id) as degree
        FROM nodes n
        LEFT JOIN edges e ON n.id = e.source_id OR n.id = e.target_id
        WHERE n.type = 'concept'
        GROUP BY n.id
        HAVING degree >= 3
        ORDER BY RANDOM()
        LIMIT ?
    """, (batch_size * 3,)).fetchall()

    if verbose:
        print(f"\n{'='*60}")
        print(f"Rational Expansion — Missing Edge Types")
        print(f"{'='*60}")
        print(f"Sampling from {len(concepts)} well-connected concepts")

    edges_added = 0
    type_counts = Counter()

    # Process in batches
    for i in range(0, len(concepts), 5):
        batch = concepts[i:i+5]
        labels = [c["label"].replace("_", " ") for c in batch]

        prompt = (
            f"For these concepts: {', '.join(labels)}\n\n"
            f"Propose connections using ONLY these relation types:\n"
            f"- SoundsLike: phonetic similarity (rhymes, alliteration, puns)\n"
            f"- AssociatedWith: cultural/media associations\n"
            f"- FeelsLike: emotional or sensory similarity\n"
            f"- DuringSameEra: temporal co-occurrence\n"
            f"- SymbolOf: symbolic/metaphoric meaning\n\n"
            f"Format: CONCEPT -> RELATION -> TARGET: reason\n"
            f"Propose 2-4 connections. TARGET can be any concept, not just from the list."
        )

        response = call_llm(prompt, temperature=0.65, max_tokens=300,
                           dry_run=dry_run, verbose=verbose)
        if not response:
            continue

        proposed = _parse_edge_proposals(response)

        for edge in proposed:
            src_label = _normalize_label(edge["source"])
            tgt_label = _normalize_label(edge["target"])
            rel_type = edge["relation"]

            # Only allow the enrichment types
            if rel_type not in {"SoundsLike", "RhymesWith", "AssociatedWith",
                                "FeelsLike", "DuringSameEra", "SymbolOf",
                                "ReferencedIn", "EvokedBy", "SimultaneousWith"}:
                continue

            # Get or create target node
            src = conn.execute(
                "SELECT id FROM nodes WHERE label = ?", (src_label,)
            ).fetchone()
            tgt = conn.execute(
                "SELECT id FROM nodes WHERE label = ?", (tgt_label,)
            ).fetchone()

            if not src:
                continue

            if not tgt and not dry_run:
                # Create new node for the target
                try:
                    cur = conn.execute(
                        "INSERT INTO nodes (label, type, source) VALUES (?, 'concept', 'rational_expansion')",
                        (tgt_label,)
                    )
                    tgt_id = cur.lastrowid
                except sqlite3.IntegrityError:
                    tgt = conn.execute(
                        "SELECT id FROM nodes WHERE label = ?", (tgt_label,)
                    ).fetchone()
                    tgt_id = tgt["id"] if tgt else None
            else:
                tgt_id = tgt["id"] if tgt else None

            if not tgt_id:
                continue

            if not dry_run:
                try:
                    conn.execute(
                        """INSERT INTO edges (source_id, target_id, type, weight, layer, speculative)
                           VALUES (?, ?, ?, 0.8, 1, 0)""",
                        (src["id"], tgt_id, rel_type)
                    )
                    edges_added += 1
                    type_counts[rel_type] += 1
                    if verbose:
                        print(f"  ✓ {src_label} -[{rel_type}]-> {tgt_label}")
                except sqlite3.IntegrityError:
                    pass

        if edges_added >= batch_size:
            break

    if not dry_run:
        conn.commit()
    conn.close()

    if verbose:
        print(f"\n  Edges added: {edges_added}")
        for rt, c in type_counts.most_common():
            print(f"    {rt}: {c}")

    return edges_added


# -------------------------------------------------------------------
# Expansion Mode 4: Narrative Seeding
# -------------------------------------------------------------------

def seed_narratives(db_path=DB_PATH, dry_run=False, verbose=True, num_seeds=5):
    """
    Plant narrative fragments that enable story-like traversals.

    These are dream_fragment nodes with FollowedBy edges that create
    small narrative chains. During dream walks, finding these gives
    the dream something to structure around.

    Examples:
    - "someone_left_a_light_on" -> FollowedBy -> "the_house_remembers"
    - "the_sound_stopped" -> FollowedBy -> "waiting_for_it_again"
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    if verbose:
        print(f"\n{'='*60}")
        print(f"Rational Expansion — Narrative Seeding")
        print(f"{'='*60}")

    # Get some evocative concepts to seed narratives from
    evocative = conn.execute("""
        SELECT n.id, n.label FROM nodes n
        JOIN edges e ON n.id = e.source_id OR n.id = e.target_id
        WHERE n.type IN ('concept', 'memory', 'dream_fragment')
        GROUP BY n.id
        HAVING COUNT(e.id) >= 2
        ORDER BY RANDOM()
        LIMIT 30
    """).fetchall()

    seeds_created = 0

    for _ in range(num_seeds):
        # Pick 2-3 evocative concepts
        sample = random.sample(list(evocative), min(3, len(evocative)))
        concepts = [s["label"].replace("_", " ") for s in sample]

        prompt = (
            f"Create a tiny narrative chain (2-3 fragments) inspired by: "
            f"{', '.join(concepts)}\n\n"
            f"Each fragment should be a poetic observation or image, like:\n"
            f"- 'the light changed but no one noticed'\n"
            f"- 'something heavy in the air today'\n"
            f"- 'the sound of closing doors'\n\n"
            f"Output exactly 2-3 fragments, one per line. Short. Evocative. "
            f"Not a story, just images that suggest one."
        )

        response = call_llm(prompt, temperature=0.85, max_tokens=150,
                           dry_run=dry_run, verbose=verbose)
        if not response:
            continue

        # Parse fragments (one per line)
        fragments = [
            _normalize_label(line.strip().strip("'\"-.•*"))
            for line in response.split("\n")
            if line.strip() and len(line.strip()) > 5
        ][:3]

        if len(fragments) < 2:
            continue

        if verbose:
            print(f"\n  Seed concepts: {', '.join(concepts)}")
            print(f"  Fragments: {fragments}")

        if dry_run:
            continue

        # Create fragment nodes and link them
        prev_id = None
        for frag in fragments:
            try:
                cur = conn.execute(
                    """INSERT INTO nodes (label, type, source, metadata)
                       VALUES (?, 'dream_fragment', 'rational_expansion', ?)""",
                    (frag, json.dumps({"seed_concepts": concepts}))
                )
                frag_id = cur.lastrowid

                # Link to seed concepts
                for s in sample:
                    try:
                        conn.execute(
                            """INSERT INTO edges (source_id, target_id, type, weight, layer, speculative)
                               VALUES (?, ?, 'EvokedBy', 0.5, 1, 0)""",
                            (frag_id, s["id"])
                        )
                    except sqlite3.IntegrityError:
                        pass

                # Chain fragments with FollowedBy
                if prev_id is not None:
                    try:
                        conn.execute(
                            """INSERT INTO edges (source_id, target_id, type, weight, layer, speculative)
                               VALUES (?, ?, 'FollowedBy', 1.0, 1, 0)""",
                            (prev_id, frag_id)
                        )
                    except sqlite3.IntegrityError:
                        pass

                prev_id = frag_id
                seeds_created += 1

            except sqlite3.IntegrityError:
                if verbose:
                    print(f"  DUPE: {frag}")

    if not dry_run:
        conn.commit()
    conn.close()

    if verbose:
        print(f"\n  Narrative fragments created: {seeds_created}")

    return seeds_created


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


def _parse_edge_proposals(text):
    """
    Parse LLM output for edge proposals in the format:
    CONCEPT -> RELATION -> TARGET: reason
    """
    edges = []
    for line in text.split("\n"):
        line = line.strip().strip("-•*")
        if "->" not in line:
            continue
        parts = line.split("->")
        if len(parts) < 3:
            continue
        source = parts[0].strip()
        relation = parts[1].strip()
        # Target might have ": reason" after it
        target_part = "->".join(parts[2:])
        if ":" in target_part:
            target = target_part.split(":")[0].strip()
        else:
            target = target_part.strip()
        edges.append({
            "source": source,
            "relation": relation,
            "target": target,
        })
    return edges


def log_expansion(entry, log_dir=LOG_DIR):
    """Log an expansion operation."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"expansion_{datetime.now().strftime('%Y%m%d')}.jsonl"
    with open(log_file, "a") as f:
        f.write(json.dumps(entry) + "\n")


# -------------------------------------------------------------------
# Full expansion pipeline
# -------------------------------------------------------------------

def run_full_expansion(db_path=DB_PATH, dry_run=False, verbose=True):
    """
    Run the complete Stage 2 rational expansion pipeline:
    1. Survey graph topology
    2. Bridge isolated clusters
    3. Generate knowledge condensates
    4. Enrich missing edge types
    5. Seed narrative fragments
    """
    if verbose:
        print(f"\n{'='*60}")
        print(f"STAGE 2: RATIONAL EXPANSION — FULL PIPELINE")
        print(f"{'='*60}")

    t0 = time.time()
    results = {}

    # 1. Survey
    if verbose:
        print("\n[1/5] Surveying graph topology...")
    survey = survey_graph(db_path, verbose=verbose)
    results["survey"] = {
        "nodes": survey["node_count"],
        "edges": survey["edge_count"],
        "communities": len(survey["communities"]),
        "orphans": len(survey["orphan_nodes"]),
        "missing_types": len(survey["missing_edge_types"]),
    }

    # 2. Bridge clusters
    if verbose:
        print("\n[2/5] Bridging isolated clusters...")
    bridges = bridge_clusters(db_path, dry_run=dry_run, verbose=verbose)
    results["bridges_created"] = bridges

    # 3. Knowledge condensates
    if verbose:
        print("\n[3/5] Generating knowledge condensates...")
    condensates = generate_condensates(db_path, dry_run=dry_run, verbose=verbose)
    results["condensates_created"] = condensates

    # 4. Missing edge types
    if verbose:
        print("\n[4/5] Enriching missing edge types...")
    enriched = enrich_edge_types(db_path, dry_run=dry_run, verbose=verbose)
    results["edges_enriched"] = enriched

    # 5. Narrative seeds
    if verbose:
        print("\n[5/5] Seeding narrative fragments...")
    narratives = seed_narratives(db_path, dry_run=dry_run, verbose=verbose)
    results["narratives_seeded"] = narratives

    elapsed = time.time() - t0

    # Log results
    log_expansion({
        "timestamp": datetime.now().isoformat(),
        "operation": "full_expansion",
        "results": results,
        "elapsed_s": round(elapsed, 1),
        "dry_run": dry_run,
    })

    if verbose:
        print(f"\n{'='*60}")
        print(f"Stage 2 Expansion Complete — {elapsed:.1f}s")
        print(f"{'='*60}")
        print(f"  Bridges created:    {bridges}")
        print(f"  Condensates:        {condensates}")
        print(f"  Edge types added:   {enriched}")
        print(f"  Narrative seeds:    {narratives}")

    return results


# -------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Robody Stage 2: Rational Expansion"
    )
    parser.add_argument("--db", type=str, default=str(DB_PATH),
                        help=f"Database path (default: {DB_PATH})")
    parser.add_argument("--survey", action="store_true",
                        help="Survey graph topology only")
    parser.add_argument("--bridge", action="store_true",
                        help="Bridge isolated clusters")
    parser.add_argument("--condense", action="store_true",
                        help="Generate knowledge condensates")
    parser.add_argument("--enrich", action="store_true",
                        help="Add missing edge types")
    parser.add_argument("--narratives", action="store_true",
                        help="Seed narrative fragments")
    parser.add_argument("--full", action="store_true",
                        help="Run full expansion pipeline")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't modify database")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    db = Path(args.db)
    v = not args.quiet

    if args.survey:
        survey_graph(db, verbose=v)
    elif args.bridge:
        bridge_clusters(db, dry_run=args.dry_run, verbose=v)
    elif args.condense:
        generate_condensates(db, dry_run=args.dry_run, verbose=v)
    elif args.enrich:
        enrich_edge_types(db, dry_run=args.dry_run, verbose=v)
    elif args.narratives:
        seed_narratives(db, dry_run=args.dry_run, verbose=v)
    elif args.full:
        run_full_expansion(db, dry_run=args.dry_run, verbose=v)
    else:
        # Default: survey
        survey_graph(db, verbose=v)
