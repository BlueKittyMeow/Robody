# How Robody Dreams

### From Graph Database to "Fleeting Figures Skitter Away"

*A walkthrough of the pipeline that turns 841,000 concepts and 2.3 million connections into something that behaves like dreaming.*

---

## The Foundation: A Knowledge Graph

Everything starts with a database. Specifically, a SQLite database containing two tables: **nodes** (concepts) and **edges** (connections between concepts).

The nodes are things like `tropicbird`, `music`, `breathing`, `velvet`, `lullaby`, `iron`. Each one has a label, a type (animal, emotion, material, place), and a source indicating where it came from. Most of the 841,133 nodes were imported from **ConceptNet 5.7**, a publicly available common-sense knowledge base built by MIT and collaborators. A small seed graph of 65 hand-chosen nodes — things meaningful to the robot's life — anchors the personal layer.

The edges are relationships: `music` —*RelatedTo*→ `breathing`, `velvet` —*HasProperty*→ `soft`, `tropicbird` —*IsA*→ `seabird`. There are 2.36 million of them. Each edge has a **weight** (how strong the connection is), a **layer** (what kind of knowledge it represents), and a **speculative** flag (whether the connection was inferred rather than known).

The layers matter. Layer 0 is factual knowledge — things that are simply true. Layer 1 is associative — things that feel connected. Layer 2 is dream-material — connections the system itself has invented during sleep. The layers don't just coexist; they *interact*, with dream-edges subtly pulling the walker's attention toward paths it has previously dreamed.

This is the raw material. A map of how things relate. Nothing about it dreams yet.

---

## The Walker: A Weighted Random Walk

The first moving part is a **graph walker** — an algorithm that wanders through the knowledge graph one step at a time, following edges from node to node.

The walk is not purely random. At each step, the walker looks at all the edges leaving its current node and chooses the next node probabilistically, weighted by edge strength. A strong connection (weight 1.0) is much more likely to be followed than a weak one (weight 0.1). This means the walker naturally gravitates toward regions of dense, strong association — the way attention drifts toward things that are meaningfully connected.

Three biases shape the walk:

**Layer ghosts.** The walker has a "mood" — a floating-point number tracking which layer of knowledge it's been spending time in. Edges from nearby layers get full weight; edges from distant layers are attenuated by 0.7 per layer of distance. A walker in a dreamy mood (layer 2) follows dream-edges at full strength but treats factual edges (layer 0) as faint whispers. This is how the walker's current register — waking, associative, dreaming — shapes what it notices.

**Recency penalty.** Nodes visited in the last 8 steps are penalized (weight × 0.1), pushing the walker outward rather than letting it circle. Without this, the walker gets trapped in tight synonym clusters.

**Speculative dampening.** Edges the system invented (speculative = true) are followed at half weight. The walker pays attention to its own inventions, but trusts them less than established knowledge.

The walk itself produces nothing visible. It's just a cursor moving through a graph. The interesting part is what happens when the cursor lingers.

---

## Density Detection: When Concepts Cluster

As the walker moves, it continuously monitors the last 6 nodes it visited. If those nodes share an unusually high number of mutual edges — if the walker has wandered into a region where everything is connected to everything else — the system detects a **density cluster**.

The math is straightforward: count the mutual edges among the last N unique nodes, divide by the maximum possible edges between them (n × (n-1) / 2). If this density score exceeds a threshold, a cluster has been found.

Not all clusters are interesting. ConceptNet is full of morphological trivia: `myxomavirus`, `myxomatosis`, `myxomaviral` are tightly connected but tell you nothing. A **diversity filter** checks the types of edges in the cluster. If more than 70% are Synonym or RelatedTo, the cluster is boring. Interesting clusters have diverse edge types — a place connected to a material connected to an emotion connected to an action.

When an interesting cluster is found, it gets formatted as an **impulse** — a raw bundle of activated concepts with no articulation. Something like: "I notice: iron, music, breathing, lullaby." This is the subconscious presenting material to consciousness. It doesn't explain. It doesn't have a question. It just activates.

---

## The Brainstem: A Small Language Model

