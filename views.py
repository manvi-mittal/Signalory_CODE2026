"""
Main application routes: watchlist management, thesis creation, and the
"While You Were Away" dashboard - the product's actual homepage.
"""
import hashlib
from datetime import datetime, timezone, timedelta

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from extensions import db
from models import (
    Stock, WatchlistItem, Thesis, ThesisBreaker, Signal, Evidence,
    ThesisSnapshot, MarketSnapshot, UserLastSeen, SIGNAL_CATEGORIES,
)
from domain.thesis import extract_signals_from_thesis, parse_breaker_condition
from domain.change_detection import evaluate_thesis, detect_thesis_drift
from domain.market_data import get_default_provider, MarketDataUnavailable

views_bp = Blueprint("views", __name__)


def _get_or_create_stock(symbol: str, name: str = None, exchange: str = "NSE") -> Stock:
    symbol = symbol.strip().upper()
    stock = Stock.query.filter_by(symbol=symbol).first()
    if stock is None:
        stock = Stock(symbol=symbol, name=name or symbol, exchange=exchange)
        db.session.add(stock)
        db.session.commit()
    return stock


def _signal_weights_for(thesis: Thesis) -> dict:
    return {s.category: s.weight for s in thesis.signals}


def _get_market_snapshot(stock: Stock) -> dict:
    """Fetch market data through the provider boundary and persist a snapshot.

    The UI can always show source/freshness metadata, while the domain engine
    only consumes validated metrics. A provider failure never breaks the page.
    """
    provider = get_default_provider()
    try:
        data = provider.get_snapshot(stock.symbol)
        fetched_at = data["fetched_at"]
        age = datetime.now(timezone.utc) - fetched_at
        is_stale = age > timedelta(minutes=60)
        db.session.add(MarketSnapshot(
            stock_id=stock.id,
            price=float(data["price"]),
            volume=int(data.get("volume", 0)),
            metrics_json=data.get("metrics", {}),
            source=data.get("source", "unknown"),
            fetched_at=fetched_at,
            is_stale=is_stale,
        ))
        db.session.commit()
        return {**data, "is_stale": is_stale}
    except (MarketDataUnavailable, KeyError, TypeError, ValueError):
        last = (MarketSnapshot.query.filter_by(stock_id=stock.id)
                .order_by(MarketSnapshot.fetched_at.desc()).first())
        if last:
            return {
                "symbol": stock.symbol,
                "name": stock.name,
                "price": last.price,
                "change_pct": 0.0,
                "previous_close": last.price,
                "volume": last.volume or 0,
                "metrics": last.metrics_json or {},
                "source": f"last known · {last.source}",
                "fetched_at": last.fetched_at,
                "is_stale": True,
            }
        return {
            "symbol": stock.symbol, "name": stock.name, "price": 0.0,
            "change_pct": 0.0, "previous_close": 0.0, "volume": 0,
            "metrics": {}, "source": "unavailable",
            "fetched_at": datetime.now(timezone.utc), "is_stale": True,
        }


def _evaluate_and_snapshot(thesis: Thesis, since: datetime | None, market: dict) -> "ThesisEvaluationResult":
    query = Evidence.query.filter_by(thesis_id=thesis.id)
    if since is not None:
        query = query.filter(Evidence.occurred_at >= since)
    evidence_items = [
        {
            "signal_category": e.signal_category,
            "direction": e.direction,
            "confidence": e.confidence,
            "headline": e.headline,
        }
        for e in query.order_by(Evidence.occurred_at.desc()).all()
    ]

    breaker = None
    if thesis.breaker:
        breaker = {
            "metric": thesis.breaker.metric,
            "operator": thesis.breaker.operator,
            "threshold": thesis.breaker.threshold,
            "description": thesis.breaker.description,
        }

    result = evaluate_thesis(
        evidence_items=evidence_items,
        signal_weights=_signal_weights_for(thesis),
        breaker=breaker,
        current_metrics=market.get("metrics", {}),
    )

    snapshot = ThesisSnapshot(
        thesis_id=thesis.id,
        status=result.status,
        score=result.score,
        reasons_json=result.reasons,
    )
    db.session.add(snapshot)
    db.session.commit()
    return result


@views_bp.route("/")
def index():
    return redirect(url_for("views.dashboard"))


