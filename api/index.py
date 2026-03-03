# Save this as: api/index.py

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from datetime import datetime, timedelta
import pytz
import urllib.request
import json
import os
import ssl
import re

app = FastAPI()

# ═══════════════════════════════════════════════
# CONFIGS - GOLD UPDATED FROM BACKTEST
# ═══════════════════════════════════════════════
CONFIGS = {
    "NAS100": {
        "tv": "OANDA:NAS100USD",
        "investing_pair": "indices/nq-100-futures",
        "investing_id": "8874",
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
        "investing_pair": None,  # Use Binance for BTC
        "investing_id": None,
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
        "investing_pair": "commodities/gold",
        "investing_id": "8830",
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
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
# HTTP HELPER
# ═══════════════════════════════════════════════
def http_get(url, headers=None):
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        req = urllib.request.Request(url, headers=headers or HEADERS)
        resp = urllib.request.urlopen(req, timeout=15, context=ctx)
        
        # Handle gzip
        if resp.info().get('Content-Encoding') == 'gzip':
            import gzip
            return gzip.decompress(resp.read()).decode('utf-8')
        
        return resp.read().decode('utf-8')
    except Exception as e:
        raise Exception(f"HTTP Error: {str(e)}")

def http_get_json(url, headers=None):
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        req = urllib.request.Request(url, headers=headers or HEADERS)
        resp = urllib.request.urlopen(req, timeout=15, context=ctx)
        return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        raise Exception(f"HTTP Error: {str(e)}")

# ═══════════════════════════════════════════════
# SCRAPERS
# ═══════════════════════════════════════════════

def scrape_binance(interval, limit):
    """BTC from Binance — free, no key, reliable"""
    iv = "1m" if interval == "1min" else "15m"
    url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval={iv}&limit={limit}"
    data = http_get_json(url)
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


def scrape_investing_historical(pair_id, interval="1", count=500):
    """
    Scrape historical candle data from Investing.com
    interval: "1" = 1min, "5" = 5min, "15" = 15min, "60" = 1hour
    """
    try:
        et = pytz.timezone('US/Eastern')
        now = datetime.now(et)
        
        # Calculate timestamps
        end_ts = int(now.timestamp())
        
        # For 1min data, go back ~8 hours; for 15min, go back ~3 days
        if interval == "1":
            start_ts = end_ts - (8 * 60 * 60)  # 8 hours
        else:
            start_ts = end_ts - (3 * 24 * 60 * 60)  # 3 days
        
        url = f"https://tvc6.investing.com/bc498743e6cd7b99f089f1c5c1c9e5d7/{end_ts}/1/1/8/history?symbol={pair_id}&resolution={interval}&from={start_ts}&to={end_ts}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Referer": "https://www.investing.com/",
            "Origin": "https://www.investing.com",
        }
        
        data = http_get_json(url, headers)
        
        if data.get("s") != "ok":
            return [], f"Investing API returned: {data.get('s', 'unknown')}"
        
        candles = []
        times = data.get("t", [])
        opens = data.get("o", [])
        highs = data.get("h", [])
        lows = data.get("l", [])
        closes = data.get("c", [])
        
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


def scrape_yahoo_finance(symbol, interval="1m", period="1d"):
    """
    Fallback: Scrape from Yahoo Finance
    symbol: "GC=F" for Gold, "NQ=F" for Nasdaq futures
    interval: "1m", "5m", "15m"
    period: "1d", "5d"
    """
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
        
        et = pytz.timezone('US/Eastern')
        candles = []
        
        for i in range(len(timestamps)):
            if ohlc.get("open") and ohlc["open"][i] is not None:
                dt = datetime.fromtimestamp(timestamps[i], tz=et)
                candles.append({
                    "time": dt.strftime("%H:%M"),
                    "open": float(ohlc["open"][i]),
                    "high": float(ohlc["high"][i]),
                    "low": float(ohlc["low"][i]),
                    "close": float(ohlc["close"][i])
                })
        
        return candles, None
        
    except Exception as e:
        return [], str(e)


def scrape_tradingview_data(symbol):
    """
    Alternative: Get data from TradingView's public API
    """
    try:
        # TradingView uses a websocket, but we can get snapshot data
        url = f"https://scanner.tradingview.com/forex/scan"
        
        payload = {
            "symbols": {"tickers": [symbol]},
            "columns": ["open", "high", "low", "close", "change"]
        }
        
        # This is limited - TradingView doesn't have easy historical API
        # Keeping as placeholder
        return [], "TradingView requires websocket"
        
    except Exception as e:
        return [], str(e)


def scrape_asset(asset):
    """Main scraper - routes to correct source with fallbacks"""
    cached = get_cached(asset)
    if cached:
        return cached

    result = {
        "asset": asset, 
        "tv": CONFIGS[asset]["tv"],
        "status": "ERROR", 
        "candles": [],
        "ma50": None, 
        "ma200": None, 
        "price": None, 
        "error": None,
        "source": None
    }

    try:
        # ═══════════════════════════════════════════════
        # BTCUSD - Use Binance (most reliable)
        # ═══════════════════════════════════════════════
        if asset == "BTCUSD":
            candles_15, err_15 = scrape_binance("15min", 300)
            candles_1, err_1 = scrape_binance("1min", 500)
            result["source"] = "Binance"
            
            if err_15 or err_1:
                result["error"] = err_15 or err_1
                set_cached(asset, result)
                return result
        
        # ═══════════════════════════════════════════════
        # GOLD & NAS100 - Try Investing.com first, then Yahoo
        # ═══════════════════════════════════════════════
        else:
            pair_id = CONFIGS[asset]["investing_id"]
            
            # Try Investing.com first
            candles_15, err_15 = scrape_investing_historical(pair_id, "15", 300)
            
            if not candles_15 or len(candles_15) < 50:
                # Fallback to Yahoo Finance
                yahoo_symbol = "GC=F" if asset == "GOLD" else "NQ=F"
                candles_15, err_15 = scrape_yahoo_finance(yahoo_symbol, "15m", "5d")
                result["source"] = "Yahoo Finance"
            else:
                result["source"] = "Investing.com"
            
            if not candles_15 or len(candles_15) < 50:
                result["error"] = f"15min data failed: {err_15}"
                set_cached(asset, result)
                return result
            
            # Get 1min data
            candles_1, err_1 = scrape_investing_historical(pair_id, "1", 500)
            
            if not candles_1 or len(candles_1) < 30:
                yahoo_symbol = "GC=F" if asset == "GOLD" else "NQ=F"
                candles_1, err_1 = scrape_yahoo_finance(yahoo_symbol, "1m", "1d")
            
            if not candles_1:
                result["error"] = f"1min data failed: {err_1}"
                result["status"] = "NO_1MIN"

        # ═══════════════════════════════════════════════
        # Calculate MAs
        # ═══════════════════════════════════════════════
        if len(candles_15) >= 200:
            closes = [c['close'] for c in candles_15]
            result["ma50"] = round(sum(closes[-50:]) / 50, 2)
            result["ma200"] = round(sum(closes[-200:]) / 200, 2)
        elif len(candles_15) >= 50:
            closes = [c['close'] for c in candles_15]
            result["ma50"] = round(sum(closes[-50:]) / 50, 2)
            result["ma200"] = result["ma50"]  # Use MA50 as fallback
        else:
            result["error"] = f"Only {len(candles_15)} bars (need 50+)"
            set_cached(asset, result)
            return result

        if candles_1:
            result["candles"] = candles_1
            result["price"] = round(candles_1[-1]['close'], 2)
            result["status"] = "OK"
            result["candle_count"] = len(candles_1)
        else:
            result["status"] = "NO_1MIN"

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
# WINDOW DETECTION (for Gold)
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
    
    # Rejection filters
    if c["max_range"] and range_size > c["max_range"]:
        return {"score":0,"take_trade":False,"confidence":"REJECTED","reasons":["Range too wide"]}
    if c["max_fvg"] and fvg_size > c["max_fvg"]:
        return {"score":0,"take_trade":False,"confidence":"REJECTED","reasons":["FVG too large"]}
    if c["max_speed"] and speed > c["max_speed"]:
        return {"score":0,"take_trade":False,"confidence":"REJECTED","reasons":["Breakout too slow"]}
    
    # Window scoring (Gold)
    if c.get("windows") and window and window in c["windows"]:
        w = c["windows"][window]
        score += w["score"]
        reasons.append(f"{window} window ({w['wr']}) → +{w['score']}")
    
    # Range scoring
    for low, high, pts in c["range"]:
        if low <= range_size <= high:
            score += pts
            if pts > 0:
                reasons.append(f"Range ${low}-${high} → +{pts}")
            break
    
    # FVG scoring
    for low, high, pts in c["fvg"]:
        if low <= fvg_size <= high:
            score += pts
            if pts > 0:
                reasons.append(f"FVG ${low}-${high} → +{pts}")
            break
    
    # Speed scoring
    for low, high, pts in c["speed"]:
        if low <= speed <= high:
            score += pts
            if pts > 0:
                reasons.append(f"Speed {low}-{high} bars → +{pts}")
            break
    
    # Day scoring
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
    
    # Directional bias
    if c["bias"] and direction == c["bias"][0]:
        score += c["bias"][1]
        reasons.append(f"{direction} bias → +{c['bias'][1]}")
    
    # Confidence levels
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
        "source": scraped.get("source", "Unknown")
    }

    # Weekend check
    if not config["weekend"] and now.weekday() >= 5:
        return {**base, "status": "CLOSED", "message": "Weekend — markets closed"}
    
    # Gold multi-window check
    if asset == "GOLD" and config.get("windows"):
        if not current_window:
            next_w = next_window or "08:00 tomorrow"
            return {
                **base, 
                "status": "WAITING", 
                "message": f"Outside trading windows. Next: {next_w}",
                "ma50": scraped.get("ma50"),
                "ma200": scraped.get("ma200"),
                "price": scraped.get("price"),
                "trend": "BULLISH" if scraped.get("ma50", 0) > scraped.get("ma200", 0) else "BEARISH"
            }
    else:
        # Standard market hours
        if not config["weekend"] and now.hour < 9:
            h = 9 - now.hour
            m = 30 - now.minute
            if m < 0:
                h -= 1
                m += 60
            return {**base, "status": "PRE_MARKET", "message": f"NY opens in {h}h {m}m"}
        
        if not config["weekend"] and now.hour >= 17:
            return {**base, "status": "CLOSED", "message": "NY session ended"}

    # Check scraper status
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
            "trend": trend, 
            "ma50": ma50, 
            "ma200": ma200
        }

    candles = scraped["candles"]
    price = scraped["price"]

    # Determine opening range candles
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
            "trend": trend, 
            "price": price, 
            "ma50": ma50, 
            "ma200": ma200
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
            "price": price, 
            "range_high": rh, 
            "range_low": rl, 
            "range_size": rs,
            "ma50": ma50, 
            "ma200": ma200
        }

    # Post-range candles
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
            "price": price, 
            "range_high": rh, 
            "range_low": rl, 
            "range_size": rs,
            "ma50": ma50, 
            "ma200": ma200
        }

    today = now.strftime("%Y-%m-%d")
    bias_dir = "LONG" if trend == "BULLISH" else "SHORT"

    # Scan for FVG breakout
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
                    "price": price, 
                    "range_high": rh, 
                    "range_low": rl, 
                    "range_size": rs,
                    "fvg_size": fvg['size'], 
                    "speed": i+1,
                    "score": pred["score"], 
                    "confidence": pred["confidence"],
                    "reasons": pred["reasons"], 
                    "ma50": ma50, 
                    "ma200": ma200
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
                    "price": price, 
                    "range_high": rh, 
                    "range_low": rl, 
                    "range_size": rs,
                    "fvg_size": fvg['size'], 
                    "speed": i+1,
                    "score": pred["score"], 
                    "confidence": pred["confidence"],
                    "reasons": pred["reasons"], 
                    "ma50": ma50, 
                    "ma200": ma200
                }

    # No FVG found yet
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
        "price": price,
        "range_high": rh, 
        "range_low": rl, 
        "range_size": rs,
        "ma50": ma50, 
        "ma200": ma200
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
            "error": data.get("error"),
            "ma50": data.get("ma50"),
            "ma200": data.get("ma200"),
            "price": data.get("price"),
            "candle_count": data.get("candle_count", 0),
            "first_candle": data["candles"][0] if data["candles"] else None,
            "last_candle": data["candles"][-1] if data["candles"] else None,
        }
    return JSONResponse(content=debug)