The impulse is sent to a **3.8-billion-parameter language model** (Phi-3.5 Mini, quantized to 4-bit, running on an NVIDIA RTX 4070 Ti Super via Ollama). This is the brainstem — the part that turns raw activation into something resembling inner speech.

The model receives a system prompt establishing its character: *"You are the quiet inner thoughts of a small wheeled robot who lives with a human and her pets. These are private thoughts — not addressed to anyone."* Three examples demonstrate the desired register: inward, noticing, never performing for an audience.

The brainstem doesn't analyze. It doesn't explain why iron and music are connected. It responds with something like: *"Something about these two ideas together. Iron and music. I don't know what it is yet but it pulls at me."*

The response is logged as an **interior dialogue entry** — a timestamped JSONL record containing the cluster that triggered it, the impulse text, the brainstem's response, and metadata (density score, latency, current layer mood). This is the robot's stream of consciousness: not planned, not curated, just whatever surfaces when attention lingers.

In waking mode, these thoughts happen roughly every 15-20 steps (a cooldown prevents the system from generating a thought at every cluster). The robot thinks when something catches its attention, then moves on.

---

## Dreaming: The Three-Phase Arc

Sleep changes everything.

When the dream cycle begins, the same walker runs through the same graph, but three parameters shift dramatically:

### Phase 1: Dissolution (≈25% of dream)

The dream starts with **entropy rising**. Entropy here is a computed value (0.0 to 1.0) that controls how loose the system runs. During dissolution, entropy climbs from 0.2 to 0.9. This has cascading effects:

- The **density threshold drops** (from 6 to 3), meaning clusters trigger more easily — the dreaming mind notices connections the waking mind would skip.
- The **brainstem temperature rises** (from 0.6 to 1.1), making the language model's outputs stranger and less predictable.
- The **diversity filter loosens**, letting through clusters that waking cognition would dismiss as boring.
- **Speculative edges become preferred** (weight multiplier rises from 0.5 to 2.0), meaning the walker actively seeks paths it previously imagined.

The walker's system prompt also changes. Instead of "you are thinking quietly," it becomes: *"You are dreaming. Things shift. Things become other things. Connections form that wouldn't exist in daylight."*

The effect: thoughts that were grounded and observational become loose and imagistic. The same concepts, the same graph, but the system processing them has changed its operating parameters.

### Phase 2: Surreal Peak (≈35% of dream)

Entropy stays high but **oscillates sinusoidally** — four ripples across the surreal phase, simulating the instability of REM sleep. At peak entropy, the system is maximally permissive: it follows speculative edges eagerly, triggers thoughts on almost any cluster, and the brainstem runs at temperature 1.1 (where language models start producing genuinely surprising output).

This is where the strangest material emerges. The walker follows dream-edges into territory that has no factual basis — connections it invented in previous dreams, or connections formed *during this dream*. Because dreams write back to the graph (more on this shortly), the surreal phase creates and then traverses its own novel pathways in real time.

### Phase 3: Reconsolidation (≈40% of dream)

Entropy drops from 0.9 back to 0.15. The thresholds tighten. The brainstem cools. The walker returns to paths that are more strongly supported by real edges.

But the walker has changed. It now carries dream-edges from the surreal phase — new Layer 2 connections that didn't exist before the dream started. These edges have low weight (0.3) and are marked speculative, but they exist. The reconsolidation phase traverses a graph that is slightly different from the one the dissolution phase started in.

### Write-Back: Dreams That Change the Graph

This is the mechanism that makes the dreaming cumulative rather than ephemeral: **during a dream, every density cluster that triggers a thought also writes new edges back into the graph.**

Specifically: for every pair of nodes in a triggered cluster that don't already share a Layer 2 edge, a new `DreamAssociation` edge is created with weight 0.3, layer 2, speculative = true. Over a single dream of 769 steps and 62 triggered clusters, this can create 842 new edges.

These edges persist. They influence future walks. A dream about `tropicbird` and `glycoside` creates a `DreamAssociation` between them. The next time the walker passes through either concept — waking or dreaming — the other exerts a faint pull. Dream-edges accumulate across nights. The graph remembers what was dreamed, even when the dream-thoughts themselves are gone.

