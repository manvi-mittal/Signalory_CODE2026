"""
Database models.

Read this top to bottom - it tells the whole data story of the app:
a User has WatchlistItems, each WatchlistItem has one Thesis, each
Thesis has Signals (what to watch for) and an optional ThesisBreaker
(what would prove it wrong). Evidence flows in over time and gets
scored into ThesisSnapshots, which is what "While You Were Away" reads.
"""
from datetime import datetime, timezone
from flask_login import UserMixin
from extensions import db


def utcnow():
    return datetime.now(timezone.utc)


# Fixed taxonomy of signal categories.
# Keeping this a small, fixed list (instead of freeform tags) is what makes
# the deterministic keyword-fallback possible, and keeps "Why?" explanations
# consistent across every thesis instead of a different vocabulary each time.
SIGNAL_CATEGORIES = [
    "growth",                 # revenue / volume / user growth
    "margin",                 # profitability / cost trends
    "management_commentary",  # guidance, calls, interviews
    "announcement",           # deals, partnerships, product launches, orders
    "earnings",                # quarterly/annual results
    "macro_sector",            # sector-wide or macroeconomic news
]

EVIDENCE_DIRECTIONS = ["supporting", "contradicting", "neutral"]

SIGNALORY_STATUSES = ["STRENGTHENING", "WEAKENING", "MIXED", "UNCHANGED", "BROKEN"]


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    watchlist_items = db.relationship(
        "WatchlistItem", backref="user", lazy=True, cascade="all, delete-orphan"
    )
    last_seen = db.relationship(
        "UserLastSeen", backref="user", uselist=False, cascade="all, delete-orphan"
    )


class Stock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(20), unique=True, nullable=False, index=True)  # "TCS"
    name = db.Column(db.String(255), nullable=False)                              # "Tata Consultancy Services"
    exchange = db.Column(db.String(10), nullable=False, default="NSE")
    created_at = db.Column(db.DateTime, default=utcnow)

    snapshots = db.relationship("MarketSnapshot", backref="stock", lazy=True)


class WatchlistItem(db.Model):
    """One row = one stock a user is watching, tied to their reason for watching it."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    stock_id = db.Column(db.Integer, db.ForeignKey("stock.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    stock = db.relationship("Stock")
    thesis = db.relationship(
        "Thesis", backref="watchlist_item", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        db.UniqueConstraint("user_id", "stock_id", name="uq_user_stock"),
    )


class Thesis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    watchlist_item_id = db.Column(
        db.Integer, db.ForeignKey("watchlist_item.id"), nullable=False, unique=True, index=True
    )
    # original_text is NEVER edited after creation - it's the baseline "why" we
    # compare everything against. current_text can be edited by the user later;
    # if the two diverge a lot, that's "thesis drift".
    original_text = db.Column(db.Text, nullable=False)
    current_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    signals = db.relationship("Signal", backref="thesis", lazy=True, cascade="all, delete-orphan")
    breaker = db.relationship(
        "ThesisBreaker", backref="thesis", uselist=False, cascade="all, delete-orphan"
    )
    evidence = db.relationship(
        "Evidence", backref="thesis", lazy=True,
        cascade="all, delete-orphan", order_by="Evidence.occurred_at.desc()"
    )
    snapshots = db.relationship(
        "ThesisSnapshot", backref="thesis", lazy=True,
        cascade="all, delete-orphan", order_by="ThesisSnapshot.computed_at.desc()"
    )


class ThesisBreaker(db.Model):
    """The 'Prove Me Wrong' condition - a single measurable rule the user defines."""
    id = db.Column(db.Integer, primary_key=True)
    thesis_id = db.Column(db.Integer, db.ForeignKey("thesis.id"), nullable=False, index=True)
    metric = db.Column(db.String(50), nullable=False)     # e.g. "operating_margin"
    operator = db.Column(db.String(2), nullable=False)    # "<", ">", "<=", ">="
    threshold = db.Column(db.Float, nullable=False)        # e.g. 8.0
    description = db.Column(db.String(500))                # user's own words
    created_at = db.Column(db.DateTime, default=utcnow)


class Signal(db.Model):
    """A category of evidence this thesis cares about, derived from the thesis text."""
    id = db.Column(db.Integer, primary_key=True)
    thesis_id = db.Column(db.Integer, db.ForeignKey("thesis.id"), nullable=False, index=True)
    category = db.Column(db.String(50), nullable=False)   # one of SIGNAL_CATEGORIES
    weight = db.Column(db.Float, default=1.0)               # relevance weight, tunable
    source = db.Column(db.String(10), default="rule")       # "rule" | "ai" - provenance
    created_at = db.Column(db.DateTime, default=utcnow)


class MarketSnapshot(db.Model):
    """A point-in-time capture of a stock's price/metrics from a data provider."""
    id = db.Column(db.Integer, primary_key=True)
    stock_id = db.Column(db.Integer, db.ForeignKey("stock.id"), nullable=False, index=True)
    price = db.Column(db.Float, nullable=False)
    volume = db.Column(db.Integer)
    metrics_json = db.Column(db.JSON, default=dict)  # {"operating_margin": 7.8, ...}
    source = db.Column(db.String(50), nullable=False)  # "mock" | provider name
    fetched_at = db.Column(db.DateTime, default=utcnow, index=True)
    is_stale = db.Column(db.Boolean, default=False)


class Evidence(db.Model):
    """A single piece of news/data linked to a specific thesis's signal categories."""
    id = db.Column(db.Integer, primary_key=True)
    thesis_id = db.Column(db.Integer, db.ForeignKey("thesis.id"), nullable=False, index=True)
    signal_category = db.Column(db.String(50), nullable=False)
    direction = db.Column(db.String(15), nullable=False)   # supporting | contradicting | neutral
    headline = db.Column(db.String(500), nullable=False)
    source = db.Column(db.String(100), nullable=False)
    confidence = db.Column(db.String(10), default="MEDIUM")  # LOW | MEDIUM | HIGH
    occurred_at = db.Column(db.DateTime, nullable=False, index=True)
    ingested_at = db.Column(db.DateTime, default=utcnow)
    # Guards against the same evidence being inserted twice (retries, overlapping
    # polls, multiple tabs triggering a refresh at once).
    dedupe_key = db.Column(db.String(255), unique=True, nullable=False)


class ThesisSnapshot(db.Model):
    """
    An append-only log of evaluate_thesis() results over time.
    This IS the evidence timeline and the demo-mode Day1->Day4 story -
    we just read this table ordered by time, we never overwrite a row.
    """
    id = db.Column(db.Integer, primary_key=True)
    thesis_id = db.Column(db.Integer, db.ForeignKey("thesis.id"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False)   # one of SIGNALORY_STATUSES
    score = db.Column(db.Float, nullable=False)
    reasons_json = db.Column(db.JSON, nullable=False, default=list)
    computed_at = db.Column(db.DateTime, default=utcnow, index=True)


class UserLastSeen(db.Model):
    """
    Server-side source of truth for 'when did this user last check the dashboard'.
    One row per user, always upserted - this is what makes multi-tab / multi-device
    behavior consistent without any client-side state or locking.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, unique=True, index=True)
    last_seen_at = db.Column(db.DateTime, default=utcnow)
