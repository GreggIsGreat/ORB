# Save as: api/index.py

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from datetime import datetime
import pytz
import urllib.request
import urllib.parse
import json
import ssl
import gzip

app = FastAPI()

# ═══════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════
SCRAPER_URL = "https://tradingview-scraper-production.up.railway.app"
TZ = pytz.timezone("Africa/Gaborone")

CONFIGS = {
    "NAS100": {
        "symbol": "OANDA:NAS100USD",
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
        "windows": None,
        "min_score": 5,
    },
    "BTCUSD": {
        "symbol": "BITSTAMP:BTCUSD",
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
        "windows": None,
        "min_score": 5,
    },
    "GOLD": {
        "symbol": "OANDA:XAUUSD",
        "max_range": None,
        "max_fvg": None,
        "max_speed": None,
        "weekend": False,
        "range": [(0,5,3),(5,10,2),(10,15,2),(25,9999,1),(15,25,0)],
        "fvg": [(1,3,2),(0,1,1),(5,10,1),(3,5,0),(10,9999,0)],
        "speed": [(60,120,3),(0,10,1),(10,30,1),(30,60,0),(120,9999,0)],
        "best_day": ("Friday",3),
        "good_days": [("Tuesday",3),("Wednesday",1)],
        "worst_day": ("Monday",-2),
        "bias": None,
        "windows": {
            "08:00 ET": {"start": 800, "end": 859, "score": 2, "wr": "69.4%"},
            "09:00 ET": {"start": 900, "end": 959, "score": 3, "wr": "73%+"},
            "13:00 ET": {"start": 1300, "end": 1359, "score": 3, "wr": "73%+"},
            "14:30 ET": {"start": 1430, "end": 1529, "score": 2, "wr": "71.4%"},
            "16:00 ET": {"start": 1600, "end": 1659, "score": 1, "wr": "65.9%"},
        },
        "min_score": 7,
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
# HTTP HELPER
# ═══════════════════════════════════════════════
def http_get(url, headers=None):
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        h = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        }
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, headers=h)
        resp = urllib.request.urlopen(req, timeout=15, context=ctx)
        raw = resp.read()
        if raw[:2] == b'\x1f\x8b':
            raw = gzip.decompress(raw)
        return json.loads(raw.decode('utf-8'))
    except Exception as e:
        raise Exception(f"HTTP error [{url[:80]}]: {str(e)}")

# ═══════════════════════════════════════════════
# RAILWAY SCRAPER
# ═══════════════════════════════════════════════
def fetch_candles(symbol, interval="1", limit=500):
    enc = urllib.parse.quote(symbol, safe='')
    endpoints = [
        f"{SCRAPER_URL}/api/history?symbol={enc}&interval={interval}&limit={limit}",
        f"{SCRAPER_URL}/api/history?symbol={enc}&resolution={interval}&bars_count={limit}",
        f"{SCRAPER_URL}/api/history?symbol={enc}&resolution={interval}&countback={limit}",
        f"{SCRAPER_URL}/api/candles?symbol={enc}&interval={interval}&limit={limit}",
        f"{SCRAPER_URL}/api/data?symbol={enc}&interval={interval}&limit={limit}",
    ]
    data = None
    last_err = None
    for url in endpoints:
        try:
            data = http_get(url)
            if data:
                break
        except Exception as e:
            last_err = str(e)
            continue
    if not data:
        return [], f"Scraper unreachable: {last_err}"
    return parse_candles(data)


def parse_candles(data):
    raw_list = []
    if isinstance(data, dict) and "t" in data and isinstance(data["t"], list):
        times = data.get("t", [])
        opens = data.get("o", [])
        highs = data.get("h", [])
        lows = data.get("l", [])
        closes = data.get("c", [])
        candles = []
        for i in range(len(times)):
            try:
                ts = times[i]
                if ts > 1e12:
                    ts = ts / 1000
                dt = datetime.fromtimestamp(ts, tz=TZ)
                candles.append({
                    "time": dt.strftime("%H:%M"),
                    "open": float(opens[i]),
                    "high": float(highs[i]),
                    "low": float(lows[i]),
                    "close": float(closes[i])
                })
            except:
                continue
        return (candles, None) if candles else ([], "No candles parsed from TV format")

    if isinstance(data, list):
        raw_list = data
    elif isinstance(data, dict):
        for key in ["candles", "data", "result", "bars", "ohlc", "klines"]:
            if key in data and isinstance(data[key], list):
                raw_list = data[key]
                break
        if not raw_list:
            return [], f"Unknown response keys: {list(data.keys())}"

    candles = []
    for item in raw_list:
        try:
            time_str = None
            if 'time' in item and isinstance(item['time'], str) and ':' in item['time']:
                time_str = item['time'][:5]
            elif 'timestamp' in item or 't' in item:
                ts = item.get('timestamp', item.get('t', 0))
                if isinstance(ts, (int, float)):
                    if ts > 1e12:
                        ts = ts / 1000
                    dt = datetime.fromtimestamp(ts, tz=TZ)
                    time_str = dt.strftime("%H:%M")
            elif 'datetime' in item or 'date' in item:
                dt_str = str(item.get('datetime', item.get('date', '')))
                try:
                    dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
                    dt = dt.astimezone(TZ)
                    time_str = dt.strftime("%H:%M")
                except:
                    continue
            if not time_str:
                continue
            o = float(item.get('open', item.get('o', 0)))
            h = float(item.get('high', item.get('h', 0)))
            l = float(item.get('low', item.get('l', 0)))
            c = float(item.get('close', item.get('c', 0)))
            if o == 0 and h == 0 and l == 0 and c == 0:
                continue
            candles.append({"time": time_str, "open": o, "high": h, "low": l, "close": c})
        except:
            continue
    return (candles, None) if candles else ([], "Could not parse any candles")


