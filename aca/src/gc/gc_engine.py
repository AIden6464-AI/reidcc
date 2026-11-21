"""Tier 1: The Global Context (GC) Interning & Masking Dictionary.

Implements:
1. Regex Entropy Masking (`mask_narrative_data` / `maskNarrativeData`)
2. Hierarchical Prefix Promotion (`tally_prefixes` / `promote_prefixes`)
3. Global Entity Interning (`[CMD_n]`, `U1..Un`, `C1..Cn`, `I1..In`, `W1..Wn`, `R1..Rn`)
4. Semantic Pointers & Dynamic Token Injection (`[STATE_n]`) + Hydration on API egress
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

from src.schemas import GlobalContextState


class GCEngine:
    """Deterministic Global Context (GC) Preprocessor and Hydrator."""

    # 1. Entropy masking regexes
    GUID_RE = re.compile(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
    )
    WIN_SID_RE = re.compile(r"\bS-1-\d+(?:-\d+){2,15}\b")
    TMP_FILE_RE = re.compile(r"(?:[A-Za-z]:[\\/]|\/|\b)[\w\-.\\/]+?\.tmp\b", re.IGNORECASE)
    ANSIBLE_TOKEN_RE = re.compile(
        r"\b(?:ANSIBLE_VAULT;[0-9.]+;[A-Z0-9]+|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}|Bearer\s+[A-Za-z0-9\-._~+/]+=*)"
    )
    HEX_HASH_RE = re.compile(r"\b(?=[0-9a-fA-F]*[a-fA-F])(?=[0-9a-fA-F]*[0-9])[0-9a-fA-F]{24,64}\b")
    LONG_NUM_ID_RE = re.compile(r"\b\d{11,24}\b")

    # 2. File path & namespace detection regex (supports drive letters with spaces in folder names)
    PATH_RE = re.compile(
        r"(?:[A-Za-z]:[\\/](?:[^\\/:*?\"<>|\r\n\s]+(?:\s[^\\/:*?\"<>|\r\n\s]+)?[\\/]){2,}[^\\/:*?\"<>|\r\n\s]*|(?:\.{0,2}\/|[A-Za-z0-9_-]+\/){2,}[A-Za-z0-9_.\-\/]*)"
    )

    # 3. Entity detection regexes
    IP_RE = re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?::\d{2,5})?\b"
    )
    HOST_RE = re.compile(
        r"\b(?:(?:srv|wkst|node|host|db|prod|stg|dev)-[a-zA-Z0-9\-]+|[A-Za-z0-9\-]+\.(?:internal|corp|local|lan))\b",
        re.IGNORECASE,
    )
    USER_RE = re.compile(
        r"(?:(?<=user[=:\s])|(?<=author[=:\s])|(?<=by\s@)|(?<=Users[\\/]))([A-Za-z0-9_.\-]{3,24})\b",
        re.IGNORECASE,
    )
    PROC_RE = re.compile(
        r"\b(?:uvicorn|pytest|python(?:3(?:\.\d+)?)?|node|npm|cargo|docker|postgres|redis-server|llama-server|git|pwsh|powershell|cmd|systemd|nginx|gunicorn)(?:\.exe)?\b"
    )
    CMD_LINE_RE = re.compile(
        r"(?:(?:^\s*(?:\$|\>|PS[^>]*>)\s*)|(?:command|cmd|exec|ran):\s*[`'\"]?)((?:pytest|python|pip|uvicorn|git|docker|npm|node|cargo|curl|pwsh|powershell|Get-ChildItem|Select-Object)[^\r\n`'\"]{44,})",
        re.IGNORECASE | re.MULTILINE,
    )

    def __init__(self) -> None:
        # Per-session state
        self._prefixes: Dict[str, str] = {}            # "<P_1>": "E:/ACA- systems-prodo/src/"
        self._reverse_prefixes: Dict[str, str] = {}    # "E:/ACA- systems-prodo/src/": "<P_1>"
        self._prefix_counts: Counter[str] = Counter()

        self._entities: Dict[str, str] = {}            # "CMD_1": "...", "U1": "..."
        self._reverse_entities: Dict[str, str] = {}

        self._semantic_pointers: Dict[str, str] = {}   # "[STATE_1]": "long explanation..."
        self._reverse_semantic: Dict[str, str] = {}
        self._phrase_counts: Counter[str] = Counter()

        self._entropy_masks: Dict[str, str] = {}       # "<GUID_1>": "5c3cc550-..."
        self._reverse_masks: Dict[str, str] = {}

        self._compound_targets: Dict[str, str] = {}    # "R1": "<P_1>file.py + [CMD_1] + <HASH_1>"
        self._reverse_compounds: Dict[str, str] = {}

        self._counters: Counter[str] = Counter()

        # Bumped on every mutation so callers can persist only when the dictionary changed
        self.version: int = 0

    def _next_token(self, prefix: str, bracket_style: str = "angle") -> str:
        self.version += 1
        self._counters[prefix] += 1
        idx = self._counters[prefix]
        if bracket_style == "angle":
            return f"<{prefix}_{idx}>"
        elif bracket_style == "square":
            return f"[{prefix}_{idx}]"
        else:
            return f"{prefix}{idx}"

    # -------------------------------------------------------------------------
    # 1. Regex Entropy Masking (maskNarrativeData)
    # -------------------------------------------------------------------------
    def maskNarrativeData(self, text: str) -> str:
        """Strip high-entropy strings (GUIDs, .tmp, Windows SIDs, long numeric IDs,
        Ansible/JWT tokens, and raw hex hashes) into compact deterministic placeholders.
        """
        if not text:
            return text

        def _replace_with_mask(match: re.Match, kind: str) -> str:
            val = match.group(0)
            if val in self._reverse_masks:
                return self._reverse_masks[val]
            tok = self._next_token(kind, bracket_style="angle")
            self._entropy_masks[tok] = val
            self._reverse_masks[val] = tok
            return tok

        text = self.ANSIBLE_TOKEN_RE.sub(lambda m: _replace_with_mask(m, "TOK"), text)
        text = self.GUID_RE.sub(lambda m: _replace_with_mask(m, "GUID"), text)
        text = self.WIN_SID_RE.sub(lambda m: _replace_with_mask(m, "SID"), text)
        text = self.TMP_FILE_RE.sub(lambda m: _replace_with_mask(m, "TMP"), text)
        text = self.HEX_HASH_RE.sub(lambda m: _replace_with_mask(m, "HASH"), text)
        text = self.LONG_NUM_ID_RE.sub(lambda m: _replace_with_mask(m, "ID"), text)
        return text

    mask_narrative_data = maskNarrativeData

    # -------------------------------------------------------------------------
    # 2. Hierarchical Prefix Promotion (tallyPrefixes / promotePrefixes)
    # -------------------------------------------------------------------------
    @staticmethod
    def _normalize_path(p: str) -> str:
        return p.replace("\\", "/")

    def tallyPrefixes(self, text: str) -> Counter[str]:
        """Split file paths and namespaces on `/` and `\\`. Tally candidate base paths > 30 chars."""
        candidates = self.PATH_RE.findall(text)
        for raw_path in candidates:
            norm = self._normalize_path(raw_path)
            parts = [p for p in norm.split("/") if p]
            if len(parts) < 2:
                continue
            # Build cumulative directory prefixes ending with '/'
            leading_slash = "/" if norm.startswith("/") else ""
            for i in range(2, len(parts) + 1):
                prefix_candidate = leading_slash + "/".join(parts[:i])
                if not prefix_candidate.endswith("/"):
                    prefix_candidate += "/"
                # Ensure it's an actual prefix of norm (or norm is a directory path)
                if norm.startswith(prefix_candidate) and len(prefix_candidate) > 30:
                    self._prefix_counts[prefix_candidate] += 1
        return self._prefix_counts

    tally_prefixes = tallyPrefixes

    def promotePrefixes(self, text: str, min_occurrences: int = 3, tally: bool = True) -> str:
        """Promote any prefix (> 30 chars) appearing >= 3 times into <P_1>, <P_2>,
        filtering redundant substrings so the longest common path with the same frequency wins.
        With `tally=False` the text is compressed with existing prefixes but not counted again.
        """
        if tally:
            self.tallyPrefixes(text)
            self.version += 1
        eligible = {
            pref: count
            for pref, count in self._prefix_counts.items()
            if len(pref) > 30 and count >= min_occurrences
        }
        if not eligible and not self._prefixes:
            return text

        # Filter redundant substrings: if shorter prefix S is a prefix of longer L
        # and count(S) == count(L), drop S so longest common path wins.
        filtered_prefixes: List[str] = []
        sorted_by_len_desc = sorted(eligible.keys(), key=len, reverse=True)
        for cand in sorted_by_len_desc:
            is_redundant_substring = False
            for longer in filtered_prefixes:
                if longer.startswith(cand) and eligible[cand] <= eligible[longer]:
                    is_redundant_substring = True
                    break
            if not is_redundant_substring:
                filtered_prefixes.append(cand)

        # Register promoted prefixes in deterministic order
        for pref in filtered_prefixes:
            if pref not in self._reverse_prefixes:
                tok = self._next_token("P", bracket_style="angle")
                self._prefixes[tok] = pref
                self._reverse_prefixes[pref] = tok

        # Apply replacements (longest registered prefix first, handling both '/' and '\\')
        active_prefixes = sorted(self._reverse_prefixes.keys(), key=len, reverse=True)
        for pref in active_prefixes:
            tok = self._reverse_prefixes[pref]
            win_pref = pref.replace("/", "\\")
            text = text.replace(pref, tok)
            text = text.replace(win_pref, tok)

        return text

    promote_prefixes = promotePrefixes

    # -------------------------------------------------------------------------
    # 3. Global Entity Interning
    # -------------------------------------------------------------------------
    def _intern_entity(self, raw_value: str, category_prefix: str, bracket_style: str = "plain") -> str:
        clean = raw_value.strip()
        if clean in self._reverse_entities:
            return self._reverse_entities[clean]
        tok = self._next_token(category_prefix, bracket_style=bracket_style)
        # Store both bracketed and raw key in entities dictionary for clean inspection
        dict_key = tok.strip("[]<>") if category_prefix == "CMD" else tok
        self._entities[dict_key] = clean
        self._reverse_entities[clean] = tok
        return tok

    def internEntities(self, text: str) -> str:
        """Intern commands > 50 chars -> [CMD_1], Actors -> U1..Un / C1..Cn,
        Network -> I1..In / W1..Wn, and Compound Targets -> R1..Rn.
        """
        if not text:
            return text

        # 3a. Commands > 50 chars -> [CMD_1], [CMD_2]
        def _replace_cmd(match: re.Match) -> str:
            full_match = match.group(0)
            cmd_str = match.group(1).strip()
            if len(cmd_str) <= 50:
                return full_match
            tok = self._intern_entity(cmd_str, "CMD", bracket_style="square")
            return full_match.replace(cmd_str, tok)

        text = self.CMD_LINE_RE.sub(_replace_cmd, text)

        # Also catch standalone backticked commands > 50 chars
        def _replace_backtick_cmd(match: re.Match) -> str:
            inner = match.group(1).strip()
            if len(inner) > 50 and any(
                inner.startswith(k)
                for k in ("pytest", "python", "uvicorn", "git", "docker", "npm", "cargo", "pwsh", "curl")
            ):
                tok = self._intern_entity(inner, "CMD", bracket_style="square")
                return f"`{tok}`"
            return match.group(0)

        text = re.sub(r"`([^`\r\n]{51,})`", _replace_backtick_cmd, text)

        # 3b. Network IPs -> I1..In and Hosts -> W1..Wn
        text = self.IP_RE.sub(lambda m: self._intern_entity(m.group(0), "I", "plain"), text)
        text = self.HOST_RE.sub(lambda m: self._intern_entity(m.group(0), "W", "plain"), text)

        # 3c. Users -> U1..Un and System/Compute processes -> C1..Cn
        text = self.USER_RE.sub(lambda m: self._intern_entity(m.group(1), "U", "plain"), text)
        text = self.PROC_RE.sub(lambda m: self._intern_entity(m.group(0), "C", "plain"), text)

        # 3d. Compound Targets (compressed path + interned command + hash) -> R1..Rn
        compound_re = re.compile(
            r"(<P_\d+>[^\s,;]+)\s*(?:\||::|->|@)\s*(\[CMD_\d+\])\s*(?:\||::|->|@)\s*(<(?:HASH|GUID)_\d+>)"
        )

        def _replace_compound(match: re.Match) -> str:
            comp_val = f"{match.group(1)} | {match.group(2)} | {match.group(3)}"
            if comp_val in self._reverse_compounds:
                return self._reverse_compounds[comp_val]
            tok = self._next_token("R", bracket_style="plain")
            self._compound_targets[tok] = comp_val
            self._reverse_compounds[comp_val] = tok
            self._entities[tok] = comp_val
            return tok

        text = compound_re.sub(_replace_compound, text)
        return text

    # -------------------------------------------------------------------------
    # 4. Semantic Pointers & Dynamic Token Injection
    # -------------------------------------------------------------------------
    def registerSemanticState(self, explanation: str, pointer_id: Optional[str] = None) -> str:
        """Explicitly register an active contextual state or recurring explanation into [STATE_n]."""
        clean = " ".join(explanation.strip().split())
        if clean in self._reverse_semantic:
            return self._reverse_semantic[clean]
        if pointer_id:
            tok = pointer_id if pointer_id.startswith("[") else f"[{pointer_id}]"
            m = re.search(r"(\d+)", tok)
            if m:
                self._counters["STATE"] = max(self._counters["STATE"], int(m.group(1)))
        else:
            tok = self._next_token("STATE", bracket_style="square")
        self._semantic_pointers[tok] = clean
        self._reverse_semantic[clean] = tok
        self.version += 1
        return tok

    def injectSemanticPointers(self, text: str, min_words: int = 18, tally: bool = True) -> str:
        """Map recurring long explanations (40+ tokens /clauses or registered states)
        into short symbolic pointers ([STATE_1], [STATE_2]).
        """
        if not text:
            return text

        # First replace any already-registered semantic pointers
        for phrase, tok in sorted(self._reverse_semantic.items(), key=lambda x: len(x[0]), reverse=True):
            if phrase in text:
                text = text.replace(phrase, tok)

        # Scan sentences/clauses for recurring 40+ token (or >=min_words) explanations
        sentences = re.split(r"(?<=[.!?;])\s+|\n+", text) if tally else []
        for sent in sentences:
            norm_sent = " ".join(sent.strip().split())
            word_count = len(norm_sent.split())
            # Approximate token count (~1.35 tokens per word + punctuation) or character length >= 140
            if word_count >= min_words or len(norm_sent) >= 160:
                self._phrase_counts[norm_sent] += 1
                if self._phrase_counts[norm_sent] >= 2 and norm_sent not in self._reverse_semantic:
                    tok = self._next_token("STATE", bracket_style="square")
                    self._semantic_pointers[tok] = norm_sent
                    self._reverse_semantic[norm_sent] = tok

        for phrase, tok in sorted(self._reverse_semantic.items(), key=lambda x: len(x[0]), reverse=True):
            if phrase in text:
                text = text.replace(phrase, tok)

        return text

    # -------------------------------------------------------------------------
    # Full Compression & Egress Expansion
    # -------------------------------------------------------------------------
    def compress(
        self,
        text: str,
        register_states: Optional[Dict[str, str]] = None,
        min_prefix_occurrences: int = 3,
        tally: bool = True,
    ) -> str:
        """Execute full 4-step Tier 1 GC compression pipeline on incoming text.

        Pass `tally=False` when re-compressing text that has already been counted once, so
        prefix and recurring-phrase thresholds reflect real occurrences rather than re-reads.
        """
        if register_states:
            for k, v in register_states.items():
                ptr = k if k.startswith("[") else f"[{k}]"
                self.registerSemanticState(v, pointer_id=ptr)

        step1 = self.maskNarrativeData(text)
        step2 = self.promotePrefixes(step1, min_occurrences=min_prefix_occurrences, tally=tally)
        step3 = self.internEntities(step2)
        step4 = self.injectSemanticPointers(step3, tally=tally)
        return step4

    def expand(self, compressed_text: str, unmask: bool = True) -> str:
        """Hydrate all GC pointers ([STATE_n], R1..Rn, [CMD_n], <P_n>, U1..Un, <GUID_n>)
        back to full ground-truth strings on API egress. `unmask=False` leaves entropy masks
        (tokens, GUIDs, hashes) as placeholders for callers not allowed to see secrets.
        """
        if not compressed_text:
            return compressed_text

        out = compressed_text

        # 1. Expand Semantic Pointers first (since they may contain <P_n> or entities)
        for tok, val in sorted(self._semantic_pointers.items(), key=lambda x: len(x[0]), reverse=True):
            out = out.replace(tok, val)

        # 2. Expand Compound Targets R1..Rn
        for tok, val in sorted(self._compound_targets.items(), key=lambda x: len(x[0]), reverse=True):
            out = re.sub(rf"\b{re.escape(tok)}\b", lambda _: val, out)

        # 3. Expand Commands [CMD_n] and Entities (U1, C1, I1, W1)
        for key, val in sorted(self._entities.items(), key=lambda x: len(x[0]), reverse=True):
            if key.startswith("CMD_"):
                bracketed = f"[{key}]"
                out = out.replace(bracketed, val)
            else:
                out = re.sub(rf"\b{re.escape(key)}\b", lambda _: val, out)

        # 4. Expand Prefixes <P_n>
        for tok, val in sorted(self._prefixes.items(), key=lambda x: len(x[0]), reverse=True):
            out = out.replace(tok, val)

        # 5. Expand Entropy Masks (<GUID_n>, <HASH_n>, <SID_n>, <TMP_n>, <TOK_n>, <ID_n>)
        if unmask:
            for tok, val in sorted(self._entropy_masks.items(), key=lambda x: len(x[0]), reverse=True):
                out = out.replace(tok, val)

        return out

    def extract_active_tokens(self, text: str) -> List[str]:
        """Extract all GC tokens (<P_n>, [CMD_n], [STATE_n], U1, C1, etc.) present in text."""
        found: List[str] = []
        for tok in self._prefixes:
            if tok in text:
                found.append(tok)
        for key in self._entities:
            tok = f"[{key}]" if key.startswith("CMD_") else key
            if tok in text:
                found.append(tok)
        for tok in self._semantic_pointers:
            if tok in text:
                found.append(tok)
        return found

    # -------------------------------------------------------------------------
    # Persistence (stored nodes reference these pointers, so they must survive restarts)
    # -------------------------------------------------------------------------
    def export_state(self) -> Dict[str, Dict[str, object]]:
        return {
            "prefixes": dict(self._prefixes),
            "prefix_counts": dict(self._prefix_counts),
            "entities": dict(self._entities),
            "semantic_pointers": dict(self._semantic_pointers),
            "phrase_counts": dict(self._phrase_counts),
            "entropy_masks": dict(self._entropy_masks),
            "compound_targets": dict(self._compound_targets),
            "counters": dict(self._counters),
        }

    @classmethod
    def from_state(cls, state: Dict[str, Dict[str, object]]) -> "GCEngine":
        gc = cls()
        gc._prefixes = dict(state.get("prefixes", {}))
        gc._reverse_prefixes = {v: k for k, v in gc._prefixes.items()}
        gc._prefix_counts = Counter(state.get("prefix_counts", {}))
        gc._entities = dict(state.get("entities", {}))
        gc._compound_targets = dict(state.get("compound_targets", {}))
        gc._reverse_compounds = {v: k for k, v in gc._compound_targets.items()}
        gc._reverse_entities = {
            val: (f"[{key}]" if key.startswith("CMD_") else key)
            for key, val in gc._entities.items()
            if key not in gc._compound_targets
        }
        gc._semantic_pointers = dict(state.get("semantic_pointers", {}))
        gc._reverse_semantic = {v: k for k, v in gc._semantic_pointers.items()}
        gc._phrase_counts = Counter(state.get("phrase_counts", {}))
        gc._entropy_masks = dict(state.get("entropy_masks", {}))
        gc._reverse_masks = {v: k for k, v in gc._entropy_masks.items()}
        gc._counters = Counter(state.get("counters", {}))
        return gc

    def snapshot(self) -> "GCEngine":
        """Independent copy for read-only expansion outside the engine lock (e.g. SSE streaming)."""
        return GCEngine.from_state(self.export_state())

    def get_state(self) -> GlobalContextState:
        return GlobalContextState(
            prefixes=dict(self._prefixes),
            entities=dict(self._entities),
            semantic_pointers=dict(self._semantic_pointers),
            entropy_masks=dict(self._entropy_masks),
            compound_targets=dict(self._compound_targets),
        )

    def build_system_prompt_directive(self) -> str:
        """Build the compact GC dictionary header and native pointer instruction for LLM prompts."""
        lines = [
            "=== GLOBAL CONTEXT (GC) POINTER DICTIONARY ===",
            "INSTRUCTION: Reason and emit output natively using these exact symbolic pointers (<P_n>, [CMD_n], [STATE_n], U1..Un, C1..Cn). The API egress layer will hydrate them back automatically.",
        ]
        if self._prefixes:
            lines.append("PREFIXES: " + ", ".join(f"{k}={v}" for k, v in self._prefixes.items()))
        if self._entities:
            lines.append("ENTITIES: " + ", ".join(f"{k}={v}" for k, v in self._entities.items()))
        if self._semantic_pointers:
            lines.append(
                "SEMANTIC STATES: " + " | ".join(f"{k}: {v}" for k, v in self._semantic_pointers.items())
            )
        return "\n".join(lines)
