# **The Firing System — Architectural Specification**

# **1\. Core Thesis and Philosophy**

The Firing System is a stateful, dynamical memory architecture built around a foundational shift in how agent context is managed: relevance is treated as a continuous state that each piece of memory is already in, rather than a score recomputed from scratch at query time.

When an agent works through a technical trajectory—opening a file, following imports, modifying a function, running tests, interpreting errors, and adjusting its plan—the relevant context evolves gradually from step to step. Stateless retrieval discards that continuity on every turn. By carrying activation forward across turns, The Firing System preserves active constraints, ongoing hypotheses, rejected approaches, and environmental facts without relying on traditional query-time similarity ranking, top-ranked selection of any kind, or rigid database schemas.

The working set is a graded readout of the whole activation field, not a list of winners: strongly active fragments appear in full, weaker ones as summaries or pointers, and no fragment enters or leaves context merely for ranking above or below another.

# **2\. Memory Primitives: Fragments, Links, and the Raw Log**

## **Schema-Free Prose Fragments**

The atomic unit of memory in The Firing System is a **Fragment**: a small, dense piece of settled state written in open-ended natural prose. Rather than storing multi-page terminal dumps or forcing knowledge into predefined database schemas—which pre-decide what matters before the task is understood—a fragment captures a distilled operational truth (for example, noting that integration tests depend on a local service on port 5433 and are not covered by the standard unit-test command).

Every fragment \$f\$ maintains a persistent activation level \$a \\in \[0, 1\]\$ and connects to other fragments through directed, weighted links \$w(f, g)\$.

## **Emergent Regions**

As fragments co-fire and strengthen their mutual links over time, strongly connected subsets naturally organize into local clusters called Regions. Activation dynamics operate locally within the currently active trajectory so that growth elsewhere in the memory store does not create global noise.

## **The Append-Only Raw Log**

Alongside the fragment network, every raw turn and tool interaction is recorded in an append-only historical log. The full raw log is never passed as routine model input; instead, the model receives only the last few raw turns for immediate continuity plus the composed state from the active working set, while the historical log remains available as the permanent ground-truth recovery path.

# **3\. The Four-Stage Firing Pass**

On every turn, incoming input drives a four-stage dynamical pass across the fragment space:

| Stage | Operation | Description | Runtime Dynamics |
| :---- | :---- | :---- | :---- |
| **1\. INJECT** | Direct Perturbation | Incoming input hits fragments directly, raising activation proportional to match strength. | Serves as entry evidence perturbing the carried-over activation state. |
| **2\. FIRE** | Network Propagation & Updating | Fragments crossing threshold \$a \\ge \\theta\$ enter active firing set \$F\$. | Spreading activation along \$w(f,g)\$; refractory dampening; co-firing potentiation (\$w(f,g) += \\eta\$); multiplicative decay. |
| **3\. ADMIT** | Graded Admission | Divides the token budget across candidate fragments in proportion to weight, setting each fragment's resolution in the Working Set \$W\$. | Full, summary, or pointer resolution; hysteresis on every resolution change; no ranking and no fixed count. |
| **4\. COMPOSE** | Narrative Synthesis | Synthesizes \$W\$ into Canonicalized Atomic Narrative (CAN). | Generates transient readout for inference. Invariant: CAN output never feeds back into future CANs. |

## **Stage Details**

### **Stage 1: INJECT**

Incoming input hits fragments directly, raising each fragment's activation level proportional to how strongly the input matches the fragment. This direct injection serves as the entry evidence that perturbs the existing activation state carried over from previous turns.

### **Stage 2: FIRE**

Fragments whose activation crosses the firing threshold enter the active firing set \$F\$ and trigger four coupled runtime updates:

* **Spreading Activation:** Fired fragments propagate activation outward along their outgoing directed links \$w(f, g)\$ to prime connected neighbor fragments.  
* **Refractory Period:** Once a fragment fires, it enters a refractory state that prevents it from immediately re-firing on the very next pass, curbing runaway self-reinforcement loops.  
* **Co-Firing Potentiation:** For every pair of fragments \$(f, g)\$ that fires together in \$F\$, the connecting link weight is strengthened (\$w(f, g) += \\eta\$), encoding associative structure directly from usage.  
* **Activation and Link Decay:** Across every pass, all fragment activations and link weights undergo gradual multiplicative decay. Ordinary forgetting is handled entirely through decay rather than explicit deletion, and broader conceptual categories emerge naturally as surface-level episodic differences decay away.

### **Stage 3: ADMIT**

ADMIT decides how the model sees each candidate fragment. It never ranks fragments and keeps the top few. A ranked cut treats the strongest fragments as the whole story: near-duplicates rise together and crowd out a quieter constraint that still governs the work, the region around the current hypothesis takes every slot, and fragments near the cutoff flicker in and out of context from pass to pass. ADMIT instead divides the token budget \$B\$ across every candidate in proportion to its weight:

