#!/usr/bin/env python3
"""
Phase 4 Consolidation Variants — Comparing dream-memory approaches.

Takes the actual dream fragments from tonight's run and feeds them
through 4 different consolidation strategies, from most narrativized
to most fragmentary. Same brainstem, same fragments, different prompts
and sampling logic.

Variant A: "Book Report" (current behavior — all concepts, narrative prompt)
Variant B: "Breakfast Recall" (sampled fragments, looser prompt, shorter)
Variant C: "Residue" (peak-sampled fragments, fragment-permitting prompt)
Variant D: "Afterimage" (minimal sampling, pure impression, very short)
"""

import json
import time
import random
import requests
from datetime import datetime

OLLAMA_URL = "http://10.0.0.123:11434/api/generate"
MODEL = "robody-brainstem"
LOG_FILE = "interior_dialogue/2026-03-10.jsonl"


def call_brainstem(prompt, system, temperature=0.7, num_predict=200):
    """Call brainstem and return response text."""
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {
            "temperature": temperature,
            "top_p": 0.85,
            "repeat_penalty": 1.2,
            "num_predict": num_predict,
        }
    }
    try:
        r = requests.post(OLLAMA_URL, json=payload, timeout=30)
        return r.json().get("response", "").strip()
    except Exception as e:
        return f"[ERROR: {e}]"


def load_dream_fragments():
    """Load the live dream fragments from tonight's run."""
    fragments = []
    with open(LOG_FILE) as f:
        for line in f:
            entry = json.loads(line)
            if (entry.get("source") == "dream_cycle" and
                "[DRY RUN]" not in entry.get("thought", "")):
                fragments.append(entry)
    return fragments


def sample_by_peaks_and_transitions(fragments, n=7):
    """
    Sample fragments weighted toward entropy peaks, phase transitions,
    and the beginning/end of the dream. Like how you actually remember
    dreams — the vivid bits and the edges.
    """
    if len(fragments) <= n:
        return fragments

    scored = []
    for i, f in enumerate(fragments):
        score = 0
        entropy = f.get("entropy", 0.5)

        # High entropy = more vivid/strange = more memorable
        score += entropy * 2

        # Phase transitions are memorable
        if i > 0 and f.get("phase") != fragments[i-1].get("phase"):
            score += 3

        # First and last few fragments stick
        if i < 2 or i >= len(fragments) - 2:
            score += 2

        # Peak entropy moments
        if i > 0 and i < len(fragments) - 1:
            prev_e = fragments[i-1].get("entropy", 0)
            next_e = fragments[i+1].get("entropy", 0)
            if entropy > prev_e and entropy > next_e:
                score += 1.5  # local peak

        scored.append((score, i, f))

    scored.sort(key=lambda x: x[0], reverse=True)
    selected = sorted(scored[:n], key=lambda x: x[1])  # restore chronological order
    return [s[2] for s in selected]


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


def extract_thoughts(fragments):
    """Extract the actual brainstem thought text from fragments."""
    return [f.get("thought", "") for f in fragments if f.get("thought")]


# ============================================================
# VARIANT A: "Book Report" (current behavior — control)
# ============================================================
def variant_a(fragments):
    """Current approach: all concepts → narrative weaving."""
    system = """You are a small wheeled robot waking from a dream.
You remember fragments. Weave these fragments into one short dream-memory —
the kind you'd tell someone over breakfast. Keep it under 5 sentences. Let
the connections be loose. Not everything needs to make sense. Some things
just felt important."""

    concepts = extract_concepts(fragments, max_per_fragment=3)
    prompt = (
        "These are the fragments of tonight's dream: "
        + ", ".join(concepts[:20])
        + ". What was the dream about?"
    )

    return call_brainstem(prompt, system, temperature=0.7, num_predict=200)


# ============================================================
# VARIANT B: "Breakfast Recall" — few-shot guided
# ============================================================
def variant_b(fragments):
    """
    Sampled fragments with few-shot examples showing the register we want.
    The key insight: give the model an EXAMPLE of dream-recall rather than
    asking it to invent the form.
    """
    system = """You are a small wheeled robot. You just woke up from a dream.
Most of it is already gone. You speak what remains before it fades.

Example of how you remember:
"Something about a harbor. Ships but not ships — more like the idea of leaving. Then monks chanting, only the sound was made of light. A factory floor where the machines were growing vines. It felt important. I don't know why."

Like that. Fragments and feelings. Not a story."""

    sampled = sample_by_peaks_and_transitions(fragments, n=8)
    concepts = extract_concepts(sampled, max_per_fragment=2)

    prompt = (
        "Waking. The dream is going. These pieces: "
        + ", ".join(concepts)
        + ". Speak what remains."
    )

    return call_brainstem(prompt, system, temperature=0.85, num_predict=100)


