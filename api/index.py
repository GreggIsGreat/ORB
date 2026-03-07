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
# RAILWAY SCRAPER — SINGLE DATA SOURCE
# ═══════════════════════════════════════════════
def fetch_candles(symbol, interval="1", limit=500):
    """Fetch OHLC candles from Railway TradingView scraper."""
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
    """Normalise any response format into [{time,open,high,low,close}, ...]"""
    raw_list = []

    # ── TradingView array format {t:[],o:[],h:[],l:[],c:[]} ──
    if isinstance(data, dict) and "t" in data and isinstance(data["t"], list):
        times  = data.get("t", [])
        opens  = data.get("o", [])
        highs  = data.get("h", [])
        lows   = data.get("l", [])
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

    # ── Direct array ──
    if isinstance(data, list):
        raw_list = data

    # ── Wrapped object ──
    elif isinstance(data, dict):
        for key in ["candles", "data", "result", "bars", "ohlc", "klines"]:
            if key in data and isinstance(data[key], list):
                raw_list = data[key]
                break
        if not raw_list:
            return [], f"Unknown response keys: {list(data.keys())}"

    # ── Normalise individual candle objects ──
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


# ═══════════════════════════════════════════════
# SCRAPE ASSET (single entry point)
# ═══════════════════════════════════════════════
def scrape_asset(asset):
    cached = get_cached(asset)
    if cached:
        return cached

    config = CONFIGS[asset]
    symbol = config["symbol"]

    result = {
        "asset": asset,
        "symbol": symbol,
        "status": "ERROR",
        "candles": [],
        "ma50": None,
        "ma200": None,
        "price": None,
        "price_change": None,
        "price_change_pct": None,
        "day_open": None,
        "error": None,
        "source": "Railway Scraper",
        "candle_count": 0,
    }

    try:
        # ── 15-min candles → MAs ──
        c15, err15 = fetch_candles(symbol, "15", 300)
        if not c15 or len(c15) < 50:
            result["error"] = f"Not enough 15m data ({len(c15) if c15 else 0} bars). {err15 or ''}"
            set_cached(asset, result)
            return result

        closes15 = [c['close'] for c in c15]
        result["ma50"] = round(sum(closes15[-50:]) / 50, 2)
        result["ma200"] = round(sum(closes15[-200:]) / 200, 2) if len(closes15) >= 200 else round(sum(closes15) / len(closes15), 2)

        # ── 1-min candles → scanning ──
        c1, err1 = fetch_candles(symbol, "1", 500)

        if c1 and len(c1) > 0:
            result["candles"] = c1
            result["price"] = round(c1[-1]['close'], 2)
            result["day_open"] = round(c1[0]['open'], 2)
            result["candle_count"] = len(c1)
            result["status"] = "OK"
        else:
            # Fallback to 15m bars
            result["candles"] = c15[-60:]
            result["price"] = round(c15[-1]['close'], 2)
            result["day_open"] = round(c15[0]['open'], 2)
            result["candle_count"] = len(c15)
            result["source"] += " (15m fallback)"
            result["status"] = "OK"

        # Daily change
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
# WINDOW DETECTION (GOLD — scored in ET)
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
# SCORING MODEL
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
            if pts > 0:
                reasons.append(f"Range ${lo}-${hi} → +{pts}")
            break

    for lo, hi, pts in c["fvg"]:
        if lo <= fvg_size <= hi:
            score += pts
            if pts > 0:
                reasons.append(f"FVG ${lo}-${hi} → +{pts}")
            break

    for lo, hi, pts in c["speed"]:
        if lo <= speed <= hi:
            score += pts
            if pts > 0:
                reasons.append(f"Speed {lo}-{hi} bars → +{pts}")
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
# SCANNER — DYNAMIC, ANY TIME
# ═══════════════════════════════════════════════
def run_scan(asset, scraped):
    config = CONFIGS[asset]
    now = datetime.now(TZ)
    now_utc = now.astimezone(pytz.UTC)

    current_window, window_info = get_current_window(asset, now_utc)
    next_window = get_next_window(asset, now_utc) if not current_window else None

    base = {
        "asset": asset,
        "symbol": config["symbol"],
        "time": now.strftime("%H:%M:%S"),
        "day": now.strftime("%A"),
        "window": current_window,
        "next_window": next_window,
        "source": scraped.get("source", "Railway Scraper"),
        "price": scraped.get("price"),
        "price_change": scraped.get("price_change"),
        "price_change_pct": scraped.get("price_change_pct"),
        "day_open": scraped.get("day_open"),
        "ma50": scraped.get("ma50"),
        "ma200": scraped.get("ma200"),
    }

    # Weekend gate for non-crypto only
    if not config["weekend"] and now.weekday() >= 5:
        return {**base, "status": "CLOSED", "message": "Weekend — markets closed"}

    # Scraper error
    if scraped["status"] == "ERROR":
        return {**base, "status": "ERROR", "message": scraped.get("error", "Scraper failed")}

    # Trend
    ma50 = scraped["ma50"]
    ma200 = scraped["ma200"]
    trend = "BULLISH" if ma50 and ma200 and ma50 > ma200 else "BEARISH" if ma50 and ma200 else "UNKNOWN"
    base["trend"] = trend

    candles = scraped["candles"]
    price = scraped["price"]

    if not candles or len(candles) < 20:
        return {**base, "status": "FORMING", "message": f"Need more data — only {len(candles) if candles else 0} candles"}

    # ══════════════════════════════════
    # DYNAMIC OPENING RANGE
    # Last 60 candles → first 15 = range,
    # remaining = scan zone for breakout+FVG
    # ══════════════════════════════════
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

    # Scan for breakout + FVG
    for i in range(len(post_candles) - 2):
        c1, c2, c3 = post_candles[i], post_candles[i+1], post_candles[i+2]

        if bias_dir == "LONG" and c2['close'] > rh:
            fvg = detect_fvg(c1, c2, c3, "LONG")
            if fvg['valid']:
                pred = score_trade(asset, rs, fvg['size'], i+1, "LONG", day_name, window=current_window)
                return {
                    **base,
                    "status": "TRADE" if pred["take_trade"] else "SKIP",
                    "message": f"{pred['confidence']} LONG — Score {pred['score']}/12",
                    "direction": "LONG",
                    "entry": round(fvg['entry'], 2),
                    "stop": rl,
                    "target": round(fvg['entry'] + (fvg['entry'] - rl), 2),
                    "fvg_size": fvg['size'],
                    "speed": i + 1,
                    "score": pred["score"],
                    "confidence": pred["confidence"],
                    "reasons": pred["reasons"],
                    "fvg_detected": True,
                }

        if bias_dir == "SHORT" and c2['close'] < rl:
            fvg = detect_fvg(c1, c2, c3, "SHORT")
            if fvg['valid']:
                pred = score_trade(asset, rs, fvg['size'], i+1, "SHORT", day_name, window=current_window)
                return {
                    **base,
                    "status": "TRADE" if pred["take_trade"] else "SKIP",
                    "message": f"{pred['confidence']} SHORT — Score {pred['score']}/12",
                    "direction": "SHORT",
                    "entry": round(fvg['entry'], 2),
                    "stop": rh,
                    "target": round(fvg['entry'] - (rh - fvg['entry']), 2),
                    "fvg_size": fvg['size'],
                    "speed": i + 1,
                    "score": pred["score"],
                    "confidence": pred["confidence"],
                    "reasons": pred["reasons"],
                    "fvg_detected": True,
                }

    # No FVG found yet
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
            "status": d["status"],
            "source": d.get("source"),
            "error": d.get("error"),
            "ma50": d.get("ma50"),
            "ma200": d.get("ma200"),
            "price": d.get("price"),
            "price_change": d.get("price_change"),
            "candle_count": d.get("candle_count", 0),
            "first_candle": d["candles"][0] if d["candles"] else None,
            "last_candle": d["candles"][-1] if d["candles"] else None,
        }
    debug["_config"] = {
        "scraper_url": SCRAPER_URL,
        "timezone": str(TZ),
        "symbols": {a: c["symbol"] for a, c in CONFIGS.items()},
    }
    return JSONResponse(debug)