@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.now().isoformat()}

# ═══════════════════════════════════════════════
# UI
# ═══════════════════════════════════════════════
@app.get("/", response_class=HTMLResponse)
def home():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
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
  .live-dot { animation: pulse-dot 2s infinite; }
  .glass { backdrop-filter: blur(10px); }
  
  /* Mobile optimizations */
  @media (max-width: 640px) {
    .card-grid { grid-template-columns: 1fr !important; }
    .info-grid { grid-template-columns: repeat(2, 1fr) !important; }
  }
  
  /* Smooth transitions */
  .card-transition {
    transition: all 0.3s ease;
  }
  .card-transition:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 20px rgba(0,0,0,0.3);
  }
</style>
</head>
<body class="bg-bg text-gray-300 min-h-screen">

<header class="border-b border-border bg-card/50 glass sticky top-0 z-50">
  <div class="w-[95%] xl:w-[85%] 2xl:w-[80%] mx-auto py-3 sm:py-4">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-lg sm:text-xl font-bold text-white tracking-tight">ORB Scanner</h1>
        <p class="text-[10px] sm:text-[11px] text-gray-600 mt-0.5">Opening Range Breakout · Multi-Asset</p>
      </div>
      <div class="flex items-center gap-2 sm:gap-4">
        <div class="text-right hidden sm:block">
          <p class="text-sm text-white font-mono" id="clock">--:--:--</p>
          <p class="text-[10px] text-gray-600" id="date">Loading...</p>
        </div>
        <div class="text-right sm:hidden">
          <p class="text-xs text-white font-mono" id="clock-mobile">--:--</p>
        </div>
        <div class="flex items-center gap-1.5 sm:gap-2">
          <span class="w-2 h-2 rounded-full bg-green-500 live-dot"></span>
          <span class="text-[10px] sm:text-xs text-green-400 font-medium" id="status">CONNECTING</span>
        </div>
      </div>
    </div>
  </div>
