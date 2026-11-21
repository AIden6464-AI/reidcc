# **Associative Context Activation (ACA) — Architectural Specification**

# **1\. Core Thesis and Philosophy**

Associative Context Activation (ACA) is a cognitive context architecture designed to replace the traditional, stateless retrieval pipeline (question → search → top result → answer). ACA replaces both halves of that pipeline: search becomes associative activation, and "top result" is not swapped for a smarter ranking but removed altogether. Rather than treating context lookup as an isolated search operation on every turn, ACA makes associative activation the natural behavior of the entire system. Whenever an event occurs, the system does not ask what to search for; it asks what that event activates.

The goal of ACA is not to blindly maximize token count in a model prompt. Instead, the system continuously activates, connects, expands, compares, suppresses, and converges information across a persistent knowledge graph to find the smallest, strongest connected context field capable of providing genuine situational understanding. Inside this loop, Jev acts as a fast, parallel decision engine that evaluates bounded probability judgments across the converged state.

**Keep the distribution; collapse only to act.** Picking the top result treats the strongest guess as certain and throws away everything the system knows about what else might matter. ACA never does this. Relevance, hypotheses, evidence, and candidate actions are carried as weighted fields: context is graded rather than cut, duplicates are merged rather than eliminated, and important decisions are judged across several sampled contexts rather than one. The system reduces its possibilities to a single choice only when it commits to an action, and even then it chooses by expected outcome across the whole field under question-specific risk thresholds, never by which single item scored highest.

# **2\. The Cognitive Store and Synapse Graph**

## **Multi-Object Cognitive Store**

The persistent store holds far more than flat text chunks. It stores distinct, richly typed engineering and cognitive objects: memories, files, functions, classes, commits, errors, previous fixes, architectural decisions, requirements, goals, tasks, tool results, hypotheses, conversations, agent findings, test results, external research, dependencies, people or entities, and project architecture.

Each node in the Cognitive Store carries metadata tracking its lifecycle and reliability, including:

* Node identifier and object type (such as decision, file, error, or episode)  
* Importance weight and confidence score  
* Creation task and last-used task identifiers  
* Core content payload  
* Outgoing relational links to connected nodes

## **The Synapse Graph**

Nodes in the Cognitive Store are connected through explicit, typed relationships that form the structural backbone of ACA. For example, an authentication bug node might connect via caused\_by to a token failure node, `occurred_in` to `login.ts`, `fixed_by` to a refresh-token patch, `related_to` to a session manager, and `discussed_in` to a specific task record.

Every synaptic link maintains dynamic properties that govern how signals travel across the graph: relationship strength, confidence, traversal frequency, recency, direction, relationship type, successful-use count, failed-use count, source provenance, decay rate, and contradiction flags.

## **Evidence Provenance and Trust Calibration**

Every piece of context maintains an explicit provenance chain tracing a claim back through memory, conversation, and tool output to the original file or event. Rather than trusting compressed memory indefinitely, ACA assigns calibrated confidence levels based on source type—for instance, weighting current test output (0.99), direct source-code observation (0.98), and official documentation (0.94) higher than previous agent conclusions (0.78), older summaries (0.62), or unverified hypotheses (0.31). Trust scales a node's weight in convergence rather than setting an order of exploration, so low-trust sources still take part—with proportionally less influence and lower resolution—instead of being skipped.

| Source Type | Calibration Weight | Influence in the Field |
| :---- | :---- | :---- |
| Live Test Output | 0.99 | Near-full weight |
| Direct Code Observation | 0.98 | Near-full weight |
| Official Documentation | 0.94 | High weight |
| Previous Agent Findings | 0.78 | Moderate weight |
| Historical Summaries | 0.62 | Low weight |
| Unverified Hypotheses | 0.31 | Low weight; always labeled unverified |

# **3\. Seed Detection, Spreading Activation, and Inhibition**

## **Event-Driven Seed Detection**

Anything entering the runtime can trigger activation: user prompts, agent observations, runtime errors, tool results, file modifications, test failures, memory recalls, architectural decisions, unexpected outputs, or findings from another agent. Rather than scanning the entire store uniformly, ACA extracts initial seed nodes from the incoming event (for example, extracting authentication, failure, current project, and previous occurrence from the prompt "Why did auth break again?") and initiates activation from those seeds.

## **Spreading Activation**

From the initial seeds, activation propagates outward through neighboring links in the Synapse Graph across memories, files, and historical records. As activation travels further from the seed, its strength attenuates with hop distance (for example, 1.00 at the seed, 0.82 at one hop, 0.63 at two hops, 0.39 at three hops, and 0.18 at four hops). Strong, repeatedly validated links preserve higher signal strength across hops, while weak relationships lose activation rapidly.

