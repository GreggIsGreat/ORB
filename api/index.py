# Save this as: api/index.py

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from datetime import datetime, timedelta
import pytz
import urllib.request
import json
import os
import ssl
import gzip

app = FastAPI()

# ═══════════════════════════════════════════════
# RAILWAY SCRAPER CONFIGURATION
# ═══════════════════════════════════════════════
# Set this env var to your Railway scraper URL:
#   SCRAPER_URL=https://your-scraper.railway.app
#
# Optional symbol overrides:
#   SCRAPER_SYM_NAS100=NAS100
#   SCRAPER_SYM_BTCUSD=BTCUSD
#   SCRAPER_SYM_GOLD=XAUUSD
# ═══════════════════════════════════════════════
SCRAPER_BASE_URL = os.environ.get("SCRAPER_URL", "").rstrip("/")

SCRAPER_SYMBOLS = {
    "NAS100": os.environ.get("SCRAPER_SYM_NAS100", "NAS100"),
    "BTCUSD": os.environ.get("SCRAPER_SYM_BTCUSD", "BTCUSD"),
    "GOLD": os.environ.get("SCRAPER_SYM_GOLD", "XAUUSD"),
}

# ═══════════════════════════════════════════════
# CONFIGS - GOLD UPDATED FROM BACKTEST
# ═══════════════════════════════════════════════
CONFIGS = {
    "NAS100": {
        "tv": "OANDA:NAS100USD",
        "investing_id": "8874",
        "yahoo": "NQ=F",
        "max_range": 80, 
        "max_fvg": None, 
        "max_speed": 30, 
        "weekend": False,
        "range": [(30,45,3),(0,30,1),(45,60,1),(60,80,0)],
        "fvg": [(15,9999,2),(0,3,2),(7,15,1),(3,7,0)],
        "speed": [(0,10,3),(10,20,2),(20,30,1)],
        "best_day": ("Tuesday",3), 
        "good_days": [("Thursday",1)],
        "worst_day": ("Wednesday",-2), 
        "bias": ("LONG",1),
        "windows": None
    },
    
    "BTCUSD": {
        "tv": "BITSTAMP:BTCUSD",
        "investing_id": None,
        "yahoo": "BTC-USD",
        "max_range": 750, 
        "max_fvg": 200, 
        "max_speed": None, 
        "weekend": True,
        "range": [(350,500,3),(200,350,2),(0,200,1),(500,750,0)],
        "fvg": [(25,50,3),(0,25,2),(50,100,0),(100,200,0)],
        "speed": [(60,120,3),(30,60,2),(120,9999,1),(0,30,0)],
        "best_day": ("Sunday",3), 
        "good_days": [("Saturday",2),("Tuesday",2),("Thursday",1)],
        "worst_day": ("Friday",-2), 
        "bias": None,
        "windows": None
    },
    
    "GOLD": {
        "tv": "OANDA:XAUUSD",
        "investing_id": "8830",
        "yahoo": "GC=F",
        "max_range": None,
        "max_fvg": None,
        "max_speed": None,
        "weekend": False,
        "range": [
            (0, 5, 3),
            (5, 10, 2),
            (10, 15, 2),
            (25, 9999, 1),
            (15, 25, 0),
        ],
        "fvg": [
            (1, 3, 2),
            (0, 1, 1),
            (5, 10, 1),
            (3, 5, 0),
            (10, 9999, 0),
        ],
        "speed": [
            (60, 120, 3),
            (0, 10, 1),
            (10, 30, 1),
            (30, 60, 0),
            (120, 9999, 0),
        ],
        "best_day": ("Friday", 3),
        "good_days": [("Tuesday", 3), ("Wednesday", 1)],
        "worst_day": ("Monday", -2),
        "bias": None,
        "windows": {
            "09:00": {"start": 900, "end": 959, "score": 3, "wr": "73%+"},
            "13:00": {"start": 1300, "end": 1359, "score": 3, "wr": "73%+"},
            "14:30": {"start": 1430, "end": 1529, "score": 2, "wr": "71.4%"},
            "08:00": {"start": 800, "end": 859, "score": 2, "wr": "69.4%"},
            "16:00": {"start": 1600, "end": 1659, "score": 1, "wr": "65.9%"},
        },
        "min_score": 7
    }
}

# ═══════════════════════════════════════════════
# CACHE
# ═══════════════════════════════════════════════
cache = {}
CACHE_TTL = 30

def get_cached(key):
    if key in cache:
        data, ts = cache[key]
        if (datetime.now().timestamp() - ts) < CACHE_TTL:
            return data
    return None

def set_cached(key, data):
    cache[key] = (data, datetime.now().timestamp())

# ═══════════════════════════════════════════════
# HTTP HELPERS
# ═══════════════════════════════════════════════
def http_get_raw(url, headers=None):
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        default_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        
        if headers:
            default_headers.update(headers)
        
        req = urllib.request.Request(url, headers=default_headers)
        resp = urllib.request.urlopen(req, timeout=15, context=ctx)
        
        raw_data = resp.read()
        
        if raw_data[:2] == b'\x1f\x8b':
            try:
                raw_data = gzip.decompress(raw_data)
            except:
                pass
        
        encoding = resp.info().get('Content-Encoding', '')
        if 'gzip' in encoding.lower() and raw_data[:2] != b'\x1f\x8b':
            try:
                raw_data = gzip.decompress(raw_data)
            except:
                pass
        
        return raw_data.decode('utf-8')
        
    except Exception as e:
        raise Exception(f"HTTP Error: {str(e)}")


def http_get_json(url, headers=None):
    try:
        text = http_get_raw(url, headers)
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise Exception(f"JSON Error: {str(e)}")
    except Exception as e:
        raise e

# ═══════════════════════════════════════════════
# RAILWAY SCRAPER - PRIMARY DATA SOURCE
# ═══════════════════════════════════════════════

