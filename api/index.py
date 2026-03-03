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
# SCRAPERS
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
        "error": None,
        "source": None
    }

    candles_15 = []
    candles_1 = []
    
    try:
        if asset == "BTCUSD":
            candles_15, err = scrape_binance("15min", 300)
            if candles_15 and len(candles_15) >= 50:
                candles_1, _ = scrape_binance("1min", 500)
                result["source"] = "Binance"
            else:
                candles_15, err = scrape_yahoo_finance("BTC-USD", "15m", "5d")
                candles_1, _ = scrape_yahoo_finance("BTC-USD", "1m", "1d")
                result["source"] = "Yahoo Finance"
                
                if not candles_15:
                    result["error"] = f"All sources failed: {err}"
                    set_cached(asset, result)
                    return result
        
        else:
            pair_id = config["investing_id"]
            yahoo_symbol = config["yahoo"]
            
            candles_15, err = scrape_investing(pair_id, "15", 300)
            
            if candles_15 and len(candles_15) >= 50:
                candles_1, _ = scrape_investing(pair_id, "1", 500)
                result["source"] = "Investing.com"
            else:
                candles_15, err = scrape_yahoo_finance(yahoo_symbol, "15m", "5d")
                candles_1, _ = scrape_yahoo_finance(yahoo_symbol, "1m", "1d")
                result["source"] = "Yahoo Finance"
                
                if not candles_15:
                    result["error"] = f"All sources failed: {err}"
                    set_cached(asset, result)
                    return result

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

        if candles_1 and len(candles_1) > 0:
            result["candles"] = candles_1
            result["price"] = round(candles_1[-1]['close'], 2)
            result["status"] = "OK"
            result["candle_count"] = len(candles_1)
        else:
            result["candles"] = candles_15[-60:]
            result["price"] = round(candles_15[-1]['close'], 2)
            result["status"] = "OK"
            result["candle_count"] = len(candles_15)
            result["source"] += " (15min)"

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
        "source": scraped.get("source", "Unknown")
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
                "ma50": scraped.get("ma50"),
                "ma200": scraped.get("ma200"),
                "price": scraped.get("price"),
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
            "trend": trend, 
            "ma50": ma50, 
            "ma200": ma200
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
                    "ma200": ma200,
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
                    "ma200": ma200,
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
        "price": price,
        "range_high": rh, 
        "range_low": rl, 
        "range_size": rs,
        "ma50": ma50, 
        "ma200": ma200,
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
# UI WITH FVG ICON
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
  .live-dot { animation: pulse-dot 2s infinite; }
  .fvg-glow { animation: fvg-glow 1.5s infinite; }
  .glass { backdrop-filter: blur(10px); }
  * { -webkit-tap-highlight-color: transparent; }
  
  @media (max-width: 640px) {
    .info-grid { grid-template-columns: repeat(2, 1fr) !important; }
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
      <p class="text-[8px] text-gray-600 uppercase">Last</p>
      <p class="text-sm font-bold text-white font-mono" id="last-update">--:--</p>
    </div>
  </div>

  <div class="grid grid-cols-1 lg:grid-cols-3 gap-3" id="dashboard">
    <div class="bg-card border border-border rounded-xl p-5 animate-pulse"><div class="h-4 bg-accent rounded w-20 mb-3"></div><div class="h-6 bg-accent rounded w-28"></div></div>
    <div class="bg-card border border-border rounded-xl p-5 animate-pulse"><div class="h-4 bg-accent rounded w-20 mb-3"></div><div class="h-6 bg-accent rounded w-28"></div></div>
    <div class="bg-card border border-border rounded-xl p-5 animate-pulse"><div class="h-4 bg-accent rounded w-20 mb-3"></div><div class="h-6 bg-accent rounded w-28"></div></div>
  </div>

  <div class="mt-4 text-center">
    <p class="text-[9px] text-gray-700">
      Binance · Investing.com · Yahoo · 
      <a href="/api/debug" class="text-blue-500">Debug</a>
    </p>
  </div>
</main>

<script>
const ST={TRADE:{bg:'bg-green-500/10',bd:'border-green-500/40',tx:'text-green-400',lb:'TRADE'},SKIP:{bg:'bg-yellow-500/10',bd:'border-yellow-500/40',tx:'text-yellow-400',lb:'SKIP'},SCANNING:{bg:'bg-blue-500/10',bd:'border-blue-500/40',tx:'text-blue-400',lb:'SCAN'},CLOSED:{bg:'bg-gray-500/10',bd:'border-gray-500/40',tx:'text-gray-500',lb:'CLOSED'},PRE_MARKET:{bg:'bg-purple-500/10',bd:'border-purple-500/40',tx:'text-purple-400',lb:'PRE'},WAITING:{bg:'bg-purple-500/10',bd:'border-purple-500/40',tx:'text-purple-400',lb:'WAIT'},FORMING:{bg:'bg-indigo-500/10',bd:'border-indigo-500/40',tx:'text-indigo-400',lb:'FORM'},NO_TRADE:{bg:'bg-orange-500/10',bd:'border-orange-500/40',tx:'text-orange-400',lb:'NO'},ERROR:{bg:'bg-red-500/10',bd:'border-red-500/40',tx:'text-red-400',lb:'ERR'}};

// FVG Icon SVG - Shows 3 candles with gap
const fvgIconLong = `
<svg viewBox="0 0 60 40" class="w-12 h-8">
  <!-- Candle 1 (left) - bearish -->
  <rect x="5" y="8" width="8" height="20" fill="#ef4444" rx="1"/>
  <line x1="9" y1="4" x2="9" y2="8" stroke="#ef4444" stroke-width="2"/>
  <line x1="9" y1="28" x2="9" y2="34" stroke="#ef4444" stroke-width="2"/>
  
  <!-- Candle 2 (middle) - big bullish impulse -->
  <rect x="22" y="4" width="10" height="28" fill="#22c55e" rx="1"/>
  <line x1="27" y1="2" x2="27" y2="4" stroke="#22c55e" stroke-width="2"/>
  <line x1="27" y1="32" x2="27" y2="36" stroke="#22c55e" stroke-width="2"/>
  
  <!-- Candle 3 (right) - bullish -->
  <rect x="41" y="6" width="8" height="16" fill="#22c55e" rx="1"/>
  <line x1="45" y1="2" x2="45" y2="6" stroke="#22c55e" stroke-width="2"/>
  <line x1="45" y1="22" x2="45" y2="28" stroke="#22c55e" stroke-width="2"/>
  
  <!-- FVG Zone (gap between candle 1 high and candle 3 low) -->
  <rect x="13" y="8" width="28" height="6" fill="#22c55e" fill-opacity="0.2" stroke="#22c55e" stroke-width="1" stroke-dasharray="2,2" rx="2"/>
  
  <!-- Arrow pointing to gap -->
  <path d="M 27 17 L 27 11" stroke="#22c55e" stroke-width="1.5" fill="none" marker-end="url(#arrowGreen)"/>
  <defs>
    <marker id="arrowGreen" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
      <path d="M 0 0 L 6 3 L 0 6 Z" fill="#22c55e"/>
    </marker>
  </defs>
</svg>`;

const fvgIconShort = `
<svg viewBox="0 0 60 40" class="w-12 h-8">
  <!-- Candle 1 (left) - bullish -->
  <rect x="5" y="12" width="8" height="20" fill="#22c55e" rx="1"/>
  <line x1="9" y1="6" x2="9" y2="12" stroke="#22c55e" stroke-width="2"/>
  <line x1="9" y1="32" x2="9" y2="36" stroke="#22c55e" stroke-width="2"/>
  
  <!-- Candle 2 (middle) - big bearish impulse -->
  <rect x="22" y="8" width="10" height="28" fill="#ef4444" rx="1"/>
  <line x1="27" y1="4" x2="27" y2="8" stroke="#ef4444" stroke-width="2"/>
  <line x1="27" y1="36" x2="27" y2="38" stroke="#ef4444" stroke-width="2"/>
  
  <!-- Candle 3 (right) - bearish -->
  <rect x="41" y="18" width="8" height="16" fill="#ef4444" rx="1"/>
  <line x1="45" y1="12" x2="45" y2="18" stroke="#ef4444" stroke-width="2"/>
  <line x1="45" y1="34" x2="45" y2="38" stroke="#ef4444" stroke-width="2"/>
  
  <!-- FVG Zone (gap between candle 1 low and candle 3 high) -->
  <rect x="13" y="26" width="28" height="6" fill="#ef4444" fill-opacity="0.2" stroke="#ef4444" stroke-width="1" stroke-dasharray="2,2" rx="2"/>
  
  <!-- Arrow pointing to gap -->
  <path d="M 27 23 L 27 29" stroke="#ef4444" stroke-width="1.5" fill="none" marker-end="url(#arrowRed)"/>
  <defs>
    <marker id="arrowRed" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
      <path d="M 0 0 L 6 3 L 0 6 Z" fill="#ef4444"/>
    </marker>
  </defs>
</svg>`;

// Waiting for FVG icon
const fvgIconWaiting = `
<svg viewBox="0 0 60 40" class="w-12 h-8 opacity-40">
  <!-- Candle 1 -->
  <rect x="8" y="10" width="8" height="18" fill="#6b7280" rx="1"/>
  <line x1="12" y1="6" x2="12" y2="10" stroke="#6b7280" stroke-width="2"/>
  <line x1="12" y1="28" x2="12" y2="34" stroke="#6b7280" stroke-width="2"/>
  
  <!-- Candle 2 -->
  <rect x="24" y="8" width="8" height="22" fill="#6b7280" rx="1"/>
  <line x1="28" y1="4" x2="28" y2="8" stroke="#6b7280" stroke-width="2"/>
  <line x1="28" y1="30" x2="28" y2="36" stroke="#6b7280" stroke-width="2"/>
  
  <!-- Question mark / waiting indicator -->
  <text x="46" y="24" font-size="16" fill="#6b7280" font-weight="bold">?</text>
</svg>`;

const badge=s=>{const c=ST[s]||ST.ERROR;return`<span class="px-2 py-0.5 rounded-full text-[9px] font-bold ${c.bg} ${c.bd} ${c.tx} border">${c.lb}</span>`};
const box=(l,v,c='text-white')=>`<div class="bg-bg/50 border border-border rounded px-2 py-1.5"><p class="text-[8px] text-gray-600 uppercase">${l}</p><p class="text-xs font-semibold ${c} truncate">${v}</p></div>`;
const bar=s=>{const p=Math.min(Math.round(s/12*100),100),c=s>=9?'#22c55e':s>=7?'#84cc16':s>=5?'#eab308':'#ef4444';return`<div class="mt-2"><div class="flex justify-between text-[9px] mb-1"><span class="text-gray-500">Score</span><span class="font-bold" style="color:${c}">${s}/12</span></div><div class="bg-gray-800 rounded-full h-1.5"><div class="h-full rounded-full" style="width:${p}%;background:${c}"></div></div></div>`};

// FVG indicator component
function fvgIndicator(d) {
  if (d.fvg_detected && d.direction) {
    const icon = d.direction === 'LONG' ? fvgIconLong : fvgIconShort;
    const color = d.direction === 'LONG' ? 'border-green-500/50 bg-green-500/5' : 'border-red-500/50 bg-red-500/5';
    return `
      <div class="flex items-center gap-2 p-2 rounded-lg border ${color} fvg-glow">
        ${icon}
        <div>
          <p class="text-[9px] text-gray-400 uppercase">FVG Detected</p>
          <p class="text-xs font-bold ${d.direction === 'LONG' ? 'text-green-400' : 'text-red-400'}">${d.direction} $${d.fvg_size}</p>
        </div>
      </div>`;
  } else if (d.status === 'SCANNING') {
    return `
      <div class="flex items-center gap-2 p-2 rounded-lg border border-gray-700/50 bg-gray-800/30">
        ${fvgIconWaiting}
        <div>
          <p class="text-[9px] text-gray-500 uppercase">Waiting for FVG</p>
          <p class="text-[10px] text-gray-600">Scanning...</p>
        </div>
      </div>`;
  }
  return '';
}

function render(d){
  const tr=d.status==='TRADE'||d.status==='SKIP';
  const dc=d.direction==='LONG'?'text-green-400':'text-red-400';
  const di=d.direction==='LONG'?'↑':'↓';
  const tc=d.trend==='BULLISH'?'text-green-400':d.trend==='BEARISH'?'text-red-400':'text-gray-400';
  
  let h=`<div class="bg-card border border-border rounded-xl overflow-hidden ${d.status==='TRADE'?'ring-2 ring-green-500/50':''}">
    <div class="px-4 py-3 border-b border-border flex items-center justify-between">
      <div>
        <div class="flex items-center gap-2">
          <span class="text-xs font-semibold text-gray-300">${d.asset}</span>
          ${d.window?`<span class="text-[8px] text-purple-400 bg-purple-500/10 px-1.5 py-0.5 rounded">${d.window}</span>`:''}
        </div>
        <p class="text-[9px] text-gray-600">${d.source||''}</p>
      </div>
      ${badge(d.status)}
    </div>
    <div class="px-4 py-3">
      <p class="text-xs text-white mb-3">${d.message}</p>`;
  
  if(tr){
    // FVG indicator for trade signals
    h += fvgIndicator(d);
    
    h+=`<div class="grid grid-cols-2 gap-1.5 mb-2 mt-3">${box('Dir',di+' '+d.direction,dc)}${box('Conf',d.confidence,d.confidence==='HIGH'?'text-green-400':'text-yellow-400')}</div>${bar(d.score)}
    <div class="border-t border-border my-3"></div>
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-1.5 info-grid">${box('Entry','$'+d.entry,dc)}${box('Stop','$'+d.stop,'text-red-400')}${box('Target','$'+d.target,'text-green-400')}${box('Price','$'+d.price)}</div>
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-1.5 mt-1.5 info-grid">${box('Range','$'+d.range_size)}${box('FVG','$'+d.fvg_size)}${box('Speed',d.speed+' bars')}${box('Trend',d.trend,tc)}</div>`;
    if(d.reasons?.length){h+=`<div class="border-t border-border my-3"></div><details><summary class="text-[9px] text-gray-500 cursor-pointer">Score Breakdown</summary><div class="mt-2 space-y-0.5">`;d.reasons.forEach(r=>{h+=`<p class="text-[10px] ${r.includes('+')?'text-green-400':'text-red-400'}">${r.includes('+')?'✓':'✗'} ${r}</p>`});h+=`</div></details>`}
  }else if(['SCANNING','WAITING','FORMING','NO_TRADE'].includes(d.status)){
    // FVG waiting indicator for scanning state
    if (d.status === 'SCANNING') {
      h += fvgIndicator(d);
      h += `<div class="mt-3"></div>`;
    }
    
    h+=`<div class="grid grid-cols-2 sm:grid-cols-3 gap-1.5 info-grid">`;
    if(d.price)h+=box('Price','$'+d.price);
    if(d.trend)h+=box('Trend',d.trend,tc);
    if(d.range_high)h+=box('High','$'+d.range_high);
    if(d.range_low)h+=box('Low','$'+d.range_low);
    if(d.range_size)h+=box('Range','$'+d.range_size);
    if(d.next_window)h+=box('Next',d.next_window,'text-purple-400');
    h+=`</div>`;
  }else{
    h+=`<div class="grid grid-cols-2 gap-1.5">`;
    if(d.trend)h+=box('Trend',d.trend,tc);
    if(d.next_window)h+=box('Next',d.next_window,'text-purple-400');
    h+=`</div>`;
  }
  h+=`</div></div>`;
  return h;
}

let n=0;
async function go(){
  const st=document.getElementById('status');
  try{
    st.textContent='⟳';st.className='text-[10px] text-blue-400';
    const r=await fetch('/api/scan'),d=await r.json();
    document.getElementById('dashboard').innerHTML=render(d.NAS100)+render(d.BTCUSD)+render(d.GOLD);
    n++;document.getElementById('refresh-count').textContent=n;
    document.getElementById('last-update').textContent=new Date().toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit',hour12:false});
    st.textContent='LIVE';st.className='text-[10px] text-green-400 font-medium';
  }catch(e){st.textContent='ERR';st.className='text-[10px] text-red-400';}
}

function ck(){
  const n=new Date();
  document.getElementById('clock').textContent=n.toLocaleTimeString('en-US',{timeZone:'America/New_York',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false})+' ET';
  document.getElementById('date').textContent=n.toLocaleDateString('en-US',{timeZone:'America/New_York',weekday:'short',month:'short',day:'numeric'});
}

go();ck();setInterval(go,2000);setInterval(ck,1000);

if('Notification'in window&&Notification.permission==='default')Notification.requestPermission();
</script>
</body>
</html>"""