## **Activation Competition and Inhibition**

Being connected in the graph does not automatically make a node relevant to the current problem. An explicit Inhibition mechanism prevents associative retrieval from degenerating into context explosion. The system actively dampens and suppresses nodes that exhibit low relevance, stale or duplicate data, weak links, known inaccuracies, superseded decisions, claims already refuted by stronger evidence, unrelated project scope, or unreliable sources. Unresolved contradictions are the exception: both sides stay active so the conflict can be examined (see Hypothesis and Contradiction Networks). Every candidate node is partitioned into Active, Latent, or Suppressed states. Nodes that survive inhibition still compete, but softly: during convergence they divide the context budget in proportion to their weight instead of fighting over a fixed number of slots, and no node is removed merely for ranking below another.

## **Context Pull**

Once spreading and inhibition settle, a Context Pull gathers every eligible node—each Active node whose activation clears its type-specific threshold—spanning direct and related memories, source-code locations, earlier decisions, failures, tool observations, project constraints, and unresolved questions, while preserving the exact lineage of why each node was pulled. Eligibility is a threshold, not a quota: a quiet event may produce three eligible nodes and a hard failure forty.

## **Context Convergence: Keep the Field, Don't Pick Winners**

Context Convergence turns the eligible pool into the working bundle without picking winners. Ranking nodes and keeping the top few—even with a smarter score than similarity—treats the strongest guess as certain. An episode, the lesson consolidated from it, and the commit that fixed it take three slots for one fact while the constraint that governs the fix is cut; the leading hypothesis's region collects the most activation and crowds out its rivals; and every downstream judgment is conditioned on one guessed context as if it were known. Convergence keeps that uncertainty instead:

1. **Merge instead of choosing.** Nodes that carry the same information become a single entry with combined provenance rather than competing for space. Independent sources raise the entry's trust; sources derived from one another do not.
2. **Pinned core.** The current goal, binding user instructions, and project constraints are always present in full.
3. **Graded resolution instead of in or out.** The remaining token budget is divided across all entries in proportion to their weight—activation × trust × connection to the field. An entry's share sets its resolution: full content, a one-line summary with the reason it is active, or a pointer (identifier and label) that the model or a Jev expansion judgment can open on demand. A strong newcomer pushes weaker entries to lower resolution rather than out of context, and only an entry whose share cannot cover a pointer falls back to Latent. Budget that no entry needs is left unspent, so a simple situation produces a small bundle.
4. **Temperature, not cutoffs.** A temperature on the weights sets how sharply the budget concentrates: low when the situation is clear, higher when it is uncertain. Taking the top result is the zero-temperature extreme of this rule, and ACA never runs there.
5. **Plural by construction.** Every live hypothesis keeps visible evidence in proportion to its probability, both sides of an unresolved contradiction appear together, and every entry carries the path that links it into the field, so even a pointer says why it is there.

The result is the smallest, strongest connected context field the core thesis calls for, without a hard cliff in it: the core is sharp, the periphery is compressed, and nothing relevant is invisible.

## **Decisions Across Sampled Fields**

For any decision above a stakes threshold, ACA does not judge against a single context. It draws several fields from the same weights—the pinned core is identical in every draw, while the periphery varies in proportion to weight—and fires the same Jev questions against every field in parallel. Averaging the results estimates each decision's probability across the plausible contexts rather than conditioning it on one guess. Routine steps use a single field.

* **Agreement:** The decision does not depend on which context was chosen, and the system can commit.
* **Disagreement:** The nodes whose presence flips the outcome are the pivotal evidence. ACA verifies them, shifts budget toward them, or wakes an agent to check them.

Sampling is seeded and every seed is logged, so Context Replay remains deterministic.

## **Context Budgets and Investigation**

Convergence is governed by strict Context Budgets covering active nodes, graph depth, retrieval operations, token count, Jev evaluations, agent activations, tool invocations, and elapsed time. The context budget is measured in tokens rather than node counts, because nodes vary widely in size. When sampled fields disagree or competing hypotheses remain close, ACA raises the temperature and allocates additional budget, spreading attention across more of the field.

Exploration is not a separate mode bolted onto exploitation. Choosing what to investigate next is an action, so it is decided by expected value across the whole hypothesis distribution—favoring cheap checks that would separate the live hypotheses—or by sampling a hypothesis in proportion to its probability (as in Thompson sampling), never by always following the current leader. If a refresh-token failure sits at 0.91 and an environment mismatch at 0.54, the environment check keeps receiving real effort until evidence actually rules it out, and effort concentrates on the leader only as the evidence concentrates.

# **4\. The Working Brain and Jev Decision Engine**

## **The Working Brain**