\$\$\\text{share}(f) = B \\cdot \\frac{w\_f^{1/\\tau}}{\\sum\_{g \\in C} w\_g^{1/\\tau}}, \\qquad w\_f = a\_f \\cdot \\text{novelty}(f) \\cdot \\text{connection}(f)\$\$

The candidate set \$C\$ is the firing set \$F\$ plus every fragment resident on the previous pass whose activation is still above a release threshold \$\\theta\_{\\text{out}} < \\theta\$.

* **Resolution follows share.** A share that covers the full fragment admits it verbatim, a smaller share admits a one-line summary, and a share that covers only a pointer admits a reference the model can expand on request. A fragment whose share cannot cover a pointer stays out of \$W\$ until its weight rises. Surplus from fragments shorter than their share is redistributed to the rest, and budget no fragment needs goes unspent, so an easy situation produces a small working set.
* **Temperature, not cutoffs.** Lower \$\\tau\$ concentrates the budget on the most active fragments; higher \$\\tau\$ spreads it when the trajectory is uncertain. Taking the top result is the \$\\tau \\to 0\$ extreme of this rule, and the system never runs there.
* **Redundancy and connection.** \$\\text{novelty}(f)\$ falls toward zero as \$f\$ repeats a more active fragment, and a fragment that only restates another is folded into that fragment's entry instead of receiving a share of its own. \$\\text{connection}(f)\$ combines every link into \$f\$ from fragments resident on the previous pass with its INJECT match \$m\_f\$ against the current input, as a noisy-OR with a small floor: \$\\text{connection}(f) = 1 - (1 - m\_f)\\prod\_{g \\in W\_{\\text{prev}}} (1 - w(g, f))\$. Several weak connections add up instead of only the single strongest one counting, and because the current input counts directly, a genuine task switch can enter context while the old region fades below \$\\theta\_{\\text{out}}\$.
* **Hysteresis.** A fragment moves up a resolution level only when its share clears that level's cost by a margin, and moves down only when its share falls clearly below it, so \$W\$ stays stable from pass to pass. Residency is independent of the refractory period: a refractory fragment cannot re-fire or re-potentiate its links, but it remains a candidate while its activation stays above \$\\theta\_{\\text{out}}\$.

A strong newcomer therefore pushes weaker fragments to lower resolution rather than out of context, and fragments that remain crucial to an ongoing trajectory stay sharp across turns.

### **Stage 4: COMPOSE (Canonicalized Atomic Narrative)**

Rather than handing the model a disconnected list of raw chunks, the admitted fragments in \$W\$ are synthesized into a Canonicalized Atomic Narrative (CAN)—a cohesive, temporary prose state narrative that bridges the active fragments and supplies smooth situational context alongside the last few raw turns. Each fragment appears at the resolution ADMIT assigned it: full fragments carry the narrative, summaries appear as brief mentions, and pointers are listed so the model knows what else is active and can expand it.

To prevent narrative drift from corrupting long-term memory, COMPOSE enforces a strict invariant: a CAN is purely a transient readout for model inference and never becomes input to a later CAN (*reconstruction never becomes assertion*).

# **4\. Recurrent Settling ("Think Until It Settles")**

The Firing System supports multi-pass internal settling before the agent commits to an external action. During recurrent thinking, the model's intermediate reasoning is fed back into `INJECT` as an internal self-cue with a reduced gain factor.

The firing pass repeats across the network until the lit set of firing fragments stops changing. Convergence emerges directly from the settling of the activation dynamics without requiring a separate external halting classifier.

# **5\. Surprise-Gated Encoding (Write Policy)**

To prevent memory bloat and redundant storage, The Firing System governs memory creation strictly through prediction error:

* **Prediction vs. Outcome:** The currently lit set of fragments establishes an implicit or explicit expectation for what the current action or command will produce. When the outcome returns, it is compared against what the lit set predicted.  
* **Encode Only on Surprise:** A new canonical fragment (*"one form per settled thing"*) is written to the store only when the current understanding fails—such as an unexpected tool failure, a violated assumption, or a newly discovered environmental mismatch.  
* **Confirmation Writes Nothing:** When an action succeeds as expected and confirms the predictions of the currently active region, no new fragment is written (*"confirmation teaches nothing"*), keeping the fragment store compact and high-signal.

# **6\. Trace Viewer and Diagnostics**

Because the memory system is a live dynamical network, it is paired with an interactive **Trace Viewer** built early in the development cycle. The Trace Viewer exposes real-time fragment activation levels, threshold crossings, spreading pathways, co-firing link updates, refractory states, budget shares and resolution changes for each fragment with the weights behind them, and emergent region clusters so developers can inspect and tune the coupled activation, potentiation, and decay parameters across real task trajectories.