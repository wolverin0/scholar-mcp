import pytest
from scholar.core.papers import Paper, Claim, Evidence
from scholar.core.predicates import SemanticPredicate, PredicateStore
from scholar.jev.client import JevClient
from scholar.jev.gates import PreRAGGate, PostRAGVerifier


@pytest.mark.asyncio
async def test_jev_client_simulation():
    client = JevClient(force_simulation=True)
    assert client.is_simulated is True

    text = "We evaluate our scheduler on an outdoor 802.11ac testbed with real hardware and CPE devices."
    decision = await client.evaluate_noul(text, "Does this paper evaluate real hardware?")
    
    assert decision.probability > 0.50
    assert decision.latency_ms >= 0


@pytest.mark.asyncio
async def test_pre_rag_gate_filtering():
    client = JevClient()
    store = PredicateStore(":memory:")
    gate = PreRAGGate(client, store)

    paper_hw = Paper(
        id="2401.0001",
        title="Field Trial of PtMP MAC Scheduler on Atheros Hardware",
        abstract="We deployed prototype hardware and evaluated loaded latency across 40 customer CPEs."
    )
    paper_sim = Paper(
        id="2401.0002",
        title="Theoretical Bounds on Queueing in Abstract Networks",
        abstract="This is a purely theoretical paper with NS-3 simulation only. No hardware experiments."
    )

    predicates = [
        SemanticPredicate(
            id="P_hardware",
            question="Does this paper evaluate real hardware?",
            default_threshold=0.50
        )
    ]

    report = await gate.screen_papers([paper_hw, paper_sim], predicates)

    assert report.total_candidates == 2
    assert report.passed_count == 1
    assert report.rejected_count == 1
    assert report.surviving_papers[0].id == "2401.0001"
    assert "2401.0002" in report.rejection_reasons


@pytest.mark.asyncio
async def test_post_rag_verifier():
    client = JevClient()
    verifier = PostRAGVerifier(client)

    evidence = Evidence(
        paper_id="2401.0001",
        section="results",
        text="The proposed airtime scheduler reduces 99th percentile loaded latency by 68% on QCA988x hardware."
    )

    claim = Claim(
        id="c1",
        statement="The scheduler demonstrates loaded latency reductions on physical hardware.",
        paper_id="2401.0001"
    )

    verified = await verifier.verify_claim(claim, evidence)
    assert verified.status in ["supported", "partial"]
    assert verified.verification_probability is not None
    assert verified.verification_probability > 0.40