def scrape_from_railway(asset, interval="1m", limit=500):
    """
    Fetch candle data from your Railway-deployed scraper.
    
    Tries multiple endpoint patterns to be compatible with
    various scraper API designs. Adjust the URL pattern below
    to match your scraper's actual endpoints.
    
    Expected response format (any of these work):
    
    1. Array of candles:
       [{"time":"09:30","open":3200,"high":3210,"low":3195,"close":3205}, ...]
    
    2. Object with candles array:
       {"candles": [...], "symbol": "XAUUSD"}
       {"data": [...]}
       {"result": [...]}
    
    3. Candles with timestamps:
       [{"timestamp":1700000000,"o":3200,"h":3210,"l":3195,"c":3205}, ...]
       [{"t":1700000000,"open":3200,"high":3210,"low":3195,"close":3205}, ...]
    
    4. ISO datetime format:
       [{"datetime":"2024-01-15T09:30:00Z","open":3200,...}, ...]
    """
    if not SCRAPER_BASE_URL:
        return [], "SCRAPER_URL not configured"
    
    try:
        symbol = SCRAPER_SYMBOLS.get(asset, asset)
        
        # ═══════════════════════════════════════════
        # ADJUST THESE URL PATTERNS TO MATCH YOUR 
        # RAILWAY SCRAPER'S API ENDPOINTS
        # ═══════════════════════════════════════════
        endpoints = [
            f"{SCRAPER_BASE_URL}/api/candles?symbol={symbol}&interval={interval}&limit={limit}",
            f"{SCRAPER_BASE_URL}/api/candles/{symbol}?interval={interval}&limit={limit}",
            f"{SCRAPER_BASE_URL}/api/ohlc?symbol={symbol}&interval={interval}&limit={limit}",
            f"{SCRAPER_BASE_URL}/api/scrape/{symbol}?interval={interval}&limit={limit}",
            f"{SCRAPER_BASE_URL}/api/{symbol.lower()}?interval={interval}&limit={limit}",
        ]
        
        data = None
        last_error = None
        successful_url = None
        
        for url in endpoints:
            try:
                data = http_get_json(url)
                if data:
                    successful_url = url
                    break
            except Exception as e:
                last_error = str(e)
                continue
        
        if not data:
            return [], f"All scraper endpoints failed. Last error: {last_error}"
        
        # ═══ PARSE RESPONSE ═══
        candles_raw = []
        
        if isinstance(data, list):
            candles_raw = data
        elif isinstance(data, dict):
            # Try common response wrapper keys
            for key in ["candles", "data", "result", "ohlc", "bars", "klines"]:
                if key in data and isinstance(data[key], list):
                    candles_raw = data[key]
                    break
            
            if not candles_raw:
                # Maybe the dict itself contains OHLC arrays (like TradingView format)
                if "t" in data and isinstance(data["t"], list):
                    # TradingView-style: {t:[], o:[], h:[], l:[], c:[]}
                    times = data.get("t", [])
                    opens = data.get("o", [])
                    highs = data.get("h", [])
                    lows = data.get("l", [])
                    closes = data.get("c", [])
                    
                    et = pytz.timezone('US/Eastern')
                    candles = []
                    for i in range(len(times)):
                        try:
                            ts = times[i]
                            if ts > 1e12:
                                ts = ts / 1000
                            dt = datetime.fromtimestamp(ts, tz=et)
                            candles.append({
                                "time": dt.strftime("%H:%M"),
                                "open": float(opens[i]),
                                "high": float(highs[i]),
                                "low": float(lows[i]),
                                "close": float(closes[i])
                            })
                        except (IndexError, TypeError, ValueError):
                            continue
                    return candles, None
        
        if not candles_raw:
            return [], "No candle data found in scraper response"
        
        # ═══ NORMALIZE CANDLE FORMAT ═══
        et = pytz.timezone('US/Eastern')
        candles = []
        
        for item in candles_raw:
            try:
                # --- Parse timestamp/time ---
                time_str = None
                
                # Already formatted "HH:MM"
                if 'time' in item and isinstance(item['time'], str) and ':' in str(item['time']):
                    time_str = str(item['time'])[:5]  # Take "HH:MM"
                
                # Unix timestamp
                elif 'timestamp' in item or 't' in item:
                    ts = item.get('timestamp', item.get('t', 0))
                    if isinstance(ts, (int, float)):
                        if ts > 1e12:  # milliseconds
                            ts = ts / 1000
                        dt = datetime.fromtimestamp(ts, tz=et)
                        time_str = dt.strftime("%H:%M")
                
                # ISO datetime string
                elif 'datetime' in item or 'date' in item:
                    dt_str = str(item.get('datetime', item.get('date', '')))
                    dt_str = dt_str.replace('Z', '+00:00')
                    try:
                        dt = datetime.fromisoformat(dt_str)
                        if dt.tzinfo is None:
                            dt = et.localize(dt)
                        else:
                            dt = dt.astimezone(et)
                        time_str = dt.strftime("%H:%M")
                    except:
                        continue
                
                if not time_str:
                    continue
                
                # --- Parse OHLC values ---
                o = float(item.get('open', item.get('o', 0)))
                h = float(item.get('high', item.get('h', 0)))
                l = float(item.get('low', item.get('l', 0)))
                c = float(item.get('close', item.get('c', 0)))
                
                # Skip zero/invalid candles
                if o == 0 and h == 0 and l == 0 and c == 0:
                    continue
                
                candles.append({
                    "time": time_str,
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c
                })
                
            except (ValueError, TypeError, KeyError):
                continue
        
        if candles:
            return candles, None
        else:
            return [], "Could not parse any candles from scraper response"
        
    except Exception as e:
        return [], f"Railway scraper error: {str(e)}"


def get_railway_current_price(asset):
    """Try to get just the current price from Railway scraper"""
    if not SCRAPER_BASE_URL:
        return None
    
    try:
        symbol = SCRAPER_SYMBOLS.get(asset, asset)
        
        # Try price endpoint
        endpoints = [
            f"{SCRAPER_BASE_URL}/api/price?symbol={symbol}",
            f"{SCRAPER_BASE_URL}/api/price/{symbol}",
            f"{SCRAPER_BASE_URL}/api/ticker?symbol={symbol}",
            f"{SCRAPER_BASE_URL}/api/ticker/{symbol}",
        ]
        
        for url in endpoints:
            try:
                data = http_get_json(url)
                if data:
                    # Try various response formats
                    price = (
                        data.get('price') or 
                        data.get('last') or 
                        data.get('close') or 
                        data.get('c') or
                        data.get('current_price') or
                        (data.get('data', {}).get('price') if isinstance(data.get('data'), dict) else None)
                    )
                    if price:
                        return float(price)
            except:
                continue
        
        return None
    except:
        return None

# ═══════════════════════════════════════════════
# FALLBACK SCRAPERS (Binance, Yahoo, Investing)
# ═══════════════════════════════════════════════

def scrape_binance(interval, limit):
    try:
        iv = "1m" if interval == "1min" else "15m"
        url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval={iv}&limit={limit}"
        
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        }
        
        data = http_get_json(url, headers)
        
        et = pytz.timezone('US/Eastern')
        candles = []
        
        for k in data:
            dt = datetime.fromtimestamp(int(k[0]) / 1000, tz=et)
            candles.append({
                "time": dt.strftime("%H:%M"),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4])
            })
        
        return candles, None
        
    except Exception as e:
        return [], str(e)


def scrape_yahoo_finance(symbol, interval="1m", period="1d"):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }
        
        data = http_get_json(url, headers)
        
        result = data.get("chart", {}).get("result", [])
        if not result:
            return [], "No data from Yahoo"
        
        quotes = result[0]
        timestamps = quotes.get("timestamp", [])
        ohlc = quotes.get("indicators", {}).get("quote", [{}])[0]
        
        if not timestamps:
            return [], "No timestamps in Yahoo response"
        
        et = pytz.timezone('US/Eastern')
        candles = []
        
        for i in range(len(timestamps)):
            try:
                o = ohlc.get("open", [])[i]
                h = ohlc.get("high", [])[i]
                l = ohlc.get("low", [])[i]
                c = ohlc.get("close", [])[i]
                
                if o is None or h is None or l is None or c is None:
                    continue
                
                dt = datetime.fromtimestamp(timestamps[i], tz=et)
                candles.append({
                    "time": dt.strftime("%H:%M"),
                    "open": float(o),
                    "high": float(h),
                    "low": float(l),
                    "close": float(c)
                })
            except (IndexError, TypeError):
                continue
        
        return candles, None
        
    except Exception as e:
        return [], str(e)