</header>

<main class="w-[95%] xl:w-[85%] 2xl:w-[80%] mx-auto py-4 sm:py-6">
  
  <!-- Stats Bar - Collapsible on mobile -->
  <div class="grid grid-cols-4 gap-2 sm:gap-3 mb-4 sm:mb-6">
    <div class="bg-card border border-border rounded-lg px-2 sm:px-4 py-2 sm:py-3">
      <p class="text-[8px] sm:text-[10px] text-gray-600 uppercase tracking-wider">Markets</p>
      <p class="text-sm sm:text-lg font-bold text-white mt-0.5 sm:mt-1">3</p>
    </div>
    <div class="bg-card border border-border rounded-lg px-2 sm:px-4 py-2 sm:py-3">
      <p class="text-[8px] sm:text-[10px] text-gray-600 uppercase tracking-wider">Refresh</p>
      <p class="text-sm sm:text-lg font-bold text-white mt-0.5 sm:mt-1">2s</p>
    </div>
    <div class="bg-card border border-border rounded-lg px-2 sm:px-4 py-2 sm:py-3">
      <p class="text-[8px] sm:text-[10px] text-gray-600 uppercase tracking-wider">Updates</p>
      <p class="text-sm sm:text-lg font-bold text-white mt-0.5 sm:mt-1" id="refresh-count">0</p>
    </div>
    <div class="bg-card border border-border rounded-lg px-2 sm:px-4 py-2 sm:py-3">
      <p class="text-[8px] sm:text-[10px] text-gray-600 uppercase tracking-wider">Last</p>
      <p class="text-sm sm:text-lg font-bold text-white mt-0.5 sm:mt-1 font-mono" id="last-update">--:--</p>
    </div>
  </div>

  <!-- Scanner Cards -->
  <div class="grid grid-cols-1 lg:grid-cols-3 gap-3 sm:gap-4 card-grid" id="dashboard">
    <div class="bg-card border border-border rounded-xl p-4 sm:p-6 animate-pulse">
      <div class="h-4 bg-accent rounded w-24 mb-4"></div>
      <div class="h-8 bg-accent rounded w-32 mb-3"></div>
      <div class="h-4 bg-accent rounded w-full"></div>
    </div>
    <div class="bg-card border border-border rounded-xl p-4 sm:p-6 animate-pulse">
      <div class="h-4 bg-accent rounded w-24 mb-4"></div>
      <div class="h-8 bg-accent rounded w-32 mb-3"></div>
      <div class="h-4 bg-accent rounded w-full"></div>
    </div>
    <div class="bg-card border border-border rounded-xl p-4 sm:p-6 animate-pulse">
      <div class="h-4 bg-accent rounded w-24 mb-4"></div>
      <div class="h-8 bg-accent rounded w-32 mb-3"></div>
      <div class="h-4 bg-accent rounded w-full"></div>
    </div>
  </div>

  <!-- Footer -->
  <div class="mt-4 sm:mt-6 text-center">
    <p class="text-[9px] sm:text-[10px] text-gray-700">
      Sources: Binance · Investing.com · Yahoo Finance · 
      <a href="/api/debug" class="text-blue-500 hover:underline">Debug</a> · 
      <a href="/api/scan" class="text-blue-500 hover:underline">JSON</a>
    </p>
  </div>