@app.get("/api/scraper-test")
def api_scraper_test():
    results = {}
    for asset, cfg in CONFIGS.items():
        c, err = fetch_candles(cfg["symbol"], "1", 5)
        results[asset] = {
            "symbol": cfg["symbol"],
            "success": len(c) > 0,
            "count": len(c),
            "error": err,
            "sample": c[:2] if c else None,
        }
    ok = all(r["success"] for r in results.values())
    return JSONResponse({
        "status": "OK" if ok else "PARTIAL" if any(r["success"] for r in results.values()) else "FAILED",
        "scraper_url": SCRAPER_URL,
        "results": results,
    })

@app.get("/api/health")
def health():
    scraper_ok = False
    try:
        http_get(f"{SCRAPER_URL}/api/health")
        scraper_ok = True
    except:
        pass
    return {
        "status": "ok",
        "time": datetime.now(TZ).isoformat(),
        "timezone": str(TZ),
        "scraper_url": SCRAPER_URL,
        "scraper_connected": scraper_ok,
    }

# ═══════════════════════════════════════════════
# UI — PRICES + CAT TIMEZONE
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
tailwind.config={theme:{extend:{colors:{bg:'#09090b',card:'#111113',border:'#1e1e22',accent:'#18181b'}}}}
</script>
<style>
@keyframes pulse-dot{0%,100%{opacity:1}50%{opacity:.5}}
@keyframes fvg-glow{0%,100%{box-shadow:0 0 5px rgba(34,197,94,.5)}50%{box-shadow:0 0 20px rgba(34,197,94,.8)}}
@keyframes price-flash-up{0%{color:#22c55e;transform:scale(1.02)}100%{color:#fff;transform:scale(1)}}
@keyframes price-flash-dn{0%{color:#ef4444;transform:scale(1.02)}100%{color:#fff;transform:scale(1)}}
.live-dot{animation:pulse-dot 2s infinite}
.fvg-glow{animation:fvg-glow 1.5s infinite}
.flash-up{animation:price-flash-up .6s ease-out}
.flash-dn{animation:price-flash-dn .6s ease-out}
.glass{backdrop-filter:blur(10px)}
*{-webkit-tap-highlight-color:transparent}
@media(max-width:640px){.info-grid{grid-template-columns:repeat(2,1fr)!important}}
</style>
</head>
<body class="bg-bg text-gray-300 min-h-screen overscroll-none">

<!-- ═══ HEADER ═══ -->
<header class="border-b border-border bg-card/80 glass sticky top-0 z-50">
  <div class="w-[96%] max-w-7xl mx-auto py-3 flex items-center justify-between">
    <div>
      <h1 class="text-base sm:text-xl font-bold text-white">ORB Scanner</h1>
      <p class="text-[9px] text-gray-600">Railway Scraper · Africa/Gaborone</p>
    </div>
    <div class="flex items-center gap-3">
      <div class="text-right">
        <p class="text-xs sm:text-sm text-white font-mono" id="clock">--:--:--</p>
        <p class="text-[9px] text-gray-600" id="date">Loading...</p>
      </div>
      <div class="flex items-center gap-1.5">
        <span class="w-2 h-2 rounded-full bg-green-500 live-dot"></span>
        <span class="text-[10px] text-green-400 font-medium" id="status">...</span>
      </div>
    </div>
  </div>
</header>

<!-- ═══ PRICE TICKER BAR ═══ -->
<div class="border-b border-border bg-card/50" id="ticker-wrap">
  <div class="w-[96%] max-w-7xl mx-auto py-2 flex items-center justify-between gap-4 overflow-x-auto" id="ticker">
    <span class="text-[10px] text-gray-600">Loading prices...</span>
  </div>
</div>

<!-- ═══ MAIN ═══ -->
<main class="w-[96%] max-w-7xl mx-auto py-4">

  <div class="grid grid-cols-4 gap-2 mb-4">
    <div class="bg-card border border-border rounded-lg px-2 py-2 text-center">
      <p class="text-[8px] text-gray-600 uppercase">Markets</p>
      <p class="text-sm font-bold text-white">3</p>
    </div>
    <div class="bg-card border border-border rounded-lg px-2 py-2 text-center">
      <p class="text-[8px] text-gray-600 uppercase">Refresh</p>
      <p class="text-sm font-bold text-white">2 s</p>
    </div>
    <div class="bg-card border border-border rounded-lg px-2 py-2 text-center">
      <p class="text-[8px] text-gray-600 uppercase">Updates</p>
      <p class="text-sm font-bold text-white" id="n">0</p>
    </div>
    <div class="bg-card border border-border rounded-lg px-2 py-2 text-center">
      <p class="text-[8px] text-gray-600 uppercase">Scraper</p>
      <p class="text-[10px] font-bold text-green-400" id="scraper-tag">Railway</p>
    </div>
  </div>

  <div class="grid grid-cols-1 lg:grid-cols-3 gap-3" id="cards">
    <div class="bg-card border border-border rounded-xl p-5 animate-pulse"><div class="h-4 bg-accent rounded w-20 mb-3"></div><div class="h-8 bg-accent rounded w-32 mb-2"></div><div class="h-6 bg-accent rounded w-28"></div></div>
    <div class="bg-card border border-border rounded-xl p-5 animate-pulse"><div class="h-4 bg-accent rounded w-20 mb-3"></div><div class="h-8 bg-accent rounded w-32 mb-2"></div><div class="h-6 bg-accent rounded w-28"></div></div>
    <div class="bg-card border border-border rounded-xl p-5 animate-pulse"><div class="h-4 bg-accent rounded w-20 mb-3"></div><div class="h-8 bg-accent rounded w-32 mb-2"></div><div class="h-6 bg-accent rounded w-28"></div></div>
  </div>

  <div class="mt-4 text-center">
    <p class="text-[9px] text-gray-700">
      <a href="/api/debug" class="text-blue-500 hover:underline">Debug</a> ·
      <a href="/api/scraper-test" class="text-blue-500 hover:underline">Test Scraper</a> ·
      <a href="/api/health" class="text-blue-500 hover:underline">Health</a>
    </p>
  </div>
</main>

<script>
/* ── helpers ── */
const ST={TRADE:{bg:'bg-green-500/10',bd:'border-green-500/40',tx:'text-green-400',lb:'TRADE'},SKIP:{bg:'bg-yellow-500/10',bd:'border-yellow-500/40',tx:'text-yellow-400',lb:'SKIP'},SCANNING:{bg:'bg-blue-500/10',bd:'border-blue-500/40',tx:'text-blue-400',lb:'SCAN'},CLOSED:{bg:'bg-gray-500/10',bd:'border-gray-500/40',tx:'text-gray-500',lb:'CLOSED'},FORMING:{bg:'bg-indigo-500/10',bd:'border-indigo-500/40',tx:'text-indigo-400',lb:'FORM'},NO_TRADE:{bg:'bg-orange-500/10',bd:'border-orange-500/40',tx:'text-orange-400',lb:'SKIP'},ERROR:{bg:'bg-red-500/10',bd:'border-red-500/40',tx:'text-red-400',lb:'ERR'}};

const fmt=p=>{if(p==null)return'--';return Number(p).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})};
const badge=s=>{const c=ST[s]||ST.ERROR;return`<span class="px-2 py-0.5 rounded-full text-[9px] font-bold ${c.bg} ${c.bd} ${c.tx} border">${c.lb}</span>`};
const box=(l,v,c='text-white')=>`<div class="bg-bg/50 border border-border rounded px-2 py-1.5"><p class="text-[8px] text-gray-600 uppercase">${l}</p><p class="text-xs font-semibold ${c} truncate">${v}</p></div>`;
const bar=s=>{const p=Math.min(Math.round(s/12*100),100),c=s>=9?'#22c55e':s>=7?'#84cc16':s>=5?'#eab308':'#ef4444';return`<div class="mt-2"><div class="flex justify-between text-[9px] mb-1"><span class="text-gray-500">Score</span><span class="font-bold" style="color:${c}">${s}/12</span></div><div class="bg-gray-800 rounded-full h-1.5"><div class="h-full rounded-full" style="width:${p}%;background:${c}"></div></div></div>`};

/* ── FVG icons ── */
const FVGL=`<svg viewBox="0 0 60 40" class="w-12 h-8"><rect x="5" y="8" width="8" height="20" fill="#ef4444" rx="1"/><line x1="9" y1="4" x2="9" y2="8" stroke="#ef4444" stroke-width="2"/><line x1="9" y1="28" x2="9" y2="34" stroke="#ef4444" stroke-width="2"/><rect x="22" y="4" width="10" height="28" fill="#22c55e" rx="1"/><line x1="27" y1="2" x2="27" y2="4" stroke="#22c55e" stroke-width="2"/><line x1="27" y1="32" x2="27" y2="36" stroke="#22c55e" stroke-width="2"/><rect x="41" y="6" width="8" height="16" fill="#22c55e" rx="1"/><line x1="45" y1="2" x2="45" y2="6" stroke="#22c55e" stroke-width="2"/><line x1="45" y1="22" x2="45" y2="28" stroke="#22c55e" stroke-width="2"/><rect x="13" y="8" width="28" height="6" fill="#22c55e" fill-opacity=".2" stroke="#22c55e" stroke-width="1" stroke-dasharray="2,2" rx="2"/></svg>`;
const FVGS=`<svg viewBox="0 0 60 40" class="w-12 h-8"><rect x="5" y="12" width="8" height="20" fill="#22c55e" rx="1"/><line x1="9" y1="6" x2="9" y2="12" stroke="#22c55e" stroke-width="2"/><line x1="9" y1="32" x2="9" y2="36" stroke="#22c55e" stroke-width="2"/><rect x="22" y="8" width="10" height="28" fill="#ef4444" rx="1"/><line x1="27" y1="4" x2="27" y2="8" stroke="#ef4444" stroke-width="2"/><line x1="27" y1="36" x2="27" y2="38" stroke="#ef4444" stroke-width="2"/><rect x="41" y="18" width="8" height="16" fill="#ef4444" rx="1"/><line x1="45" y1="12" x2="45" y2="18" stroke="#ef4444" stroke-width="2"/><line x1="45" y1="34" x2="45" y2="38" stroke="#ef4444" stroke-width="2"/><rect x="13" y="26" width="28" height="6" fill="#ef4444" fill-opacity=".2" stroke="#ef4444" stroke-width="1" stroke-dasharray="2,2" rx="2"/></svg>`;
const FVGW=`<svg viewBox="0 0 60 40" class="w-12 h-8 opacity-40"><rect x="8" y="10" width="8" height="18" fill="#6b7280" rx="1"/><line x1="12" y1="6" x2="12" y2="10" stroke="#6b7280" stroke-width="2"/><line x1="12" y1="28" x2="12" y2="34" stroke="#6b7280" stroke-width="2"/><rect x="24" y="8" width="8" height="22" fill="#6b7280" rx="1"/><line x1="28" y1="4" x2="28" y2="8" stroke="#6b7280" stroke-width="2"/><line x1="28" y1="30" x2="28" y2="36" stroke="#6b7280" stroke-width="2"/><text x="46" y="24" font-size="16" fill="#6b7280" font-weight="bold">?</text></svg>`;

function fvgBadge(d){
  if(d.fvg_detected&&d.direction){
    const ic=d.direction==='LONG'?FVGL:FVGS;
    const bc=d.direction==='LONG'?'border-green-500/50 bg-green-500/5':'border-red-500/50 bg-red-500/5';
    const tc=d.direction==='LONG'?'text-green-400':'text-red-400';
    return`<div class="flex items-center gap-2 p-2 rounded-lg border ${bc} fvg-glow">${ic}<div><p class="text-[9px] text-gray-400 uppercase">FVG Detected</p><p class="text-xs font-bold ${tc}">${d.direction} $${d.fvg_size}</p></div></div>`;
  }
  if(d.status==='SCANNING') return`<div class="flex items-center gap-2 p-2 rounded-lg border border-gray-700/50 bg-gray-800/30">${FVGW}<div><p class="text-[9px] text-gray-500 uppercase">Waiting for FVG</p><p class="text-[10px] text-gray-600">Scanning…</p></div></div>`;
  return'';
}

function chg(d){
  if(d.price_change==null)return'';
  const up=d.price_change>=0;
  const s=up?'+':'';
  return`<span class="text-xs font-medium ${up?'text-green-400':'text-red-400'}">${up?'▲':'▼'} ${s}$${fmt(Math.abs(d.price_change))} (${s}${d.price_change_pct||0}%)</span>`;
}

/* ── CARD RENDERER ── */
let prevP={};
function card(d){
  const isTrade=d.status==='TRADE'||d.status==='SKIP';
  const dc=d.direction==='LONG'?'text-green-400':'text-red-400';
  const di=d.direction==='LONG'?'↑':'↓';
  const tc=d.trend==='BULLISH'?'text-green-400':d.trend==='BEARISH'?'text-red-400':'text-gray-400';

  /* detect price move for flash */
  const prev=prevP[d.asset];
  const flash=prev&&d.price!==prev?(d.price>prev?'flash-up':'flash-dn'):'';
  prevP[d.asset]=d.price;

  let h=`<div class="bg-card border border-border rounded-xl overflow-hidden ${d.status==='TRADE'?'ring-2 ring-green-500/50':''}">`;

  /* header */
  h+=`<div class="px-4 pt-3 pb-1 flex items-center justify-between">
    <div class="flex items-center gap-2">
      <span class="text-sm font-bold text-white">${d.asset}</span>
      <span class="text-[8px] px-1.5 py-0.5 rounded bg-green-500/10 text-green-400 border border-green-500/30">Railway</span>
      ${d.window?`<span class="text-[8px] text-purple-400 bg-purple-500/10 px-1.5 py-0.5 rounded">${d.window}</span>`:''}
    </div>
    ${badge(d.status)}
  </div>`;

  /* ── PRICE BLOCK ── */
  h+=`<div class="px-4 pb-3 border-b border-border">
    <div class="flex items-end justify-between">
      <div>
        <p class="text-2xl sm:text-3xl font-bold text-white font-mono ${flash}">$${fmt(d.price)}</p>
        <div class="mt-0.5">${chg(d)}</div>
      </div>
      <div class="text-right">
        ${d.trend?`<p class="text-xs font-semibold ${tc}">${d.trend==='BULLISH'?'▲':'▼'} ${d.trend}</p>`:''}
        ${d.ma50?`<p class="text-[9px] text-gray-600 font-mono">MA50 $${fmt(d.ma50)}</p>`:''}
        ${d.ma200?`<p class="text-[9px] text-gray-600 font-mono">MA200 $${fmt(d.ma200)}</p>`:''}
      </div>
    </div>
  </div>`;

  /* ── BODY ── */
  h+=`<div class="px-4 py-3"><p class="text-xs text-white mb-3">${d.message}</p>`;

  if(isTrade){
    h+=fvgBadge(d);
    h+=`<div class="grid grid-cols-2 gap-1.5 mb-2 mt-3">${box('Dir',di+' '+d.direction,dc)}${box('Conf',d.confidence,d.confidence==='HIGH'?'text-green-400':'text-yellow-400')}</div>`;
    h+=bar(d.score);
    h+=`<div class="border-t border-border my-3"></div>`;
    h+=`<div class="grid grid-cols-2 sm:grid-cols-4 gap-1.5 info-grid">${box('Entry','$'+fmt(d.entry),dc)}${box('Stop','$'+fmt(d.stop),'text-red-400')}${box('Target','$'+fmt(d.target),'text-green-400')}${box('Range','$'+fmt(d.range_size))}</div>`;
    h+=`<div class="grid grid-cols-3 gap-1.5 mt-1.5">${box('FVG','$'+d.fvg_size)}${box('Speed',d.speed+' bars')}${box('Day',d.day||'--')}</div>`;
    if(d.reasons?.length){
      h+=`<div class="border-t border-border my-3"></div><details><summary class="text-[9px] text-gray-500 cursor-pointer hover:text-gray-300">Score Breakdown</summary><div class="mt-2 space-y-0.5">`;
      d.reasons.forEach(r=>{h+=`<p class="text-[10px] ${r.includes('+')?'text-green-400':'text-red-400'}">${r.includes('+')?'✓':'✗'} ${r}</p>`});
      h+=`</div></details>`;
    }
  }else if(['SCANNING','FORMING','NO_TRADE'].includes(d.status)){
    if(d.status==='SCANNING'){h+=fvgBadge(d);h+=`<div class="mt-3"></div>`}
    h+=`<div class="grid grid-cols-2 sm:grid-cols-3 gap-1.5 info-grid">`;
    if(d.range_high)h+=box('High','$'+fmt(d.range_high));
    if(d.range_low)h+=box('Low','$'+fmt(d.range_low));
    if(d.range_size)h+=box('Range','$'+fmt(d.range_size));
    if(d.day_open)h+=box('Open','$'+fmt(d.day_open));
    if(d.next_window)h+=box('Next Window',d.next_window,'text-purple-400');
    if(d.day)h+=box('Day',d.day);
    h+=`</div>`;
  }else{
    h+=`<div class="grid grid-cols-2 gap-1.5">`;
    if(d.trend)h+=box('Trend',d.trend,tc);
    if(d.day)h+=box('Day',d.day);
    h+=`</div>`;
  }

  h+=`</div></div>`;
  return h;
}

/* ── TICKER BAR ── */
function ticker(data){
  const icons={NAS100:'📈',BTCUSD:'₿',GOLD:'🥇'};
  let h='';
  ['NAS100','BTCUSD','GOLD'].forEach(a=>{
    const d=data[a];if(!d||!d.price)return;
    const up=(d.price_change||0)>=0;
    const cc=up?'text-green-400':'text-red-400';
    h+=`<div class="flex items-center gap-2 min-w-fit">
      <span class="text-xs">${icons[a]}</span>
      <span class="text-[10px] text-gray-500 font-medium">${a}</span>
      <span class="text-sm font-bold text-white font-mono">$${fmt(d.price)}</span>
      ${d.price_change!=null?`<span class="text-[10px] ${cc}">${up?'▲':'▼'}${Math.abs(d.price_change_pct||0)}%</span>`:''}
    </div>`;
  });
  document.getElementById('ticker').innerHTML=h||'<span class="text-[10px] text-gray-600">No prices</span>';
}

/* ── MAIN LOOP ── */
let n=0;
async function go(){
  const st=document.getElementById('status');
  try{
    st.textContent='⟳';st.className='text-[10px] text-blue-400';
    const r=await fetch('/api/scan'),d=await r.json();
    document.getElementById('cards').innerHTML=card(d.NAS100)+card(d.BTCUSD)+card(d.GOLD);
    ticker(d);
    n++;document.getElementById('n').textContent=n;
    st.textContent='LIVE';st.className='text-[10px] text-green-400 font-medium';
  }catch(e){
    st.textContent='ERR';st.className='text-[10px] text-red-400';
    console.error(e);
  }
}

function ck(){
  const d=new Date();
  document.getElementById('clock').textContent=d.toLocaleTimeString('en-US',{timeZone:'Africa/Gaborone',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false})+' CAT';
  document.getElementById('date').textContent=d.toLocaleDateString('en-US',{timeZone:'Africa/Gaborone',weekday:'short',month:'short',day:'numeric'});
}

go();ck();setInterval(go,2000);setInterval(ck,1000);
</script>
</body>
</html>"""