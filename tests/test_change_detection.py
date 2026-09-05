"""
Unit tests for the meaningful-change engine - the core of the product.
Run with: pytest tests/ -v

These test the domain layer directly with plain dicts, no Flask/DB needed -
that's deliberate, and it's a good thing to run live in front of judges.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domain.change_detection import evaluate_thesis, check_breaker, detect_thesis_drift


def test_no_evidence_means_unchanged():
    result = evaluate_thesis([], signal_weights={"margin": 1.0})
    assert result.status == "UNCHANGED"


def test_only_supporting_evidence_means_strengthening():
    evidence = [
        {"signal_category": "margin", "direction": "supporting", "confidence": "HIGH", "headline": "Margin beat"},
    ]
    result = evaluate_thesis(evidence, signal_weights={"margin": 1.0})
    assert result.status == "STRENGTHENING"
    assert result.score > 0


def test_only_contradicting_evidence_means_weakening():
    evidence = [
        {"signal_category": "margin", "direction": "contradicting", "confidence": "HIGH", "headline": "Margin miss"},
    ]
    result = evaluate_thesis(evidence, signal_weights={"margin": 1.0})
    assert result.status == "WEAKENING"
    assert result.score < 0


def test_mixed_evidence_means_mixed_status():
    evidence = [
        {"signal_category": "margin", "direction": "supporting", "confidence": "HIGH", "headline": "Margin beat"},
        {"signal_category": "margin", "direction": "contradicting", "confidence": "MEDIUM", "headline": "Growth slowed"},
    ]
    result = evaluate_thesis(evidence, signal_weights={"margin": 1.0})
    assert result.status == "MIXED"


def test_breaker_overrides_everything_even_positive_evidence():
    evidence = [
        {"signal_category": "margin", "direction": "supporting", "confidence": "HIGH", "headline": "Great news"},
    ]
    breaker = {"metric": "operating_margin", "operator": "<", "threshold": 8.0, "description": "margin < 8"}
    result = evaluate_thesis(
        evidence, signal_weights={"margin": 1.0}, breaker=breaker,
        current_metrics={"operating_margin": 7.5},
    )
    assert result.status == "BROKEN"
    assert result.breaker_triggered is True


def test_breaker_does_not_fire_when_condition_not_met():
    breaker = {"metric": "operating_margin", "operator": "<", "threshold": 8.0, "description": "margin < 8"}
    assert check_breaker(breaker, {"operating_margin": 9.0}) is False
    assert check_breaker(breaker, {"operating_margin": 7.9}) is True


def test_breaker_with_missing_metric_never_guesses():
    breaker = {"metric": "operating_margin", "operator": "<", "threshold": 8.0, "description": "x"}
    assert check_breaker(breaker, {}) is False


def test_unweighted_signal_category_still_scores_but_lower():
    # Evidence in a category the thesis didn't flag still counts (default weight 0.5),
    # just less than a category the thesis explicitly tracks (weight 1.0).
    evidence = [{"signal_category": "macro_sector", "direction": "supporting", "confidence": "HIGH", "headline": "x"}]
    result = evaluate_thesis(evidence, signal_weights={"margin": 1.0})
    assert result.status == "STRENGTHENING"
    assert result.score == 0.75  # 0.5 relevance * 1.5 HIGH confidence


def test_thesis_drift_detected_on_major_rewrite():
    original = "I think TCS AI and cloud growth will accelerate"
    current = "Actually I am now watching for dividend yield stability"
    assert detect_thesis_drift(original, current) is True


def test_thesis_drift_not_flagged_for_minor_edit():
    original = "I think TCS AI and cloud growth will accelerate"
    current = "I think TCS AI and cloud growth will accelerate strongly"
    assert detect_thesis_drift(original, current) is False


def test_thesis_drift_false_when_text_unchanged():
    text = "same thesis text"
    assert detect_thesis_drift(text, text) is False