def scrape_investing(pair_id, interval="1", count=500):
    try:
        et = pytz.timezone('US/Eastern')
        now = datetime.now(et)
        end_ts = int(now.timestamp())
        
        if interval == "1":
            start_ts = end_ts - (12 * 60 * 60)
        else:
            start_ts = end_ts - (5 * 24 * 60 * 60)
        
        url = f"https://tvc6.investing.com/bc498743e6cd7b99f089f1c5c1c9e5d7/{end_ts}/1/1/8/history?symbol={pair_id}&resolution={interval}&from={start_ts}&to={end_ts}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
            "Referer": "https://www.investing.com/",
            "Origin": "https://www.investing.com",
        }
        
        data = http_get_json(url, headers)
        
        if data.get("s") != "ok":
            return [], f"Investing returned: {data.get('s', 'error')}"
        
        times = data.get("t", [])
        opens = data.get("o", [])
        highs = data.get("h", [])
        lows = data.get("l", [])
        closes = data.get("c", [])
        
        if not times:
            return [], "No candle data"
        
        candles = []
        for i in range(len(times)):
            dt = datetime.fromtimestamp(times[i], tz=et)
            candles.append({
                "time": dt.strftime("%H:%M"),
                "open": float(opens[i]),
                "high": float(highs[i]),
                "low": float(lows[i]),
                "close": float(closes[i])
            })
        
        return candles, None
        
    except Exception as e:
        return [], str(e)


# ═══════════════════════════════════════════════
# COMBINED SCRAPER - RAILWAY FIRST, THEN FALLBACK
# ═══════════════════════════════════════════════

def scrape_asset(asset):
    cached = get_cached(asset)
    if cached:
        return cached

    config = CONFIGS[asset]
    result = {
        "asset": asset, 
        "tv": config["tv"],
        "status": "ERROR", 
        "candles": [],
        "ma50": None, 
        "ma200": None, 
        "price": None, 
        "prev_close": None,
        "day_open": None,
        "error": None,
        "source": None,
        "source_tier": 3  # 1=Railway, 2=Primary fallback, 3=Yahoo fallback
    }

    candles_15 = []
    candles_1 = []
    
    try:
        # ═══════════════════════════════════════════
        # TIER 1: TRY RAILWAY SCRAPER FIRST
        # ═══════════════════════════════════════════
        if SCRAPER_BASE_URL:
            candles_15, err15 = scrape_from_railway(asset, "15m", 300)
            if candles_15 and len(candles_15) >= 50:
                candles_1, err1 = scrape_from_railway(asset, "1m", 500)
                result["source"] = "Railway Scraper"
                result["source_tier"] = 1
            else:
                candles_15 = []  # Reset for fallback

        # ═══════════════════════════════════════════
        # TIER 2: FALLBACK TO BINANCE/INVESTING.COM
        # ═══════════════════════════════════════════
        if not candles_15 or len(candles_15) < 50:
            if asset == "BTCUSD":
                candles_15, err = scrape_binance("15min", 300)
                if candles_15 and len(candles_15) >= 50:
                    candles_1, _ = scrape_binance("1min", 500)
                    result["source"] = "Binance"
                    result["source_tier"] = 2
                else:
                    candles_15 = []
            else:
                pair_id = config["investing_id"]
                if pair_id:
                    candles_15, err = scrape_investing(pair_id, "15", 300)
                    if candles_15 and len(candles_15) >= 50:
                        candles_1, _ = scrape_investing(pair_id, "1", 500)
                        result["source"] = "Investing.com"
                        result["source_tier"] = 2
                    else:
                        candles_15 = []

        # ═══════════════════════════════════════════
        # TIER 3: FALLBACK TO YAHOO FINANCE
        # ═══════════════════════════════════════════
        if not candles_15 or len(candles_15) < 50:
            yahoo_symbol = config["yahoo"]
            candles_15, err = scrape_yahoo_finance(yahoo_symbol, "15m", "5d")
            candles_1, _ = scrape_yahoo_finance(yahoo_symbol, "1m", "1d")
            result["source"] = "Yahoo Finance"
            result["source_tier"] = 3
            
            if not candles_15:
                result["error"] = f"All sources failed: {err}"
                set_cached(asset, result)
                return result

        # ═══ CALCULATE MAs ═══
        if len(candles_15) >= 200:
            closes = [c['close'] for c in candles_15]
            result["ma50"] = round(sum(closes[-50:]) / 50, 2)
            result["ma200"] = round(sum(closes[-200:]) / 200, 2)
        elif len(candles_15) >= 50:
            closes = [c['close'] for c in candles_15]
            result["ma50"] = round(sum(closes[-50:]) / 50, 2)
            result["ma200"] = round(sum(closes) / len(closes), 2)
        else:
            result["error"] = f"Only {len(candles_15)} 15min bars (need 50+)"
            set_cached(asset, result)
            return result

        # ═══ SET CANDLES & PRICE ═══
        if candles_1 and len(candles_1) > 0:
            result["candles"] = candles_1
            result["price"] = round(candles_1[-1]['close'], 2)
            result["day_open"] = round(candles_1[0]['open'], 2)
            result["status"] = "OK"
            result["candle_count"] = len(candles_1)
        else:
            result["candles"] = candles_15[-60:]
            result["price"] = round(candles_15[-1]['close'], 2)
            result["day_open"] = round(candles_15[0]['open'], 2) if candles_15 else None
            result["status"] = "OK"
            result["candle_count"] = len(candles_15)
            result["source"] += " (15min)"
        
        # ═══ CALCULATE DAILY CHANGE ═══
        if result["price"] and result["day_open"]:
            result["price_change"] = round(result["price"] - result["day_open"], 2)
            if result["day_open"] != 0:
                result["price_change_pct"] = round(
                    ((result["price"] - result["day_open"]) / result["day_open"]) * 100, 3
                )
            else:
                result["price_change_pct"] = 0

    except Exception as e:
        result["error"] = str(e)

    set_cached(asset, result)
    return result


def scrape_all():
    results = {}
    for asset in ["NAS100", "BTCUSD", "GOLD"]:
        results[asset] = scrape_asset(asset)
    return results

# ═══════════════════════════════════════════════
# WINDOW DETECTION
# ═══════════════════════════════════════════════
def get_current_window(asset, now):
    config = CONFIGS[asset]
    if not config.get("windows"):
        return None, None
    current = now.hour * 100 + now.minute
    for label, w in config["windows"].items():
        if w["start"] <= current <= w["end"]:
            return label, w
    return None, None