@views_bp.route("/dashboard")
@login_required
def dashboard():
    last_seen_row = UserLastSeen.query.filter_by(user_id=current_user.id).first()
    previous_seen_at = last_seen_row.last_seen_at if last_seen_row else None
    items = WatchlistItem.query.filter_by(user_id=current_user.id).all()
    cards = []
    meaningful_count = 0
    checkpoint_count = 0
    fresh_count = 0
    checkpoints = []

    for item in items:
        if not item.thesis:
            continue
        market = _get_market_snapshot(item.stock)
        if market.get("name") and item.stock.name == item.stock.symbol:
            item.stock.name = market["name"]
            db.session.commit()
        result = _evaluate_and_snapshot(item.thesis, since=previous_seen_at, market=market)
        drifted = detect_thesis_drift(item.thesis.original_text, item.thesis.current_text)

        # Use all evidence for the visual balance. Use only since-last-check
        # evidence for the attention classification above.
        all_evidence = item.thesis.evidence
        support_count = sum(1 for e in all_evidence if e.direction == "supporting")
        contra_count = sum(1 for e in all_evidence if e.direction == "contradicting")
        total_directional = support_count + contra_count
        support_pct = round((support_count / total_directional) * 100) if total_directional else 50
        contra_pct = 100 - support_pct
        balance_label = "Balanced" if support_count and contra_count else ("Leaning support" if support_count else ("Leaning against" if contra_count else "No signal yet"))

        status_weight = {"BROKEN": 100, "WEAKENING": 88, "MIXED": 76, "STRENGTHENING": 64, "UNCHANGED": 18}.get(result.status, 18)
        attention_score = min(99, status_weight + min(15, len(all_evidence) * 2))
        if result.status == "UNCHANGED" and not result.reasons:
            attention_score = 10
        if result.status in ("STRENGTHENING", "WEAKENING", "MIXED", "BROKEN"):
            meaningful_count += 1
        if not market.get("is_stale"):
            fresh_count += 1
        if item.thesis.breaker:
            checkpoint_count += 1
            checkpoints.append({"symbol": item.stock.symbol, "description": item.thesis.breaker.description, "thesis_id": item.thesis.id})

        cards.append({
            "item": item, "result": result, "drifted": drifted, "market": market,
            "support_count": support_count, "contra_count": contra_count,
            "support_pct": support_pct, "contra_pct": contra_pct,
            "balance_label": balance_label, "attention_score": attention_score,
        })

    cards.sort(key=lambda c: (-c["attention_score"], c["item"].stock.symbol))
    focus_score = round(sum(c["attention_score"] for c in cards) / len(cards)) if cards else 0

    if last_seen_row is None:
        last_seen_row = UserLastSeen(user_id=current_user.id, last_seen_at=datetime.now(timezone.utc))
        db.session.add(last_seen_row)
    else:
        last_seen_row.last_seen_at = datetime.now(timezone.utc)
    db.session.commit()

    return render_template("dashboard.html", cards=cards, previous_seen_at=previous_seen_at,
                           meaningful_count=meaningful_count, is_first_visit=(previous_seen_at is None),
                           checkpoint_count=checkpoint_count, checkpoints=checkpoints,
                           fresh_count=fresh_count, focus_score=focus_score)


@views_bp.route("/watchlist/add", methods=["GET", "POST"])
@login_required
def add_stock():
    if request.method == "POST":
        symbol = request.form.get("symbol", "").strip().upper()
        thesis_text = request.form.get("thesis_text", "").strip()
        breaker_metric = request.form.get("breaker_metric", "").strip()
        breaker_operator = request.form.get("breaker_operator", "").strip()
        breaker_threshold = request.form.get("breaker_threshold", "").strip()

        if not symbol:
            flash("Please enter a stock symbol.", "error")
            return render_template("add_stock.html")
        if not thesis_text:
            flash("Please describe the belief behind the stock.", "error")
            return render_template("add_stock.html")

        stock = _get_or_create_stock(symbol)
        existing = WatchlistItem.query.filter_by(user_id=current_user.id, stock_id=stock.id).first()
        if existing:
            flash(f"{symbol} is already in your workspace.", "error")
            return redirect(url_for("views.dashboard"))

        item = WatchlistItem(user_id=current_user.id, stock_id=stock.id)
        db.session.add(item)
        db.session.flush()
        thesis = Thesis(watchlist_item_id=item.id, original_text=thesis_text, current_text=thesis_text)
        db.session.add(thesis)
        db.session.flush()
        for sig in extract_signals_from_thesis(thesis_text):
            db.session.add(Signal(thesis_id=thesis.id, **sig))
        if breaker_metric and breaker_operator and breaker_threshold:
            try:
                parsed = parse_breaker_condition(breaker_metric, breaker_operator, float(breaker_threshold))
                db.session.add(ThesisBreaker(thesis_id=thesis.id, **parsed))
            except ValueError as e:
                flash(f"Checkpoint ignored: {e}", "error")
        db.session.commit()
        flash(f"{symbol} added to your focus board.", "success")
        return redirect(url_for("views.dashboard"))
    return render_template("add_stock.html", categories=SIGNAL_CATEGORIES)


