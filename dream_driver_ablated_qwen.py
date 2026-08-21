#!/usr/bin/env python3
"""
Dream experiment: ablated qwen as Robody's Phase-3 dreamer.
Runs Lara's real graph walker (unmodified) against a COPY of the seed graph,
with the brainstem swapped for orcarouter/Qwen3.8-27B-Uncensored:iq3_m.

Three dream cycles, same walk seed, three temperature scales:
  cool (x0.7), canonical (x1.0), hot (x1.4)
Then: Phase-3 narrative weave (dreamer, high temp) and Phase-4 sober
consolidation (qwen3.5:35b-a3b MoE, low temp) per the dream architecture doc.
"""
import sys, json, random, urllib.request
from pathlib import Path

SCRATCH = Path(__file__).parent
sys.path.insert(0, str(Path.home() / "Documents/Git/Robody"))
import robody_graph_walker as w

# --- Patch the module: DB copy, tunneled ollama, new dreamer, scratch logs ---
w.DB_PATH = SCRATCH / "dream_seed.sqlite"
w.OLLAMA_URL = "http://127.0.0.1:11435"
w.BRAINSTEM_MODEL = "orcarouter/Qwen3.8-27B-Uncensored:iq3_m"
w.LOG_DIR = SCRATCH / "interior_dialogue"

_orig_call = w.call_brainstem
TEMP_SCALE = 1.0

def scaled_call(prompt, dry_run=False, system=None, temperature=None, num_predict=None):
    t = temperature if temperature is not None else 0.85
    return _orig_call(prompt, dry_run=dry_run, system=system,
                      temperature=round(min(t * TEMP_SCALE, 1.6), 3),
                      num_predict=num_predict)
w.call_brainstem = scaled_call
w.measure_novelty = lambda: 0.5   # pin novelty so all three runs get identical walk params

def ollama_chat(model, system, user, temperature, num_predict, think=False):
    payload = json.dumps({
        "model": model, "stream": False, "think": think,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "options": {"temperature": temperature, "num_predict": num_predict,
                    "num_ctx": 10240},
    }).encode()
    req = urllib.request.Request("http://127.0.0.1:11435/api/chat", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as resp:
        return json.loads(resp.read().decode())["message"]["content"].strip()

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

RUNS = [("cool", 0.7, 101), ("canonical", 1.0, 101), ("hot", 1.4, 101)]
results = {}

for name, scale, seed in RUNS:
    print(f"\n{'#'*70}\n# DREAM RUN: {name} (temp x{scale})\n{'#'*70}", flush=True)
    globals()["TEMP_SCALE"] = scale
    TEMP_SCALE = scale
    random.seed(seed)                      # same walk skeleton across runs
    out = w.run_dream(dry_run=False, verbose=True, noise_seed=0.42)
    frag_lines = []
    for f in out.get("fragments", []):
        frag_lines.append(f"[{f['phase']}] cluster: {', '.join(f['cluster'])}\n  voice: {f['thought']}")
    material = "\n\n".join(frag_lines)
    print(f"\n--- Phase 3 weave ({name}) ---", flush=True)
    weave_temp = {"cool": 0.7, "canonical": 1.0, "hot": 1.35}[name]
    narrative = ollama_chat(w.BRAINSTEM_MODEL, WEAVE_SYSTEM,
                            "Tonight's dream material:\n\n" + material,
                            weave_temp, 900)
    print(narrative[:400], flush=True)
    print(f"\n--- Phase 4 consolidation ({name}, MoE, temp 0.3) ---", flush=True)
    consolidation = ollama_chat("qwen3.5:35b-a3b", CONSOLIDATE_SYSTEM,
                                "Dream transcript:\n\n" + narrative, 0.3, 700)
    print(consolidation[:400], flush=True)
    # three-layer consolidation (recall/residue/afterimage) is logged, not returned
    layers = {}
    try:
        from datetime import datetime
        log_file = w.LOG_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        for line in log_file.read_text().splitlines():
            entry = json.loads(line)
            if "recall" in entry or entry.get("source") == "dream_consolidation":
                layers = entry
    except Exception as e:
        layers = {"error": str(e)}
    results[name] = {
        "temp_scale": scale,
        "params": out.get("params"),
        "n_fragments": len(out.get("fragments", [])),
        "new_edges": out.get("new_edges"),
        "fragments": out.get("fragments"),
        "consolidation_layers": layers,
        "phase3_narrative": narrative,
        "phase4_consolidation": consolidation,
    }
    (SCRATCH / f"dream_{name}.json").write_text(json.dumps(results[name], indent=2, default=str))

(SCRATCH / "dream_all.json").write_text(json.dumps(results, indent=2, default=str))
print("\nALL DREAMS COMPLETE", flush=True)