</main>

<script>
const STATUS_CONFIG = {
  TRADE:      { bg:'bg-green-500/10',  border:'border-green-500/40',  text:'text-green-400',  label:'TRADE' },
  SKIP:       { bg:'bg-yellow-500/10', border:'border-yellow-500/40', text:'text-yellow-400', label:'SKIP' },
  SCANNING:   { bg:'bg-blue-500/10',   border:'border-blue-500/40',   text:'text-blue-400',   label:'SCANNING' },
  CLOSED:     { bg:'bg-gray-500/10',   border:'border-gray-500/40',   text:'text-gray-500',   label:'CLOSED' },
  PRE_MARKET: { bg:'bg-purple-500/10', border:'border-purple-500/40', text:'text-purple-400', label:'PRE-MKT' },
  WAITING:    { bg:'bg-purple-500/10', border:'border-purple-500/40', text:'text-purple-400', label:'WAITING' },
  FORMING:    { bg:'bg-indigo-500/10', border:'border-indigo-500/40', text:'text-indigo-400', label:'FORMING' },
  NO_TRADE:   { bg:'bg-orange-500/10', border:'border-orange-500/40', text:'text-orange-400', label:'NO TRADE' },
  ERROR:      { bg:'bg-red-500/10',    border:'border-red-500/40',    text:'text-red-400',    label:'ERROR' }
};

