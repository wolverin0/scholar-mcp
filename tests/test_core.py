import pytest
from scholar.core.papers import Paper, Author, Claim, Evidence
from scholar.core.predicates import SemanticPredicate, PredicateResult, PredicateStore


def test_paper_model_and_predicates():
    paper = Paper(
        id="2401.12345",
        title="Low Latency MAC Scheduling for Fixed Wireless PtMP",
        abstract="We present an airtime-fair scheduler tested on Qualcomm QCA988x hardware achieving sub-5ms loaded latency.",
        categories=["cs.NI", "cs.IT"],
        semantic_features={
            "P_real_hardware": 0.95,
            "P_mac_scheduler": 0.92,
            "P_simulation_only": 0.05
        }
    )

    assert paper.id == "2401.12345"
    assert paper.matches_predicates({"P_real_hardware": 0.80, "P_mac_scheduler": 0.90}) is True
    assert paper.matches_predicates({"P_real_hardware": 0.99}) is False


def test_predicate_store_sqlite():
    store = PredicateStore(":memory:")
    
    pred = SemanticPredicate(
        id="P_real_hw",
        question="Does this paper evaluate real hardware?",
        domain="wireless",
        default_threshold=0.85
    )
    store.register_predicate(pred)
    
    retrieved_pred = store.get_predicate("P_real_hw")
    assert retrieved_pred is not None
    assert retrieved_pred.id == "P_real_hw"
    assert retrieved_pred.default_threshold == 0.85

    # Record result
    res = PredicateResult(
        predicate_id="P_real_hw",
        paper_id="2401.12345",
        probability=0.96,
        latency_ms=12.4
    )
    store.record_result(res)

    saved_res = store.get_result("P_real_hw", "2401.12345")
    assert saved_res is not None
    assert saved_res.probability == 0.96

    # Filter papers by threshold
    passing = store.filter_papers_by_threshold("P_real_hw", 0.90)
    assert "2401.12345" in passing
    failing = store.filter_papers_by_threshold("P_real_hw", 0.98)
    assert "2401.12345" not in failing