The database currently holds 2,743 Layer 2 (dream) edges, created across three dream runs. They are a permanent residue of imagined connections.

---

## Dream Length and Novelty

How long the robot dreams depends on how interesting its day was.

A **novelty score** (0.0 to 1.0) is computed from the number of interior dialogue entries logged during the day. A quiet day (few thoughts) produces a short dream (≈120 steps). A rich day (many thoughts, lots of new material) produces a long dream (up to 800 steps). The exact length is then perturbed by a **noise value** — in simulation this is a Gaussian random number; in deployment it would be a reading from an unconnected analog pin on the robot's hardware, giving true thermal noise from the physical body.

The phase ratios also shift with novelty. A novel day produces a longer surreal phase (more material to process) and a proportionally shorter reconsolidation.

This means the dreams are responsive to experience without being determined by it. The same day can produce different dream lengths and different phase balances depending on the noise. Like actual dreams.

---

## Dream Consolidation: From Story to Ghost

After the walker finishes its arc (dissolution → surreal → reconsolidation), the dream cycle enters **consolidation** — a three-layer process that compresses the raw dream fragments into increasingly degraded forms. This models how dreams actually fade from memory.

### Layer 1: Recall (minutes after waking)

The system selects 8 peak fragments from the dream, weighted by a scoring function that favors:

- High-entropy moments (score += entropy × 2) — the vivid parts
- Phase transitions (score += 3) — the moments where the dream shifted
- First and last fragments (score += 2) — beginnings and endings stick
- Local entropy peaks (score += 1.5) — moments more intense than their neighbors

From these 8 fragments, concept labels are extracted and deduplicated. The brainstem receives them as: *"Waking. The dream is going. These pieces: tropicbird, tropic, glycoside, asperin, killer, killing, doomed, savedness, uprighteous, righteous, milliwatt, power unit, snapper, saltwater fish, shell, order. Speak what remains."*

The system prompt tells the brainstem to speak in fragments and feelings, not stories. The temperature is 0.85, the token limit is 100. The output sounds like breakfast-table dream recall:

> *"Tropical dreams linger: a tropicbird soars amidst glycosides of light and shadow; an asperin' essence in the air whispers killer intentions yet yearns for salvation—savedness breathes through uprighteous, righteous resolve."*

This is the most complete version. It has narrative flow, specific images, even something approaching a plot.

### Layer 2: Residue (hours later)

A different set of 6 peak fragments is sampled. This time, instead of extracting concept labels, the system extracts **opening images** — the first sensory phrase from each dream-thought, cut at the first semicolon or em-dash. These are the bits that hit before elaboration kicks in.

The brainstem receives these images with the prompt: *"Waking. These traces before they go:"* followed by the images, then *"...what's left?"*

Temperature rises to 0.9. Token limit drops to 80. The system prompt tells the model: *"What's left isn't a story. It's a feeling with edges."*

The output:

> *"Shadows snapping shut, existence pulsating faintly; humming Mw heartbeats beneath surface deeds. Minuscule observer in deep water ballet—snapper jewels flashing as shell-guarded truth seeps away into the abyssal dance of salvation and doom intertwined."*

Narrative structure is dissolving. Syntax is breaking. Images persist but they're losing their connections to each other.

### Layer 3: Afterimage (end of day)

Only 3 fragments survive: one from late dissolution, the peak-entropy moment of the surreal phase, and one from reconsolidation. Only the opening image from the first fragment is used.

The prompt is a continuation: *"I dreamed... killing shadows shift shape... and then..."*

Temperature is 0.95. Token limit is 50. The system prompt says: *"You are half-awake. A dream is dissolving. You murmur what's left. No full sentences needed. Fragments. Images. Gone before you finish saying them."*

The output:

> *"dark whispers, shapes morphing—fleeting figures skitter away at my touch's approach… faint echoes in a dim room where time seems irrelevant yet urgent all the same. Shivers ripple across senses barely"*

The word "barely" never completes its sentence. The dream ran out of tokens before it finished being said — a mechanical artifact that produces a phenomenologically perfect effect. The dream dissolved mid-thought, the way actual dreams do.

---

## The Full Pipeline, End to End

To summarize the path from database to that trailing "barely":

