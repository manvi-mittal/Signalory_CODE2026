"""
Turns a user's free-text thesis into structured Signal categories.

This is intentionally NOT full NLP. The hackathon brief is explicit:
"Do NOT over-engineer natural-language parsing. Use AI only where it
adds genuine value. Create a deterministic fallback." So the default
path here is simple keyword matching - it's honest about what it is,
it's instant, and it never breaks the product if an AI API is down.

If you later want to plug in an LLM call to do this more cleverly,
that function should call this one as its fallback, and mark any
signals it creates with source="ai" instead of source="rule" (see
models.Signal.source) so we always know provenance.
"""
from models import SIGNAL_CATEGORIES

# Keyword -> signal category. Deliberately simple and inspectable -
# you can read this list out loud to a judge in 20 seconds.
KEYWORD_MAP = {
    "growth": ["growth", "grow", "expand", "scale", "demand", "adoption", "users", "volume"],
    "margin": ["margin", "profitability", "cost", "efficiency", "expense"],
    "management_commentary": ["management", "guidance", "ceo", "cfo", "leadership", "commentary", "outlook"],
    "announcement": ["deal", "partnership", "launch", "order", "contract", "acquisition", "announcement"],
    "earnings": ["earnings", "results", "quarter", "revenue", "profit", "q1", "q2", "q3", "q4"],
    "macro_sector": ["sector", "industry", "market", "regulation", "policy", "macro", "economy"],
}


def extract_signals_from_thesis(thesis_text: str) -> list[dict]:
    """
    Deterministic fallback: scans the thesis text for keywords and returns
    the matching signal categories with a default weight.

    Returns a list of {"category": str, "weight": float, "source": "rule"}.
    Always returns at least one signal (falls back to "earnings" + "growth",
    the two most universally relevant categories) so a thesis is never left
    with zero signals to track.
    """
    text = thesis_text.lower()
    matched = []

    for category, keywords in KEYWORD_MAP.items():
        if any(keyword in text for keyword in keywords):
            matched.append({"category": category, "weight": 1.0, "source": "rule"})

    if not matched:
        matched = [
            {"category": "earnings", "weight": 0.7, "source": "rule"},
            {"category": "growth", "weight": 0.7, "source": "rule"},
        ]

    return matched


def parse_breaker_condition(metric: str, operator: str, threshold: float, description: str = "") -> dict:
    """
    Validates a user-defined 'Prove Me Wrong' condition before it's stored.
    Kept as a plain function (not tied to Flask/DB) so it's trivially unit-testable.
    """
    valid_operators = {"<", ">", "<=", ">="}
    valid_metrics = {"operating_margin", "revenue_growth_yoy"}

    if operator not in valid_operators:
        raise ValueError(f"operator must be one of {valid_operators}")
    if metric not in valid_metrics:
        raise ValueError(f"metric must be one of {valid_metrics}")

    return {
        "metric": metric,
        "operator": operator,
        "threshold": float(threshold),
        "description": description or f"Thesis breaks if {metric} {operator} {threshold}",
    }
