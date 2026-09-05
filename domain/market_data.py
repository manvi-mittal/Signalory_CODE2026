"""
Market data provider abstraction.

WHY THIS EXISTS: the hackathon brief explicitly warns against making the
whole app depend on one flaky external API. So every place in the app that
wants a stock price talks to a MarketDataProvider - never to a specific API
directly. Today that's MockMarketDataProvider (fully deterministic, good for
demos). Later you can add a RealMarketDataProvider that calls a live API,
and a FallbackProvider that tries real-first and falls back to mock/last-known
data if the real one fails. Nothing else in the app needs to change.
"""
from abc import ABC, abstractmethod
from datetime import datetime, timezone
import json
import random
import urllib.parse
import urllib.request


class MarketDataProvider(ABC):
    @abstractmethod
    def get_snapshot(self, symbol: str) -> dict:
        """
        Must return a dict shaped like:
        {
            "symbol": str,
            "price": float,
            "volume": int,
            "metrics": {"operating_margin": float, "revenue_growth_yoy": float, ...},
            "source": str,
            "fetched_at": datetime,
        }
        Must raise MarketDataUnavailable if it cannot get real data -
        callers are responsible for falling back to last-known DB data.
        """
        raise NotImplementedError


class MarketDataUnavailable(Exception):
    """Raised by a provider when it genuinely cannot return data right now."""
    pass


class MockMarketDataProvider(MarketDataProvider):
    """
    Deterministic, seeded-by-symbol fake data. Good enough to demo the whole
    product without depending on any live API being up during judging.
    """

    _BASE_METRICS = {
        "TCS": {"name": "Tata Consultancy Services", "price": 3950.0, "change_pct": 1.84, "operating_margin": 24.5, "revenue_growth_yoy": 6.8},
        "TATAMOTORS": {"name": "Tata Motors", "price": 780.0, "change_pct": -3.42, "operating_margin": 8.5, "revenue_growth_yoy": 4.2},
        "HDFCBANK": {"name": "HDFC Bank", "price": 1650.0, "change_pct": 0.62, "operating_margin": 0, "revenue_growth_yoy": 15.1},
        "INFY": {"name": "Infosys", "price": 1820.0, "change_pct": -0.74, "operating_margin": 21.2, "revenue_growth_yoy": 5.9},
    }

    def get_snapshot(self, symbol: str) -> dict:
        symbol = symbol.upper()
        base = self._BASE_METRICS.get(symbol)
        if base is None:
            # Unknown symbol - deterministic pseudo-random baseline so any
            # searched stock still "works" in fallback mode.
            seed = sum(ord(c) for c in symbol)
            rnd = random.Random(seed)
            base = {
                "name": symbol,
                "price": round(rnd.uniform(100, 3000), 2),
                "change_pct": round(rnd.uniform(-4.5, 4.5), 2),
                "operating_margin": round(rnd.uniform(5, 30), 1),
                "revenue_growth_yoy": round(rnd.uniform(-5, 20), 1),
            }

        return {
            "symbol": symbol,
            "price": base["price"],
            "change_pct": base["change_pct"],
            "previous_close": round(base["price"] / (1 + base["change_pct"] / 100), 2),
            "name": base["name"],
            "volume": 1_000_000,
            "metrics": {
                "operating_margin": base["operating_margin"],
                "revenue_growth_yoy": base["revenue_growth_yoy"],
            },
            "source": "mock",
            "fetched_at": datetime.now(timezone.utc),
        }



class YahooFinanceProvider(MarketDataProvider):
    """Lightweight public Yahoo Finance chart provider for current price data.

    It intentionally supplies only market-price fields. Fundamental metrics stay
    with the deterministic demo provider unless a licensed fundamentals source is
    configured, so the app never pretends to have live fundamentals it cannot verify.
    """

    def get_snapshot(self, symbol: str) -> dict:
        yahoo_symbol = f"{symbol.upper()}.NS"
        url = "https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(yahoo_symbol) + "?range=1d&interval=1m"
        req = urllib.request.Request(url, headers={"User-Agent": "SIGNALORY/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            result = payload["chart"]["result"][0]
            meta = result["meta"]
            price = meta.get("regularMarketPrice") or meta.get("previousClose")
            previous_close = meta.get("previousClose") or meta.get("chartPreviousClose")
            if price is None or previous_close in (None, 0):
                raise MarketDataUnavailable("Yahoo returned incomplete price data")
            change_pct = ((float(price) - float(previous_close)) / float(previous_close)) * 100
            return {
                "symbol": symbol.upper(),
                "name": symbol.upper(),
                "price": round(float(price), 2),
                "change_pct": round(change_pct, 2),
                "previous_close": round(float(previous_close), 2),
                "volume": int(meta.get("regularMarketVolume") or 0),
                "metrics": {},
                "source": "Yahoo Finance",
                "fetched_at": datetime.now(timezone.utc),
            }
        except Exception as exc:
            raise MarketDataUnavailable(str(exc)) from exc

def get_default_provider() -> MarketDataProvider:
    """Select the provider without coupling the rest of the app to it.

    `auto` tries live price data and the caller can fall back to the last known
    database snapshot; `mock` is deterministic and ideal for the hackathon demo.
    """
    import os
    mode = os.environ.get("MARKET_DATA_MODE", "auto").lower()
    if mode in {"yahoo", "auto"}:
        return YahooFinanceProvider()
    return MockMarketDataProvider()