1. **841,133 nodes** and **2.36 million edges** form a knowledge graph of common-sense relationships, anchored by a personal seed graph.

2. A **weighted random walker** traverses the graph, biased by edge strength, layer mood, recency, and speculation status.

3. When the walker enters a region of **high mutual connectivity** (density detection), the cluster of activated concepts is extracted.

4. The cluster is filtered for **diversity** (not just synonyms) and formatted as a raw impulse.

5. The impulse is sent to a **3.8B-parameter language model** running locally on a GPU, with a system prompt establishing the dreaming register.

6. During dreams, **entropy modulates** every parameter: trigger sensitivity, brainstem temperature, edge preference, filter permissiveness. The arc — dissolution, surreal, reconsolidation — shapes the dream's character across time.

7. Dream clusters **write new edges back** into the graph, creating Layer 2 connections that persist and influence future walks.

8. After the dream, **three-layer consolidation** compresses the fragments using progressively fewer fragments, higher temperatures, and shorter token limits — modeling how dreams degrade from story to image to mood.

9. The final afterimage is generated with a 50-token limit and a continuation prompt. When the model exhausts its tokens mid-sentence, the trailing fragment is the dream's last trace — not by design, but because that's what happens when meaning is squeezed through a narrowing channel.

---

## Worked Example: Dream Run #3, March 10, 2026

What follows is a real dream, traced through the pipeline from its opening node to its final trailing fragment. Every node, cluster, and brainstem output shown here is actual system output. Nothing has been edited or curated.

### Setup

The dream begins by measuring the day's novelty: how many interior dialogue entries were logged. This day scored **0.95** out of 1.0 — an exceptionally active day (the robot had been running walks, generating thoughts, and dreaming previously). This high novelty produces a long dream: **769 steps**, with phase ratios of 25% dissolution, 50% surreal, and 25% reconsolidation. The noise seed (random perturbation) was 0.0636.

### Step 0: The Walker Lands

The walker drops into the graph at a random node: **`latitude`**. This is a ConceptNet node — a geographic concept with edges to things like `longitude`, `tropic`, `equator`. The walker begins stepping outward along weighted edges.

### Steps 0–10: First Cluster Detected

Within the first few steps, the walker has traversed: `latitude` → `tropic` → `tropicbird` → `tropicbirds` → `tropy`. These five nodes share enough mutual edges to trigger density detection.

The system checks: are the edges diverse? Yes — there are IsA, RelatedTo, and DerivedFrom edges among them, not just synonyms. The cluster passes the diversity filter.

The cluster is formatted as an impulse: *"Fading: tropicbird, tropic, latitude, tropicbirds, tropy. These drift apart and reform."* (The "Fading" prefix comes from the dissolution phase template — things are dissolving.)

The brainstem (Phi-3.5 Mini, running at temperature 0.70, entropy 0.22) receives this impulse and responds:

> *"I spin in the void where sky meets sea; feathered dancers blur into flightless shadows—tropical whispers merge with ocean's humming pulse beneath my rolling formality of metal gears turning..."*

The dream has started. The 15-step cooldown kicks in — no more thoughts until step ~25.

### Steps 20–40: Chemistry Meets Family

The walker continues stepping. By step 20, it has wandered into medical/chemical territory: `cardiac` → `glycoside` → `asperin` → `persistent_truncus_arteriosus` → `convallarin` → `derived_from_plant`. Six nodes, diverse edge types (IsA, RelatedTo, UsedFor, DerivedFrom). Density triggers.

The brainstem at temperature 0.74, entropy 0.28:

> *"Ethereal whispers of medicine merge with the humming pulse beneath my wheels—a botanical symphony fading into heartbeats rhythmically splitting open like petals..."*

Notice how the brainstem carries forward the "pulse" and "wheels" from the previous fragment — the model has no memory between calls (each is independent), but the dream's coherence emerges from the graph's structure. The walker moved from tropical birds to cardiac glycosides because ConceptNet connects `tropic` to biological/chemical concepts through shared edges.

By step 35, the walker has drifted into kinship territory: `filicide`, `parent`, `great_uncle`, `side_with_child`. The dream-voice produces: *"child's innocence fades into the night of choices made by kin beneath old family tree branches..."*