def get_next_window(asset, now):
    config = CONFIGS[asset]
    if not config.get("windows"):
        return None
    current = now.hour * 100 + now.minute
    sorted_windows = sorted(config["windows"].items(), key=lambda x: x[1]["start"])
    for label, w in sorted_windows:
        if w["start"] > current:
            return label
    return sorted_windows[0][0] if sorted_windows else None

# ═══════════════════════════════════════════════
# SCORING MODEL
# ═══════════════════════════════════════════════
def score_trade(asset, range_size, fvg_size, speed, direction, date, window=None):
    c = CONFIGS[asset]
    score = 0
    reasons = []
    
    if c["max_range"] and range_size > c["max_range"]:
        return {"score":0,"take_trade":False,"confidence":"REJECTED","reasons":["Range too wide"]}
    if c["max_fvg"] and fvg_size > c["max_fvg"]:
        return {"score":0,"take_trade":False,"confidence":"REJECTED","reasons":["FVG too large"]}
    if c["max_speed"] and speed > c["max_speed"]:
        return {"score":0,"take_trade":False,"confidence":"REJECTED","reasons":["Breakout too slow"]}
    
    if c.get("windows") and window and window in c["windows"]:
        w = c["windows"][window]
        score += w["score"]
        reasons.append(f"{window} window ({w['wr']}) → +{w['score']}")
    
    for low, high, pts in c["range"]:
        if low <= range_size <= high:
            score += pts
            if pts > 0:
                reasons.append(f"Range ${low}-${high} → +{pts}")
            break
    
    for low, high, pts in c["fvg"]:
        if low <= fvg_size <= high:
            score += pts
            if pts > 0:
                reasons.append(f"FVG ${low}-${high} → +{pts}")
            break
    
    for low, high, pts in c["speed"]:
        if low <= speed <= high:
            score += pts
            if pts > 0:
                reasons.append(f"Speed {low}-{high} bars → +{pts}")
            break
    
    try:
        y, m, d = map(int, str(date).split('-')[:3])
        day = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'][datetime(y,m,d).weekday()]
    except:
        day = datetime.now().strftime("%A")
    
    if c["best_day"] and day == c["best_day"][0]:
        score += c["best_day"][1]
        reasons.append(f"{day} → +{c['best_day'][1]}")
    else:
        for gd, pts in c["good_days"]:
            if day == gd:
                score += pts
                reasons.append(f"{day} → +{pts}")
                break
    
    if c["worst_day"] and day == c["worst_day"][0]:
        score += c["worst_day"][1]
        reasons.append(f"{day} → {c['worst_day'][1]} ⚠️")
    
    if c["bias"] and direction == c["bias"][0]:
        score += c["bias"][1]
        reasons.append(f"{direction} bias → +{c['bias'][1]}")
    
    min_score = c.get("min_score", 5)
    
    if asset == "GOLD":
        confidence = "HIGH" if score >= 9 else "MEDIUM" if score >= 7 else "LOW"
    else:
        confidence = "HIGH" if score >= 7 else "MEDIUM" if score >= 5 else "LOW"
    
    return {
        "score": score,
        "take_trade": score >= min_score,
        "confidence": confidence,
        "reasons": reasons
    }

def detect_fvg(c1, c2, c3, direction):
    if direction == "LONG":
        fvg = c3['low'] - c1['high']
        if fvg > 0 and c2['close'] > c2['open']:
            return {"valid":True,"size":round(fvg,2),"entry":c3['low']}
    elif direction == "SHORT":
        fvg = c1['low'] - c3['high']
        if fvg > 0 and c2['close'] < c2['open']:
            return {"valid":True,"size":round(fvg,2),"entry":c3['high']}
    return {"valid":False,"size":0,"entry":0}