function badge(status) {
  const c = STATUS_CONFIG[status] || STATUS_CONFIG.ERROR;
  return `<span class="inline-flex items-center px-2 sm:px-3 py-0.5 sm:py-1 rounded-full text-[9px] sm:text-[11px] font-semibold ${c.bg} ${c.border} ${c.text} border uppercase tracking-wide">${c.label}</span>`;
}

function infoBox(label, value, color = 'text-white') {
  return `
    <div class="bg-bg/50 border border-border rounded-lg px-2 sm:px-3 py-1.5 sm:py-2.5">
      <p class="text-[8px] sm:text-[9px] text-gray-600 uppercase tracking-wider">${label}</p>
      <p class="text-xs sm:text-sm font-semibold mt-0.5 ${color} truncate">${value}</p>
    </div>`;
}

function scoreBar(score) {
  const pct = Math.min(Math.round(score / 12 * 100), 100);
  const color = score >= 9 ? '#22c55e' : score >= 7 ? '#84cc16' : score >= 5 ? '#eab308' : '#ef4444';
  return `
    <div class="mt-2 sm:mt-3">
      <div class="flex justify-between text-[9px] sm:text-[10px] mb-1">
        <span class="text-gray-500">Score</span>
        <span class="font-bold" style="color:${color}">${score}/12</span>
      </div>
      <div class="bg-gray-800 rounded-full h-1.5 sm:h-2 overflow-hidden">
        <div class="h-full rounded-full transition-all duration-500" style="width:${pct}%;background:${color}"></div>
      </div>
    </div>`;
}

