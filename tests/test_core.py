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


def test_predicate_store_migrates_legacy_schema(tmp_path):
    import sqlite3

    db_file = tmp_path / "legacy_predicates.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("""
        CREATE TABLE predicates (
            id TEXT PRIMARY KEY,
            question TEXT NOT NULL,
            domain TEXT,
            default_threshold REAL,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE predicate_results (
            predicate_id TEXT NOT NULL,
            paper_id TEXT NOT NULL,
            probability REAL NOT NULL,
            confidence REAL,
            model TEXT,
            latency_ms REAL,
            created_at TEXT,
            PRIMARY KEY (predicate_id, paper_id)
        )
    """)
    conn.execute(
        "INSERT INTO predicate_results VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("P_legacy", "2401.9999", 0.91, 1.0, "jev-simulated-v1", 1.2, "2026-01-01T00:00:00+00:00"),
    )
    conn.commit()
    conn.close()

    store = PredicateStore(str(db_file))
    # Legacy simulated row must not be served as live
    assert store.get_result("P_legacy", "2401.9999") is None

    # New live rows with same predicate_id and different question hashes coexist cleanly
    store.record_result(PredicateResult(
        predicate_id="P_legacy",
        question_hash="hash_a",
        paper_id="2401.9999",
        probability=0.88,
        model="jev-latest",
        source="live",
    ))
    store.record_result(PredicateResult(
        predicate_id="P_legacy",
        question_hash="hash_b",
        paper_id="2401.9999",
        probability=0.22,
        model="jev-latest",
        source="live",
    ))
    with store._get_conn() as c:
        rows = c.execute(
            "SELECT question_hash, probability, source FROM predicate_results WHERE predicate_id = 'P_legacy'"
        ).fetchall()
    assert len(rows) == 3