# ═══════════════════════════════════════════════
# SCANNER
# ═══════════════════════════════════════════════
def run_scan(asset, scraped):
    config = CONFIGS[asset]
    et = pytz.timezone('US/Eastern')
    now = datetime.now(et)
    
    current_window, window_info = get_current_window(asset, now)
    next_window = get_next_window(asset, now) if not current_window else None
    
    base = {
        "asset": asset, 
        "tv": config["tv"], 
        "time": now.strftime("%H:%M:%S"), 
        "day": now.strftime("%A"),
        "window": current_window,
        "next_window": next_window,
        "source": scraped.get("source", "Unknown"),
        "source_tier": scraped.get("source_tier", 3),
        "price": scraped.get("price"),
        "price_change": scraped.get("price_change"),
        "price_change_pct": scraped.get("price_change_pct"),
        "day_open": scraped.get("day_open"),
        "ma50": scraped.get("ma50"),
        "ma200": scraped.get("ma200"),
    }

    if not config["weekend"] and now.weekday() >= 5:
        return {**base, "status": "CLOSED", "message": "Weekend — markets closed"}
    
    if asset == "GOLD" and config.get("windows"):
        if not current_window:
            next_w = next_window or "08:00 tomorrow"
            return {
                **base, 
                "status": "WAITING", 
                "message": f"Outside trading windows. Next: {next_w}",
                "trend": "BULLISH" if scraped.get("ma50", 0) > scraped.get("ma200", 0) else "BEARISH"
            }
    else:
        if not config["weekend"] and now.hour < 9:
            h = 9 - now.hour
            m = 30 - now.minute
            if m < 0:
                h -= 1
                m += 60
            return {**base, "status": "PRE_MARKET", "message": f"NY opens in {h}h {m}m"}
        
        if not config["weekend"] and now.hour >= 17:
            return {**base, "status": "CLOSED", "message": "NY session ended"}

    if scraped["status"] == "ERROR":
        return {**base, "status": "ERROR", "message": scraped.get("error", "Scraper failed")}

    ma50 = scraped["ma50"]
    ma200 = scraped["ma200"]
    trend = "BULLISH" if ma50 and ma200 and ma50 > ma200 else "BEARISH" if ma50 and ma200 else "UNKNOWN"

    if scraped["status"] in ["NO_1MIN", "NO_CANDLES"]:
        return {
            **base, 
            "status": "ERROR", 
            "message": scraped.get("error", "No candle data"),
            "trend": trend
        }

    candles = scraped["candles"]
    price = scraped["price"]

    if asset == "GOLD" and current_window:
        w = config["windows"][current_window]
        window_start = w["start"]
        window_end = window_start + 14
        oc = [c for c in candles if window_start <= int(c['time'].replace(':','')) <= window_end]
    elif asset == "BTCUSD":
        oc = candles[-30:-15] if len(candles) > 30 else candles[:15]
    else:
        oc = [c for c in candles if 930 <= int(c['time'].replace(':','')) <= 944]

    if not oc or len(oc) < 3:
        return {
            **base, 
            "status": "FORMING", 
            "message": f"Building opening range{' for ' + current_window if current_window else ''}",
            "trend": trend
        }

    rh = round(max(c['high'] for c in oc), 2)
    rl = round(min(c['low'] for c in oc), 2)
    rs = round(rh - rl, 2)

    if config["max_range"] and rs > config["max_range"]:
        return {
            **base, 
            "status": "NO_TRADE", 
            "message": f"Range too wide (${rs})",
            "trend": trend, 
            "range_high": rh, 
            "range_low": rl, 
            "range_size": rs
        }

    if asset == "GOLD" and current_window:
        w = config["windows"][current_window]
        post_start = w["start"] + 15
        post = [c for c in candles if int(c['time'].replace(':','')) >= post_start]
    elif asset == "BTCUSD":
        post = candles[-15:]
    else:
        post = [c for c in candles if int(c['time'].replace(':','')) >= 945]

    if len(post) < 3:
        return {
            **base, 
            "status": "FORMING", 
            "message": "Waiting for breakout candles",
            "trend": trend, 
            "range_high": rh, 
            "range_low": rl, 
            "range_size": rs
        }

    today = now.strftime("%Y-%m-%d")
    bias_dir = "LONG" if trend == "BULLISH" else "SHORT"

    for i in range(len(post) - 2):
        c1, c2, c3 = post[i], post[i+1], post[i+2]
        
        if bias_dir == "LONG" and c2['close'] > rh:
            fvg = detect_fvg(c1, c2, c3, "LONG")
            if fvg['valid']:
                pred = score_trade(asset, rs, fvg['size'], i+1, "LONG", today, window=current_window)
                return {
                    **base, 
                    "status": "TRADE" if pred["take_trade"] else "SKIP",
                    "message": f"{pred['confidence']} LONG — Score {pred['score']}/12",
                    "direction": "LONG", 
                    "entry": round(fvg['entry'],2), 
                    "stop": rl,
                    "target": round(fvg['entry'] + (fvg['entry'] - rl), 2),
                    "trend": trend,
                    "range_high": rh, 
                    "range_low": rl, 
                    "range_size": rs,
                    "fvg_size": fvg['size'], 
                    "speed": i+1,
                    "score": pred["score"], 
                    "confidence": pred["confidence"],
                    "reasons": pred["reasons"],
                    "fvg_detected": True
                }
        
        if bias_dir == "SHORT" and c2['close'] < rl:
            fvg = detect_fvg(c1, c2, c3, "SHORT")
            if fvg['valid']:
                pred = score_trade(asset, rs, fvg['size'], i+1, "SHORT", today, window=current_window)
                return {
                    **base, 
                    "status": "TRADE" if pred["take_trade"] else "SKIP",
                    "message": f"{pred['confidence']} SHORT — Score {pred['score']}/12",
                    "direction": "SHORT", 
                    "entry": round(fvg['entry'],2), 
                    "stop": rh,
                    "target": round(fvg['entry'] - (rh - fvg['entry']), 2),
                    "trend": trend,
                    "range_high": rh, 
                    "range_low": rl, 
                    "range_size": rs,
                    "fvg_size": fvg['size'], 
                    "speed": i+1,
                    "score": pred["score"], 
                    "confidence": pred["confidence"],
                    "reasons": pred["reasons"],
                    "fvg_detected": True
                }

    if price > rh:
        pm = f"Price ABOVE range (+${round(price - rh, 2)}) — Waiting for FVG"
    elif price < rl:
        pm = f"Price BELOW range (-${round(rl - price, 2)}) — Waiting for FVG"
    else:
        pm = "Price INSIDE range — No breakout yet"

    return {
        **base, 
        "status": "SCANNING", 
        "message": pm,
        "trend": trend,
        "range_high": rh, 
        "range_low": rl, 
        "range_size": rs,
        "fvg_detected": False
    }

# ═══════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════
@app.get("/api/scan")
def api_scan():
    scraped = scrape_all()
    results = {}
    for asset in ["NAS100", "BTCUSD", "GOLD"]:
        results[asset] = run_scan(asset, scraped[asset])
    return JSONResponse(content=results)

@app.get("/api/debug")
def api_debug():
    scraped = scrape_all()
    debug = {}
    for asset, data in scraped.items():
        debug[asset] = {
            "status": data["status"],
            "source": data.get("source"),
            "source_tier": data.get("source_tier"),
            "error": data.get("error"),
            "ma50": data.get("ma50"),
            "ma200": data.get("ma200"),
            "price": data.get("price"),
            "price_change": data.get("price_change"),
            "price_change_pct": data.get("price_change_pct"),
            "candle_count": data.get("candle_count", 0),
            "first_candle": data["candles"][0] if data["candles"] else None,
            "last_candle": data["candles"][-1] if data["candles"] else None,
        }
    
    debug["_scraper_config"] = {
        "url": SCRAPER_BASE_URL or "NOT SET",
        "symbols": SCRAPER_SYMBOLS,
        "connected": bool(SCRAPER_BASE_URL),
    }
    
    return JSONResponse(content=debug)

@app.get("/api/scraper-test")
def api_scraper_test():
    """Test connectivity to the Railway scraper"""
    if not SCRAPER_BASE_URL:
        return JSONResponse(content={
            "status": "NOT_CONFIGURED",
            "message": "Set SCRAPER_URL environment variable to your Railway scraper URL",
            "example": "SCRAPER_URL=https://your-scraper.railway.app"
        })
    
    results = {}
    for asset in ["NAS100", "BTCUSD", "GOLD"]:
        symbol = SCRAPER_SYMBOLS[asset]
        candles, error = scrape_from_railway(asset, "1m", 10)
        results[asset] = {
            "symbol": symbol,
            "success": len(candles) > 0,
            "candle_count": len(candles),
            "error": error,
            "sample": candles[:2] if candles else None,
        }
    
    all_ok = all(r["success"] for r in results.values())
    
    return JSONResponse(content={
        "status": "OK" if all_ok else "PARTIAL" if any(r["success"] for r in results.values()) else "FAILED",
        "scraper_url": SCRAPER_BASE_URL,
        "symbols": SCRAPER_SYMBOLS,
        "results": results
    })

@app.get("/api/health")
def health():
    return {
        "status": "ok", 
        "time": datetime.now().isoformat(),
        "scraper_configured": bool(SCRAPER_BASE_URL),
        "scraper_url": SCRAPER_BASE_URL or "not set"
    }

# ═══════════════════════════════════════════════
# UI WITH PRICE DISPLAY + SOURCE INDICATORS
# ═══════════════════════════════════════════════
@app.get("/", response_class=HTMLResponse)
def home():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>ORB Scanner</title>
<script src="https://cdn.tailwindcss.com"></script>
<script>
tailwind.config={
  theme:{
    extend:{
      colors:{
        bg:'#09090b',
        card:'#111113',
        border:'#1e1e22',
        accent:'#18181b'
      }
    }
  }
}
</script>
<style>
  @keyframes pulse-dot { 0%,100%{opacity:1} 50%{opacity:0.5} }
  @keyframes fvg-glow { 0%,100%{box-shadow:0 0 5px rgba(34,197,94,0.5)} 50%{box-shadow:0 0 20px rgba(34,197,94,0.8)} }
  @keyframes price-flash { 0%{background:rgba(34,197,94,0.15)} 100%{background:transparent} }
  .live-dot { animation: pulse-dot 2s infinite; }
  .fvg-glow { animation: fvg-glow 1.5s infinite; }
  .price-up { animation: price-flash 0.5s ease-out; }
  .glass { backdrop-filter: blur(10px); }
  * { -webkit-tap-highlight-color: transparent; }
  
  @media (max-width: 640px) {
    .info-grid { grid-template-columns: repeat(2, 1fr) !important; }
    .price-text { font-size: 1.25rem !important; }
  }