def scrape_asset(asset):
    cached = get_cached(asset)
    if cached:
        return cached
    config = CONFIGS[asset]
    symbol = config["symbol"]
    result = {
        "asset": asset, "symbol": symbol, "status": "ERROR", "candles": [],
        "ma50": None, "ma200": None, "price": None, "price_change": None,
        "price_change_pct": None, "day_open": None, "error": None,
        "source": "Railway Scraper", "candle_count": 0,
    }
    try:
        c15, err15 = fetch_candles(symbol, "15", 300)
        if not c15 or len(c15) < 50:
            result["error"] = f"Not enough 15m data ({len(c15) if c15 else 0} bars). {err15 or ''}"
            set_cached(asset, result)
            return result
        closes15 = [c['close'] for c in c15]
        result["ma50"] = round(sum(closes15[-50:]) / 50, 2)
        result["ma200"] = round(sum(closes15[-200:]) / 200, 2) if len(closes15) >= 200 else round(sum(closes15) / len(closes15), 2)
        c1, err1 = fetch_candles(symbol, "1", 500)
        if c1 and len(c1) > 0:
            result["candles"] = c1
            result["price"] = round(c1[-1]['close'], 2)
            result["day_open"] = round(c1[0]['open'], 2)
            result["candle_count"] = len(c1)
            result["status"] = "OK"
        else:
            result["candles"] = c15[-60:]
            result["price"] = round(c15[-1]['close'], 2)
            result["day_open"] = round(c15[0]['open'], 2)
            result["candle_count"] = len(c15)
            result["source"] += " (15m fallback)"
            result["status"] = "OK"
        if result["price"] and result["day_open"] and result["day_open"] != 0:
            result["price_change"] = round(result["price"] - result["day_open"], 2)
            result["price_change_pct"] = round(((result["price"] - result["day_open"]) / result["day_open"]) * 100, 3)
    except Exception as e:
        result["error"] = str(e)
    set_cached(asset, result)
    return result


def scrape_all():
    return {asset: scrape_asset(asset) for asset in CONFIGS}

# ═══════════════════════════════════════════════
# WINDOW DETECTION
# ═══════════════════════════════════════════════
def get_current_window(asset, now_utc):
    config = CONFIGS[asset]
    if not config.get("windows"):
        return None, None
    et = pytz.timezone("US/Eastern")
    cur = now_utc.astimezone(et)
    hm = cur.hour * 100 + cur.minute
    for label, w in config["windows"].items():
        if w["start"] <= hm <= w["end"]:
            return label, w
    return None, None

def get_next_window(asset, now_utc):
    config = CONFIGS[asset]
    if not config.get("windows"):
        return None
    et = pytz.timezone("US/Eastern")
    cur = now_utc.astimezone(et)
    hm = cur.hour * 100 + cur.minute
    sw = sorted(config["windows"].items(), key=lambda x: x[1]["start"])
    for label, w in sw:
        if w["start"] > hm:
            return label
    return sw[0][0] if sw else None

# ═══════════════════════════════════════════════
# SCORING
# ═══════════════════════════════════════════════
def score_trade(asset, range_size, fvg_size, speed, direction, day_name, window=None):
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
    for lo, hi, pts in c["range"]:
        if lo <= range_size <= hi:
            score += pts
            if pts > 0: reasons.append(f"Range ${lo}-${hi} → +{pts}")
            break
    for lo, hi, pts in c["fvg"]:
        if lo <= fvg_size <= hi:
            score += pts
            if pts > 0: reasons.append(f"FVG ${lo}-${hi} → +{pts}")
            break
    for lo, hi, pts in c["speed"]:
        if lo <= speed <= hi:
            score += pts
            if pts > 0: reasons.append(f"Speed {lo}-{hi} bars → +{pts}")
            break
    if c["best_day"] and day_name == c["best_day"][0]:
        score += c["best_day"][1]
        reasons.append(f"{day_name} → +{c['best_day'][1]}")
    else:
        for gd, pts in c["good_days"]:
            if day_name == gd:
                score += pts
                reasons.append(f"{day_name} → +{pts}")
                break
    if c["worst_day"] and day_name == c["worst_day"][0]:
        score += c["worst_day"][1]
        reasons.append(f"{day_name} → {c['worst_day'][1]} ⚠️")
    if c["bias"] and direction == c["bias"][0]:
        score += c["bias"][1]
        reasons.append(f"{direction} bias → +{c['bias'][1]}")
    min_s = c.get("min_score", 5)
    if asset == "GOLD":
        conf = "HIGH" if score >= 9 else "MEDIUM" if score >= 7 else "LOW"
    else:
        conf = "HIGH" if score >= 7 else "MEDIUM" if score >= 5 else "LOW"
    return {"score": score, "take_trade": score >= min_s, "confidence": conf, "reasons": reasons}


