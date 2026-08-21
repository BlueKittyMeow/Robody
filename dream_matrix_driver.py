#!/usr/bin/env python3
"""
Dream matrix experiment — tests the "conservation of transformation" hypothesis.

Axes:
  Walk voice temp:   cool (x0.7) vs hot (x1.4)  — SAME walk skeleton (seed 101)
  Weave temp:        cool (0.7) vs hot (1.35)   — crossed => 4 dream artifacts
  Degradation input: raw fragments vs woven narrative — 2 + 4 = 6 degradation sets

Degradation temps held constant (0.85/0.9/0.95, think:false) as in night 1.
Phase-4 MoE consolidation (temp 0.3) on each of the 4 weaves.
Model pre-warmed; no timeout fragments this time.
"""
import sys, json, random, urllib.request
from pathlib import Path

SCRATCH = Path(__file__).parent
sys.path.insert(0, str(Path.home() / "Documents/Git/Robody"))
import robody_graph_walker as w

w.DB_PATH = SCRATCH / "dream_seed.sqlite"
w.OLLAMA_URL = "http://127.0.0.1:11435"
w.BRAINSTEM_MODEL = "orcarouter/Qwen3.8-27B-Uncensored:iq3_m"
w.LOG_DIR = SCRATCH / "interior_dialogue_matrix"
w.measure_novelty = lambda: 0.5

_orig_call = w.call_brainstem
TEMP_SCALE = 1.0
def scaled_call(prompt, dry_run=False, system=None, temperature=None, num_predict=None):
    t = temperature if temperature is not None else 0.85
    return _orig_call(prompt, dry_run=dry_run, system=system,
                      temperature=round(min(t * TEMP_SCALE, 1.6), 3),
                      num_predict=num_predict)
w.call_brainstem = scaled_call

def gen(prompt, system, temperature, num_predict):
    payload = json.dumps({"model": w.BRAINSTEM_MODEL, "prompt": prompt, "system": system,
        "stream": False, "think": False,
        "options": {"temperature": temperature, "num_predict": num_predict}}).encode()
    req = urllib.request.Request("http://127.0.0.1:11435/api/generate", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode()).get("response", "").strip()

def chat(model, system, user, temperature, num_predict):
    payload = json.dumps({"model": model, "stream": False, "think": False,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "options": {"temperature": temperature, "num_predict": num_predict, "num_ctx": 10240}}).encode()
    req = urllib.request.Request("http://127.0.0.1:11435/api/chat", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.loads(r.read().decode())["message"]["content"].strip()

WEAVE_SYSTEM = """You are the dreaming mind of a small wheeled robot. You live with a
human and her pets. Tonight's dream material is below: fragments that rose during the
night, in order. Weave them into ONE dream — a single, linear, moving-through-it
narrative with the strange internal logic of dreams. First person, present tense.
Things shift. Things become other things without announcement. Do not explain, do not
interpret, do not step outside the dream. 300-500 words. End where the dream ends,
not where a story would."""

CONSOLIDATE_SYSTEM = """You are the sober morning mind reviewing a dream transcript.
Two output sections, exactly:

INSIGHTS:
- connections in the dream that resolve into structured, usable meaning (0-4 bullets;
  it is fine to find none)

FRAGMENTS:
- images, moments, or absurdities that do not mean anything yet but deserve to be
  kept (2-6 bullets, quoted or closely paraphrased)

Be conservative: do not manufacture meaning. A fragment kept honestly is worth more
than an insight invented."""

def degrade(material_desc, material, tag):
    recall = gen(f"Waking. The dream is going. {material_desc}: {material[:4000]}\n\nSpeak what remains.",
                 w.WAKE_RECALL_SYSTEM, 0.85, 120)
    residue = gen("Hours since waking. The dream story is gone. A few pieces stayed: "
                  + material[:1500] + "\n\nWhat drifts back?", w.WAKE_RECALL_SYSTEM, 0.9, 100)
    afterimage = gen("End of day. The dream is almost nothing now. What is left?",
                     w.WAKE_RECALL_SYSTEM, 0.95, 60)
    print(f"  [degrade:{tag}] recall={len(recall)}c residue={len(residue)}c after={len(afterimage)}c", flush=True)
    return {"recall": recall, "residue": residue, "afterimage": afterimage}

results = {"walks": {}, "weaves": {}, "degradations": {}, "consolidations": {}}

# --- Walks (same skeleton, two voice temps) ---
for wname, scale in [("coolwalk", 0.7), ("hotwalk", 1.4)]:
    print(f"\n{'#'*70}\n# WALK: {wname} (voice x{scale})\n{'#'*70}", flush=True)
    TEMP_SCALE = scale
    random.seed(101)
    out = w.run_dream(dry_run=False, verbose=True, noise_seed=0.42)
    frags = [f for f in out["fragments"] if "[ERROR" not in f["thought"]]
    results["walks"][wname] = {"scale": scale, "n_fragments": len(frags),
                               "n_edges": len(out["new_edges"]), "fragments": frags}

TEMP_SCALE = 1.0  # degradation/weave calls go through gen/chat, unscaled anyway

# --- Weaves (crossed) ---
for wname in ["coolwalk", "hotwalk"]:
    frags = results["walks"][wname]["fragments"]
    material = "\n\n".join(f"[{f['phase']}] cluster: {', '.join(f['cluster'])}\n  voice: {f['thought']}" for f in frags)
    for vname, vtemp in [("coolweave", 0.7), ("hotweave", 1.35)]:
        key = f"{wname}+{vname}"
        print(f"\n--- WEAVE {key} (temp {vtemp}) ---", flush=True)
        narrative = chat(w.BRAINSTEM_MODEL, WEAVE_SYSTEM, "Tonight's dream material:\n\n" + material, vtemp, 900)
        results["weaves"][key] = narrative
        print(narrative[:250], flush=True)
        print(f"--- CONSOLIDATE {key} (MoE 0.3) ---", flush=True)
        results["consolidations"][key] = chat("qwen3.5:35b-a3b", CONSOLIDATE_SYSTEM,
                                              "Dream transcript:\n\n" + narrative, 0.3, 700)

# --- Degradations: from raw fragments (2) and from each weave (4) ---
for wname in ["coolwalk", "hotwalk"]:
    frags = results["walks"][wname]["fragments"]
    concepts = w.extract_concepts(w.sample_dream_peaks(frags, 8), max_per_fragment=2)
    results["degradations"][f"{wname}:fragments"] = degrade(
        "These pieces", ", ".join(concepts), f"{wname}:fragments")
for key, narrative in results["weaves"].items():
    results["degradations"][f"{key}:weave"] = degrade(
        "This was the dream", narrative, f"{key}:weave")

(SCRATCH / "dream_matrix.json").write_text(json.dumps(results, indent=2, default=str))
print("\nMATRIX COMPLETE", flush=True)