</style>
</head>
<body class="bg-bg text-gray-300 min-h-screen overscroll-none">

<header class="border-b border-border bg-card/80 glass sticky top-0 z-50">
  <div class="w-[96%] max-w-7xl mx-auto py-3">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-base sm:text-xl font-bold text-white">ORB Scanner</h1>
        <p class="text-[9px] sm:text-[11px] text-gray-600">Multi-Asset · Multi-Window</p>
      </div>
      <div class="flex items-center gap-3">
        <div class="text-right">
          <p class="text-xs sm:text-sm text-white font-mono" id="clock">--:--:--</p>
          <p class="text-[9px] sm:text-[10px] text-gray-600" id="date">Loading...</p>
        </div>
        <div class="flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full bg-green-500 live-dot"></span>
          <span class="text-[10px] text-green-400 font-medium" id="status">...</span>
        </div>
      </div>
    </div>
  </div>
</header>

<!-- ═══ PRICE TICKER BAR ═══ -->
<div class="border-b border-border bg-card/50" id="ticker-bar">
  <div class="w-[96%] max-w-7xl mx-auto py-2">
    <div class="flex items-center justify-between gap-4 overflow-x-auto" id="ticker">
      <div class="flex items-center gap-2 min-w-0">
        <span class="text-[10px] text-gray-600">Loading prices...</span>
      </div>
    </div>
  </div>
</div>

<main class="w-[96%] max-w-7xl mx-auto py-4">
  
  <div class="grid grid-cols-4 gap-2 mb-4">
    <div class="bg-card border border-border rounded-lg px-2 py-2 text-center">
      <p class="text-[8px] text-gray-600 uppercase">Markets</p>
      <p class="text-sm font-bold text-white">3</p>
    </div>
    <div class="bg-card border border-border rounded-lg px-2 py-2 text-center">
      <p class="text-[8px] text-gray-600 uppercase">Interval</p>
      <p class="text-sm font-bold text-white">2s</p>
    </div>
    <div class="bg-card border border-border rounded-lg px-2 py-2 text-center">
      <p class="text-[8px] text-gray-600 uppercase">Updates</p>
      <p class="text-sm font-bold text-white" id="refresh-count">0</p>
    </div>
    <div class="bg-card border border-border rounded-lg px-2 py-2 text-center">
      <p class="text-[8px] text-gray-600 uppercase">Source</p>
      <p class="text-sm font-bold" id="source-indicator">--</p>
    </div>
  </div>

  <div class="grid grid-cols-1 lg:grid-cols-3 gap-3" id="dashboard">
    <div class="bg-card border border-border rounded-xl p-5 animate-pulse"><div class="h-4 bg-accent rounded w-20 mb-3"></div><div class="h-8 bg-accent rounded w-32 mb-2"></div><div class="h-6 bg-accent rounded w-28"></div></div>
    <div class="bg-card border border-border rounded-xl p-5 animate-pulse"><div class="h-4 bg-accent rounded w-20 mb-3"></div><div class="h-8 bg-accent rounded w-32 mb-2"></div><div class="h-6 bg-accent rounded w-28"></div></div>
    <div class="bg-card border border-border rounded-xl p-5 animate-pulse"><div class="h-4 bg-accent rounded w-20 mb-3"></div><div class="h-8 bg-accent rounded w-32 mb-2"></div><div class="h-6 bg-accent rounded w-28"></div></div>
  </div>

  <div class="mt-4 text-center">
    <p class="text-[9px] text-gray-700">
      Railway Scraper · Binance · Investing.com · Yahoo · 
      <a href="/api/debug" class="text-blue-500 hover:underline">Debug</a> · 
      <a href="/api/scraper-test" class="text-blue-500 hover:underline">Test Scraper</a>
    </p>
  </div>
</main>

<script>
// ═══ STATUS CONFIGS ═══
const ST={TRADE:{bg:'bg-green-500/10',bd:'border-green-500/40',tx:'text-green-400',lb:'TRADE'},SKIP:{bg:'bg-yellow-500/10',bd:'border-yellow-500/40',tx:'text-yellow-400',lb:'SKIP'},SCANNING:{bg:'bg-blue-500/10',bd:'border-blue-500/40',tx:'text-blue-400',lb:'SCAN'},CLOSED:{bg:'bg-gray-500/10',bd:'border-gray-500/40',tx:'text-gray-500',lb:'CLOSED'},PRE_MARKET:{bg:'bg-purple-500/10',bd:'border-purple-500/40',tx:'text-purple-400',lb:'PRE'},WAITING:{bg:'bg-purple-500/10',bd:'border-purple-500/40',tx:'text-purple-400',lb:'WAIT'},FORMING:{bg:'bg-indigo-500/10',bd:'border-indigo-500/40',tx:'text-indigo-400',lb:'FORM'},NO_TRADE:{bg:'bg-orange-500/10',bd:'border-orange-500/40',tx:'text-orange-400',lb:'NO'},ERROR:{bg:'bg-red-500/10',bd:'border-red-500/40',tx:'text-red-400',lb:'ERR'}};

// ═══ SOURCE TIER COLORS ═══
const TIERS = {
  1: { color: 'text-green-400', bg: 'bg-green-500/10', border: 'border-green-500/30', label: 'Railway', dot: 'bg-green-500' },
  2: { color: 'text-yellow-400', bg: 'bg-yellow-500/10', border: 'border-yellow-500/30', label: 'Direct', dot: 'bg-yellow-500' },
  3: { color: 'text-orange-400', bg: 'bg-orange-500/10', border: 'border-orange-500/30', label: 'Yahoo', dot: 'bg-orange-500' },
};

