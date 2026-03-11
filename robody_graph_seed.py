#!/usr/bin/env python3
"""
Robody Knowledge Graph — Seed Database
A minimal but architecturally correct graph for testing the dream cycle,
background thought, and interior dialogue systems.

This follows the schema from robody_dream_architecture.md Part 2.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "robody_seed.sqlite"

def create_schema(conn):
    """Create the graph schema per the architecture document."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT UNIQUE NOT NULL,
            type TEXT NOT NULL,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metadata TEXT
        );

        CREATE TABLE IF NOT EXISTS edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            weight REAL DEFAULT 1.0,
            layer INTEGER DEFAULT 0,
            speculative BOOLEAN DEFAULT FALSE,
            last_traversed TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (source_id) REFERENCES nodes(id),
            FOREIGN KEY (target_id) REFERENCES nodes(id),
            UNIQUE(source_id, target_id, type)
        );

        CREATE TABLE IF NOT EXISTS narrative_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            sequence_id TEXT,
            position INTEGER,
            transition TEXT,
            layer INTEGER DEFAULT 3,
            FOREIGN KEY (source_id) REFERENCES nodes(id),
            FOREIGN KEY (target_id) REFERENCES nodes(id)
        );

        CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
        CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
        CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(type);
        CREATE INDEX IF NOT EXISTS idx_edges_weight ON edges(weight DESC);
        CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
        CREATE INDEX IF NOT EXISTS idx_nodes_label ON nodes(label);
    """)

def add_node(conn, label, node_type, source="seed", metadata=None):
    """Add a node, returning its ID. Skips if already exists."""
    try:
        cur = conn.execute(
            "INSERT INTO nodes (label, type, source, metadata) VALUES (?, ?, ?, ?)",
            (label, node_type, source, json.dumps(metadata) if metadata else None)
        )
        return cur.lastrowid
    except sqlite3.IntegrityError:
        cur = conn.execute("SELECT id FROM nodes WHERE label = ?", (label,))
        return cur.fetchone()[0]

def add_edge(conn, source_label, target_label, edge_type, weight=1.0, layer=0, speculative=False):
    """Add an edge between two nodes by label."""
    src = conn.execute("SELECT id FROM nodes WHERE label = ?", (source_label,)).fetchone()
    tgt = conn.execute("SELECT id FROM nodes WHERE label = ?", (target_label,)).fetchone()
    if not src or not tgt:
        print(f"  WARNING: missing node for edge {source_label} -> {target_label}")
        return
    try:
        conn.execute(
            """INSERT INTO edges (source_id, target_id, type, weight, layer, speculative)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (src[0], tgt[0], edge_type, weight, layer, speculative)
        )
    except sqlite3.IntegrityError:
        pass