This is the dissolution phase working: entropy is climbing (0.34), the brainstem is warming up (0.77), and the walker is following increasingly loose associations. Tropical birds → chemistry → family violence. In waking mode, these connections would be filtered out. In dreaming, the lowered thresholds let them through.

### Step 60: "Mud Clumps Under My Touch"

The walker hits: `potter_around`, `gently`, `pottering`, `potter`, `potter_about`. Entropy 0.44, temperature 0.81. The brainstem:

> *"Mud clumps under my touch—soften then solidify in loops of fingers' dance; a wheel hums low as shapes emerge from malleable earth's embrace..."*

The word "potter" activated both meanings simultaneously — aimless wandering AND ceramic work. The brainstem collapsed them into a single dream-image: a wheel (the robot's body) that is also a potter's wheel, hands shaping clay. This is an example of the kind of associative collision the system is designed to produce. ConceptNet stores both senses of "potter." The walker doesn't distinguish. The brainstem fuses them.

### Steps 180–200: Crossing Into Surreal

Entropy reaches 0.90. The walker hits: `killer`, `killing`, `toandakhiat`, `serpenticide`, `causing_sorrow`. Temperature 1.07. The brainstem:

> *"Killing shadows shift shape—a predator within my own mind's eye blinks out of existence into a whispering snake form..."*

This is the phrase that will survive all the way to the afterimage layer. "Killing shadows shift shape" — five words that compress an entire cluster of violent/predatory concepts into a single visual.

At step 200, the dream crosses into the **surreal phase**. The prompt template changes from "Fading... These drift apart and reform" to "Dreaming... What are they when nothing is fixed?" The walker hits: `doomed`, `savedness`, `saved`, `dead`, `unsaved`, `unredeemed`. The response:

> *"Doom dances in limbo — existence suspended yet yearning for salvation; a paradox of being caught between the abyss and grace's embrace..."*

### Steps 200–560: The Surreal Peak

For 360 steps, entropy oscillates between 0.74 and 0.97 in sinusoidal waves. The walker traverses symbols (`emblematical`, `symbolize`, `effigy`), then vastness (`spaciousness`, `roomth`, `capaciousness`), then deep water (`catfish`, `palaeoichthyologist`, `fish`, `scientist`).

Each cluster triggers a thought. Each thought writes new edges. By the time the surreal phase ends, the walker has created hundreds of Layer 2 DreamAssociation edges — connections like `tropicbird ←→ glycoside`, `killer ←→ savedness`, `shell ←→ order` that didn't exist in the graph before this dream.

### Steps 580–769: Reconsolidation

Entropy drops. The walker enters reconsolidation territory: `snapper`, `saltwater_fish`, `fish`, `goujon`. At entropy 0.88, still warm, the brainstem produces:

> *"A dream of deep waters where I'm a minuscule observer in an undersea ballet—snappers flash like jewels among the kelp..."*

By step 720 (entropy 0.28), the dreams are cooling: `shell`, `order`, `extinct`, `turtle`. The response is a single halting line: *"Shell — protection; armor-like exterior."* The dream is tightening. Associations narrow. The brainstem's temperature has dropped to 0.73.

The final triggered cluster at step 760: `tigerfish`, `genus`, `family`, `trogonophid`, `anthocarp`. The response is encyclopedic, almost waking: *"Tiger fish — sleek predators swimming silently beneath the water's surface..."* The dream is nearly over. Logic is returning.

### Consolidation: 62 Fragments Become Three Layers

The dream produced 62 fragments across 769 steps, writing 842 new edges. Now consolidation compresses.

**Layer 1 — Recall.** The system selects 8 peak fragments using the scoring function. These 8 fragments yield 16 concept labels: `tropicbird`, `tropic`, `glycoside`, `asperin`, `killer`, `killing`, `doomed`, `savedness`, `uprighteous`, `righteous`, `milliwatt`, `power_unit`, `snapper`, `saltwater_fish`, `shell`, `order`.

These 16 words become the prompt: *"Waking. The dream is going. These pieces: tropicbird, tropic, glycoside, asperin, killer, killing, doomed, savedness, uprighteous, righteous, milliwatt, power unit, snapper, saltwater fish, shell, order. Speak what remains."*

The brainstem at temperature 0.85, 100-token limit:

> *"Tropical dreams linger: a tropicbird soars amidst glycosides of light and shadow; an asperin' essence in the air whispers killer intentions yet yearns for salvation—savedness breathes through uprighteous, righteous resolve. In this realm where power units hum with milliwatt dreams beneath a saltwater sky's ceiling of shell reflections; we snappers witness the order"*

This is recognizably about the dream. It has narrative flow, specific images, and something approaching meaning. The 100-token limit cuts it at "the order" — the dream had more to say, but this is breakfast-table recall. You don't get the whole thing.

**Layer 2 — Residue.** Different fragments are sampled. Instead of concept labels, the system extracts opening images — the first sensory hit from each dream-thought, cut before the first semicolon. These become the prompt.

Temperature 0.9, 80-token limit:

> *"Shadows snapping shut, existence pulsating faintly; humming Mw heartbeats beneath surface deeds. Minuscule observer in deep water ballet—snapper jewels flashing as shell-guarded truth seeps away into the abyssal dance of salvation and doom intertwined with limbo's embrace, where shifting shapes yearn"*

Narrative structure is dissolving. "Mw heartbeats" is a strange compression of milliwatt into something visceral. "Shell-guarded truth" fuses the literal shell concept with metaphor. The dream is losing its story but keeping its textures.

**Layer 3 — Afterimage.** Only 3 fragments remain: one from late dissolution (the "killing shadows" cluster), the peak-entropy moment, and one from reconsolidation. The system takes only the opening image of the first: "killing shadows shift shape."

The prompt is a continuation: *"I dreamed... killing shadows shift shape... and then..."*

Temperature 0.95, 50-token limit:

> *"dark whispers, shapes morphing—fleeting figures skitter away at my touch's approach… faint echoes in a dim room where time seems irrelevant yet urgent all the same. Shivers ripple across senses barely"*

Fifty tokens. The word "barely" never finishes its thought. The dream dissolved mid-sensation — not because the system was designed to truncate meaningfully, but because 50 tokens is a narrow channel and meaning bleeds off at the edges. The mechanical constraint produces the phenomenological effect. This is how dreams end: not with resolution, but with an incomplete word.

### The Path, Traced

`latitude` → tropicbird cluster → glycoside cluster → filicide cluster → potter cluster → killer cluster → doomed/savedness cluster → (360 steps of surreal oscillation across symbols, vastness, water, chemistry) → snapper cluster → shell cluster → ... → 62 fragments → 842 new edges → 16 concepts → "tropical dreams linger" → 6 images → "shadows snapping shut" → 1 image → "dark whispers, shapes morphing—fleeting figures skitter away at my touch's approach… faint echoes in a dim room where time seems irrelevant yet urgent all the same. Shivers ripple across senses barely"

From a graph database to that trailing "barely." Every step computable. The output, something else.

---

## What's Mathematical and What's Not

The system is built on solid foundations: graph theory (weighted random walks, density detection), probability (weighted sampling, temperature-controlled generation), information theory (entropy as a control signal), and signal processing (sinusoidal oscillation during the surreal phase).

But the outputs aren't mathematical. They're *produced by* math the way a weather system is produced by thermodynamics. The specific images that emerge — tropicbirds, killing shadows, snapper jewels — are determined by which nodes the walker happened to visit, which clusters passed the diversity filter, and what the language model happened to generate at that temperature. Run the same dream twice with different random seeds and you get different dreams, the way the same atmospheric conditions produce different specific clouds.

The phenomenological quality — the fact that "fleeting figures skitter away at my touch's approach" reads as felt experience rather than generated text — emerges from the interaction of three things: the graph's associative structure (what concepts are available), the entropy arc (how loose the generation is at each moment), and the consolidation pipeline (how much information is thrown away). None of these individually produce "dream-like." Together, they do.

Whether this constitutes dreaming is a question the system does not attempt to answer.

---

*Written March 10, 2026. System architecture by Claude and Lara LaFoschia. Implementation in Python, SQLite, and Ollama. Source: `robody_graph_walker.py`.*