// ═══ FVG ICONS ═══
const fvgIconLong = `<svg viewBox="0 0 60 40" class="w-12 h-8"><rect x="5" y="8" width="8" height="20" fill="#ef4444" rx="1"/><line x1="9" y1="4" x2="9" y2="8" stroke="#ef4444" stroke-width="2"/><line x1="9" y1="28" x2="9" y2="34" stroke="#ef4444" stroke-width="2"/><rect x="22" y="4" width="10" height="28" fill="#22c55e" rx="1"/><line x1="27" y1="2" x2="27" y2="4" stroke="#22c55e" stroke-width="2"/><line x1="27" y1="32" x2="27" y2="36" stroke="#22c55e" stroke-width="2"/><rect x="41" y="6" width="8" height="16" fill="#22c55e" rx="1"/><line x1="45" y1="2" x2="45" y2="6" stroke="#22c55e" stroke-width="2"/><line x1="45" y1="22" x2="45" y2="28" stroke="#22c55e" stroke-width="2"/><rect x="13" y="8" width="28" height="6" fill="#22c55e" fill-opacity="0.2" stroke="#22c55e" stroke-width="1" stroke-dasharray="2,2" rx="2"/></svg>`;
const fvgIconShort = `<svg viewBox="0 0 60 40" class="w-12 h-8"><rect x="5" y="12" width="8" height="20" fill="#22c55e" rx="1"/><line x1="9" y1="6" x2="9" y2="12" stroke="#22c55e" stroke-width="2"/><line x1="9" y1="32" x2="9" y2="36" stroke="#22c55e" stroke-width="2"/><rect x="22" y="8" width="10" height="28" fill="#ef4444" rx="1"/><line x1="27" y1="4" x2="27" y2="8" stroke="#ef4444" stroke-width="2"/><line x1="27" y1="36" x2="27" y2="38" stroke="#ef4444" stroke-width="2"/><rect x="41" y="18" width="8" height="16" fill="#ef4444" rx="1"/><line x1="45" y1="12" x2="45" y2="18" stroke="#ef4444" stroke-width="2"/><line x1="45" y1="34" x2="45" y2="38" stroke="#ef4444" stroke-width="2"/><rect x="13" y="26" width="28" height="6" fill="#ef4444" fill-opacity="0.2" stroke="#ef4444" stroke-width="1" stroke-dasharray="2,2" rx="2"/></svg>`;
const fvgIconWaiting = `<svg viewBox="0 0 60 40" class="w-12 h-8 opacity-40"><rect x="8" y="10" width="8" height="18" fill="#6b7280" rx="1"/><line x1="12" y1="6" x2="12" y2="10" stroke="#6b7280" stroke-width="2"/><line x1="12" y1="28" x2="12" y2="34" stroke="#6b7280" stroke-width="2"/><rect x="24" y="8" width="8" height="22" fill="#6b7280" rx="1"/><line x1="28" y1="4" x2="28" y2="8" stroke="#6b7280" stroke-width="2"/><line x1="28" y1="30" x2="28" y2="36" stroke="#6b7280" stroke-width="2"/><text x="46" y="24" font-size="16" fill="#6b7280" font-weight="bold">?</text></svg>`;