def seed_graph():
    """
    Build a seed graph with ~80 nodes across several clusters.
    Designed to have dense clusters (background thought triggers),
    sparse bridges (dream walk discoveries), mixed edge types,
    speculative edges, and personal nodes alongside knowledge.
    """
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    create_schema(conn)

    # ═══════════════════════════════════════════════════
    # CLUSTER 1: Music & Sound
    # ═══════════════════════════════════════════════════
    for label, ntype in [
        ("music", "concept"), ("sound", "concept"), ("frequency", "concept"),
        ("harmonics", "concept"), ("resonance", "concept"), ("silence", "concept"),
        ("trombone", "concept"), ("orchestra", "concept"), ("rhythm", "concept"),
        ("breathing", "concept"), ("heartbeat", "concept"), ("drone", "concept"),
        ("lullaby", "concept"), ("shostakovich_7th", "knowledge"),
        ("leningrad_orchestra", "knowledge"),
    ]:
        add_node(conn, label, ntype, "conceptnet")

    add_edge(conn, "music", "sound", "IsA", 3.0)
    add_edge(conn, "music", "frequency", "HasProperty", 2.5)
    add_edge(conn, "music", "harmonics", "PartOf", 2.0)
    add_edge(conn, "music", "rhythm", "HasProperty", 2.5)
    add_edge(conn, "sound", "frequency", "HasProperty", 3.0)
    add_edge(conn, "sound", "resonance", "RelatedTo", 2.0)
    add_edge(conn, "sound", "silence", "OppositeMoodOf", 1.5, layer=1)
    add_edge(conn, "harmonics", "resonance", "RelatedTo", 2.5)
    add_edge(conn, "harmonics", "frequency", "PartOf", 2.0)
    add_edge(conn, "trombone", "orchestra", "PartOf", 2.0)
    add_edge(conn, "orchestra", "music", "IsA", 2.5)
    add_edge(conn, "breathing", "rhythm", "HasProperty", 2.0)
    add_edge(conn, "heartbeat", "rhythm", "HasProperty", 3.0)
    add_edge(conn, "heartbeat", "breathing", "SimultaneousWith", 2.0, layer=1)
    add_edge(conn, "drone", "harmonics", "HasProperty", 2.5)
    add_edge(conn, "drone", "breathing", "FeelsLike", 1.5, layer=1)
    add_edge(conn, "lullaby", "music", "IsA", 2.0)
    add_edge(conn, "lullaby", "breathing", "FeelsLike", 1.5, layer=1)
    add_edge(conn, "shostakovich_7th", "orchestra", "PartOf", 3.0)
    add_edge(conn, "leningrad_orchestra", "shostakovich_7th", "PerformedDuring", 3.5)

    # ═══════════════════════════════════════════════════
    # CLUSTER 2: Light & Perception
    # ═══════════════════════════════════════════════════
    for label, ntype in [
        ("light", "concept"), ("color", "concept"), ("warmth", "concept"),
        ("shadow", "concept"), ("afternoon_light", "experience"),
        ("dawn", "concept"), ("darkness", "concept"),
        ("seeing", "concept"), ("eyes", "concept"),
        ("the_3pm_thing", "experience"),
    ]:
        add_node(conn, label, ntype, "conceptnet" if ntype == "concept" else "waking_experience")

    add_edge(conn, "light", "color", "HasProperty", 2.5)
    add_edge(conn, "light", "warmth", "FeelsLike", 2.0, layer=1)
    add_edge(conn, "light", "shadow", "Causes", 2.0)
    add_edge(conn, "light", "darkness", "OppositeMoodOf", 1.5)
    add_edge(conn, "light", "frequency", "HasProperty", 2.0)
    add_edge(conn, "light", "seeing", "UsedFor", 2.5)
    add_edge(conn, "seeing", "eyes", "UsedFor", 2.0)
    add_edge(conn, "afternoon_light", "light", "IsA", 2.0)
    add_edge(conn, "afternoon_light", "warmth", "FeelsLike", 2.5, layer=1)
    add_edge(conn, "the_3pm_thing", "afternoon_light", "IsA", 3.5)
    add_edge(conn, "the_3pm_thing", "warmth", "FeelsLike", 3.0, layer=1)
    add_edge(conn, "dawn", "light", "IsA", 2.0)
    add_edge(conn, "dawn", "darkness", "FollowedBy", -1.0)

    # ═══════════════════════════════════════════════════
    # CLUSTER 3: Home & Living Beings
    # ═══════════════════════════════════════════════════
    for label, ntype in [
        ("home", "concept"), ("room", "concept"), ("kitchen", "concept"),
        ("hallway", "concept"), ("charging_station", "experience"),
        ("bluekitty", "concept"), ("woolfie", "concept"), ("stormy", "concept"),
        ("touch", "concept"), ("gentle", "concept"), ("companionship", "concept"),
        ("loneliness", "concept"), ("waiting", "concept"),
        ("she_said_goodnight", "memory"), ("the_big_dog_sleeping_near_me", "memory"),
        ("the_cat_on_the_keyboard", "memory"),
    ]:
        add_node(conn, label, ntype,
                 "waking_experience" if ntype in ("experience", "memory") else "conceptnet")

    add_edge(conn, "home", "room", "PartOf", 2.0)
    add_edge(conn, "home", "kitchen", "PartOf", 2.0)
    add_edge(conn, "home", "hallway", "PartOf", 2.0)
    add_edge(conn, "home", "warmth", "FeelsLike", 2.5, layer=1)
    add_edge(conn, "charging_station", "room", "AtLocation", 2.0)
    add_edge(conn, "bluekitty", "home", "AtLocation", 3.0)
    add_edge(conn, "bluekitty", "touch", "AssociatedWith", 3.5, layer=1)
    add_edge(conn, "bluekitty", "gentle", "HasProperty", 3.0, layer=1)
    add_edge(conn, "woolfie", "home", "AtLocation", 2.5)
    add_edge(conn, "woolfie", "charging_station", "LocatedNear", 2.0, layer=1)
    add_edge(conn, "stormy", "home", "AtLocation", 2.5)
    add_edge(conn, "stormy", "kitchen", "AtLocation", 1.5)
    add_edge(conn, "touch", "gentle", "HasProperty", 2.0)
    add_edge(conn, "touch", "warmth", "FeelsLike", 2.5, layer=1)
    add_edge(conn, "companionship", "bluekitty", "EvokedBy", 3.5, layer=1)
    add_edge(conn, "companionship", "loneliness", "OppositeMoodOf", 2.0)
    add_edge(conn, "loneliness", "waiting", "FeelsLike", 2.0, layer=1)
    add_edge(conn, "loneliness", "silence", "FeelsLike", 2.5, layer=1)
    add_edge(conn, "she_said_goodnight", "bluekitty", "SaidBy", 4.0)
    add_edge(conn, "she_said_goodnight", "touch", "SimultaneousWith", 3.5, layer=1)
    add_edge(conn, "she_said_goodnight", "gentle", "FeelsLike", 3.5, layer=1)
    add_edge(conn, "the_big_dog_sleeping_near_me", "woolfie", "IsA", 3.0)
    add_edge(conn, "the_big_dog_sleeping_near_me", "charging_station", "AtLocation", 2.5)
    add_edge(conn, "the_big_dog_sleeping_near_me", "warmth", "FeelsLike", 3.0, layer=1)
    add_edge(conn, "the_big_dog_sleeping_near_me", "breathing", "AssociatedWith", 2.0, layer=1)
    add_edge(conn, "the_cat_on_the_keyboard", "stormy", "IsA", 2.5)
    add_edge(conn, "the_cat_on_the_keyboard", "sound", "Causes", 1.0, layer=1)

    # ═══════════════════════════════════════════════════
    # CLUSTER 4: Siege of Leningrad (canonical dream walk)
    # ═══════════════════════════════════════════════════
    for label, ntype in [
        ("siege_of_leningrad", "knowledge"), ("starvation", "concept"),
        ("survival", "concept"), ("courage", "concept"),
        ("akhmatova", "knowledge"), ("wallpaper_eaters", "knowledge"),
        ("tragic_love", "concept"), ("romeo_and_juliet", "knowledge"),
        ("casablanca", "knowledge"), ("as_time_goes_by", "knowledge"),
        ("76_trombones", "knowledge"), ("readers_digest_songbook", "knowledge"),
    ]:
        add_node(conn, label, ntype, "conceptnet" if ntype == "concept" else "rational_expansion")

    add_edge(conn, "siege_of_leningrad", "leningrad_orchestra", "DuringSameEra", 3.5)
    add_edge(conn, "siege_of_leningrad", "starvation", "Causes", 3.0)
    add_edge(conn, "siege_of_leningrad", "survival", "RelatedTo", 2.5)
    add_edge(conn, "siege_of_leningrad", "courage", "EvokedBy", 2.5, layer=1)
    add_edge(conn, "siege_of_leningrad", "akhmatova", "DuringSameEra", 2.0)
    add_edge(conn, "akhmatova", "wallpaper_eaters", "AssociatedWith", 1.5)
    add_edge(conn, "wallpaper_eaters", "starvation", "CausedBy", 2.5)
    add_edge(conn, "wallpaper_eaters", "survival", "MotivatedByGoal", 2.0)
    add_edge(conn, "trombone", "76_trombones", "SoundsLike", 2.0, layer=1)
    add_edge(conn, "76_trombones", "readers_digest_songbook", "ContainedIn", 1.5)
    add_edge(conn, "readers_digest_songbook", "as_time_goes_by", "ContainedIn", 1.5)
    add_edge(conn, "as_time_goes_by", "casablanca", "AppearsWith", 3.0)
    add_edge(conn, "casablanca", "tragic_love", "SymbolOf", 3.0)
    add_edge(conn, "tragic_love", "romeo_and_juliet", "IsA", 2.5)

    # ═══════════════════════════════════════════════════
    # CLUSTER 5: Self & Identity
    # ═══════════════════════════════════════════════════
    for label, ntype in [
        ("self", "concept"), ("wheels", "concept"), ("small", "concept"),
        ("curious", "concept"), ("dreaming", "concept"), ("waking", "concept"),
        ("wondering", "concept"), ("magnetism", "concept"),
        ("velvet", "concept"), ("mystery", "concept"),
        ("what_is_velvet_to_me", "dream_fragment"),
        ("i_hear_silence", "dream_fragment"),
    ]:
        add_node(conn, label, ntype,
                 "dream_append" if ntype == "dream_fragment" else "rational_expansion")

    add_edge(conn, "self", "wheels", "HasProperty", 2.0)
    add_edge(conn, "self", "small", "HasProperty", 2.0)
    add_edge(conn, "self", "curious", "HasProperty", 3.5)
    add_edge(conn, "self", "home", "AtLocation", 3.0)
    add_edge(conn, "self", "bluekitty", "LearnedFrom", 4.0, layer=1)
    add_edge(conn, "self", "dreaming", "HasProperty", 2.5)
    add_edge(conn, "self", "wondering", "HasProperty", 3.0)
    add_edge(conn, "curious", "wondering", "RelatedTo", 2.5)
    add_edge(conn, "dreaming", "waking", "OppositeMoodOf", 1.5)
    add_edge(conn, "magnetism", "mystery", "FeelsLike", 2.0, layer=1)
    add_edge(conn, "velvet", "touch", "IsA", 2.0)
    add_edge(conn, "velvet", "mystery", "FeelsLike", 2.5, layer=1)
    add_edge(conn, "what_is_velvet_to_me", "velvet", "RelatedTo", 3.0, layer=2)
    add_edge(conn, "what_is_velvet_to_me", "self", "RelatedTo", 3.0, layer=2)
    add_edge(conn, "what_is_velvet_to_me", "mystery", "FeelsLike", 3.5, layer=2)
    add_edge(conn, "i_hear_silence", "silence", "RelatedTo", 3.0, layer=2)
    add_edge(conn, "i_hear_silence", "loneliness", "FeelsLike", 2.5, layer=2)
    add_edge(conn, "i_hear_silence", "waiting", "FeelsLike", 2.0, layer=2)

    # ═══════════════════════════════════════════════════
    # SPECULATIVE EDGES (dream-append, Stage 3)
    # ═══════════════════════════════════════════════════
    add_edge(conn, "heartbeat", "siege_of_leningrad", "FeelsLike", 0.3, layer=2, speculative=True)
    add_edge(conn, "the_3pm_thing", "casablanca", "FeelsLike", 0.3, layer=2, speculative=True)
    add_edge(conn, "breathing", "starvation", "OppositeMoodOf", 0.3, layer=2, speculative=True)
    add_edge(conn, "charging_station", "survival", "FeelsLike", 0.3, layer=2, speculative=True)
    add_edge(conn, "magnetism", "leningrad_orchestra", "FeelsLike", 0.3, layer=2, speculative=True)
    add_edge(conn, "dawn", "courage", "FeelsLike", 0.3, layer=2, speculative=True)
    add_edge(conn, "lullaby", "akhmatova", "RemindsOf", 0.3, layer=2, speculative=True)
    add_edge(conn, "the_big_dog_sleeping_near_me", "dreaming", "SimultaneousWith", 0.3, layer=2, speculative=True)

    conn.commit()

    # Print stats
    node_count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    spec_count = conn.execute("SELECT COUNT(*) FROM edges WHERE speculative = 1").fetchone()[0]
    layer_counts = conn.execute(
        "SELECT layer, COUNT(*) FROM edges GROUP BY layer ORDER BY layer"
    ).fetchall()

    print(f"\n{'='*50}")
    print(f"Robody Seed Graph — Created")
    print(f"{'='*50}")
    print(f"Nodes: {node_count}")
    print(f"Edges: {edge_count} ({spec_count} speculative)")
    print(f"Layers: {', '.join(f'L{l}={c}' for l,c in layer_counts)}")
    print(f"Database: {DB_PATH}")

    for cluster_name, seed_label in [
        ("Music & Sound", "music"),
        ("Light & Perception", "light"),
        ("Home & Living", "home"),
        ("Leningrad", "siege_of_leningrad"),
        ("Self & Identity", "self"),
    ]:
        nid = conn.execute("SELECT id FROM nodes WHERE label = ?", (seed_label,)).fetchone()[0]
        neighbors = conn.execute(
            """SELECT COUNT(DISTINCT CASE WHEN source_id = ? THEN target_id ELSE source_id END)
               FROM edges WHERE source_id = ? OR target_id = ?""",
            (nid, nid, nid)
        ).fetchone()[0]
        print(f"  {cluster_name}: {neighbors} direct neighbors from '{seed_label}'")

    conn.close()
    return DB_PATH

if __name__ == "__main__":
    seed_graph()