@views_bp.route("/watchlist/<int:item_id>/remove", methods=["POST"])
@login_required
def remove_stock(item_id):
    item = WatchlistItem.query.filter_by(id=item_id, user_id=current_user.id).first_or_404()
    db.session.delete(item)
    db.session.commit()
    flash("Hypothesis removed from your workspace.", "success")
    return redirect(url_for("views.dashboard"))


@views_bp.route("/signals")
@login_required
def signal_map():
    theses = Thesis.query.join(WatchlistItem).filter(WatchlistItem.user_id == current_user.id).all()
    evidence = []
    counts = {"supporting": 0, "contradicting": 0, "neutral": 0}
    for thesis in theses:
        symbol = thesis.watchlist_item.stock.symbol
        for e in thesis.evidence:
            counts[e.direction] = counts.get(e.direction, 0) + 1
            evidence.append({"thesis_id": thesis.id, "symbol": symbol, "signal_category": e.signal_category,
                             "direction": e.direction, "headline": e.headline, "confidence": e.confidence,
                             "occurred_at": e.occurred_at})
    evidence.sort(key=lambda x: x["occurred_at"], reverse=True)
    return render_template("signal_map.html", evidence=evidence, counts=counts, theses=theses)


@views_bp.route("/thesis/<int:thesis_id>")
@login_required
def thesis_detail(thesis_id):
    thesis = Thesis.query.get_or_404(thesis_id)
    item = thesis.watchlist_item
    if item.user_id != current_user.id:
        return redirect(url_for("views.dashboard"))

    latest_snapshot = thesis.snapshots[0] if thesis.snapshots else None
    drifted = detect_thesis_drift(thesis.original_text, thesis.current_text)
    market = _get_market_snapshot(item.stock)
    if market.get("name") and item.stock.name == item.stock.symbol:
        item.stock.name = market["name"]
        db.session.commit()

    support_count = sum(1 for e in thesis.evidence if e.direction == "supporting")
    contra_count = sum(1 for e in thesis.evidence if e.direction == "contradicting")
    total = support_count + contra_count
    support_pct = round((support_count / total) * 100) if total else 50
    contra_pct = 100 - support_pct
    conviction = 50 if not total else max(8, min(92, round((support_count / total) * 100)))
    if latest_snapshot and latest_snapshot.status == "BROKEN":
        conviction = 0
    if support_count and contra_count:
        balance_text = "Both sides have evidence. The useful question is which signal is newer and more reliable."
    elif support_count:
        balance_text = "The ledger currently leans toward the original belief. Keep watching the failure point."
    elif contra_count:
        balance_text = "The ledger leans against the original belief. This deserves a deliberate review."
    else:
        balance_text = "No directional evidence has been logged yet."

    return render_template("thesis_detail.html", thesis=thesis, item=item, latest_snapshot=latest_snapshot,
                           drifted=drifted, market=market, support_count=support_count, contra_count=contra_count,
                           support_pct=support_pct, contra_pct=contra_pct, conviction=conviction,
                           balance_text=balance_text)


@views_bp.route("/thesis/<int:thesis_id>/log", methods=["POST"])
@login_required
def log_signal(thesis_id):
    thesis = Thesis.query.get_or_404(thesis_id)
    if thesis.watchlist_item.user_id != current_user.id:
        return redirect(url_for("views.dashboard"))

    category = request.form.get("category", "growth").strip()
    direction = request.form.get("direction", "neutral").strip()
    confidence = request.form.get("confidence", "MEDIUM").strip().upper()
    headline = request.form.get("headline", "").strip()
    if direction not in ("supporting", "contradicting", "neutral") or confidence not in ("LOW", "MEDIUM", "HIGH"):
        flash("Invalid signal classification.", "error")
        return redirect(url_for("views.thesis_detail", thesis_id=thesis_id))
    if not headline:
        flash("Add a short description of the signal.", "error")
        return redirect(url_for("views.thesis_detail", thesis_id=thesis_id))

    now = datetime.now(timezone.utc)
    dedupe_source = f"user|{thesis_id}|{category}|{direction}|{headline}|{now.isoformat()}"
    evidence = Evidence(thesis_id=thesis_id, signal_category=category, direction=direction,
                        headline=headline, source="your research note", confidence=confidence,
                        occurred_at=now, dedupe_key=hashlib.sha256(dedupe_source.encode()).hexdigest())
    db.session.add(evidence)
    db.session.commit()
    flash("Signal added to the evidence ledger.", "success")
    return redirect(url_for("views.thesis_detail", thesis_id=thesis_id))