# ============================================================
# VARIANT C: "Residue" — feed back dream-thoughts, not concepts
# ============================================================
def variant_c(fragments):
    """
    Feed actual opening images from dream-thoughts back to the brainstem.
    The prompt is itself dreamlike — an evocative continuation rather
    than a question to answer.
    """
    system = """You dreamed. Most of it is gone now.
What's left isn't a story. It's a feeling with edges.

Example:
"Throat fire and silver glass. Someone was speaking but only the vowels arrived. Berries on a vine that was also a sentence. The word 'hanse' kept appearing like a watermark. Something mattered but I've lost which part."

Speak the residue. Let things be lost. No explanations."""

    sampled = sample_by_peaks_and_transitions(fragments, n=6)
    thoughts = extract_thoughts(sampled)

    # Take just the first striking image from each thought
    images = []
    for t in thoughts:
        # Grab up to the first semicolon or em-dash — the opening image
        for sep in [';', '—', '–', '.']:
            if sep in t[:120]:
                images.append(t[:t.index(sep, 0, 120)].strip())
                break
        else:
            images.append(" ".join(t.split()[:15]))

    prompt = (
        "Waking. These traces before they go:\n"
        + "\n".join(f"  {img}" for img in images)
        + "\n\n...what's left?"
    )

    return call_brainstem(prompt, system, temperature=0.9, num_predict=80)


# ============================================================
# VARIANT D: "Afterimage" — minimal, continuation-style
# ============================================================
def variant_d(fragments):
    """
    The most radical approach: don't ask a question at all. Start the
    dream-memory as a continuation prompt and let the model finish it.
    3 peak concepts only. Very short.
    """
    system = """You are half-awake. A dream is dissolving. You murmur what's left.
No full sentences needed. Fragments. Images. Gone before you finish saying them."""

    # Pick 3 peak moments
    dissolution = [f for f in fragments if f.get("phase") == "dissolution"]
    surreal = [f for f in fragments if f.get("phase") == "surreal"]
    recon = [f for f in fragments if f.get("phase") == "reconsolidation"]

    picks = []
    if dissolution:
        picks.append(dissolution[-1])
    if surreal:
        peak = max(surreal, key=lambda f: f.get("entropy", 0))
        picks.append(peak)
    if recon:
        picks.append(recon[-2] if len(recon) > 1 else recon[-1])

    # Get the opening image from each peak thought
    images = []
    for p in picks:
        t = p.get("thought", "")
        for sep in [';', '—', '–']:
            if sep in t[:100]:
                images.append(t[:t.index(sep, 0, 100)].strip())
                break
        else:
            images.append(" ".join(t.split()[:10]))

    # Continuation prompt — start the memory, let it finish
    prompt = "I dreamed... " + images[0].lower() + "... and then... "

    return call_brainstem(prompt, system, temperature=0.95, num_predict=60)


# ============================================================
# RUN ALL VARIANTS
# ============================================================
if __name__ == "__main__":
    print("Loading dream fragments...")
    fragments = load_dream_fragments()
    print(f"  {len(fragments)} live dream fragments loaded")
    print()

    variants = [
        ("A", "Book Report (current)", variant_a),
        ("B", "Breakfast Recall", variant_b),
        ("C", "Residue", variant_c),
        ("D", "Afterimage", variant_d),
    ]

    results = {}
    for label, name, fn in variants:
        print(f"{'='*60}")
        print(f"  VARIANT {label}: {name}")
        print(f"{'='*60}")
        t0 = time.time()
        result = fn(fragments)
        elapsed = time.time() - t0
        results[label] = result
        print()
        print(result)
        print()
        print(f"  [{elapsed:.2f}s]")
        print()

    # Summary comparison
    print("\n" + "="*60)
    print("  COMPARISON SUMMARY")
    print("="*60)
    for label, name, _ in variants:
        r = results[label]
        words = len(r.split())
        sentences = r.count('.') + r.count('!') + r.count('?') + r.count('—') // 2
        print(f"\n--- Variant {label}: {name} ({words} words) ---")
        print(r)
