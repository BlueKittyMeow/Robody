#!/usr/bin/env python3
"""
Robody ConceptNet Import — Stage 1 Instantiation
=================================================
Downloads the English-only high-confidence ConceptNet subset from HuggingFace
(relbert/conceptnet, ~583k edges) and imports it into the Robody knowledge
graph as Layer 0 (fact) nodes and edges.

This is Stage 1 of the three-stage instantiation described in
robody_dream_architecture.md Part 3:
  Stage 1: ConceptNet import (common-sense knowledge substrate)
  Stage 2: Rational expansion (LLM enrichment)
  Stage 3: Dream-append (speculative edges from dreaming)

The existing seed graph nodes are preserved — ConceptNet merges alongside them.
Duplicate labels get their existing IDs; new concepts get new nodes.

Usage:
    python3 robody_conceptnet_import.py [--db PATH] [--limit N] [--stats-only]

Requires: pip install datasets
"""

import sqlite3
import json
import time
import argparse
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "robody_seed.sqlite"

# ConceptNet relation types to Robody edge types
# Some map directly, others need translation
RELATION_MAP = {
    "RelatedTo": "RelatedTo",
    "IsA": "IsA",
    "PartOf": "PartOf",
    "HasA": "HasA",
    "UsedFor": "UsedFor",
    "CapableOf": "CapableOf",
    "AtLocation": "AtLocation",
    "Causes": "Causes",
    "HasSubevent": "HasSubevent",
    "HasFirstSubevent": "HasFirstSubevent",
    "HasLastSubevent": "HasLastSubevent",
    "HasPrerequisite": "HasPrerequisite",
    "HasProperty": "HasProperty",
    "MotivatedByGoal": "MotivatedByGoal",
    "ObstructedBy": "ObstructedBy",
    "Desires": "Desires",
    "CreatedBy": "CreatedBy",
    "Synonym": "Synonym",
    "Antonym": "Antonym",
    "DistinctFrom": "DistinctFrom",
    "DerivedFrom": "DerivedFrom",
    "SymbolOf": "SymbolOf",
    "DefinedAs": "DefinedAs",
    "MannerOf": "MannerOf",
    "LocatedNear": "LocatedNear",
    "HasContext": "HasContext",
    "SimilarTo": "SimilarTo",
    "EtymologicallyRelatedTo": "EtymologicallyRelatedTo",
    "EtymologicallyDerivedFrom": "EtymologicallyDerivedFrom",
    "CausesDesire": "CausesDesire",
    "MadeOf": "MadeOf",
    "ReceivesAction": "ReceivesAction",
    "InstanceOf": "IsA",  # treat as IsA
    "FormOf": "DerivedFrom",  # treat as derived
}

# Relation types we WANT for dreaming (skip purely linguistic ones)
DREAM_USEFUL_RELATIONS = {
    "RelatedTo", "IsA", "PartOf", "HasA", "UsedFor", "CapableOf",
    "AtLocation", "Causes", "HasSubevent", "HasPrerequisite",
    "HasProperty", "MotivatedByGoal", "Desires", "CreatedBy",
    "Synonym", "Antonym", "SymbolOf", "DefinedAs", "MannerOf",
    "LocatedNear", "SimilarTo", "CausesDesire", "MadeOf",
    "ReceivesAction", "HasFirstSubevent", "HasLastSubevent",
    "ObstructedBy",
}

# Skip these — too linguistic, not useful for dreaming
SKIP_RELATIONS = {
    "EtymologicallyRelatedTo", "EtymologicallyDerivedFrom",
    "FormOf", "DerivedFrom", "HasContext", "DistinctFrom",
}


def ensure_schema(conn):
    """Create tables if they don't exist (idempotent)."""
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


def normalize_label(raw):
    """
    Normalize a ConceptNet term to a graph label.
    'a beautiful sunset' → 'beautiful_sunset'
    Strips articles, lowercases, underscores.
    """
    label = raw.strip().lower()
    # Remove leading articles
    for article in ["a ", "an ", "the "]:
        if label.startswith(article):
            label = label[len(article):]
    # Replace spaces with underscores
    label = label.replace(" ", "_")
    # Remove non-alphanumeric except underscores
    label = "".join(c for c in label if c.isalnum() or c == "_")
    return label


