"""The Firing System & ACA Unified Dynamical Pass (`INJECT -> FIRE -> ADMIT -> COMPOSE`),
Recurrent Settling (`Think`), Directed Normalized Co-Firing (`POTENTIATE`), and Hybrid Write Gate.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import threading
import uuid
from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from src.aca.aca_graph import ACAGraphEngine
from src.firing.embedding_provider import (
    EmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
    SemanticProjectionEmbeddingProvider,
)
from src.gc.gc_engine import GCEngine
from src.schemas import (
    BudgetState,
    CANPacket,
    CANState,
    EngineMode,
    FragmentDynamics,
    FragmentLinks,
    FragmentProvenance,
    FragmentResolutions,
    MemoryNode,
    ModulationState,
    NodeType,
    OutcomeRequest,
    OutcomeResponse,
    ResolutionLevel,
    SettleResponse,
    SourceTrustType,
    TraceBreakdown,
)
from src.storage.store import CognitiveStorage


class FiringEngine:
    """Executes the 4-stage dynamical pass and resolves all 4 critiques from ACA-Fireing system.txt."""

    STOPWORDS = {
        "the", "and", "for", "that", "this", "with", "from", "are", "was", "were",
        "have", "has", "had", "not", "but", "what", "when", "where", "why", "how",
        "into", "onto", "upon", "can", "will", "should", "would", "could", "our",
    }

    # Environmental failure cues in tool output that signal a surprising outcome (word-bounded so
    # e.g. "report"/"import" do not match)
    ENV_SURPRISE_CUE_RE = re.compile(
        r"\b(?:connection refused|address already in use|mismatch|incompatible|deprecated|permission denied)\b"
    )

    def __init__(
        self,
        storage: CognitiveStorage,
        gc_engine: Optional[GCEngine] = None,
        event_broadcaster: Optional[Callable[[Dict[str, Any]], None]] = None,
        embedding_provider: Optional[EmbeddingProvider] = None,
    ) -> None:
        self.storage = storage
        # One GC dictionary per store: persisted nodes hold GC-compressed text and are shared
        # across sessions, so every session must resolve pointers against the same dictionary.
        if gc_engine is not None:
            self.gc = gc_engine
        else:
            saved_gc = storage.load_gc_state()
            self.gc = GCEngine.from_state(saved_gc) if saved_gc else GCEngine()
        self._saved_gc_version = self.gc.version
        # Serializes all engine/GC mutation; endpoints run in the threadpool
        self.lock = threading.RLock()
        self.aca = ACAGraphEngine()
        self.event_broadcaster = event_broadcaster
        if embedding_provider is not None:
            self.embedding_provider = embedding_provider
        elif os.environ.get("ACA_EMBEDDING_URL"):
            self.embedding_provider = OpenAICompatibleEmbeddingProvider(
                base_url=os.environ["ACA_EMBEDDING_URL"],
                api_key=os.environ.get("ACA_EMBEDDING_API_KEY"),
            )
        else:
            self.embedding_provider = SemanticProjectionEmbeddingProvider(dim=128)

        # Per-session runtime state
        self.modulations: Dict[str, ModulationState] = {}
        self.resident_sets: Dict[str, Set[str]] = {}
        self.prior_fired_sets: Dict[str, Set[str]] = {}
        self.predictions: Dict[str, str] = {}
        self.last_can_packets: Dict[str, CANPacket] = {}
        # Hashes of proxy messages already tallied into the GC, so resent history is not recounted
        self.proxy_seen_messages: Dict[str, Set[str]] = {}

    def get_gc(self, session_id: str) -> GCEngine:
        return self.gc

    def get_modulation(self, session_id: str) -> ModulationState:
        if session_id not in self.modulations:
            saved = self.storage.get_session_metadata(session_id).get("modulation")
            self.modulations[session_id] = ModulationState(**saved) if saved else ModulationState()
        return self.modulations[session_id]

    def get_prediction(self, session_id: str) -> str:
        if session_id not in self.predictions:
            saved = self.storage.get_session_metadata(session_id).get("last_prediction")
            if saved:
                self.predictions[session_id] = saved
        return self.predictions.get(session_id, "")

    def persist_extras(self, session_id: str) -> Dict[str, Any]:
        """GC dictionary (if changed) and session metadata to commit alongside a node batch."""
        extras: Dict[str, Any] = {
            "session_meta": {
                session_id: {
                    "modulation": self.get_modulation(session_id).model_dump(),
                    "last_prediction": self.get_prediction(session_id) or None,
                }
            }
        }
        if self.gc.version != self._saved_gc_version:
            extras["gc_state"] = self.gc.export_state()
            self._saved_gc_version = self.gc.version
        return extras

    def persist_gc(self) -> None:
        if self.gc.version != self._saved_gc_version:
            self.storage.save_gc_state(self.gc.export_state())
            self._saved_gc_version = self.gc.version

    def _emit_event(self, event_type: str, session_id: str, payload: Dict[str, Any]) -> None:
        if self.event_broadcaster is not None:
            self.event_broadcaster(
                {
                    "event": event_type,
                    "session_id": session_id,
                    "payload": payload,
                }
            )

    # -------------------------------------------------------------------------
    # GAP 1 RESOLUTION: Concrete Hybrid INJECT Matcher (GC + BM25/Trigram + Dense Hash Cosine)
    # -------------------------------------------------------------------------
    @classmethod
    def _tokenize(cls, text: str) -> List[str]:
        tokens = re.findall(r"(?:<P_\d+>|\[CMD_\d+\]|\[STATE_\d+\]|[A-Za-z0-9_.\-/]{2,})", text.lower())
        return [t for t in tokens if t not in cls.STOPWORDS]

    @staticmethod
    def _char_trigrams(text: str) -> Set[str]:
        clean = re.sub(r"\s+", " ", text.lower().strip())
        if len(clean) < 3:
            return {clean} if clean else set()
        return {clean[i : i + 3] for i in range(len(clean) - 2)}

    @classmethod
    def _feature_hash_cosine(cls, tokens_a: List[str], tokens_b: List[str], dim: int = 128) -> float:
        if not tokens_a or not tokens_b:
            return 0.0
        vec_a = [0.0] * dim
        vec_b = [0.0] * dim
        for tok in tokens_a:
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest()[:8], 16)
            idx = h % dim
            sign = 1.0 if ((h >> 8) & 1) == 0 else -1.0
            vec_a[idx] += sign
        for tok in tokens_b:
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest()[:8], 16)
            idx = h % dim
            sign = 1.0 if ((h >> 8) & 1) == 0 else -1.0
            vec_b[idx] += sign
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return max(0.0, min(1.0, dot / (norm_a * norm_b)))

    def compute_inject_match(
        self,
        compressed_input: str,
        node: MemoryNode,
        gc: GCEngine,
        doc_freqs: Dict[str, int],
        total_docs: int,
    ) -> float:
        """Compute deterministic hybrid match score m_f in [0, 1] combining:
        1. Exact GC entity / prefix / semantic pointer / numeric symbol overlap
        2. IDF-weighted BM25 lexical score
        3. Character trigram Jaccard + hashed dense vector cosine similarity
        """
        frag_text = f"{node.resolutions.full} {node.resolutions.pointer}"
        q_tokens = self._tokenize(compressed_input)
        f_tokens = self._tokenize(frag_text)
        if not q_tokens or not f_tokens:
            return 0.0

        q_set = set(q_tokens)
        f_set = set(f_tokens)

        # 1. Exact GC token / symbol / port / filename hits
        gc_tokens_q = set(gc.extract_active_tokens(compressed_input))
        gc_tokens_f = set(gc.extract_active_tokens(frag_text))
        gc_overlap = (
            len(gc_tokens_q.intersection(gc_tokens_f)) / max(len(gc_tokens_q), 1)
            if gc_tokens_q
            else 0.0
        )

        # Exact technical identifiers (ports, file extensions, identifiers with digits/underscores)
        tech_q = {t for t in q_set if any(c.isdigit() or c in "._-<>[]" for c in t)}
        tech_f = {t for t in f_set if any(c.isdigit() or c in "._-<>[]" for c in t)}
        tech_overlap = len(tech_q.intersection(tech_f)) / max(len(tech_q), 1) if tech_q else 0.0
        exact_signal = max(gc_overlap, tech_overlap)

        # 2. BM25-style IDF-weighted lexical overlap
        f_counts = Counter(f_tokens)
        k1 = 1.5
        b = 0.75
        avg_dl = 24.0
        dl = float(len(f_tokens))
        bm25_raw = 0.0
        max_possible_bm25 = 0.0
        for tok in q_set:
            df = doc_freqs.get(tok, 0)
            idf = math.log(1.0 + (total_docs - df + 0.5) / (df + 0.5))
            max_possible_bm25 += idf * (k1 + 1.0)
            tf = f_counts.get(tok, 0)
            if tf > 0:
                bm25_raw += idf * ((tf * (k1 + 1.0)) / (tf + k1 * (1.0 - b + b * (dl / avg_dl))))

        bm25_norm = min(1.0, (bm25_raw / max_possible_bm25) * 1.65) if max_possible_bm25 > 0 else 0.0

        # 3. Trigram Jaccard + Feature Hash Cosine + Pluggable Semantic Embedding Cosine
        tri_q = self._char_trigrams(compressed_input)
        tri_f = self._char_trigrams(frag_text)
        tri_union = len(tri_q.union(tri_f))
        trigram_sim = (len(tri_q.intersection(tri_f)) / tri_union) if tri_union > 0 else 0.0
        hash_cos = self._feature_hash_cosine(q_tokens, f_tokens)

        emb_q = self.embedding_provider.embed(compressed_input)
        emb_f = self.embedding_provider.embed(frag_text)
        semantic_emb_cos = self.embedding_provider.cosine_similarity(emb_q, emb_f)

        # Combine into calibrated m_f in [0, 1]
        combined = (
            0.36 * bm25_norm
            + 0.24 * exact_signal
            + 0.22 * semantic_emb_cos
            + 0.10 * hash_cos
            + 0.08 * trigram_sim
        )
        if exact_signal >= 0.5 and bm25_norm >= 0.25:
            combined = min(1.0, combined + 0.18)
        elif semantic_emb_cos >= 0.55 and bm25_norm < 0.20:
            # Semantic paraphrase boost when lexical overlap is low
            combined = min(1.0, max(combined, 0.58 * semantic_emb_cos + 0.15))
        return round(max(0.0, min(1.0, combined)), 4)

    # -------------------------------------------------------------------------
    # Helper: Token estimate & novelty
    # -------------------------------------------------------------------------
    @staticmethod
    def _estimate_tokens(text: str) -> int:
        if not text:
            return 1
        return max(4, int(math.ceil(len(text.split()) * 1.35)))

    def _compute_novelty(self, target: MemoryNode, stronger_nodes: List[MemoryNode]) -> float:
        """Compute novelty(f) in [0.05, 1.0]. Falls toward zero as f repeats a more active fragment."""
        if not stronger_nodes:
            return 1.0
        t_tris = self._char_trigrams(target.resolutions.full)
        if not t_tris:
            return 1.0
        max_sim = 0.0
        for other in stronger_nodes:
            if other.id == target.id:
                continue
            o_tris = self._char_trigrams(other.resolutions.full)
            if not o_tris:
                continue
            inter = len(t_tris.intersection(o_tris))
            smaller = min(len(t_tris), len(o_tris))
            sim = inter / smaller if smaller > 0 else 0.0
            if sim > max_sim:
                max_sim = sim
        return round(max(0.05, 1.0 - 0.90 * (max_sim ** 1.4)), 4)

    # -------------------------------------------------------------------------
    # The Four-Stage Dynamical Firing Pass (`INJECT -> FIRE -> ADMIT -> COMPOSE`)
    # -------------------------------------------------------------------------
    def run_firing_pass(
        self,
        session_id: str,
        turn_id: int,
        compressed_input: str,
        raw_input: str = "",
        engine_mode: EngineMode = EngineMode.HYBRID,
        scope: str = "repo:ACA-systems-prodo",
        token_budget: int = 2048,
        temperature_tau: Optional[float] = None,
        input_gain: float = 0.72,
        apply_refractory_and_decay: bool = True,
        sample_fields_count: int = 3,
    ) -> CANPacket:
        """Execute Stage 1 (INJECT) -> Stage 2 (FIRE) -> Stage 3 (ADMIT) -> Stage 4 (COMPOSE)."""
        gc = self.get_gc(session_id)
        mod = self.get_modulation(session_id)
        tau = temperature_tau if temperature_tau is not None else 0.35

        nodes = self.storage.list_nodes(scope=scope, include_superseded=False)
        node_map: Dict[str, MemoryNode] = {n.id: n for n in nodes}
        w_prev: Set[str] = set(self.resident_sets.get(session_id, set()))

        # Build document frequency table for BM25
        doc_freqs: Counter[str] = Counter()
        for n in nodes:
            for tok in set(self._tokenize(f"{n.resolutions.full} {n.resolutions.pointer}")):
                doc_freqs[tok] += 1
        total_docs = max(1, len(nodes))

        # =====================================================================
        # STAGE 1: INJECT (Direct Perturbation on Carried Activation State)
        # =====================================================================
        prior_activations: Dict[str, float] = {}
        inject_matches: Dict[str, float] = {}
        post_inject_activations: Dict[str, float] = {}

        for n in nodes:
            prior_a = n.dynamics.activation
            prior_activations[n.id] = prior_a

            m_f = self.compute_inject_match(compressed_input, n, gc, doc_freqs, total_docs)
            inject_matches[n.id] = m_f

            # Multiplicative persistence decay + direct input perturbation
            decayed_a = (mod.delta_a * prior_a) if apply_refractory_and_decay else prior_a
            # Pinned constraints maintain a protective floor >= theta_out + 0.12
            floor_a = (mod.theta_out + 0.15) if n.dynamics.pinned else 0.0
            a_inj = max(floor_a, min(1.0, decayed_a + input_gain * m_f * (1.0 - 0.35 * decayed_a)))
            post_inject_activations[n.id] = a_inj

        # =====================================================================
        # STAGE 2: FIRE (Threshold Crossing, Spreading Activation & Inhibition)
        # =====================================================================
        # Initial seed firing set: non-refractory nodes crossing theta_in
        seed_fired: Set[str] = {
            n.id
            for n in nodes
            if post_inject_activations[n.id] >= mod.theta_in and n.dynamics.refractory_remaining == 0
        }

        spread_contributions: Dict[str, float] = {n.id: 0.0 for n in nodes}
        inhibitory_suppressions: Dict[str, float] = {n.id: 0.0 for n in nodes}

        # Multi-hop attenuated spreading (up to 2 hops within pass)
        frontier = set(seed_fired)
        visited_sources: Set[str] = set()
        for hop in range(1, 3):
            hop_atten = (mod.lambda_spread ** hop)
            next_frontier: Set[str] = set()
            for src_id in frontier:
                if src_id in visited_sources or src_id not in node_map:
                    continue
                visited_sources.add(src_id)
                src_node = node_map[src_id]
                src_a = post_inject_activations[src_id] + spread_contributions[src_id]

                # Excitatory spreading along w^+(src, dst)
                for dst_id, w_val in src_node.links.excitatory.items():
                    if dst_id in node_map and w_val > 0.0:
                        delta = hop_atten * w_val * src_a
                        spread_contributions[dst_id] += delta
                        if (
                            post_inject_activations[dst_id] + spread_contributions[dst_id] >= mod.theta_in
                            and node_map[dst_id].dynamics.refractory_remaining == 0
                        ):
                            next_frontier.add(dst_id)

                # Inhibitory suppression along w^-(src, dst) (ACA / Hybrid mode)
                if engine_mode in (EngineMode.ACA, EngineMode.HYBRID):
                    for dst_id, w_inh in src_node.links.inhibitory.items():
                        if dst_id in node_map and w_inh < 0.0:
                            dst_node = node_map[dst_id]
                            # Only suppress if source has higher or equal trust; unresolved equal conflicts stay visible
                            if src_node.provenance.trust > dst_node.provenance.trust + 0.08:
                                inhibitory_suppressions[dst_id] += abs(w_inh) * src_a * 0.45
            frontier = next_frontier

        # Finalize post-FIRE activation levels and active Firing Set F_t
        firing_set: Set[str] = set()
        for n in nodes:
            raw_a = (
                post_inject_activations[n.id]
                + spread_contributions[n.id]
                - inhibitory_suppressions[n.id]
            )
            n.dynamics.activation = round(max(0.0, min(1.0, raw_a)), 4)
            if n.dynamics.activation >= mod.theta_in and n.dynamics.refractory_remaining == 0:
                firing_set.add(n.id)
                if apply_refractory_and_decay:
                    n.dynamics.last_fired_turn = turn_id
                    n.dynamics.fire_count += 1
                    # Enter refractory period for 1 subsequent pass (does NOT evict from residency!)
                    n.dynamics.refractory_remaining = 1
            elif apply_refractory_and_decay and n.dynamics.refractory_remaining > 0:
                # Refractory turn served: blocked from firing on this pass, eligible again next turn
                n.dynamics.refractory_remaining -= 1

        # =====================================================================
        # STAGE 3: ADMIT (Graded Proportional Budget Allocation + Hysteresis)
        # =====================================================================
        # Candidate set C = F union {g in W_prev | a_g >= theta_out} union {pinned}
        candidate_nodes: List[MemoryNode] = [
            n
            for n in nodes
            if (
                n.id in firing_set
                or (n.id in w_prev and n.dynamics.activation >= mod.theta_out)
                or n.dynamics.pinned
            )
        ]

        # Sort candidates by activation descending to compute novelty against stronger nodes
        candidate_nodes.sort(key=lambda x: x.dynamics.activation, reverse=True)

        novelties: Dict[str, float] = {}
        connections: Dict[str, float] = {}
        composite_weights: Dict[str, float] = {}
        scaled_weights: Dict[str, float] = {}

        for idx, cand in enumerate(candidate_nodes):
            stronger = candidate_nodes[:idx]
            nov = self._compute_novelty(cand, stronger)
            novelties[cand.id] = nov

            # Noisy-OR connection: 1 - (1 - m_f) * prod_{g in W_prev} (1 - w(g, f))
            m_f = inject_matches.get(cand.id, 0.0)
            prod_term = 1.0 - m_f
            for g_id in w_prev:
                if g_id in node_map and g_id != cand.id:
                    w_gf = max(0.0, min(0.99, node_map[g_id].links.excitatory.get(cand.id, 0.0)))
                    prod_term *= 1.0 - w_gf
            conn = max(0.12, 1.0 - prod_term)
            connections[cand.id] = round(conn, 4)

            trust_factor = (
                cand.provenance.trust
                if engine_mode in (EngineMode.ACA, EngineMode.HYBRID)
                else 1.0
            )
            w_f = max(1e-4, cand.dynamics.activation * nov * conn * trust_factor)
            composite_weights[cand.id] = round(w_f, 4)
            # Temperature scaling w_f^(1/tau) with safe clamping
            exp_power = max(0.25, min(6.0, 1.0 / max(0.15, tau)))
            scaled_weights[cand.id] = w_f ** exp_power

        # Divide token budget B across candidates in proportion to w_f^(1/tau) with surplus redistribution
        shares: Dict[str, float] = {c.id: 0.0 for c in candidate_nodes}
        full_costs: Dict[str, int] = {
            c.id: max(18, self._estimate_tokens(c.resolutions.full)) for c in candidate_nodes
        }
        sum_costs: Dict[str, int] = {
            c.id: max(10, int(full_costs[c.id] * 0.52)) for c in candidate_nodes
        }
        ptr_costs: Dict[str, int] = {
            c.id: max(4, min(8, self._estimate_tokens(c.resolutions.pointer))) for c in candidate_nodes
        }

        total_scaled = sum(scaled_weights.values())
        if total_scaled > 0:
            surplus = 0.0
            uncapped_weight = 0.0
            for cid in scaled_weights:
                raw_share = float(token_budget) * (scaled_weights[cid] / total_scaled)
                cap_cost = float(full_costs[cid]) * 1.50
                if raw_share > cap_cost:
                    shares[cid] = cap_cost
                    surplus += (raw_share - cap_cost) * 0.35
                else:
                    shares[cid] = raw_share
                    uncapped_weight += scaled_weights[cid]
            if surplus > 0 and uncapped_weight > 0:
                for cid in scaled_weights:
                    if shares[cid] < float(full_costs[cid]) * 1.50:
                        shares[cid] += surplus * (scaled_weights[cid] / uncapped_weight)

        # Assign resolution with Hysteresis
        # Upward transition requires clearing cost * 1.12; staying at prior resolution requires cost * 0.72
        up_margin = 1.12
        down_margin = 0.72

        new_resident_set: Set[str] = set()
        trace_list: List[TraceBreakdown] = []

        for cand in candidate_nodes:
            cid = cand.id
            share = shares.get(cid, 0.0)
            prev_res = cand.dynamics.current_resolution
            was_resident = cid in w_prev
            hysteresis_used = False

            c_full = full_costs[cid]
            c_sum = sum_costs[cid]
            c_ptr = ptr_costs[cid]

            if cand.dynamics.pinned:
                assigned = ResolutionLevel.FULL
            elif was_resident and prev_res == ResolutionLevel.FULL and share >= c_full * down_margin:
                assigned = ResolutionLevel.FULL
                hysteresis_used = share < c_full * up_margin
            elif share >= c_full * up_margin:
                assigned = ResolutionLevel.FULL
            elif was_resident and prev_res == ResolutionLevel.SUMMARY and share >= c_sum * down_margin:
                assigned = ResolutionLevel.SUMMARY
                hysteresis_used = share < c_sum * up_margin
            elif share >= c_sum * up_margin:
                assigned = ResolutionLevel.SUMMARY
            elif was_resident and prev_res in (ResolutionLevel.FULL, ResolutionLevel.SUMMARY) and share >= c_ptr * down_margin:
                # Even if budget compressed heavily, keep resident constraint alive at summary/pointer
                assigned = ResolutionLevel.SUMMARY if share >= c_sum * 0.60 else ResolutionLevel.POINTER
                hysteresis_used = True
            elif share >= c_ptr * 0.85:
                assigned = ResolutionLevel.POINTER
            else:
                assigned = ResolutionLevel.LATENT

            cand.dynamics.current_resolution = assigned
            cand.dynamics.is_resident = assigned != ResolutionLevel.LATENT
            if cand.dynamics.is_resident:
                new_resident_set.add(cid)

            trace_list.append(
                TraceBreakdown(
                    fragment_id=cid,
                    inject_match_m_f=inject_matches.get(cid, 0.0),
                    prior_activation=round(prior_activations.get(cid, 0.0), 4),
                    spread_contribution=round(spread_contributions.get(cid, 0.0), 4),
                    inhibitory_suppression=round(inhibitory_suppressions.get(cid, 0.0), 4),
                    post_fire_activation=cand.dynamics.activation,
                    fired=(cid in firing_set),
                    novelty=novelties.get(cid, 1.0),
                    noisy_or_connection=connections.get(cid, 0.0),
                    trust=cand.provenance.trust,
                    composite_weight_w_f=composite_weights.get(cid, 0.0),
                    token_share=round(share, 2),
                    assigned_resolution=assigned,
                    hysteresis_applied=hysteresis_used,
                )
            )

        # Clear residency on non-candidate nodes
        candidate_id_set = {c.id for c in candidate_nodes}
        for n in nodes:
            if n.id not in candidate_id_set:
                n.dynamics.is_resident = False
                n.dynamics.current_resolution = ResolutionLevel.LATENT

        # =====================================================================
        # STAGE 4: COMPOSE (Canonicalized Atomic Narrative — Ephemeral CANPacket)
        # =====================================================================
        pinned_core: List[str] = [
            "Never overwrite raw log assertions with reconstructed CAN prose."
        ]
        full_blocks: List[str] = []
        summary_list: List[str] = []
        pointer_list: List[str] = []
        pinned_texts: Set[str] = set()
        used_tokens = self._estimate_tokens(pinned_core[0])

        for cand in candidate_nodes:
            res = cand.dynamics.current_resolution
            tag = f"[{cand.node_type.value}:{cand.id}|trust={cand.provenance.trust:.2f}]"
            if cand.dynamics.pinned or cand.node_type == NodeType.CONSTRAINT:
                if cand.resolutions.full not in pinned_texts:
                    pinned_texts.add(cand.resolutions.full)
                    pinned_core.append(f"{tag} {cand.resolutions.full}")
                    used_tokens += full_costs[cand.id]
            elif res == ResolutionLevel.FULL:
                full_blocks.append(f"{tag} {cand.resolutions.full}")
                used_tokens += full_costs[cand.id]
            elif res == ResolutionLevel.SUMMARY:
                summary_list.append(f"{tag} {cand.resolutions.summary}")
                used_tokens += sum_costs[cand.id]
            elif res == ResolutionLevel.POINTER:
                pointer_list.append(cand.resolutions.pointer)
                used_tokens += ptr_costs[cand.id]

        full_narrative = (
            " ".join(full_blocks)
            if full_blocks
            else "No non-pinned fragments required full-resolution narrative expansion on this turn."
        )

        admitted_nodes = [c for c in candidate_nodes if c.dynamics.is_resident]
        contradictions = (
            self.aca.collect_active_contradictions(admitted_nodes)
            if engine_mode in (EngineMode.ACA, EngineMode.HYBRID)
            else []
        )

        jev_decisions = (
            self.aca.evaluate_jev_neurons(
                raw_input=raw_input or compressed_input,
                active_nodes=admitted_nodes,
                weights=composite_weights,
                contradictions=contradictions,
                modulation=mod,
            )
            if engine_mode in (EngineMode.ACA, EngineMode.HYBRID)
            else []
        )

        agreement, pivotal_nodes = self.aca.sample_fields_for_agreement(
            nodes=candidate_nodes,
            shares=shares,
            session_id=session_id,
            turn_id=turn_id,
            num_samples=sample_fields_count,
        )

        if apply_refractory_and_decay:
            self.prior_fired_sets[session_id] = set(firing_set)
            self.resident_sets[session_id] = set(new_resident_set)
            self.storage.bulk_save_nodes(nodes, **self.persist_extras(session_id))

        can_packet = CANPacket(
            can_id=f"can_turn_{turn_id}",
            session_id=session_id,
            turn_id=turn_id,
            engine_mode=engine_mode,
            budget=BudgetState(
                total_tokens=token_budget,
                used_tokens=min(token_budget, used_tokens),
                temperature_tau=round(tau, 3),
            ),
            modulation=mod.model_copy(deep=True),
            global_context=gc.get_state(),
            can_state=CANState(
                pinned_core=pinned_core,
                full_narrative=full_narrative,
                summary_fragments=summary_list,
                ambient_pointers=pointer_list,
                contradictions=contradictions,
            ),
            jev_decisions=jev_decisions,
            trace=trace_list,
            sampled_field_agreement=agreement,
            pivotal_nodes=pivotal_nodes,
        )
        self.last_can_packets[session_id] = can_packet
        self._emit_event("firing_pass_completed", session_id, can_packet.model_dump())
        return can_packet

    # -------------------------------------------------------------------------
    # Recurrent Settling ("Think Until It Settles" — POST /v1/settle)
    # -------------------------------------------------------------------------
    def settle_recurrent(
        self,
        session_id: str,
        intermediate_reasoning: str,
        self_cue_gain: float = 0.35,
        max_passes: int = 5,
        stability_jaccard_threshold: float = 1.0,
        token_budget: int = 2048,
        scope: str = "repo:ACA-systems-prodo",
        engine_mode: EngineMode = EngineMode.HYBRID,
    ) -> SettleResponse:
        """Feed intermediate reasoning back into INJECT with reduced self-cue gain
        until the lit set of firing/admitted fragments stabilizes or a cycle is detected.
        """
        gc = self.get_gc(session_id)
        compressed_cue = gc.compress(intermediate_reasoning)
        turn_id = self.storage.get_current_turn_id(session_id)

        history: List[List[str]] = []
        seen_sets: List[Set[str]] = []
        converged = False
        cycle_detected = False
        last_packet: Optional[CANPacket] = None

        for p in range(1, max_passes + 1):
            # Attenuate self-cue gain across recurrent sub-passes so later passes perturb less
            effective_gain = self_cue_gain * (0.82 ** (p - 1))
            packet = self.run_firing_pass(
                session_id=session_id,
                turn_id=turn_id,
                compressed_input=compressed_cue,
                raw_input=intermediate_reasoning,
                scope=scope,
                engine_mode=engine_mode,
                input_gain=effective_gain,
                apply_refractory_and_decay=False,
                token_budget=token_budget,
            )
            last_packet = packet
            current_lit = {
                t.fragment_id
                for t in packet.trace
                if t.fired or t.assigned_resolution in (ResolutionLevel.FULL, ResolutionLevel.SUMMARY)
            }
            sorted_lit = sorted(list(current_lit))
            history.append(sorted_lit)

            if seen_sets:
                prev_set = seen_sets[-1]
                union = current_lit.union(prev_set)
                inter = current_lit.intersection(prev_set)
                jaccard = (len(inter) / len(union)) if union else 1.0
                if jaccard >= stability_jaccard_threshold:
                    converged = True
                    break
                if current_lit in seen_sets[:-1]:
                    cycle_detected = True
                    break
            seen_sets.append(current_lit)

        # Persist settled activation state
        self.storage.bulk_save_nodes(**self.persist_extras(session_id))
        assert last_packet is not None
        return SettleResponse(
            session_id=session_id,
            passes_executed=len(history),
            converged=converged,
            cycle_detected=cycle_detected,
            firing_set_history=history,
            final_can_packet=last_packet,
        )

    # -------------------------------------------------------------------------
    # GAP 2 & 3 RESOLUTION: Directed Normalized POTENTIATE + Hybrid Write Gate
    # -------------------------------------------------------------------------
    def process_outcome(self, req: OutcomeRequest, *, unmask: bool = True) -> OutcomeResponse:
        """Process tool/model outcome:
        1. Compute Surprise & Progress Delta against expectation.
        2. Modulate theta_in, lambda_spread, eta_hebbian.
        3. Apply Directed & Row-Normalized Co-Firing Potentiation (POTENTIATE) + Link Decay.
        4. Trigger Hybrid Write Gate (Surprise OR Explicit High-Trust User Constraint / Decision).
        5. Hydrate GC pointers in model output.
        """
        session_id = req.session_id
        turn_id = self.storage.next_turn_id(session_id, req.turn_id)
        gc = self.get_gc(session_id)
        mod = self.get_modulation(session_id)

        compressed_out = gc.compress(req.raw_output) if req.raw_output else ""
        compressed_fact = gc.compress(req.explicit_fact_or_lesson) if req.explicit_fact_or_lesson else ""
        log_entry = self.storage.append_raw_log(
            session_id=session_id,
            turn_id=turn_id,
            caller=req.caller,
            event_type="outcome",
            raw_payload=req.raw_output or req.explicit_fact_or_lesson or req.command_or_action,
            gc_compressed_payload=compressed_out,
            external_signals={
                "exit_code": req.exit_code,
                "test_status": req.test_status,
                "is_user_constraint": req.is_user_constraint,
            },
        )

        # 1. Compute Surprise in [0, 1] and Progress Delta in [-1, 1]
        # A stored prediction answers exactly one outcome; consume it so it cannot go stale
        stored_prediction = self.get_prediction(session_id)
        self.predictions[session_id] = ""
        expected = (req.expected_prediction or stored_prediction).lower()
        actual_lower = (req.raw_output or "").lower()

        surprise = 0.08
        progress_delta = 0.25

        if req.exit_code != 0 or req.test_status in ("failed", "error"):
            if "fail" in expected or "error" in expected:
                # Expected failure confirmed
                surprise = 0.22
                progress_delta = 0.10
            else:
                # Unexpected failure / prediction violation!
                surprise = 0.86
                progress_delta = -0.65
        elif req.test_status == "passed" and req.exit_code == 0:
            if "fail" in expected:
                surprise = 0.64
                progress_delta = 0.90
            else:
                surprise = 0.10
                progress_delta = 1.00

        if expected and actual_lower:
            exp_tokens = set(self._tokenize(expected))
            act_tokens = set(self._tokenize(actual_lower))
            if exp_tokens:
                mismatch = 1.0 - (len(exp_tokens.intersection(act_tokens)) / len(exp_tokens))
                surprise = max(surprise, round(0.75 * mismatch, 4))

        # Check for surprising environmental cues in raw output
        if self.ENV_SURPRISE_CUE_RE.search(actual_lower) and surprise < 0.72:
            surprise = max(surprise, 0.76)

        mod.surprise = round(surprise, 4)
        mod.progress_delta = round(progress_delta, 4)

        # 2. Modulate firing parameters based on Surprise & Progress
        if surprise >= 0.55:
            # High surprise: lower entry threshold slightly, widen spreading, increase learning rate
            mod.theta_in = round(max(0.42, 0.55 - 0.12 * surprise), 4)
            mod.lambda_spread = round(min(0.60, 0.40 + 0.15 * surprise), 4)
            mod.eta_hebbian = round(min(0.22, 0.10 + 0.10 * surprise), 4)
        else:
            # Routine confirmation: settle back toward crisp focus
            mod.theta_in = 0.55
            mod.lambda_spread = 0.40
            mod.eta_hebbian = 0.10

        # 3. Directed & Normalized Co-Firing Potentiation (Gap #2 Resolution)
        nodes = self.storage.list_nodes(scope=req.scope, include_superseded=False)
        node_map = {n.id: n for n in nodes}
        causal_sources = self.resident_sets.get(session_id, set()).union(
            self.prior_fired_sets.get(session_id, set())
        )

        # First apply multiplicative link decay across all outgoing links
        for n in nodes:
            for dst_id in list(n.links.excitatory.keys()):
                decayed_w = round(n.links.excitatory[dst_id] * mod.delta_w, 4)
                if decayed_w < 0.02:
                    del n.links.excitatory[dst_id]
                else:
                    n.links.excitatory[dst_id] = decayed_w
            # If routine confirmation, strengthen confidence/verification timestamp on active resident nodes
            if surprise < 0.35 and n.id in causal_sources:
                n.provenance.last_verified_turn = turn_id
                n.provenance.trust = round(min(0.99, n.provenance.trust + 0.01), 4)

        # Hybrid Write Gate Evaluation (Gap #3 + Phase 2 Declarative Fact Upgrade)
        raw_candidate_text = (req.explicit_fact_or_lesson or req.raw_output).strip()
        is_decl_fact, decl_category, _ = self.aca.classify_declarative_constraint(raw_candidate_text)
        is_constraint_text = req.is_user_constraint or is_decl_fact

        write_triggered = False
        write_reason: Optional[str] = None
        created_node: Optional[MemoryNode] = None

        if raw_candidate_text and (
            is_constraint_text
            or surprise >= 0.50
            or req.explicit_fact_or_lesson is not None
        ):
            write_triggered = True
            if req.is_user_constraint or "imperative_rule" in decl_category:
                write_reason = "explicit_high_trust_user_constraint"
                src_type = SourceTrustType.USER_CONSTRAINT
                node_type = NodeType.CONSTRAINT
                should_pin = True
            elif is_decl_fact and surprise < 0.50:
                write_reason = f"declarative_architectural_fact ({decl_category})"
                src_type = SourceTrustType.VERIFIED_DECISION
                node_type = NodeType.CONSTRAINT if "runtime_os_constraint" in decl_category else NodeType.DECISION
                should_pin = "runtime_os_constraint" in decl_category
            elif surprise >= 0.50:
                write_reason = f"surprise_gated_prediction_error (surprise={surprise:.2f})"
                src_type = req.source_type
                node_type = NodeType.ERROR if req.exit_code != 0 else NodeType.FRAGMENT
                should_pin = False
            else:
                write_reason = "verified_operational_fact"
                src_type = SourceTrustType.VERIFIED_DECISION
                node_type = NodeType.DECISION
                should_pin = False

            created_node = self.encode_or_refine_fragment(
                session_id=session_id,
                turn_id=turn_id,
                raw_text=raw_candidate_text,
                source_event_id=log_entry.event_id,
                source_type=src_type,
                node_type=node_type,
                pinned=should_pin,
                scope=req.scope,
                initial_activation=0.88 if is_constraint_text else min(0.95, 0.65 + 0.30 * surprise),
                persist_immediately=False,
                compressed_text=(compressed_fact if req.explicit_fact_or_lesson else compressed_out).strip(),
            )
            node_map[created_node.id] = created_node
            if all(n.id != created_node.id for n in nodes):
                nodes.append(created_node)

        # Directed causal potentiation: causal_sources (t-1) -> newly created or currently active targets (t)
        potentiated_links: Dict[str, float] = {}
        targets = set(causal_sources)
        if created_node is not None:
            targets.add(created_node.id)

        # Order causal sources by last_fired_turn / activation to preserve temporal/causal asymmetry
        ordered_sources = [node_map[sid] for sid in causal_sources if sid in node_map]
        ordered_sources.sort(key=lambda x: (x.dynamics.last_fired_turn, x.dynamics.activation))

        for i, src_node in enumerate(ordered_sources):
            out_degree = len(src_node.links.excitatory)
            hub_penalty = 1.0 + 0.30 * out_degree
            for dst_id in targets:
                if dst_id == src_node.id or dst_id not in node_map:
                    continue
                dst_node = node_map[dst_id]
                # Asymmetric directional condition:
                # Potentiate src -> dst only if dst is newly created OR dst fired after/stronger than src
                is_causal_pair = (
                    (created_node is not None and dst_id == created_node.id)
                    or (dst_node.dynamics.last_fired_turn > src_node.dynamics.last_fired_turn)
                    or (
                        dst_node.dynamics.last_fired_turn == src_node.dynamics.last_fired_turn
                        and dst_node.id > src_node.id
                    )
                )
                if not is_causal_pair:
                    continue

                delta_w = (mod.eta_hebbian * src_node.dynamics.activation * dst_node.dynamics.activation) / hub_penalty
                old_w = src_node.links.excitatory.get(dst_id, 0.0)
                new_w = min(0.95, old_w + delta_w)
                src_node.links.excitatory[dst_id] = round(new_w, 4)
                potentiated_links[f"{src_node.id}->{dst_id}"] = round(new_w, 4)

            # Row-wise soft-cap L1 normalization so no node becomes a runaway hub
            row_sum = sum(src_node.links.excitatory.values())
            max_row_budget = 2.40
            if row_sum > max_row_budget:
                scale = max_row_budget / row_sum
                for dst_id in src_node.links.excitatory:
                    src_node.links.excitatory[dst_id] = round(
                        src_node.links.excitatory[dst_id] * scale, 4
                    )

        self.storage.upsert_nodes_batch(nodes, sync_mmap=True, **self.persist_extras(session_id))

        # Run a fresh pass so the returned CANPacket reflects the post-outcome state
        can_packet = self.run_firing_pass(
            session_id=session_id,
            turn_id=turn_id,
            compressed_input=compressed_out or compressed_fact or gc.compress(req.command_or_action),
            raw_input=req.raw_output or req.explicit_fact_or_lesson or req.command_or_action,
            scope=req.scope,
            apply_refractory_and_decay=False,
        )

        hydrated_output = gc.expand(req.model_output_to_expand, unmask=unmask)

        return OutcomeResponse(
            session_id=session_id,
            turn_id=turn_id,
            surprise=mod.surprise,
            progress_delta=mod.progress_delta,
            write_gate_triggered=write_triggered,
            write_reason=write_reason,
            created_or_updated_fragment=created_node,
            potentiated_links=potentiated_links,
            modulation=mod,
            hydrated_model_output=hydrated_output,
            can_packet=can_packet,
        )

    # -------------------------------------------------------------------------
    # Fragment Encoding, Deduplication & Contradiction Wiring
    # -------------------------------------------------------------------------
    def encode_or_refine_fragment(
        self,
        session_id: str,
        turn_id: int,
        raw_text: str,
        source_event_id: str,
        source_type: SourceTrustType = SourceTrustType.PREVIOUS_AGENT_FINDING,
        node_type: NodeType = NodeType.FRAGMENT,
        pinned: bool = False,
        scope: str = "repo:ACA-systems-prodo",
        initial_activation: float = 0.82,
        persist_immediately: bool = True,
        compressed_text: Optional[str] = None,
    ) -> MemoryNode:
        """Create a canonical Fragment / ACA Node with a full Provenance Envelope (Gap #4 Resolution),
        merging near-duplicates or wiring contradiction inhibition links automatically.
        Pass `compressed_text` when the caller already GC-compressed `raw_text`.
        """
        gc = self.get_gc(session_id)
        compressed_full = (
            compressed_text if compressed_text is not None else gc.compress(raw_text, tally=False)
        )
        existing_nodes = self.storage.list_nodes(scope=scope, include_superseded=False)

        # Check if a near-duplicate already exists in the same scope. Jaccard (not containment) so a
        # short fact is not absorbed into a longer, different one, and never merge statements that
        # contradict each other (e.g. "port 5432" vs "port 5433") — those must be wired as conflicts.
        cand_tris = self._char_trigrams(compressed_full)
        for existing in existing_nodes:
            ex_tris = self._char_trigrams(existing.resolutions.full)
            if cand_tris and ex_tris:
                overlap = len(cand_tris.intersection(ex_tris)) / len(cand_tris.union(ex_tris))
                if overlap >= 0.82 and not self.aca.texts_conflict(
                    compressed_full, existing.resolutions.full
                )[0]:
                    if source_event_id not in existing.provenance.source_event_ids:
                        existing.provenance.source_event_ids.append(source_event_id)
                    existing.provenance.last_verified_turn = turn_id
                    existing.provenance.trust = round(
                        min(0.99, max(existing.provenance.trust, self.aca.calibrate_trust(source_type)) + 0.02),
                        4,
                    )
                    existing.dynamics.activation = round(
                        min(1.0, max(existing.dynamics.activation, initial_activation)), 4
                    )
                    if pinned:
                        existing.dynamics.pinned = True
                    if persist_immediately:
                        self.storage.upsert_node(existing)
                    return existing

        frag_id = f"frag_{uuid.uuid4().hex[:12]}"
        words = compressed_full.split()
        summary_text = " ".join(words[:18]) + ("..." if len(words) > 18 else "")
        label_words = [w for w in re.findall(r"[A-Za-z0-9_.\-<>]+", compressed_full) if len(w) > 2][:5]
        short_label = " ".join(label_words) if label_words else node_type.value
        pointer_text = f"[{frag_id.upper()}: {short_label}]"

        trust_val = self.aca.calibrate_trust(source_type)

        new_node = MemoryNode(
            id=frag_id,
            engine_mode=EngineMode.HYBRID,
            node_type=node_type,
            resolutions=FragmentResolutions(
                full=compressed_full,
                summary=summary_text,
                pointer=pointer_text,
            ),
            dynamics=FragmentDynamics(
                activation=round(initial_activation, 4),
                refractory_remaining=0,
                is_resident=True,
                current_resolution=ResolutionLevel.FULL,
                pinned=pinned,
                last_fired_turn=turn_id,
                fire_count=1,
            ),
            provenance=FragmentProvenance(
                source_event_ids=[source_event_id],
                source_type=source_type,
                trust=trust_val,
                scope=scope,
                superseded_by=None,
                created_at_turn=turn_id,
                last_verified_turn=turn_id,
            ),
            links=FragmentLinks(),
        )

        # Detect contradictions and wire mutual inhibitory links
        self.aca.detect_and_link_contradictions(new_node, existing_nodes)
        if persist_immediately:
            self.storage.upsert_node(new_node)
        else:
            self.storage.cache_node(new_node)
        self.resident_sets.setdefault(session_id, set()).add(new_node.id)
        return new_node