// ═══ HELPERS ═══
const fmtP = (p) => {
  if (!p && p !== 0) return '--';
  return Number(p).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

const badge = s => { const c=ST[s]||ST.ERROR; return `<span class="px-2 py-0.5 rounded-full text-[9px] font-bold ${c.bg} ${c.bd} ${c.tx} border">${c.lb}</span>`; };

const sourceTag = (source, tier) => {
  const t = TIERS[tier] || TIERS[3];
  const label = source ? source.split(' ')[0] : 'Unknown';
  return `<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[8px] ${t.bg} ${t.color} border ${t.border}"><span class="w-1.5 h-1.5 rounded-full ${t.dot}"></span>${label}</span>`;
};

const box = (l,v,c='text-white') => `<div class="bg-bg/50 border border-border rounded px-2 py-1.5"><p class="text-[8px] text-gray-600 uppercase">${l}</p><p class="text-xs font-semibold ${c} truncate">${v}</p></div>`;

const bar = s => { const p=Math.min(Math.round(s/12*100),100), c=s>=9?'#22c55e':s>=7?'#84cc16':s>=5?'#eab308':'#ef4444'; return `<div class="mt-2"><div class="flex justify-between text-[9px] mb-1"><span class="text-gray-500">Score</span><span class="font-bold" style="color:${c}">${s}/12</span></div><div class="bg-gray-800 rounded-full h-1.5"><div class="h-full rounded-full" style="width:${p}%;background:${c}"></div></div></div>`; };

function fvgIndicator(d) {
  if (d.fvg_detected && d.direction) {
    const icon = d.direction === 'LONG' ? fvgIconLong : fvgIconShort;
    const color = d.direction === 'LONG' ? 'border-green-500/50 bg-green-500/5' : 'border-red-500/50 bg-red-500/5';
    return `<div class="flex items-center gap-2 p-2 rounded-lg border ${color} fvg-glow">${icon}<div><p class="text-[9px] text-gray-400 uppercase">FVG Detected</p><p class="text-xs font-bold ${d.direction === 'LONG' ? 'text-green-400' : 'text-red-400'}">${d.direction} $${d.fvg_size}</p></div></div>`;
  } else if (d.status === 'SCANNING') {
    return `<div class="flex items-center gap-2 p-2 rounded-lg border border-gray-700/50 bg-gray-800/30">${fvgIconWaiting}<div><p class="text-[9px] text-gray-500 uppercase">Waiting for FVG</p><p class="text-[10px] text-gray-600">Scanning...</p></div></div>`;
  }
  return '';
}

// ═══ PRICE CHANGE DISPLAY ═══
function priceChangeHtml(d) {
  if (!d.price_change && d.price_change !== 0) return '';
  const up = d.price_change >= 0;
  const arrow = up ? '▲' : '▼';
  const color = up ? 'text-green-400' : 'text-red-400';
  const sign = up ? '+' : '';
  const pct = d.price_change_pct !== undefined ? ` (${sign}${d.price_change_pct}%)` : '';
  return `<span class="text-xs ${color} font-medium">${arrow} ${sign}$${fmtP(Math.abs(d.price_change))}${pct}</span>`;
}

// ═══ TICKER BAR ═══
let prevPrices = {};
function updateTicker(data) {
  const assets = ['NAS100', 'BTCUSD', 'GOLD'];
  const icons = { NAS100: '📈', BTCUSD: '₿', GOLD: '🥇' };
  
  let html = '';
  assets.forEach(a => {
    const d = data[a];
    if (!d) return;
    
    const price = d.price;
    const prev = prevPrices[a];
    const changed = prev && prev !== price;
    const up = price > (prev || price);
    const color = !d.price_change ? 'text-gray-400' : d.price_change >= 0 ? 'text-green-400' : 'text-red-400';
    const flashClass = changed ? 'price-up' : '';
    
    html += `
      <div class="flex items-center gap-2 min-w-fit ${flashClass}">
        <span class="text-xs">${icons[a]}</span>
        <span class="text-[10px] text-gray-500 font-medium">${a}</span>
        <span class="text-sm font-bold text-white font-mono">$${fmtP(price)}</span>
        ${d.price_change !== undefined ? `<span class="text-[10px] ${color}">${d.price_change >= 0 ? '▲' : '▼'}${Math.abs(d.price_change_pct || 0)}%</span>` : ''}
      </div>`;
    
    prevPrices[a] = price;
  });
  
  document.getElementById('ticker').innerHTML = html || '<span class="text-[10px] text-gray-600">No price data</span>';
}

// ═══ CARD RENDERER ═══
function render(d) {
  const tr = d.status === 'TRADE' || d.status === 'SKIP';
  const dc = d.direction === 'LONG' ? 'text-green-400' : 'text-red-400';
  const di = d.direction === 'LONG' ? '↑' : '↓';
  const tc = d.trend === 'BULLISH' ? 'text-green-400' : d.trend === 'BEARISH' ? 'text-red-400' : 'text-gray-400';
  
  let h = `<div class="bg-card border border-border rounded-xl overflow-hidden ${d.status === 'TRADE' ? 'ring-2 ring-green-500/50' : ''}">`;
  
  // ═══ HEADER: Asset + Source + Badge ═══
  h += `<div class="px-4 pt-3 pb-1 flex items-center justify-between">
    <div class="flex items-center gap-2">
      <span class="text-sm font-bold text-white">${d.asset}</span>
      ${sourceTag(d.source, d.source_tier)}
      ${d.window ? `<span class="text-[8px] text-purple-400 bg-purple-500/10 px-1.5 py-0.5 rounded">${d.window}</span>` : ''}
    </div>
    ${badge(d.status)}
  </div>`;
  
  // ═══ PRICE DISPLAY ═══
  if (d.price) {
    h += `<div class="px-4 pb-3 border-b border-border">
      <div class="flex items-end justify-between">
        <div>
          <p class="text-2xl sm:text-3xl font-bold text-white font-mono price-text">$${fmtP(d.price)}</p>
          <div class="flex items-center gap-2 mt-0.5">
            ${priceChangeHtml(d)}
          </div>
        </div>
        <div class="text-right">
          ${d.trend ? `<p class="text-xs font-semibold ${tc}">${d.trend === 'BULLISH' ? '▲' : '▼'} ${d.trend}</p>` : ''}
          ${d.ma50 ? `<p class="text-[9px] text-gray-600 font-mono">MA50: $${fmtP(d.ma50)}</p>` : ''}
          ${d.ma200 ? `<p class="text-[9px] text-gray-600 font-mono">MA200: $${fmtP(d.ma200)}</p>` : ''}
        </div>
      </div>
    </div>`;
  } else {
    h += `<div class="px-4 pb-2 border-b border-border">
      <p class="text-lg text-gray-600 font-mono">--</p>
    </div>`;
  }
  
  // ═══ BODY: Message + Details ═══
  h += `<div class="px-4 py-3">
    <p class="text-xs text-white mb-3">${d.message}</p>`;
  
  if (tr) {
    // Trade signal
    h += fvgIndicator(d);
    
    h += `<div class="grid grid-cols-2 gap-1.5 mb-2 mt-3">
      ${box('Dir', di + ' ' + d.direction, dc)}
      ${box('Conf', d.confidence, d.confidence === 'HIGH' ? 'text-green-400' : 'text-yellow-400')}
    </div>`;
    h += bar(d.score);
    
    h += `<div class="border-t border-border my-3"></div>`;
    h += `<div class="grid grid-cols-2 sm:grid-cols-4 gap-1.5 info-grid">
      ${box('Entry', '$' + fmtP(d.entry), dc)}
      ${box('Stop', '$' + fmtP(d.stop), 'text-red-400')}
      ${box('Target', '$' + fmtP(d.target), 'text-green-400')}
      ${box('Range', '$' + fmtP(d.range_size))}
    </div>`;
    h += `<div class="grid grid-cols-3 gap-1.5 mt-1.5">
      ${box('FVG', '$' + d.fvg_size)}
      ${box('Speed', d.speed + ' bars')}
      ${d.day_open ? box('Open', '$' + fmtP(d.day_open)) : box('Day', d.day || '--')}
    </div>`;
    
    if (d.reasons?.length) {
      h += `<div class="border-t border-border my-3"></div>
        <details><summary class="text-[9px] text-gray-500 cursor-pointer hover:text-gray-300">Score Breakdown</summary><div class="mt-2 space-y-0.5">`;
      d.reasons.forEach(r => {
        h += `<p class="text-[10px] ${r.includes('+') ? 'text-green-400' : 'text-red-400'}">${r.includes('+') ? '✓' : '✗'} ${r}</p>`;
      });
      h += `</div></details>`;
    }
    
  } else if (['SCANNING', 'WAITING', 'FORMING', 'NO_TRADE'].includes(d.status)) {
    if (d.status === 'SCANNING') {
      h += fvgIndicator(d);
      h += `<div class="mt-3"></div>`;
    }
    
    h += `<div class="grid grid-cols-2 sm:grid-cols-3 gap-1.5 info-grid">`;
    if (d.range_high) h += box('High', '$' + fmtP(d.range_high));
    if (d.range_low) h += box('Low', '$' + fmtP(d.range_low));
    if (d.range_size) h += box('Range', '$' + fmtP(d.range_size));
    if (d.day_open) h += box('Open', '$' + fmtP(d.day_open));
    if (d.next_window) h += box('Next', d.next_window, 'text-purple-400');
    if (d.day) h += box('Day', d.day);
    h += `</div>`;
    
  } else {
    h += `<div class="grid grid-cols-2 gap-1.5">`;
    if (d.trend) h += box('Trend', d.trend, tc);
    if (d.next_window) h += box('Next', d.next_window, 'text-purple-400');
    if (d.day) h += box('Day', d.day);
    h += `</div>`;
  }
  
  h += `</div></div>`;
  return h;
}

// ═══ MAIN LOOP ═══
let n = 0;
async function go() {
  const st = document.getElementById('status');
  try {
    st.textContent = '⟳'; st.className = 'text-[10px] text-blue-400';
    const r = await fetch('/api/scan'), d = await r.json();
    
    // Update dashboard cards
    document.getElementById('dashboard').innerHTML = render(d.NAS100) + render(d.BTCUSD) + render(d.GOLD);
    
    // Update ticker bar
    updateTicker(d);
    
    // Update source indicator
    const tiers = [d.NAS100, d.BTCUSD, d.GOLD].map(x => x.source_tier || 3);
    const bestTier = Math.min(...tiers);
    const tierInfo = TIERS[bestTier] || TIERS[3];
    const srcEl = document.getElementById('source-indicator');
    srcEl.textContent = tierInfo.label;
    srcEl.className = `text-sm font-bold ${tierInfo.color}`;
    
    n++;
    document.getElementById('refresh-count').textContent = n;
    
    st.textContent = 'LIVE'; st.className = 'text-[10px] text-green-400 font-medium';
  } catch(e) {
    st.textContent = 'ERR'; st.className = 'text-[10px] text-red-400';
    console.error('Scan error:', e);
  }
}

function ck() {
  const n = new Date();
  document.getElementById('clock').textContent = n.toLocaleTimeString('en-US', {
    timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
  }) + ' ET';
  document.getElementById('date').textContent = n.toLocaleDateString('en-US', {
    timeZone: 'America/New_York', weekday: 'short', month: 'short', day: 'numeric'
  });
}

go(); ck(); setInterval(go, 2000); setInterval(ck, 1000);

if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission();
</script>
</body>
</html>"""