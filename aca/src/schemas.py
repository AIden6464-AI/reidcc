"""Core data schemas for the 4-tier CAN + GC layout, The Firing System, and ACA."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class EngineMode(str, Enum):
    FIRING = "firing"
    ACA = "aca"
    HYBRID = "hybrid"


class NodeType(str, Enum):
    FRAGMENT = "fragment"
    DECISION = "decision"
    FILE = "file"
    COMMIT = "commit"
    ERROR = "error"
    HYPOTHESIS = "hypothesis"
    CONSTRAINT = "constraint"
    EPISODE = "episode"
    PROCEDURE = "procedure"


class SourceTrustType(str, Enum):
    LIVE_TEST_OUTPUT = "live_test_output"          # 0.99
    DIRECT_CODE_OBSERVATION = "direct_code"        # 0.98
    USER_CONSTRAINT = "user_constraint"            # 0.98
    OFFICIAL_DOCUMENTATION = "official_docs"       # 0.94
    VERIFIED_DECISION = "verified_decision"        # 0.92
    PREVIOUS_AGENT_FINDING = "agent_finding"       # 0.78
    HISTORICAL_SUMMARY = "historical_summary"      # 0.62
    UNVERIFIED_HYPOTHESIS = "unverified_hypothesis" # 0.31


TRUST_CALIBRATION_WEIGHTS: Dict[SourceTrustType, float] = {
    SourceTrustType.LIVE_TEST_OUTPUT: 0.99,
    SourceTrustType.DIRECT_CODE_OBSERVATION: 0.98,
    SourceTrustType.USER_CONSTRAINT: 0.98,
    SourceTrustType.OFFICIAL_DOCUMENTATION: 0.94,
    SourceTrustType.VERIFIED_DECISION: 0.92,
    SourceTrustType.PREVIOUS_AGENT_FINDING: 0.78,
    SourceTrustType.HISTORICAL_SUMMARY: 0.62,
    SourceTrustType.UNVERIFIED_HYPOTHESIS: 0.31,
}


class ResolutionLevel(str, Enum):
    FULL = "full"
    SUMMARY = "summary"
    POINTER = "pointer"
    LATENT = "latent"


class FragmentResolutions(BaseModel):
    full: str = Field(..., description="GC-compressed prose statement of settled truth")
    summary: str = Field(..., description="1-sentence compressed summary")
    pointer: str = Field(..., description="Short semantic pointer, e.g. [FRAG_0192a: label]")


class FragmentDynamics(BaseModel):
    activation: float = Field(default=0.5, ge=0.0, le=1.0)
    refractory_remaining: int = Field(default=0, ge=0)
    is_resident: bool = Field(default=False)
    current_resolution: ResolutionLevel = Field(default=ResolutionLevel.LATENT)
    pinned: bool = Field(default=False)
    last_fired_turn: int = Field(default=-1)
    fire_count: int = Field(default=0)


class FragmentProvenance(BaseModel):
    source_event_ids: List[str] = Field(default_factory=list)
    source_type: SourceTrustType = Field(default=SourceTrustType.PREVIOUS_AGENT_FINDING)
    trust: float = Field(default=0.78, ge=0.0, le=1.0)
    scope: str = Field(default="repo:ACA-systems-prodo")
    superseded_by: Optional[str] = Field(default=None)
    created_at_turn: int = Field(default=0)
    last_verified_turn: int = Field(default=0)


class FragmentLinks(BaseModel):
    excitatory: Dict[str, float] = Field(default_factory=dict)
    inhibitory: Dict[str, float] = Field(default_factory=dict)
    relation_types: Dict[str, str] = Field(default_factory=dict)


class MemoryNode(BaseModel):
    """Tier 3: Persistent Memory Store (Fragment / ACA Node)."""

    id: str
    engine_mode: EngineMode = EngineMode.HYBRID
    node_type: NodeType = NodeType.FRAGMENT
    resolutions: FragmentResolutions
    dynamics: FragmentDynamics = Field(default_factory=FragmentDynamics)
    provenance: FragmentProvenance = Field(default_factory=FragmentProvenance)
    links: FragmentLinks = Field(default_factory=FragmentLinks)


class RawLogEntry(BaseModel):
    """Tier 2: Immutable Raw Log entry."""

    event_id: str
    session_id: str
    turn_id: int
    timestamp: str
    caller: str
    event_type: Literal[
        "user_turn",
        "tool_output",
        "file_diff",
        "system_alert",
        "outcome",
        "settle_cue",
    ] = "user_turn"
    raw_payload: str
    gc_compressed_payload: str = ""
    external_signals: Dict[str, Any] = Field(default_factory=dict)


class GlobalContextState(BaseModel):
    """Tier 1: Global Context (GC) Interning & Masking Dictionary."""

    prefixes: Dict[str, str] = Field(default_factory=dict)
    entities: Dict[str, str] = Field(default_factory=dict)
    semantic_pointers: Dict[str, str] = Field(default_factory=dict)
    entropy_masks: Dict[str, str] = Field(default_factory=dict)
    compound_targets: Dict[str, str] = Field(default_factory=dict)


class BudgetState(BaseModel):
    total_tokens: int = 2048
    used_tokens: int = 0
    temperature_tau: float = 0.35


class ModulationState(BaseModel):
    theta_in: float = 0.55
    theta_out: float = 0.30
    lambda_spread: float = 0.40
    eta_hebbian: float = 0.10
    delta_a: float = 0.88
    delta_w: float = 0.94
    surprise: float = 0.0
    progress_delta: float = 0.0


class ContradictionPair(BaseModel):
    node_a_id: str
    node_b_id: str
    node_a_claim: str
    node_b_claim: str
    severity: float = 0.85
    resolution_hint: str = "Verify against live code or test execution."


class CANState(BaseModel):
    pinned_core: List[str] = Field(default_factory=list)
    full_narrative: str = ""
    summary_fragments: List[str] = Field(default_factory=list)
    ambient_pointers: List[str] = Field(default_factory=list)
    contradictions: List[ContradictionPair] = Field(default_factory=list)


class JevDecision(BaseModel):
    noul: str
    question: str = ""
    choice: str
    score: float = Field(..., ge=0.0, le=1.0)
    probabilities: Dict[str, float] = Field(default_factory=dict)
    crossed_threshold: bool = False
    triggered_action: Optional[str] = None


class TraceBreakdown(BaseModel):
    fragment_id: str
    inject_match_m_f: float
    prior_activation: float
    spread_contribution: float
    inhibitory_suppression: float
    post_fire_activation: float
    fired: bool
    novelty: float
    noisy_or_connection: float
    trust: float
    composite_weight_w_f: float
    token_share: float
    assigned_resolution: ResolutionLevel
    hysteresis_applied: bool = False


class CANPacket(BaseModel):
    """Tier 4: Ephemeral CAN Packet (API Output Payload)."""

    can_id: str
    session_id: str
    turn_id: int
    engine_mode: EngineMode = EngineMode.HYBRID
    budget: BudgetState
    modulation: ModulationState
    global_context: GlobalContextState
    can_state: CANState
    jev_decisions: List[JevDecision] = Field(default_factory=list)
    trace: List[TraceBreakdown] = Field(default_factory=list)
    sampled_field_agreement: float = 1.0
    pivotal_nodes: List[str] = Field(default_factory=list)


# API Request / Response Payloads

class IngestRequest(BaseModel):
    session_id: str = "sess_01"
    turn_id: Optional[int] = None
    caller: str = "cli_agent"
    event_type: Literal["user_turn", "tool_output", "file_diff", "system_alert"] = "user_turn"
    raw_payload: str
    engine_mode: EngineMode = EngineMode.HYBRID
    scope: str = "repo:ACA-systems-prodo"
    token_budget: int = 2048
    temperature_tau: Optional[float] = None
    auto_settle: bool = False
    max_settle_passes: int = Field(default=4, ge=1, le=12)
    sample_fields_count: int = 3
    prediction: Optional[str] = None
    external_signals: Dict[str, Any] = Field(default_factory=dict)


class SettleRequest(BaseModel):
    session_id: str = "sess_01"
    intermediate_reasoning: str
    scope: str = "repo:ACA-systems-prodo"
    self_cue_gain: float = Field(default=0.35, ge=0.05, le=0.80)
    max_passes: int = Field(default=5, ge=1, le=12)
    stability_jaccard_threshold: float = Field(default=1.0, ge=0.5, le=1.0)
    token_budget: int = 2048


class SettleResponse(BaseModel):
    session_id: str
    passes_executed: int
    converged: bool
    cycle_detected: bool
    firing_set_history: List[List[str]]
    final_can_packet: CANPacket


class OutcomeRequest(BaseModel):
    session_id: str = "sess_01"
    turn_id: Optional[int] = None
    caller: str = "cli_agent"
    command_or_action: str = ""
    expected_prediction: Optional[str] = None
    exit_code: int = 0
    test_status: Literal["passed", "failed", "error", "unknown"] = "unknown"
    raw_output: str = ""
    model_output_to_expand: str = ""
    explicit_fact_or_lesson: Optional[str] = None
    is_user_constraint: bool = False
    source_type: SourceTrustType = SourceTrustType.LIVE_TEST_OUTPUT
    scope: str = "repo:ACA-systems-prodo"


class OutcomeResponse(BaseModel):
    session_id: str
    turn_id: int
    surprise: float
    progress_delta: float
    write_gate_triggered: bool
    write_reason: Optional[str] = None
    created_or_updated_fragment: Optional[MemoryNode] = None
    potentiated_links: Dict[str, float] = Field(default_factory=dict)
    modulation: ModulationState
    hydrated_model_output: str = ""
    can_packet: CANPacket


class GCCompressRequest(BaseModel):
    session_id: str = "sess_01"
    text: str
    register_semantic_states: Optional[Dict[str, str]] = None


class GCCompressResponse(BaseModel):
    compressed_text: str
    original_char_len: int
    compressed_char_len: int
    compression_ratio: float
    global_context: GlobalContextState
    system_prompt_directive: str


class GCExpandRequest(BaseModel):
    session_id: str = "sess_01"
    compressed_text: str
    # False keeps entropy masks (tokens, GUIDs) as placeholders even for write keys
    unmask: bool = True


class GCExpandResponse(BaseModel):
    expanded_text: str


class LoginRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=256)


class ProjectScopeRequest(BaseModel):
    scope: str = Field(pattern=r"^repo-path:(?:/|[a-zA-Z]:/).*$")


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    role: Literal["read", "write", "admin"] = "write"
    expires_in_days: Optional[float] = Field(default=None, gt=0, le=3650)


class ChatMessage(BaseModel):
    role: str
    content: str
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: str = "local-llm"
    messages: List[ChatMessage]
    session_id: str = "sess_01"
    engine_mode: EngineMode = EngineMode.HYBRID
    keep_last_n_raw_turns: int = 3
    token_budget: int = 2048
    upstream_base_url: Optional[str] = None
    upstream_api_key: Optional[str] = None
    temperature: float = 0.2
    max_tokens: Optional[int] = 1024
    stream: bool = False