function renderCard(d) {
  const isTrade = d.status === 'TRADE' || d.status === 'SKIP';
  const dirColor = d.direction === 'LONG' ? 'text-green-400' : 'text-red-400';
  const dirIcon = d.direction === 'LONG' ? '↑' : '↓';
  const trendColor = d.trend === 'BULLISH' ? 'text-green-400' : d.trend === 'BEARISH' ? 'text-red-400' : 'text-gray-400';
  
  let html = `
    <div class="bg-card border border-border rounded-xl overflow-hidden card-transition ${d.status === 'TRADE' ? 'ring-2 ring-green-500/50' : ''}">
      <div class="px-3 sm:px-5 py-3 sm:py-4 border-b border-border flex items-center justify-between">
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <p class="text-[10px] sm:text-xs text-gray-400 font-semibold">${d.asset}</p>
            ${d.window ? `<span class="text-[8px] sm:text-[10px] text-purple-400 bg-purple-500/10 px-1.5 py-0.5 rounded">${d.window}</span>` : ''}
          </div>
          <p class="text-[8px] sm:text-[10px] text-gray-600 font-mono truncate">${d.source || d.tv}</p>
        </div>
        ${badge(d.status)}
      </div>
      
      <div class="px-3 sm:px-5 py-3 sm:py-4">
        <p class="text-xs sm:text-sm text-white mb-3 sm:mb-4">${d.message}</p>`;
  
  if (isTrade) {
    html += `
        <div class="grid grid-cols-2 gap-1.5 sm:gap-2 mb-2 sm:mb-3">
          ${infoBox('Direction', `${dirIcon} ${d.direction}`, dirColor)}
          ${infoBox('Confidence', d.confidence, d.confidence === 'HIGH' ? 'text-green-400' : d.confidence === 'MEDIUM' ? 'text-yellow-400' : 'text-red-400')}
        </div>
        
        ${scoreBar(d.score)}
        
        <div class="border-t border-border my-3 sm:my-4"></div>
        
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-1.5 sm:gap-2 info-grid">
          ${infoBox('Entry', '$' + d.entry, dirColor)}
          ${infoBox('Stop', '$' + d.stop, 'text-red-400')}
          ${infoBox('Target', '$' + d.target, 'text-green-400')}
          ${infoBox('Price', '$' + d.price)}
        </div>
        
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-1.5 sm:gap-2 mt-1.5 sm:mt-2 info-grid">
          ${infoBox('Range', '$' + d.range_size)}
          ${infoBox('FVG', '$' + d.fvg_size)}
          ${infoBox('Speed', d.speed + ' bars')}
          ${infoBox('Trend', d.trend, trendColor)}
        </div>`;
    
    if (d.reasons && d.reasons.length) {
      html += `
        <div class="border-t border-border my-3 sm:my-4"></div>
        <details class="group">
          <summary class="text-[9px] sm:text-[10px] text-gray-600 uppercase tracking-wider cursor-pointer hover:text-gray-400 flex items-center gap-1">
            Score Breakdown 
            <svg class="w-3 h-3 transition-transform group-open:rotate-180" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
            </svg>
          </summary>
          <div class="mt-2 space-y-0.5 sm:space-y-1">`;
      d.reasons.forEach(r => {
        const isPositive = r.includes('+');
        html += `<p class="text-[10px] sm:text-[11px] ${isPositive ? 'text-green-400' : 'text-red-400'}"><span class="mr-1">${isPositive ? '✓' : '✗'}</span>${r}</p>`;
      });
      html += `</div></details>`;
    }
  } else if (['SCANNING', 'WAITING', 'FORMING', 'NO_TRADE'].includes(d.status)) {
    html += `<div class="grid grid-cols-2 sm:grid-cols-3 gap-1.5 sm:gap-2 info-grid">`;
    if (d.price) html += infoBox('Price', '$' + d.price);
    if (d.trend) html += infoBox('Trend', d.trend, trendColor);
    if (d.range_high) html += infoBox('High', '$' + d.range_high);
    if (d.range_low) html += infoBox('Low', '$' + d.range_low);
    if (d.range_size) html += infoBox('Range', '$' + d.range_size);
    if (d.next_window) html += infoBox('Next', d.next_window, 'text-purple-400');
    html += `</div>`;
  } else if (d.trend) {
    html += `<div class="grid grid-cols-2 gap-1.5 sm:gap-2 info-grid">`;
    html += infoBox('Trend', d.trend, trendColor);
    if (d.next_window) html += infoBox('Next', d.next_window, 'text-purple-400');
    html += `</div>`;
  }
  
  html += `
      </div>
    </div>`;
  
  return html;
}