def detect_fvg(c1, c2, c3, direction):
    if direction == "LONG":
        gap = c3['low'] - c1['high']
        if gap > 0 and c2['close'] > c2['open']:
            return {"valid": True, "size": round(gap, 2), "entry": c3['low']}
    elif direction == "SHORT":
        gap = c1['low'] - c3['high']
        if gap > 0 and c2['close'] < c2['open']:
            return {"valid": True, "size": round(gap, 2), "entry": c3['high']}
    return {"valid": False, "size": 0, "entry": 0}

# ═══════════════════════════════════════════════
# SCANNER
# ═══════════════════════════════════════════════
def run_scan(asset, scraped):
    config = CONFIGS[asset]
    now = datetime.now(TZ)
    now_utc = now.astimezone(pytz.UTC)
    current_window, window_info = get_current_window(asset, now_utc)
    next_window = get_next_window(asset, now_utc) if not current_window else None
    base = {
        "asset": asset, "symbol": config["symbol"],
        "time": now.strftime("%H:%M:%S"), "day": now.strftime("%A"),
        "window": current_window, "next_window": next_window,
        "source": scraped.get("source", "Railway Scraper"),
        "price": scraped.get("price"), "price_change": scraped.get("price_change"),
        "price_change_pct": scraped.get("price_change_pct"),
        "day_open": scraped.get("day_open"),
        "ma50": scraped.get("ma50"), "ma200": scraped.get("ma200"),
    }
    if not config["weekend"] and now.weekday() >= 5:
        return {**base, "status": "CLOSED", "message": "Weekend — markets closed"}
    if scraped["status"] == "ERROR":
        return {**base, "status": "ERROR", "message": scraped.get("error", "Scraper failed")}
    ma50 = scraped["ma50"]
    ma200 = scraped["ma200"]
    trend = "BULLISH" if ma50 and ma200 and ma50 > ma200 else "BEARISH" if ma50 and ma200 else "UNKNOWN"
    base["trend"] = trend
    candles = scraped["candles"]
    price = scraped["price"]
    if not candles or len(candles) < 20:
        return {**base, "status": "FORMING", "message": f"Need more data — only {len(candles) if candles else 0} candles"}
    recent = candles[-60:] if len(candles) >= 60 else candles
    range_count = min(15, len(recent) // 3)
    if range_count < 5:
        return {**base, "status": "FORMING", "message": "Not enough candles for range"}
    range_candles = recent[:range_count]
    post_candles = recent[range_count:]
    rh = round(max(c['high'] for c in range_candles), 2)
    rl = round(min(c['low'] for c in range_candles), 2)
    rs = round(rh - rl, 2)
    base["range_high"] = rh
    base["range_low"] = rl
    base["range_size"] = rs
    if config["max_range"] and rs > config["max_range"]:
        return {**base, "status": "NO_TRADE", "message": f"Range too wide (${rs} > max ${config['max_range']})"}
    if len(post_candles) < 3:
        return {**base, "status": "FORMING", "message": "Waiting for post-range candles"}
    bias_dir = "LONG" if trend == "BULLISH" else "SHORT"
    day_name = now.strftime("%A")
    for i in range(len(post_candles) - 2):
        c1, c2, c3 = post_candles[i], post_candles[i+1], post_candles[i+2]
        if bias_dir == "LONG" and c2['close'] > rh:
            fvg = detect_fvg(c1, c2, c3, "LONG")
            if fvg['valid']:
                pred = score_trade(asset, rs, fvg['size'], i+1, "LONG", day_name, window=current_window)
                return {**base, "status": "TRADE" if pred["take_trade"] else "SKIP",
                    "message": f"{pred['confidence']} LONG — Score {pred['score']}/12",
                    "direction": "LONG", "entry": round(fvg['entry'], 2), "stop": rl,
                    "target": round(fvg['entry'] + (fvg['entry'] - rl), 2),
                    "fvg_size": fvg['size'], "speed": i + 1, "score": pred["score"],
                    "confidence": pred["confidence"], "reasons": pred["reasons"], "fvg_detected": True}
        if bias_dir == "SHORT" and c2['close'] < rl:
            fvg = detect_fvg(c1, c2, c3, "SHORT")
            if fvg['valid']:
                pred = score_trade(asset, rs, fvg['size'], i+1, "SHORT", day_name, window=current_window)
                return {**base, "status": "TRADE" if pred["take_trade"] else "SKIP",
                    "message": f"{pred['confidence']} SHORT — Score {pred['score']}/12",
                    "direction": "SHORT", "entry": round(fvg['entry'], 2), "stop": rh,
                    "target": round(fvg['entry'] - (rh - fvg['entry']), 2),
                    "fvg_size": fvg['size'], "speed": i + 1, "score": pred["score"],
                    "confidence": pred["confidence"], "reasons": pred["reasons"], "fvg_detected": True}
    if price > rh:
        msg = f"Price ABOVE range (+${round(price - rh, 2)}) — Waiting for FVG"
    elif price < rl:
        msg = f"Price BELOW range (-${round(rl - price, 2)}) — Waiting for FVG"
    else:
        msg = "Price INSIDE range — No breakout yet"
    return {**base, "status": "SCANNING", "message": msg, "fvg_detected": False}

# ═══════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════
@app.get("/api/scan")
def api_scan():
    scraped = scrape_all()
    return JSONResponse({asset: run_scan(asset, scraped[asset]) for asset in CONFIGS})

@app.get("/api/debug")
def api_debug():
    scraped = scrape_all()
    debug = {}
    for asset, d in scraped.items():
        debug[asset] = {
            "status": d["status"], "source": d.get("source"), "error": d.get("error"),
            "ma50": d.get("ma50"), "ma200": d.get("ma200"), "price": d.get("price"),
            "price_change": d.get("price_change"), "candle_count": d.get("candle_count", 0),
            "first_candle": d["candles"][0] if d["candles"] else None,
            "last_candle": d["candles"][-1] if d["candles"] else None,
        }
    debug["_config"] = {
        "scraper_url": SCRAPER_URL, "timezone": str(TZ),
        "symbols": {a: c["symbol"] for a, c in CONFIGS.items()},
    }
    return JSONResponse(debug)

@app.get("/api/scraper-test")
def api_scraper_test():
    results = {}
    for asset, cfg in CONFIGS.items():
        c, err = fetch_candles(cfg["symbol"], "1", 5)
        results[asset] = {"symbol": cfg["symbol"], "success": len(c) > 0, "count": len(c), "error": err, "sample": c[:2] if c else None}
    ok = all(r["success"] for r in results.values())
    return JSONResponse({"status": "OK" if ok else "PARTIAL" if any(r["success"] for r in results.values()) else "FAILED", "scraper_url": SCRAPER_URL, "results": results})

@app.get("/api/health")
def health():
    scraper_ok = False
    try:
        http_get(f"{SCRAPER_URL}/api/health")
        scraper_ok = True
    except:
        pass
    return {"status": "ok", "time": datetime.now(TZ).isoformat(), "timezone": str(TZ), "scraper_url": SCRAPER_URL, "scraper_connected": scraper_ok}

# ═══════════════════════════════════════════════
# RESPONSIVE UI
# ═══════════════════════════════════════════════
@app.get("/", response_class=HTMLResponse)
def home():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta name="theme-color" content="#09090b">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>ORB Scanner</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='20' fill='%2309090b'/><text y='72' x='50' text-anchor='middle' font-size='55' font-weight='bold' fill='%2322c55e'>⟐</text></svg>">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdn.tailwindcss.com"></script>
<script>
tailwind.config={theme:{extend:{
  colors:{bg:'#09090b',card:'#111113',card2:'#161618',border:'#1e1e22',accent:'#18181b',hover:'#232326'},
  fontFamily:{mono:['JetBrains Mono','monospace'],sans:['Inter','system-ui','sans-serif']}
}}}
</script>
<style>
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html{font-family:'Inter',system-ui,sans-serif;-webkit-font-smoothing:antialiased}
body{overscroll-behavior:none}

/* animations */
@keyframes pulse-dot{0%,100%{opacity:1}50%{opacity:.4}}
@keyframes fvg-glow{0%,100%{box-shadow:0 0 8px rgba(34,197,94,.4)}50%{box-shadow:0 0 24px rgba(34,197,94,.7)}}
@keyframes trade-ring{0%,100%{box-shadow:0 0 0 2px rgba(34,197,94,.3)}50%{box-shadow:0 0 0 4px rgba(34,197,94,.5)}}
@keyframes flash-up{0%{color:#22c55e;transform:scale(1.03)}100%{color:#fff;transform:scale(1)}}
@keyframes flash-dn{0%{color:#ef4444;transform:scale(1.03)}100%{color:#fff;transform:scale(1)}}
@keyframes shimmer{0%{background-position:-200% 0}100%{background-position:200% 0}}
@keyframes slide-up{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
@keyframes spin{to{transform:rotate(360deg)}}

.live-dot{animation:pulse-dot 2s infinite}
.fvg-glow{animation:fvg-glow 2s infinite}
.trade-ring{animation:trade-ring 2s infinite}
.flash-up{animation:flash-up .5s ease-out}
.flash-dn{animation:flash-dn .5s ease-out}
.slide-up{animation:slide-up .3s ease-out both}
.glass{backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px)}

.shimmer{
  background:linear-gradient(90deg,#18181b 25%,#232326 50%,#18181b 75%);
  background-size:200% 100%;
  animation:shimmer 1.5s infinite;
}

/* scrollbar */
::-webkit-scrollbar{height:4px;width:4px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:#333;border-radius:4px}

/* ticker scroll */
.ticker-scroll{
  display:flex;gap:1.5rem;overflow-x:auto;scroll-snap-type:x mandatory;
  -ms-overflow-style:none;scrollbar-width:none;
}
.ticker-scroll::-webkit-scrollbar{display:none}
.ticker-item{scroll-snap-align:start;flex-shrink:0}

/* card hover */
.card-hover{transition:border-color .2s,transform .15s}
.card-hover:active{transform:scale(.995)}
@media(hover:hover){.card-hover:hover{border-color:#333}}

/* responsive grid helpers */
@media(max-width:480px){
  .price-main{font-size:1.5rem !important}
  .stat-grid{grid-template-columns:repeat(2,1fr) !important}
}
@media(min-width:481px) and (max-width:768px){
  .price-main{font-size:1.75rem !important}
}
@media(min-width:1024px){
  .stat-grid{grid-template-columns:repeat(4,1fr) !important}
}
</style>
</head>
<body class="bg-bg text-gray-300 min-h-screen">

<!-- ═══ HEADER ═══ -->
<header class="border-b border-border bg-card/90 glass sticky top-0 z-50">
  <div class="w-full max-w-7xl mx-auto px-3 sm:px-4 lg:px-6 py-2.5 sm:py-3">
    <div class="flex items-center justify-between gap-2">
      <div class="min-w-0">
        <div class="flex items-center gap-2">
          <h1 class="text-sm sm:text-lg font-bold text-white truncate">ORB Scanner</h1>
          <span class="hidden sm:inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[8px] bg-green-500/10 text-green-400 border border-green-500/20 font-medium">
            <span class="w-1 h-1 rounded-full bg-green-500"></span>RAILWAY
          </span>
        </div>
        <p class="text-[8px] sm:text-[10px] text-gray-600 truncate">Africa/Gaborone · CAT</p>
      </div>
      <div class="flex items-center gap-2 sm:gap-3 flex-shrink-0">
        <div class="text-right hidden xs:block">
          <p class="text-[11px] sm:text-sm text-white font-mono font-medium" id="clock">--:--:--</p>
          <p class="text-[8px] sm:text-[10px] text-gray-600" id="date">Loading...</p>
        </div>
        <div class="flex items-center gap-1.5 bg-accent/50 rounded-full px-2 py-1">
          <span class="w-1.5 h-1.5 sm:w-2 sm:h-2 rounded-full bg-green-500 live-dot"></span>
          <span class="text-[9px] sm:text-[10px] text-green-400 font-semibold" id="status">...</span>
        </div>
      </div>
    </div>
  </div>
</header>

<!-- ═══ PRICE TICKER ═══ -->
<div class="border-b border-border bg-bg">
  <div class="w-full max-w-7xl mx-auto px-3 sm:px-4 lg:px-6 py-2">
    <div class="ticker-scroll" id="ticker">
      <span class="text-[10px] text-gray-600 py-1">Loading prices...</span>
    </div>
  </div>
</div>

<!-- ═══ STATS ROW ═══ -->
<div class="w-full max-w-7xl mx-auto px-3 sm:px-4 lg:px-6 pt-3 pb-1">
  <div class="grid grid-cols-3 sm:grid-cols-4 gap-1.5 sm:gap-2">
    <div class="bg-card border border-border rounded-lg px-2 py-1.5 sm:py-2 text-center">
      <p class="text-[7px] sm:text-[8px] text-gray-600 uppercase tracking-wider">Markets</p>
      <p class="text-xs sm:text-sm font-bold text-white">3</p>
    </div>
    <div class="bg-card border border-border rounded-lg px-2 py-1.5 sm:py-2 text-center">
      <p class="text-[7px] sm:text-[8px] text-gray-600 uppercase tracking-wider">Refresh</p>
      <p class="text-xs sm:text-sm font-bold text-white">2s</p>
    </div>
    <div class="bg-card border border-border rounded-lg px-2 py-1.5 sm:py-2 text-center">
      <p class="text-[7px] sm:text-[8px] text-gray-600 uppercase tracking-wider">Updates</p>
      <p class="text-xs sm:text-sm font-bold text-white font-mono" id="n">0</p>
    </div>
    <div class="bg-card border border-border rounded-lg px-2 py-1.5 sm:py-2 text-center hidden sm:block">
      <p class="text-[7px] sm:text-[8px] text-gray-600 uppercase tracking-wider">Source</p>
      <p class="text-xs sm:text-sm font-bold text-green-400">Railway</p>
    </div>
  </div>
</div>

<!-- ═══ CARDS ═══ -->
<main class="w-full max-w-7xl mx-auto px-3 sm:px-4 lg:px-6 py-3">
  <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3" id="cards">
    <div class="bg-card border border-border rounded-2xl p-4 sm:p-5"><div class="h-3 shimmer rounded w-16 mb-3"></div><div class="h-7 shimmer rounded w-32 mb-2"></div><div class="h-4 shimmer rounded w-24"></div></div>
    <div class="bg-card border border-border rounded-2xl p-4 sm:p-5"><div class="h-3 shimmer rounded w-16 mb-3"></div><div class="h-7 shimmer rounded w-32 mb-2"></div><div class="h-4 shimmer rounded w-24"></div></div>
    <div class="bg-card border border-border rounded-2xl p-4 sm:p-5 md:col-span-2 lg:col-span-1"><div class="h-3 shimmer rounded w-16 mb-3"></div><div class="h-7 shimmer rounded w-32 mb-2"></div><div class="h-4 shimmer rounded w-24"></div></div>
  </div>

  <div class="mt-5 flex items-center justify-center gap-3 flex-wrap">
    <a href="/api/debug" class="text-[10px] text-gray-600 hover:text-blue-400 transition-colors px-2 py-1 rounded-md hover:bg-card">Debug</a>
    <span class="text-gray-800">·</span>
    <a href="/api/scraper-test" class="text-[10px] text-gray-600 hover:text-blue-400 transition-colors px-2 py-1 rounded-md hover:bg-card">Test Scraper</a>
    <span class="text-gray-800">·</span>
    <a href="/api/health" class="text-[10px] text-gray-600 hover:text-blue-400 transition-colors px-2 py-1 rounded-md hover:bg-card">Health</a>
  </div>
</main>

<script>
/* ══ CONSTANTS ══ */
const ST={
  TRADE:{bg:'bg-green-500/10',bd:'border-green-500/30',tx:'text-green-400',lb:'TRADE',ring:'ring-2 ring-green-500/30 trade-ring'},
  SKIP:{bg:'bg-yellow-500/10',bd:'border-yellow-500/30',tx:'text-yellow-400',lb:'SKIP',ring:''},
  SCANNING:{bg:'bg-blue-500/10',bd:'border-blue-500/30',tx:'text-blue-400',lb:'SCAN',ring:''},
  CLOSED:{bg:'bg-gray-500/10',bd:'border-gray-500/30',tx:'text-gray-500',lb:'CLOSED',ring:''},
  FORMING:{bg:'bg-indigo-500/10',bd:'border-indigo-500/30',tx:'text-indigo-400',lb:'FORMING',ring:''},
  NO_TRADE:{bg:'bg-orange-500/10',bd:'border-orange-500/30',tx:'text-orange-400',lb:'SKIP',ring:''},
  ERROR:{bg:'bg-red-500/10',bd:'border-red-500/30',tx:'text-red-400',lb:'ERROR',ring:'ring-1 ring-red-500/20'}
};
const ICONS={NAS100:'📈',BTCUSD:'₿',GOLD:'🥇'};

/* FVG SVGs */
const FVGL=`<svg viewBox="0 0 60 40" class="w-10 h-7 sm:w-12 sm:h-8"><rect x="5" y="8" width="8" height="20" fill="#ef4444" rx="1"/><line x1="9" y1="4" x2="9" y2="8" stroke="#ef4444" stroke-width="2"/><line x1="9" y1="28" x2="9" y2="34" stroke="#ef4444" stroke-width="2"/><rect x="22" y="4" width="10" height="28" fill="#22c55e" rx="1"/><line x1="27" y1="2" x2="27" y2="4" stroke="#22c55e" stroke-width="2"/><line x1="27" y1="32" x2="27" y2="36" stroke="#22c55e" stroke-width="2"/><rect x="41" y="6" width="8" height="16" fill="#22c55e" rx="1"/><line x1="45" y1="2" x2="45" y2="6" stroke="#22c55e" stroke-width="2"/><line x1="45" y1="22" x2="45" y2="28" stroke="#22c55e" stroke-width="2"/><rect x="13" y="8" width="28" height="6" fill="#22c55e" fill-opacity=".15" stroke="#22c55e" stroke-width="1" stroke-dasharray="2,2" rx="2"/></svg>`;
const FVGS=`<svg viewBox="0 0 60 40" class="w-10 h-7 sm:w-12 sm:h-8"><rect x="5" y="12" width="8" height="20" fill="#22c55e" rx="1"/><line x1="9" y1="6" x2="9" y2="12" stroke="#22c55e" stroke-width="2"/><line x1="9" y1="32" x2="9" y2="36" stroke="#22c55e" stroke-width="2"/><rect x="22" y="8" width="10" height="28" fill="#ef4444" rx="1"/><line x1="27" y1="4" x2="27" y2="8" stroke="#ef4444" stroke-width="2"/><line x1="27" y1="36" x2="27" y2="38" stroke="#ef4444" stroke-width="2"/><rect x="41" y="18" width="8" height="16" fill="#ef4444" rx="1"/><line x1="45" y1="12" x2="45" y2="18" stroke="#ef4444" stroke-width="2"/><line x1="45" y1="34" x2="45" y2="38" stroke="#ef4444" stroke-width="2"/><rect x="13" y="26" width="28" height="6" fill="#ef4444" fill-opacity=".15" stroke="#ef4444" stroke-width="1" stroke-dasharray="2,2" rx="2"/></svg>`;
const FVGW=`<svg viewBox="0 0 60 40" class="w-10 h-7 sm:w-12 sm:h-8 opacity-30"><rect x="8" y="10" width="8" height="18" fill="#555" rx="1"/><line x1="12" y1="6" x2="12" y2="10" stroke="#555" stroke-width="2"/><line x1="12" y1="28" x2="12" y2="34" stroke="#555" stroke-width="2"/><rect x="24" y="8" width="8" height="22" fill="#555" rx="1"/><line x1="28" y1="4" x2="28" y2="8" stroke="#555" stroke-width="2"/><line x1="28" y1="30" x2="28" y2="36" stroke="#555" stroke-width="2"/><text x="44" y="25" font-size="16" fill="#555" font-weight="bold">?</text></svg>`;

/* ══ HELPERS ══ */
const fmt=p=>p==null?'--':Number(p).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});

const badge=s=>{
  const c=ST[s]||ST.ERROR;
  return`<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[8px] sm:text-[9px] font-bold ${c.bg} ${c.tx} border ${c.bd} tracking-wide">${c.lb}</span>`;
};

const box=(l,v,c='text-white')=>`
  <div class="bg-bg/60 border border-border rounded-lg px-2 py-1.5 sm:px-2.5 sm:py-2 min-w-0">
    <p class="text-[7px] sm:text-[8px] text-gray-600 uppercase tracking-wider mb-0.5">${l}</p>
    <p class="text-[11px] sm:text-xs font-semibold ${c} truncate font-mono">${v}</p>
  </div>`;

const scoreBar=s=>{
  const p=Math.min(Math.round(s/12*100),100);
  const c=s>=9?'#22c55e':s>=7?'#84cc16':s>=5?'#eab308':'#ef4444';
  return`<div class="mt-3">
    <div class="flex justify-between items-center text-[9px] sm:text-[10px] mb-1.5">
      <span class="text-gray-500 font-medium">Confidence Score</span>
      <span class="font-bold font-mono" style="color:${c}">${s}/12</span>
    </div>
    <div class="bg-gray-800/80 rounded-full h-1.5 sm:h-2 overflow-hidden">
      <div class="h-full rounded-full transition-all duration-500 ease-out" style="width:${p}%;background:${c}"></div>
    </div>
  </div>`;
};

function fvgBlock(d){
  if(d.fvg_detected&&d.direction){
    const ic=d.direction==='LONG'?FVGL:FVGS;
    const bc=d.direction==='LONG'?'border-green-500/30 bg-green-500/5':'border-red-500/30 bg-red-500/5';
    const tc=d.direction==='LONG'?'text-green-400':'text-red-400';
    return`<div class="flex items-center gap-2.5 p-2 sm:p-2.5 rounded-xl border ${bc} fvg-glow mt-3">
      ${ic}
      <div class="min-w-0">
        <p class="text-[8px] sm:text-[9px] text-gray-400 uppercase tracking-wider">FVG Detected</p>
        <p class="text-xs sm:text-sm font-bold ${tc}">${d.direction} · $${d.fvg_size}</p>
      </div>
    </div>`;
  }
  if(d.status==='SCANNING')
    return`<div class="flex items-center gap-2.5 p-2 sm:p-2.5 rounded-xl border border-border bg-card2/50 mt-3">
      ${FVGW}
      <div><p class="text-[8px] sm:text-[9px] text-gray-500 uppercase tracking-wider">Waiting for FVG</p>
      <p class="text-[10px] text-gray-600">Scanning candles…</p></div>
    </div>`;
  return'';
}

function changeTag(d){
  if(d.price_change==null) return'';
  const up=d.price_change>=0;
  const s=up?'+':'';
  const cl=up?'text-green-400':'text-red-400';
  return`<span class="text-[10px] sm:text-xs font-medium ${cl}">
    ${up?'▲':'▼'} ${s}$${fmt(Math.abs(d.price_change))}
    <span class="opacity-70">(${s}${d.price_change_pct||0}%)</span>
  </span>`;
}

/* ══ CARD RENDERER ══ */
let prevP={};
function card(d,idx){
  const isTrade=d.status==='TRADE'||d.status==='SKIP';
  const dc=d.direction==='LONG'?'text-green-400':'text-red-400';
  const di=d.direction==='LONG'?'↑':'↓';
  const tc=d.trend==='BULLISH'?'text-green-400':d.trend==='BEARISH'?'text-red-400':'text-gray-500';
  const st=ST[d.status]||ST.ERROR;

  const prev=prevP[d.asset];
  const flash=prev&&d.price!==prev?(d.price>prev?'flash-up':'flash-dn'):'';
  prevP[d.asset]=d.price;

  let h=`<div class="bg-card border border-border rounded-2xl overflow-hidden card-hover slide-up ${st.ring}" style="animation-delay:${idx*60}ms">`;

  /* ── HEADER ── */
  h+=`<div class="px-3 sm:px-4 pt-3 pb-1.5 flex items-center justify-between">
    <div class="flex items-center gap-1.5 sm:gap-2 min-w-0">
      <span class="text-base sm:text-lg">${ICONS[d.asset]||'📊'}</span>
      <span class="text-sm sm:text-base font-bold text-white">${d.asset}</span>
      ${d.window?`<span class="text-[7px] sm:text-[8px] text-purple-400 bg-purple-500/10 px-1.5 py-0.5 rounded-md border border-purple-500/20 truncate max-w-[80px]">${d.window}</span>`:''}
    </div>
    ${badge(d.status)}
  </div>`;

  /* ── PRICE ── */
  h+=`<div class="px-3 sm:px-4 pb-3 border-b border-border">
    <div class="flex items-end justify-between gap-2">
      <div class="min-w-0 flex-1">
        <p class="text-xl sm:text-2xl md:text-3xl font-bold text-white font-mono price-main ${flash} leading-tight">
          $${fmt(d.price)}
        </p>
        <div class="mt-1">${changeTag(d)}</div>
      </div>
      <div class="text-right flex-shrink-0 space-y-0.5">
        ${d.trend?`<p class="text-[10px] sm:text-xs font-semibold ${tc}">${d.trend==='BULLISH'?'▲':'▼'} ${d.trend}</p>`:''}
        ${d.ma50?`<p class="text-[8px] sm:text-[9px] text-gray-600 font-mono">MA50 ${fmt(d.ma50)}</p>`:''}
        ${d.ma200?`<p class="text-[8px] sm:text-[9px] text-gray-600 font-mono">MA200 ${fmt(d.ma200)}</p>`:''}
      </div>
    </div>
  </div>`;

  /* ── BODY ── */
  h+=`<div class="px-3 sm:px-4 py-3">
    <p class="text-[11px] sm:text-xs text-gray-200 leading-relaxed">${d.message}</p>`;

  if(isTrade){
    h+=fvgBlock(d);
    h+=`<div class="grid grid-cols-2 gap-1.5 mt-3">
      ${box('Direction',di+' '+d.direction,dc)}
      ${box('Confidence',d.confidence,d.confidence==='HIGH'?'text-green-400':d.confidence==='MEDIUM'?'text-yellow-400':'text-orange-400')}
    </div>`;
    h+=scoreBar(d.score);
    h+=`<div class="border-t border-border my-3"></div>`;
    h+=`<div class="grid grid-cols-2 sm:grid-cols-4 gap-1.5 stat-grid">
      ${box('Entry','$'+fmt(d.entry),dc)}
      ${box('Stop','$'+fmt(d.stop),'text-red-400')}
      ${box('Target','$'+fmt(d.target),'text-green-400')}
      ${box('Range','$'+fmt(d.range_size))}
    </div>`;
    h+=`<div class="grid grid-cols-3 gap-1.5 mt-1.5">
      ${box('FVG','$'+d.fvg_size)}
      ${box('Speed',d.speed+' bar'+(d.speed>1?'s':''))}
      ${box('Day',d.day||'--')}
    </div>`;
    if(d.reasons?.length){
      h+=`<details class="mt-3 group">
        <summary class="text-[9px] sm:text-[10px] text-gray-500 cursor-pointer hover:text-gray-300 transition-colors flex items-center gap-1">
          <svg class="w-3 h-3 transition-transform group-open:rotate-90" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
          Score Breakdown
        </summary>
        <div class="mt-2 space-y-1 pl-4 border-l-2 border-border">`;
      d.reasons.forEach(r=>{
        const pos=r.includes('+');
        h+=`<p class="text-[9px] sm:text-[10px] ${pos?'text-green-400':'text-red-400'} flex items-center gap-1">
          <span class="w-3.5 text-center">${pos?'✓':'✗'}</span>${r}</p>`;
      });
      h+=`</div></details>`;
    }
  }else if(['SCANNING','FORMING','NO_TRADE'].includes(d.status)){
    if(d.status==='SCANNING') h+=fvgBlock(d);
    h+=`<div class="grid grid-cols-2 sm:grid-cols-3 gap-1.5 mt-3 stat-grid">`;
    if(d.range_high) h+=box('High','$'+fmt(d.range_high));
    if(d.range_low) h+=box('Low','$'+fmt(d.range_low));
    if(d.range_size) h+=box('Range','$'+fmt(d.range_size));
    if(d.day_open) h+=box('Open','$'+fmt(d.day_open));
    if(d.next_window) h+=box('Next Window',d.next_window,'text-purple-400');
    if(d.day) h+=box('Day',d.day);
    h+=`</div>`;
  }else{
    h+=`<div class="grid grid-cols-2 gap-1.5 mt-3">`;
    if(d.trend) h+=box('Trend',d.trend,tc);
    if(d.day) h+=box('Day',d.day);
    if(d.next_window) h+=box('Next',d.next_window,'text-purple-400');
    h+=`</div>`;
  }

  h+=`</div></div>`;
  return h;
}

/* ══ TICKER ══ */
function ticker(data){
  let h='';
  ['NAS100','BTCUSD','GOLD'].forEach(a=>{
    const d=data[a]; if(!d||!d.price) return;
    const up=(d.price_change||0)>=0;
    const cc=up?'text-green-400':'text-red-400';
    const bg=up?'bg-green-500/5':'bg-red-500/5';
    h+=`<div class="ticker-item flex items-center gap-2 ${bg} rounded-lg px-2.5 py-1.5 sm:px-3">
      <span class="text-sm sm:text-base">${ICONS[a]}</span>
      <div class="flex items-center gap-1.5 sm:gap-2">
        <span class="text-[10px] sm:text-xs text-gray-400 font-medium">${a}</span>
        <span class="text-xs sm:text-sm font-bold text-white font-mono">$${fmt(d.price)}</span>
        ${d.price_change!=null?`<span class="text-[9px] sm:text-[10px] font-medium ${cc}">${up?'▲':'▼'}${Math.abs(d.price_change_pct||0)}%</span>`:''}
      </div>
    </div>`;
  });
  document.getElementById('ticker').innerHTML=h||'<span class="text-[10px] text-gray-600 py-1">No prices available</span>';
}

/* ══ MAIN ══ */
let n=0, errCount=0;

async function go(){
  const st=document.getElementById('status');
  try{
    st.innerHTML='<span class="inline-block w-3 h-3 border-2 border-blue-400 border-t-transparent rounded-full" style="animation:spin .6s linear infinite"></span>';
    
    const r=await fetch('/api/scan');
    if(!r.ok) throw new Error('HTTP '+r.status);
    const d=await r.json();
    
    const el=document.getElementById('cards');
    el.innerHTML=card(d.NAS100,0)+card(d.BTCUSD,1)+card(d.GOLD,2);
    
    ticker(d);
    n++; errCount=0;
    document.getElementById('n').textContent=n;
    st.textContent='LIVE';
    st.className='text-[9px] sm:text-[10px] text-green-400 font-semibold';
  }catch(e){
    errCount++;
    st.textContent=errCount>3?'OFFLINE':'RETRY';
    st.className='text-[9px] sm:text-[10px] text-red-400 font-semibold';
    console.error('Scan error:',e);
  }
}

function ck(){
  const d=new Date();
  const el=document.getElementById('clock');
  if(el) el.textContent=d.toLocaleTimeString('en-US',{timeZone:'Africa/Gaborone',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false})+' CAT';
  const del=document.getElementById('date');
  if(del) del.textContent=d.toLocaleDateString('en-US',{timeZone:'Africa/Gaborone',weekday:'short',month:'short',day:'numeric'});
}

/* Start */
go(); ck();
setInterval(go, 2000);
setInterval(ck, 1000);
</script>
</body>
</html>"""