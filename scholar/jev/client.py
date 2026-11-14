"""
TypeSafe Jev System One Client.
High-speed, low-cost structured probabilistic decision caller.
Supports live API calls or high-fidelity simulated/deterministic evaluation.
"""

from __future__ import annotations
import logging
import math
import os
import time
import httpx
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class JevEvaluationRequest(BaseModel):
    state: str = Field(description="Evidence or unstructured text (e.g. abstract, paper excerpt, claim)")
    question: str = Field(description="Typed question to evaluate")
    decision_type: str = Field(default="noul", description="'noul' (yes/no prob), 'choice', or 'score'")
    choices: Optional[List[str]] = Field(default=None, description="Candidate choices for 'choice' type")


class JevDecision(BaseModel):
    question: str
    probability: float
    choice: Optional[str] = None
    scores: Optional[Dict[str, float]] = None
    latency_ms: float
    model_version: str = "jev-system-one"
    source: str = Field(default="live", description="'live' (verified API/LLM) or 'heuristic' (simulated/fallback)")
    is_heuristic: bool = Field(default=False, description="True if result was generated via local heuristics")


class JevClient:
    """
    Client for TypeSafe Jev API.
    If TYPESAFE_API_KEY is unset or simulation is forced, uses high-speed deterministic heuristic simulation.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.typesafe.ai/v1",
        force_simulation: bool = False,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.api_key = api_key if api_key is not None else os.environ.get("TYPESAFE_API_KEY")
        self.base_url = base_url
        self.is_simulated = force_simulation or not bool(self.api_key)
        self.transport = transport

    def _make_http_client(self, timeout: float) -> httpx.AsyncClient:
        if self.transport is not None:
            return httpx.AsyncClient(timeout=timeout, transport=self.transport)
        return httpx.AsyncClient(timeout=timeout)

    @staticmethod
    def _parse_noul_prob(ans: Any) -> float:
        if not isinstance(ans, dict) or "noul" not in ans:
            raise ValueError("Malformed response: missing 'noul' probability in answers")
        prob = float(ans["noul"])
        if not math.isfinite(prob) or prob < 0.0 or prob > 1.0:
            raise ValueError(f"Malformed response: 'noul' probability {prob} outside [0.0, 1.0]")
        return prob

    def _heuristic_decision(
        self, state: str, question: str, t0: float, model_version: str
    ) -> JevDecision:
        prob = self._simulate_noul(state, question)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        return JevDecision(
            question=question,
            probability=prob,
            latency_ms=round(latency_ms, 2),
            model_version=model_version,
            source="heuristic",
            is_heuristic=True,
        )

    async def evaluate_noul(self, state: str, question: str) -> JevDecision:
        """
        Evaluates a boolean/probabilistic proposition (Noul) against state.
        Returns probability in [0.0, 1.0].
        """
        t0 = time.perf_counter()

        if self.is_simulated:
            return self._heuristic_decision(state, question, t0, "jev-simulated-v1")

        # Real API request
        try:
            async with self._make_http_client(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.base_url}/systemone",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "state": state,
                        "model": "jev-latest",
                        "questions": {
                            "q0": {
                                "type": "noul",
                                "instructions": question,
                            }
                        },
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                latency_ms = (time.perf_counter() - t0) * 1000.0
                ans = data.get("answers", {}).get("q0")
                prob = self._parse_noul_prob(ans)
                return JevDecision(
                    question=question,
                    probability=prob,
                    latency_ms=round(latency_ms, 2),
                    model_version=data.get("model", "jev-latest"),
                    source="live",
                    is_heuristic=False,
                )
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            logger.warning(
                "Jev evaluate_noul failed (%s: %s); falling back to heuristic",
                type(exc).__name__,
                exc,
            )
            return self._heuristic_decision(state, question, t0, "jev-simulated-fallback")

    async def batch_evaluate_predicates(self, state: str, questions: List[str]) -> Dict[str, JevDecision]:
        """
        Evaluates multiple predicate questions in parallel against a single state block.
        """
        t0 = time.perf_counter()
        if self.is_simulated:
            return {
                q: self._heuristic_decision(state, q, t0, "jev-simulated-v1")
                for q in questions
            }

        try:
            q_map = {f"q_{i}": {"type": "noul", "instructions": q} for i, q in enumerate(questions)}
            async with self._make_http_client(timeout=15.0) as client:
                resp = await client.post(
                    f"{self.base_url}/systemone",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "state": state,
                        "model": "jev-latest",
                        "questions": q_map,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                latency_ms = (time.perf_counter() - t0) * 1000.0
                answers = data.get("answers")
                if not isinstance(answers, dict):
                    raise ValueError("Malformed response: 'answers' must be a dict")
                results: Dict[str, JevDecision] = {}
                for i, q in enumerate(questions):
                    key = f"q_{i}"
                    if key not in answers:
                        raise KeyError(f"Missing batch answer for '{key}'")
                    prob = self._parse_noul_prob(answers[key])
                    results[q] = JevDecision(
                        question=q,
                        probability=prob,
                        latency_ms=round(latency_ms, 2),
                        model_version=data.get("model", "jev-latest"),
                        source="live",
                        is_heuristic=False,
                    )
                return results
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            logger.warning(
                "Jev batch_evaluate_predicates failed (%s: %s); falling back to heuristic",
                type(exc).__name__,
                exc,
            )
            return {
                q: self._heuristic_decision(state, q, t0, "jev-simulated-fallback")
                for q in questions
            }

    def _simulate_noul(self, state: str, question: str) -> float:
        """
        Semantic heuristic simulator for testing and offline development.
        Extracts key terms from question and tests presence/sentiment in state.
        """
        state_lower = state.lower()
        q_lower = question.lower()
        
        # Real hardware / experiment test
        if "real hardware" in q_lower or "experimental" in q_lower or "testbed" in q_lower:
            keywords = ["testbed", "hardware", "cpe", "access point", "prototype", "deployed", "measurements", "in the wild", "qca", "atheros", "mikrotik"]
            matches = sum(1 for kw in keywords if kw in state_lower)
            if "simulation only" in state_lower or "ns-3" in state_lower or "matlab" in state_lower and matches == 0:
                return 0.08
            return min(0.98, 0.40 + matches * 0.15) if matches > 0 else 0.12

        # MAC scheduler / latency test
        if "mac" in q_lower or "scheduler" in q_lower or "latency" in q_lower:
            keywords = ["scheduler", "scheduling", "queue", "airtime", "mac", "latency", "jitter", "tdma", "fairness", "ptmp", "bufferbloat"]
            matches = sum(1 for kw in keywords if kw in state_lower)
            return min(0.97, 0.35 + matches * 0.12) if matches > 0 else 0.15

        # Simulation only test
        if "simulation only" in q_lower:
            if any(term in state_lower for term in ["simulation only", "purely simulation", "omnet++", "ns-2", "ns-3"]):
                return 0.94
            if any(term in state_lower for term in ["deployed", "testbed", "hardware", "field trial"]):
                return 0.05
            return 0.30

        # Claim verification check (Post-RAG)
        if "evidence passage" in state_lower and "claim to verify" in state_lower:
            parts = state_lower.split("claim to verify:")
            evidence_part = parts[0].replace("evidence passage:", "").strip()
            claim_part = parts[1].strip() if len(parts) > 1 else ""

            if "contradict" in q_lower:
                # check for opposing terms
                if "no" in claim_part and "reduces" in evidence_part:
                    return 0.85
                return 0.05
            
            # Support question: check overlap of key content words
            claim_words = [w.strip('.,;:"') for w in claim_part.split() if len(w) > 4 and w not in ["scheduler", "proposed", "demonstrates", "physical", "tested"]]
            if not claim_words:
                return 0.82
            matches = sum(1 for w in claim_words if w in evidence_part)
            overlap = matches / len(claim_words)
            return min(0.96, max(0.20, 0.40 + overlap * 0.55))

        # General semantic keyword overlap
        q_words = [w for w in q_lower.split() if len(w) > 3 and w not in ["this", "that", "with", "from", "does", "have", "paper", "work"]]
        if not q_words:
            return 0.50
        
        matches = sum(1 for w in q_words if w in state_lower)
        ratio = matches / len(q_words)
        return min(0.95, max(0.05, ratio * 0.9 + 0.1))