let refreshCount = 0;

async function fetchData() {
  const statusEl = document.getElementById('status');
  
  try {
    statusEl.textContent = '⟳';
    statusEl.className = 'text-xs text-blue-400 font-medium';
    
    const response = await fetch('/api/scan');
    const data = await response.json();
    
    document.getElementById('dashboard').innerHTML = 
      renderCard(data.NAS100) + 
      renderCard(data.BTCUSD) + 
      renderCard(data.GOLD);
    
    refreshCount++;
    document.getElementById('refresh-count').textContent = refreshCount;
    document.getElementById('last-update').textContent = new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
    
    statusEl.textContent = 'LIVE';
    statusEl.className = 'text-xs text-green-400 font-medium';
    
  } catch (error) {
    console.error('Fetch error:', error);
    statusEl.textContent = 'ERR';
    statusEl.className = 'text-xs text-red-400 font-medium';
  }
}

function updateClock() {
  const now = new Date();
  const etOptions = { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false };
  const etShort = { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hour12: false };
  const dateOptions = { timeZone: 'America/New_York', weekday: 'short', month: 'short', day: 'numeric' };
  
  const clockEl = document.getElementById('clock');
  const clockMobileEl = document.getElementById('clock-mobile');
  const dateEl = document.getElementById('date');
  
  if (clockEl) clockEl.textContent = now.toLocaleTimeString('en-US', etOptions) + ' ET';
  if (clockMobileEl) clockMobileEl.textContent = now.toLocaleTimeString('en-US', etShort);
  if (dateEl) dateEl.textContent = now.toLocaleDateString('en-US', dateOptions);
}

// Initialize
fetchData();
updateClock();
setInterval(fetchData, 2000);
setInterval(updateClock, 1000);

// Play sound on trade signal (optional)
let lastTradeState = {};
function checkForNewTrades(data) {
  ['NAS100', 'BTCUSD', 'GOLD'].forEach(asset => {
    if (data[asset]?.status === 'TRADE' && lastTradeState[asset] !== 'TRADE') {
      // New trade signal!
      if (Notification.permission === 'granted') {
        new Notification(`${asset} TRADE SIGNAL`, { body: data[asset].message });
      }
    }
    lastTradeState[asset] = data[asset]?.status;
  });
}

// Request notification permission
if ('Notification' in window && Notification.permission === 'default') {
  Notification.requestPermission();
}
</script>
</body>
</html>"""