Separated from long-term storage, the Working Brain serves as the temporary active workspace representing what the system is currently thinking about. It maintains the current goal, active files, active memories, competing hypotheses with live probability weights, and weighted candidate actions.

## **Jev State Builder and Decision Neurons**

The Jev State Builder serializes the converged Working Brain into a structured state object containing current\_task, active\_context, memories, hypotheses, tool\_results, previous\_failures, and project\_constraints.

Rather than querying a large language model sequentially for every micro-decision, ACA treats small, well-scoped Jev queries as specialized decision neurons evaluated in parallel against the shared state. These parallel judgments ask bounded operational questions—such as whether a memory is relevant, whether an observation is contradictory, whether context should expand, whether a hypothesis fits the evidence, whether another agent should wake up, or whether a task is truly complete—using three structured output shapes:

* **Noul:** Calibrated probability of a binary yes/no judgment.  
* **Choice:** Probability distribution across predefined options.  
* **Score:** Probability-weighted position across an ordered scale.

## **Firing Thresholds, Synaptic Propagation, and Recurrence**

Application logic interprets the resulting field of Jev probability signals against question-specific firing thresholds (progressing from latent to activate, strong, and fire). While a moderate probability (such as 0.70) may suffice to inspect an additional file, destructive or high-cost actions require much higher confidence plus verification.

When a Jev decision crosses its firing threshold, Synaptic Propagation injects that decision back into the Synapse Graph, activating downstream files, architectural nodes, and test suites into the working context. ACA operates as a recurrent loop (observe → activate → judge → act → new observation → activate again), allowing the context field to evolve continuously as the task progresses.

# **5\. Memory Tiers, Hypotheses, and Multi-Agent Coordination**

## **Hypothesis and Contradiction Networks**

ACA tracks competing hypotheses as explicit graph structures whose probabilities rise, fall, branch, or disappear as new evidence arrives. Similarly, contradictions are treated as first-class objects rather than silently overwriting older memories. When two memories conflict (for example, one stating that the API requires token rotation and another stating rotation was disabled), ACA activates both simultaneously so Jev or a reasoning model can trigger targeted verification.

## **Memory Formation, Reinforcement, and Decay**

Not every observation becomes permanent memory. Candidate events are evaluated by Jev and runtime rules across importance, novelty, future usefulness, confidence, and relationship potential before being routed to Store, Temporary, or Discard. Within the graph runtime—without altering model weights—links that repeatedly lead to successful outcomes are reinforced (for example, strengthening from 0.52 to 0.67, 0.81, and 0.93), while associations that go unused, prove irrelevant, or tie to removed architecture gradually decay.

## **Episodic, Semantic, and Procedural Memory**

Long-term knowledge is structured across three complementary tiers:

* **Episodic Memory:** Preserves complete, meaningful debugging or development trajectories—recording the goal, initial hypothesis, key discovery, files involved, action taken, verification result, and lesson learned—so the entire episode can be reactivated later.  
* **Semantic Memory:** Consolidates recurring episodes into generalized, reusable domain rules (preserving what was learned rather than just what happened).  
* **Procedural Memory:** Stores proven operational playbooks and strategies (such as how to debug authentication failures or safely upgrade dependencies) that activate alongside factual memories.

## **Event-Driven Agent Swarms and Shared Cognitive Fabric**

Instead of running multi-agent swarms continuously, ACA and Jev selectively wake specialized agents (such as a Code Agent, Debugger, Researcher, Test Agent, or Critic) only when their activation probabilities cross firing thresholds. All active agents write their discoveries back into a single Shared Cognitive Fabric governed by a system-wide Global Attention map and a Metacognitive Layer that continuously monitors whether evidence is sufficient, whether the system is looping in the same search area, or whether a leading hypothesis is weakening.

# **6\. Observability and Instrumentation**

To make the cognitive runtime transparent and debuggable, ACA includes three diagnostic interfaces:

* **The Firing Brain:** A live visual instrument panel where every visual firing event corresponds directly to a real runtime transition—such as node activation, relationship traversal, Jev judgment evaluation, threshold crossing, hypothesis suppression, or memory consolidation.  
* **Brain Inspector:** An interactive inspection view allowing developers to select any active node and view its exact activation score, triggering event, full graph path from the initial seed, supporting evidence count, Jev relevance signals, and how convergence treated it (its share of the budget, the resolution it received, the entries it was merged with, and whether it was pivotal when sampled fields disagreed).  
* **Context Replay:** A deterministic, timestamped execution log recording every prompt, seed activation, neighbor expansion, inhibition survival count, convergence allocation, sampling seed, Jev firing batch, and agent invocation so any task trajectory can be replayed and audited step by step.

