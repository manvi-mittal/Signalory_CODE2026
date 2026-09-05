# SIGNALORY — Know what changed. Know why it matters.

Signalory is a hackathon-ready, thesis-aware market workspace. Instead of making a conventional price watchlist, it stores the *reason* behind an idea and turns new observations into an attention queue.

## What makes it different

Signalory is intentionally **not another stock dashboard**. Its unit of attention is a *belief*, not a ticker.

- **Return Brief** — when the user comes back, the first thing shown is a compact explanation of thesis-level changes since the previous check.
- **Focus Board** — ranks hypotheses by thesis impact rather than biggest price move.
- **Evidence Balance** — every logged signal is supporting, contradicting, or neutral.
- **Hypothesis Cockpit** — one place for the original belief, current balance, checkpoint, market context, and evidence ledger.
- **Falsifiable checkpoints** — define a measurable “if this happens, I revisit my thesis” condition.
- **Signal Map** — a cross-portfolio stream of evidence so you can see where your research is leaning.
- **Hypothesis drift** — the original wording is preserved so the app can flag when the current belief has materially changed.
- **Freshness handling** — market provider failures fall back to the latest stored snapshot and are labelled as delayed.
- **Persistent state** — SQLite + SQLAlchemy stores users, watchlists, theses, signals, evidence, snapshots and last-seen timestamps.

## Tech

Flask 3 · SQLAlchemy · Flask-Login · SQLite · pure Python domain engine · optional Yahoo Finance chart endpoint.

## Run locally

```powershell
cd Signalory_CODE2026
python -m pip install -r .\requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

For fresher market data, leave `MARKET_DATA_MODE=auto` (the default). If the provider is unavailable, Signalory uses the last stored market snapshot and marks it delayed.

## Judge demo flow

1. Create an account.
2. Build a hypothesis for TCS / INFY / HDFCBANK / TATAMOTORS.
3. Define a checkpoint such as operating margin below 8%.
4. Open the Hypothesis Cockpit and log one supporting signal and one contradicting signal.
5. Return to the Focus Board: the **Return Brief** explains what changed since the previous check, followed by the ranked attention queue.
6. Open the hypothesis card to show the **Change → Consequence** memo, then Signal Map to show that the evidence is now part of a persistent research ledger.

Signalory does **not** provide buy/sell recommendations. It is a research and attention tool.
