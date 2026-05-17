import logging
import random
import time
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from models.database import save_market_data, get_market_data

logger = logging.getLogger(__name__)

# Key tickers to track by sector
WATCHLIST = [
    # Major Indices
    {"ticker": "^GSPC", "name": "S&P 500", "sector": "Index"},
    {"ticker": "^DJI", "name": "Dow Jones", "sector": "Index"},
    {"ticker": "^IXIC", "name": "NASDAQ", "sector": "Index"},
    {"ticker": "^RUT", "name": "Russell 2000", "sector": "Index"},
    {"ticker": "^VIX", "name": "VIX Volatility", "sector": "Index"},
    # Tech
    {"ticker": "AAPL", "name": "Apple", "sector": "Tech"},
    {"ticker": "MSFT", "name": "Microsoft", "sector": "Tech"},
    {"ticker": "GOOGL", "name": "Alphabet", "sector": "Tech"},
    {"ticker": "NVDA", "name": "NVIDIA", "sector": "Tech"},
    {"ticker": "META", "name": "Meta", "sector": "Tech"},
    {"ticker": "TSLA", "name": "Tesla", "sector": "Tech"},
    {"ticker": "AVGO", "name": "Broadcom", "sector": "Tech"},
    # Markets / Finance
    {"ticker": "JPM", "name": "JPMorgan Chase", "sector": "Finance"},
    {"ticker": "GS", "name": "Goldman Sachs", "sector": "Finance"},
    {"ticker": "V", "name": "Visa", "sector": "Finance"},
    {"ticker": "MA", "name": "Mastercard", "sector": "Finance"},
    {"ticker": "BAC", "name": "Bank of America", "sector": "Finance"},
    {"ticker": "BRK-B", "name": "Berkshire Hathaway", "sector": "Finance"},
    # Energy
    {"ticker": "XOM", "name": "Exxon Mobil", "sector": "Energy"},
    {"ticker": "CVX", "name": "Chevron", "sector": "Energy"},
    {"ticker": "COP", "name": "ConocoPhillips", "sector": "Energy"},
    {"ticker": "SLB", "name": "Schlumberger", "sector": "Energy"},
    # Healthcare
    {"ticker": "UNH", "name": "UnitedHealth", "sector": "Healthcare"},
    {"ticker": "JNJ", "name": "Johnson & Johnson", "sector": "Healthcare"},
    {"ticker": "PFE", "name": "Pfizer", "sector": "Healthcare"},
    {"ticker": "LLY", "name": "Eli Lilly", "sector": "Healthcare"},
    # Consumer
    {"ticker": "WMT", "name": "Walmart", "sector": "Consumer"},
    {"ticker": "AMZN", "name": "Amazon", "sector": "Consumer/ Tech"},
    {"ticker": "HD", "name": "Home Depot", "sector": "Consumer"},
    {"ticker": "MCD", "name": "McDonald's", "sector": "Consumer"},
    {"ticker": "NKE", "name": "Nike", "sector": "Consumer"},
    # India / Emerging Markets
    {"ticker": "^BSESN", "name": "BSE Sensex", "sector": "India"},
    {"ticker": "^NSEI", "name": "Nifty 50", "sector": "India"},
    {"ticker": "EEM", "name": "iShares MSCI Emerging Markets", "sector": "Markets"},
]

MAX_RETRIES = 3
RETRY_DELAY_S = 1.5


def _is_index(ticker: str) -> bool:
    """Check if a ticker is a market index (starts with ^)."""
    return ticker.startswith("^")


def _format_market_cap(market_cap: float | None) -> str | None:
    """Format a market cap number into a human-readable string."""
    if not market_cap:
        return None
    if market_cap >= 1e12:
        return f"${market_cap / 1e12:.2f}T"
    elif market_cap >= 1e9:
        return f"${market_cap / 1e9:.2f}B"
    elif market_cap >= 1e6:
        return f"${market_cap / 1e6:.2f}M"
    else:
        return f"${market_cap:,.0f}"


