"""ACA Engine: Provenance Trust Calibration, Contradiction Network, Multi-Field Sampling,
Declarative Architectural Fact Detection, and Parallel Jev Decision Neurons (`Noul`, `Choice`, `Score`).
"""

from __future__ import annotations

import hashlib
import random
import re
from typing import Dict, List, Optional, Set, Tuple

from src.schemas import (
    ContradictionPair,
    JevDecision,
    MemoryNode,
    ModulationState,
    NodeType,
    SourceTrustType,
    TRUST_CALIBRATION_WEIGHTS,
)


class ACAGraphEngine:
    """Implements the Associative Context Activation (ACA) Synapse Graph & Jev Decision Layer."""

    NEGATION_PAIRS = [
        ("enabled", "disabled"),
        ("require", "disable"),
        ("requires", "disabled"),
        ("always", "never"),
        ("must", "must not"),
        ("true", "false"),
        ("allow", "forbid"),
        ("sync", "async"),
    ]

    IMPERATIVE_CONSTRAINT_RE = re.compile(
        r"\b(?:never|always|must(?:\s+not)?|do\s+not|shall\s+not|prohibited|forbidden|constraint:|rule:|pinned:)\b",
        re.IGNORECASE,
    )
    PORT_BINDING_RE = re.compile(
        r"\b(?:port\s+\d{2,5}|listens?\s+on|bound\s+to\s+port|listening\s+on|:\d{4,5}\b)",
        re.IGNORECASE,
    )
    RUNTIME_OS_CONSTRAINT_RE = re.compile(
        r"\b(?:python\s+\d+\.\d+|node(?:\.js)?\s+\d+|compatible\s+with|compatibility|requires\s+python|windows\s+1[01]|linux\s+kernel|runtime\s+constraint)\b",
        re.IGNORECASE,
    )
    FILE_LAYOUT_RE = re.compile(
        r"\b(?:located\s+in|lives\s+in|directory\s+layout|module\s+layout|stored\s+in|entry\s+point\s+is|schema\s+defined\s+in)\b",
        re.IGNORECASE,
    )
    NEGATIVE_OUTCOME_RE = re.compile(
        r"\b(?:does\s+not\s+validate|not\s+covered\s+by|is\s+not\s+covered|unsupported|incompatible\s+with|fails\s+when|cannot\s+reach|connection\s+refused)\b",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        pass

    @classmethod
    def classify_declarative_constraint(cls, text: str) -> Tuple[bool, str, float]:
        """Detect imperative constraints AND declarative architectural facts
        (port bindings, OS/runtime constraints, file layout declarations, negative outcomes)
        even when they do not start with 'Never', 'Must', or 'Always'.
        """
        if not text or not text.strip():
            return False, "none", 0.0

        matches: List[str] = []
        base_score = 0.0

        if cls.IMPERATIVE_CONSTRAINT_RE.search(text):
            matches.append("imperative_rule")
            base_score = max(base_score, 0.94)
        if cls.PORT_BINDING_RE.search(text):
            matches.append("port_binding")
            base_score = max(base_score, 0.88)
        if cls.RUNTIME_OS_CONSTRAINT_RE.search(text):
            matches.append("runtime_os_constraint")
            base_score = max(base_score, 0.90)
        if cls.FILE_LAYOUT_RE.search(text):
            matches.append("file_layout_declaration")
            base_score = max(base_score, 0.85)
        if cls.NEGATIVE_OUTCOME_RE.search(text):
            matches.append("negative_operational_invariant")
            base_score = max(base_score, 0.89)

        if not matches:
            return False, "none", 0.0

        # Multiple reinforcing signals boost score toward 0.98
        final_score = min(0.98, base_score + 0.03 * (len(matches) - 1))
        return True, "+".join(matches), round(final_score, 3)

    @staticmethod
    def calibrate_trust(source_type: SourceTrustType, explicit_trust: Optional[float] = None) -> float:
        base = TRUST_CALIBRATION_WEIGHTS.get(source_type, 0.78)
        if explicit_trust is not None:
            return max(0.05, min(1.0, 0.5 * base + 0.5 * explicit_trust))
        return base

    @staticmethod
    def _polarity(text: str, pos: str, neg: str) -> Optional[str]:
        """Which side of a negation pair a text asserts. The negative form is checked first
        because it can contain the positive one ("must not" contains "must")."""
        if re.search(rf"\b{re.escape(neg)}\b", text):
            return "neg"
        if re.search(rf"\b{re.escape(pos)}\b", text):
            return "pos"
        return None

    @classmethod
    def texts_conflict(cls, text_a: str, text_b: str) -> Tuple[bool, Set[str]]:
        """Return whether two statements make opposing polarity or numeric claims about
        shared terms, plus the shared terms."""
        a = text_a.lower()
        b = text_b.lower()
        shared = set(re.findall(r"[a-z0-9_]{3,}", a)).intersection(re.findall(r"[a-z0-9_]{3,}", b))
        if len(shared) < 2:
            return False, shared

        for pos, neg in cls.NEGATION_PAIRS:
            pol_a = cls._polarity(a, pos, neg)
            pol_b = cls._polarity(b, pos, neg)
            if pol_a and pol_b and pol_a != pol_b:
                return True, shared

        if "port" in shared or "version" in shared or "python" in shared:
            a_nums = set(re.findall(r"\b\d+(?:\.\d+)?\b", a))
            b_nums = set(re.findall(r"\b\d+(?:\.\d+)?\b", b))
            if a_nums and b_nums and a_nums.isdisjoint(b_nums) and len(shared) >= 3:
                return True, shared

        return False, shared

    def detect_and_link_contradictions(
        self, candidate_node: MemoryNode, existing_nodes: List[MemoryNode]
    ) -> List[ContradictionPair]:
        """Detect semantic or numeric/polarity contradictions between a candidate node
        and existing active nodes, wiring bidirectional inhibitory links.
        """
        contradictions: List[ContradictionPair] = []

        for other in existing_nodes:
            if other.id == candidate_node.id or other.provenance.superseded_by is not None:
                continue
            is_conflict, shared = self.texts_conflict(
                candidate_node.resolutions.full, other.resolutions.full
            )

            if is_conflict:
                candidate_node.links.inhibitory[other.id] = -0.75
                other.links.inhibitory[candidate_node.id] = -0.75
                candidate_node.links.relation_types[other.id] = "contradicts"
                other.links.relation_types[candidate_node.id] = "contradicts"

                contradictions.append(
                    ContradictionPair(
                        node_a_id=candidate_node.id,
                        node_b_id=other.id,
                        node_a_claim=candidate_node.resolutions.summary,
                        node_b_claim=other.resolutions.summary,
                        severity=0.88,
                        resolution_hint=(
                            f"Conflict on shared terms {sorted(list(shared))[:4]}: "
                            f"trust({candidate_node.id})={candidate_node.provenance.trust:.2f} vs "
                            f"trust({other.id})={other.provenance.trust:.2f}"
                        ),
                    )
                )
        return contradictions

    def collect_active_contradictions(self, active_nodes: List[MemoryNode]) -> List[ContradictionPair]:
        """Surface unresolved contradictions where at least one side is active in the field."""
        active_map = {n.id: n for n in active_nodes}
        seen_pairs: Set[Tuple[str, str]] = set()
        results: List[ContradictionPair] = []

        for node in active_nodes:
            for target_id, weight in node.links.inhibitory.items():
                if weight < -0.2 and target_id in active_map:
                    pair_key = tuple(sorted((node.id, target_id)))  # type: ignore[assignment]
                    if pair_key in seen_pairs:
                        continue
                    seen_pairs.add(pair_key)
                    other = active_map[target_id]
                    results.append(
                        ContradictionPair(
                            node_a_id=node.id,
                            node_b_id=other.id,
                            node_a_claim=node.resolutions.summary,
                            node_b_claim=other.resolutions.summary,
                            severity=min(1.0, abs(weight)),
                            resolution_hint=(
                                f"Both {node.id} (trust={node.provenance.trust:.2f}) and "
                                f"{other.id} (trust={other.provenance.trust:.2f}) are active; verify via tool."
                            ),
                        )
                    )
        return results

    def evaluate_jev_neurons(
        self,
        raw_input: str,
        active_nodes: List[MemoryNode],
        weights: Dict[str, float],
        contradictions: List[ContradictionPair],
        modulation: ModulationState,
    ) -> List[JevDecision]:
        """Fire parallel Jev Decision Neurons (`Noul`, `Choice`, `Score`) across the converged Working Brain."""
        max_w = max(weights.values(), default=0.0)
        mean_w = sum(weights.values()) / max(len(weights), 1)

        is_decl_fact, decl_category, decl_score = self.classify_declarative_constraint(raw_input)
        has_error_cue = any(
            kw in raw_input.lower()
            for kw in ("error", "fail", "exception", "traceback", "broken", "bug", "timeout", "crash")
        )

        # 1. Memory Gate Neuron (Choice + Score) — upgraded to admit declarative architectural facts
        mem_score = min(
            0.99,
            max(
                decl_score,
                0.15,
                0.45 * modulation.surprise
                + (0.45 if is_decl_fact else 0.15)
                + (0.25 if has_error_cue else 0.05)
                + 0.15 * (1.0 - min(1.0, max_w)),
            ),
        )
        if mem_score >= 0.65 or is_decl_fact:
            mem_choice = "STORE"
        elif mem_score >= 0.40:
            mem_choice = "TEMPORARY"
        else:
            mem_choice = "DISCARD"

        decisions: List[JevDecision] = [
            JevDecision(
                noul="memory_gate",
                question=(
                    "Should this observation, constraint, or declarative architectural fact be encoded into persistent memory?"
                    + (f" [detected: {decl_category}]" if is_decl_fact else "")
                ),
                choice=mem_choice,
                score=round(mem_score, 3),
                probabilities={
                    "STORE": round(mem_score, 3),
                    "TEMPORARY": round(max(0.0, 1.0 - mem_score) * 0.6, 3),
                    "DISCARD": round(max(0.0, 1.0 - mem_score) * 0.4, 3),
                },
                crossed_threshold=(mem_choice == "STORE"),
                triggered_action=f"encode_{decl_category}" if is_decl_fact else ("encode_fragment" if mem_choice == "STORE" else None),
            )
        ]

        # 2. Contradiction Verification Neuron (Noul)
        conflict_score = min(0.99, 0.85 if contradictions else 0.12 + 0.25 * modulation.surprise)
        decisions.append(
            JevDecision(
                noul="contradiction_verify",
                question="Is there conflicting evidence in the active field requiring verification?",
                choice="VERIFY" if conflict_score >= 0.60 else "CONSISTENT",
                score=round(conflict_score, 3),
                probabilities={"yes": round(conflict_score, 3), "no": round(1.0 - conflict_score, 3)},
                crossed_threshold=(conflict_score >= 0.60),
                triggered_action="wake_critic_verifier" if conflict_score >= 0.60 else None,
            )
        )

        # 3. Context Expansion Neuron (Noul)
        uncertainty = 1.0 - min(1.0, max_w - mean_w + 0.3)
        expand_score = min(0.98, max(0.10, 0.5 * uncertainty + 0.4 * modulation.surprise))
        decisions.append(
            JevDecision(
                noul="context_expansion",
                question="Should ambient pointers be expanded on the next pass due to high uncertainty?",
                choice="EXPAND" if expand_score >= 0.68 else "CONVERGED",
                score=round(expand_score, 3),
                probabilities={"yes": round(expand_score, 3), "no": round(1.0 - expand_score, 3)},
                crossed_threshold=(expand_score >= 0.68),
                triggered_action="raise_temperature_tau" if expand_score >= 0.68 else None,
            )
        )

        # 4. Event-Driven Agent Swarm Router (Choice)
        if has_error_cue or modulation.surprise >= 0.45:
            agent_choice = "DEBUG_AGENT"
            agent_score = round(min(0.96, 0.72 + 0.25 * modulation.surprise), 3)
        elif is_decl_fact:
            agent_choice = "CRITIC_AGENT"
            agent_score = max(0.84, decl_score)
        elif active_nodes:
            agent_choice = "CODE_AGENT"
            agent_score = round(min(0.94, 0.65 + 0.3 * max_w), 3)
        else:
            agent_choice = "RESEARCH_AGENT"
            agent_score = 0.71

        decisions.append(
            JevDecision(
                noul="agent_swarm_router",
                question="Which specialized capability should wake up for the active field?",
                choice=agent_choice,
                score=agent_score,
                probabilities={
                    agent_choice: agent_score,
                    "STANDBY": round(1.0 - agent_score, 3),
                },
                crossed_threshold=(agent_score >= 0.70),
                triggered_action=f"wake_{agent_choice.lower()}",
            )
        )

        return decisions

    def sample_fields_for_agreement(
        self,
        nodes: List[MemoryNode],
        shares: Dict[str, float],
        session_id: str,
        turn_id: int,
        num_samples: int = 3,
    ) -> Tuple[float, List[str]]:
        """ACA Section 3: Decisions Across Sampled Fields."""
        if num_samples <= 1 or len(nodes) <= 1:
            return 1.0, []

        pinned_ids = {n.id for n in nodes if n.dynamics.pinned or n.node_type == NodeType.CONSTRAINT}
        periphery = [n for n in nodes if n.id not in pinned_ids and shares.get(n.id, 0.0) > 0]
        if not periphery:
            return 1.0, []

        max_share = max((shares.get(n.id, 0.0) for n in periphery), default=1.0) or 1.0
        sampled_sets: List[Set[str]] = []

        for k in range(num_samples):
            seed_str = f"{session_id}:{turn_id}:sample:{k}"
            seed_int = int(hashlib.sha256(seed_str.encode("utf-8")).hexdigest()[:8], 16)
            rng = random.Random(seed_int)
            draw: Set[str] = set(pinned_ids)
            for n in periphery:
                prob = min(0.98, max(0.15, (shares.get(n.id, 0.0) / max_share) ** 0.65))
                if rng.random() <= prob:
                    draw.add(n.id)
            sampled_sets.append(draw)

        jaccards: List[float] = []
        for i in range(len(sampled_sets)):
            for j in range(i + 1, len(sampled_sets)):
                union = sampled_sets[i].union(sampled_sets[j])
                inter = sampled_sets[i].intersection(sampled_sets[j])
                jaccards.append(len(inter) / len(union) if union else 1.0)

        agreement = sum(jaccards) / len(jaccards) if jaccards else 1.0
        all_union = set().union(*sampled_sets)
        all_inter = sampled_sets[0].intersection(*sampled_sets[1:])
        pivotal = sorted(list(all_union - all_inter))
        return round(agreement, 4), pivotal