def get_or_create_node(conn, label, node_type="concept", source="conceptnet"):
    """Get existing node ID or create a new one."""
    cur = conn.execute("SELECT id FROM nodes WHERE label = ?", (label,))
    row = cur.fetchone()
    if row:
        return row[0]
    try:
        cur = conn.execute(
            "INSERT INTO nodes (label, type, source) VALUES (?, ?, ?)",
            (label, node_type, source)
        )
        return cur.lastrowid
    except sqlite3.IntegrityError:
        cur = conn.execute("SELECT id FROM nodes WHERE label = ?", (label,))
        return cur.fetchone()[0]


def import_conceptnet(db_path, limit=None, stats_only=False, verbose=True):
    """
    Download and import ConceptNet into the Robody graph.
    """
    import csv
    import gzip
    import urllib.request
    import io
    from collections import Counter

    CONCEPTNET_URL = "https://s3.amazonaws.com/conceptnet/downloads/2019/edges/conceptnet-assertions-5.7.0.csv.gz"
    CACHE_PATH = Path(__file__).parent / "conceptnet-assertions-5.7.0.csv.gz"

    if verbose:
        print(f"\n{'='*60}")
        print(f"Robody ConceptNet Import — Stage 1 Instantiation")
        print(f"{'='*60}")

    # Download if not cached
    if not CACHE_PATH.exists():
        if verbose:
            print(f"Downloading ConceptNet 5.7 from S3 (~300MB compressed)...")
            print(f"  {CONCEPTNET_URL}")
        t0 = time.time()
        urllib.request.urlretrieve(CONCEPTNET_URL, CACHE_PATH)
        dl_time = time.time() - t0
        size_mb = CACHE_PATH.stat().st_size / (1024*1024)
        if verbose:
            print(f"  Downloaded {size_mb:.0f}MB in {dl_time:.1f}s")
    else:
        if verbose:
            size_mb = CACHE_PATH.stat().st_size / (1024*1024)
            print(f"Using cached download ({size_mb:.0f}MB)")

    # Parse — ConceptNet TSV format:
    # col 0: edge URI (/a/[/r/RelatedTo/,/c/en/cat/,/c/en/animal/])
    # col 1: relation URI (/r/RelatedTo)
    # col 2: start node URI (/c/en/cat)
    # col 3: end node URI (/c/en/animal)
    # col 4: JSON metadata
    if verbose:
        print("Scanning for English-only edges...")

    t0 = time.time()
    edges_to_import = []
    total_scanned = 0
    rel_counts = Counter()

    with gzip.open(CACHE_PATH, "rt", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            total_scanned += 1
            if len(row) < 4:
                continue

            relation_uri = row[1]  # /r/RelatedTo
            start_uri = row[2]     # /c/en/cat
            end_uri = row[3]       # /c/en/animal

            # Filter: both nodes must be English
            if not start_uri.startswith("/c/en/") or not end_uri.startswith("/c/en/"):
                continue

            # Extract relation name
            relation = relation_uri.split("/")[-1]

            # Extract labels (strip /c/en/ prefix, take first segment)
            head_raw = start_uri.split("/")[3] if len(start_uri.split("/")) > 3 else ""
            tail_raw = end_uri.split("/")[3] if len(end_uri.split("/")) > 3 else ""

            if not head_raw or not tail_raw:
                continue

            # Extract weight from JSON metadata
            weight = 1.0
            if len(row) > 4:
                try:
                    meta = json.loads(row[4])
                    weight = meta.get("weight", 1.0)
                except (json.JSONDecodeError, IndexError):
                    pass

            rel_counts[relation] += 1
            edges_to_import.append((relation, head_raw, tail_raw, weight))

            if limit and len(edges_to_import) >= limit:
                break

            if total_scanned % 1_000_000 == 0 and verbose:
                print(f"  Scanned {total_scanned:,} rows, "
                      f"found {len(edges_to_import):,} English edges...")

    scan_time = time.time() - t0
    if verbose:
        print(f"Scanned {total_scanned:,} rows in {scan_time:.1f}s")
        print(f"Found {len(edges_to_import):,} English edges")

    # Show relation distribution
    if verbose or stats_only:
        print(f"\nRelation distribution ({len(rel_counts)} types):")
        for rel, count in rel_counts.most_common():
            skip_marker = " [SKIP]" if rel in SKIP_RELATIONS else ""
            print(f"  {rel:<35s} {count:>7d}{skip_marker}")
        useful = sum(c for r, c in rel_counts.items() if r not in SKIP_RELATIONS)
        print(f"\nTotal English: {sum(rel_counts.values()):,}")
        print(f"After filtering: ~{useful:,} edges")

    if stats_only:
        return

    # Open database
    conn = sqlite3.connect(db_path)
    ensure_schema(conn)

    # Get existing counts
    existing_nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    existing_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    if verbose:
        print(f"\nExisting graph: {existing_nodes} nodes, {existing_edges} edges")
        print(f"Importing ConceptNet as Layer 0 (fact)...")

    # Import
    t0 = time.time()
    imported = 0
    skipped_relation = 0
    skipped_duplicate = 0
    skipped_self = 0
    batch_size = 10000

    for i, (relation, head_raw, tail_raw, weight) in enumerate(edges_to_import):
        head = normalize_label(head_raw)
        tail = normalize_label(tail_raw)

        # Skip unwanted relations
        if relation in SKIP_RELATIONS:
            skipped_relation += 1
            continue

        # Skip self-edges
        if head == tail:
            skipped_self += 1
            continue

        # Skip empty labels
        if not head or not tail:
            continue

        # Map relation type
        edge_type = RELATION_MAP.get(relation, relation)

        # Get or create nodes
        head_id = get_or_create_node(conn, head)
        tail_id = get_or_create_node(conn, tail)

        # Add edge (Layer 0, use ConceptNet weight, not speculative)
        try:
            conn.execute(
                """INSERT INTO edges (source_id, target_id, type, weight, layer, speculative)
                   VALUES (?, ?, ?, ?, 0, 0)""",
                (head_id, tail_id, edge_type, min(weight, 5.0))
            )
            imported += 1
        except sqlite3.IntegrityError:
            skipped_duplicate += 1

        # Progress and batch commit
        if (i + 1) % batch_size == 0:
            conn.commit()
            if verbose:
                elapsed = time.time() - t0
                rate = (i + 1) / elapsed
                print(f"  {i+1:>7,}/{len(edges_to_import):,} ({rate:.0f}/s) "
                      f"imported={imported:,} skipped_rel={skipped_relation:,} "
                      f"dupes={skipped_duplicate:,}")

    conn.commit()
    elapsed = time.time() - t0

    # Final stats
    final_nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    final_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    cn_nodes = final_nodes - existing_nodes
    cn_edges = final_edges - existing_edges

    if verbose:
        print(f"\n{'='*60}")
        print(f"Import complete in {elapsed:.1f}s")
        print(f"{'='*60}")
        print(f"ConceptNet edges processed: {len(edges_to_import):,}")
        print(f"  Imported:         {imported:,}")
        print(f"  Skipped (relation): {skipped_relation:,}")
        print(f"  Skipped (dupe):   {skipped_duplicate:,}")
        print(f"  Skipped (self):   {skipped_self:,}")
        print(f"\nGraph now: {final_nodes:,} nodes (+{cn_nodes:,}), "
              f"{final_edges:,} edges (+{cn_edges:,})")
        print(f"Database: {db_path}")
        print(f"Size: {db_path.stat().st_size / (1024*1024):.1f} MB")

    conn.close()
    return {"nodes_added": cn_nodes, "edges_added": cn_edges}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import ConceptNet into Robody graph")
    parser.add_argument("--db", type=str, default=str(DB_PATH),
                        help=f"Database path (default: {DB_PATH})")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit number of edges to import (for testing)")
    parser.add_argument("--stats-only", action="store_true",
                        help="Just show dataset statistics, don't import")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    import_conceptnet(
        db_path=Path(args.db),
        limit=args.limit,
        stats_only=args.stats_only,
        verbose=not args.quiet,
    )