def _fetch_one(item: dict) -> dict | None:
    """Fetch market data for a single ticker with retries. Runs in a worker thread."""
    ticker_symbol = item["ticker"]

    for attempt in range(MAX_RETRIES):
        try:
            # Add jitter to avoid thundering herd
            if attempt > 0:
                time.sleep(RETRY_DELAY_S * attempt + random.uniform(0, 0.5))

            ticker = yf.Ticker(ticker_symbol)
            # Try to get info dict (contains currentPrice, marketCap, etc.)
            info = ticker.info if ticker.info else {}

            if not info or info == {}:
                # yfinance may return an empty dict when rate-limited
                if attempt < MAX_RETRIES - 1:
                    continue
                return None

            price = info.get("regularMarketPrice") or info.get("currentPrice") or info.get("previousClose") or 0
            prev_close = info.get("regularMarketPreviousClose") or info.get("previousClose") or price

            if price and prev_close and prev_close > 0:
                change = round(price - prev_close, 2)
                change_pct = round((change / prev_close) * 100, 2)
            else:
                # Fallback to fast_info if info is sparse (common for indices)
                try:
                    fast = ticker.fast_info
                    price = fast.get("lastPrice", 0)
                    prev_close = fast.get("previousClose", 0) or price
                    change = round(price - prev_close, 2)
                    change_pct = round((change / prev_close) * 100, 2) if prev_close > 0 else 0
                except Exception:
                    if attempt < MAX_RETRIES - 1:
                        continue
                    return None

            return {
                "ticker": ticker_symbol,
                "name": item["name"],
                "price": round(price, 2) if price else 0,
                "change": change,
                "change_pct": change_pct,
                "market_cap": _format_market_cap(info.get("marketCap")),
                "sector": item["sector"],
            }

        except Exception:
            if attempt < MAX_RETRIES - 1:
                continue
            return None

    return None


def fetch_and_store_market_data() -> list[dict]:
    """Fetch stock prices for all watchlist tickers in parallel and store in DB.

    Uses a ThreadPoolExecutor (8 workers) to parallelize I/O-bound yfinance
    API calls. Each ticker gets up to 3 retries with jittered delays.
    """
    results: list[dict] = []
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        future_map = {executor.submit(_fetch_one, item): item for item in WATCHLIST}

        for future in as_completed(future_map):
            item = future_map[future]
            try:
                result = future.result()
                if result is not None:
                    results.append(result)
                else:
                    errors.append(item["ticker"])
            except Exception as e:
                errors.append(f"{item['ticker']}: {e}")

    # Store in database (single batch write)
    if results:
        try:
            save_market_data(results)
        except Exception as e:
            logger.error(f"Failed to save market data: {e}")

    if errors:
        logger.warning(f"Market data fetch errors ({len(errors)}): {errors[:3]}...")

    logger.info(f"Fetched market data: {len(results)} tickers (from {len(WATCHLIST)} watchlist items)")
    return results


def get_big_market_movers(threshold: float = 0.75) -> dict:
    """Get significant market movers (stocks with > threshold% change).

    Indices are identified by tickers starting with '^'. Lowered from 1.5%
    to 0.75% so data shows on calm market days.
    """
    data = get_market_data()

    # Exclude indices from gainers/losers using the ^ prefix check
    gainers = [d for d in data if d["change_pct"] >= threshold and not _is_index(d["ticker"])]
    losers = [d for d in data if d["change_pct"] <= -threshold and not _is_index(d["ticker"])]

    # Include any ticker whose sector is 'Index' OR whose ticker starts with ^
    indices = [d for d in data if d["sector"] == "Index" or _is_index(d["ticker"])]

    return {
        "gainers": sorted(gainers, key=lambda x: -x["change_pct"])[:10],
        "losers": sorted(losers, key=lambda x: x["change_pct"])[:10],
        "indices": sorted(indices, key=lambda x: -abs(x.get("change_pct", 0)))[:5],
        "all": data,
    }
