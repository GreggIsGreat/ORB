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
ET = pytz.timezone("US/Eastern")

CONFIGS = {
    "NAS100": {
        "symbol": "OANDA:NAS100USD",
        "max_range": 80, "max_fvg": None, "max_speed": 30, "weekend": False,
        "range_start": 930, "range_end": 944, "post_range_start": 945,
        "session_open": 930, "session_close": 1600, "session_tz": "US/Eastern",
        "range": [(30,45,3),(0,30,1),(45,60,1),(60,80,0)],
        "fvg": [(15,9999,2),(0,3,2),(7,15,1),(3,7,0)],
        "speed": [(0,10,3),(10,20,2),(20,30,1)],
        "best_day": ("Tuesday",3), "good_days": [("Thursday",1)],
        "worst_day": ("Wednesday",-2), "bias": ("LONG",1),
        "windows": None, "min_score": 5,
    },
    "BTCUSD": {
        "symbol": "BITSTAMP:BTCUSD",
        "max_range": 750, "max_fvg": 200, "max_speed": None, "weekend": True,
        "range_start": 0, "range_end": 14, "post_range_start": 15,
        "session_open": 0, "session_close": 2359, "session_tz": "UTC",
        "range": [(350,500,3),(200,350,2),(0,200,1),(500,750,0)],
        "fvg": [(25,50,3),(0,25,2),(50,100,0),(100,200,0)],
        "speed": [(0,10,3),(10,20,2),(20,30,1),(30,60,0)],
        "best_day": ("Sunday",3), "good_days": [("Saturday",2),("Tuesday",2),("Thursday",1)],
        "worst_day": ("Friday",-2), "bias": None,
        "windows": None, "min_score": 5,
    },
    "GOLD": {
        "symbol": "OANDA:XAUUSD",
        "max_range": None, "max_fvg": None, "max_speed": None, "weekend": False,
        "range_start": 930, "range_end": 944, "post_range_start": 945,
        "session_open": 930, "session_close": 1600, "session_tz": "US/Eastern",
        "range": [(0,5,3),(5,10,2),(10,15,2),(25,9999,1),(15,25,0)],
        "fvg": [(1,3,2),(0,1,1),(5,10,1),(3,5,0),(10,9999,0)],
        "speed": [(0,10,3),(10,20,2),(20,30,1),(30,60,0)],
        "best_day": ("Friday",3), "good_days": [("Tuesday",3),("Wednesday",1)],
        "worst_day": ("Monday",-2), "bias": None,
        "windows": {
            "08:00 ET": {"start":800,"end":859,"score":2,"wr":"69.4%"},
            "09:00 ET": {"start":900,"end":959,"score":3,"wr":"73%+"},
            "13:00 ET": {"start":1300,"end":1359,"score":3,"wr":"73%+"},
            "14:30 ET": {"start":1430,"end":1529,"score":2,"wr":"71.4%"},
            "16:00 ET": {"start":1600,"end":1659,"score":1,"wr":"65.9%"},
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
        h = {"User-Agent":"Mozilla/5.0","Accept":"application/json"}
        if headers: h.update(headers)
        req = urllib.request.Request(url, headers=h)
        resp = urllib.request.urlopen(req, timeout=15, context=ctx)
        raw = resp.read()
        if raw[:2] == b'\x1f\x8b': raw = gzip.decompress(raw)
        return json.loads(raw.decode('utf-8'))
    except Exception as e:
        raise Exception(f"HTTP error [{url[:80]}]: {str(e)}")

# ═══════════════════════════════════════════════
# SCRAPER
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
    data = None; last_err = None
    for url in endpoints:
        try:
            data = http_get(url)
            if data: break
        except Exception as e:
            last_err = str(e); continue
    if not data: return [], f"Scraper unreachable: {last_err}"
    return parse_candles(data)

def parse_candles(data):
    if isinstance(data, dict) and "t" in data and isinstance(data["t"], list):
        times,opens,highs,lows,closes = data.get("t",[]),data.get("o",[]),data.get("h",[]),data.get("l",[]),data.get("c",[])
        candles = []
        for i in range(len(times)):
            try:
                ts = times[i]
                if ts > 1e12: ts = ts/1000
                dt_utc = datetime.fromtimestamp(ts, tz=pytz.UTC)
                dt_cat = dt_utc.astimezone(TZ); dt_et = dt_utc.astimezone(ET)
                candles.append({"time":dt_cat.strftime("%H:%M"),"time_et":dt_et.strftime("%H:%M"),
                    "time_hhmm_et":dt_et.hour*100+dt_et.minute,"date_et":dt_et.strftime("%Y-%m-%d"),
                    "open":float(opens[i]),"high":float(highs[i]),"low":float(lows[i]),"close":float(closes[i])})
            except: continue
        return (candles, None) if candles else ([], "No candles parsed")
    raw_list = []
    if isinstance(data, list): raw_list = data
    elif isinstance(data, dict):
        for key in ["candles","data","result","bars","ohlc","klines"]:
            if key in data and isinstance(data[key], list): raw_list = data[key]; break
        if not raw_list: return [], f"Unknown keys: {list(data.keys())}"
    candles = []
    for item in raw_list:
        try:
            ts = item.get('timestamp', item.get('t', None))
            if ts and isinstance(ts, (int,float)):
                if ts > 1e12: ts = ts/1000
                dt_utc = datetime.fromtimestamp(ts, tz=pytz.UTC)
            else: continue
            dt_cat = dt_utc.astimezone(TZ); dt_et = dt_utc.astimezone(ET)
            o,h,l,c = float(item.get('open',item.get('o',0))),float(item.get('high',item.get('h',0))),float(item.get('low',item.get('l',0))),float(item.get('close',item.get('c',0)))
            if o==0 and h==0 and l==0 and c==0: continue
            candles.append({"time":dt_cat.strftime("%H:%M"),"time_et":dt_et.strftime("%H:%M"),
                "time_hhmm_et":dt_et.hour*100+dt_et.minute,"date_et":dt_et.strftime("%Y-%m-%d"),
                "open":o,"high":h,"low":l,"close":c})
        except: continue
    return (candles, None) if candles else ([], "Could not parse candles")

def scrape_asset(asset):
    cached = get_cached(asset)
    if cached: return cached
    config = CONFIGS[asset]; symbol = config["symbol"]
    result = {"asset":asset,"symbol":symbol,"status":"ERROR","candles":[],"ma50":None,"ma200":None,
        "price":None,"price_change":None,"price_change_pct":None,"day_open":None,"error":None,
        "source":"Railway Scraper","candle_count":0}
    try:
        c15, err15 = fetch_candles(symbol, "15", 300)
        if not c15 or len(c15) < 50:
            result["error"] = f"Not enough 15m data ({len(c15) if c15 else 0}). {err15 or ''}"
            set_cached(asset, result); return result
        closes15 = [c['close'] for c in c15]
        result["ma50"] = round(sum(closes15[-50:])/50, 2)
        result["ma200"] = round(sum(closes15[-200:])/200, 2) if len(closes15)>=200 else round(sum(closes15)/len(closes15), 2)
        c1, err1 = fetch_candles(symbol, "1", 500)
        if c1 and len(c1) > 0:
            result["candles"] = c1; result["price"] = round(c1[-1]['close'], 2)
            session_tz = pytz.timezone(config["session_tz"])
            today_str = datetime.now(session_tz).strftime("%Y-%m-%d")
            today_candles = [c for c in c1 if c.get("date_et")==today_str]
            result["day_open"] = round(today_candles[0]['open'], 2) if today_candles else round(c1[0]['open'], 2)
            result["candle_count"] = len(c1); result["status"] = "OK"
        else:
            result["candles"] = c15[-60:]; result["price"] = round(c15[-1]['close'], 2)
            result["day_open"] = round(c15[0]['open'], 2); result["candle_count"] = len(c15)
            result["source"] += " (15m fallback)"; result["status"] = "OK"
        if result["price"] and result["day_open"] and result["day_open"] != 0:
            result["price_change"] = round(result["price"]-result["day_open"], 2)
            result["price_change_pct"] = round(((result["price"]-result["day_open"])/result["day_open"])*100, 3)
    except Exception as e: result["error"] = str(e)
    set_cached(asset, result); return result

def scrape_all():
    return {asset: scrape_asset(asset) for asset in CONFIGS}

# ═══════════════════════════════════════════════
# SESSION & WINDOW
# ═══════════════════════════════════════════════
def get_session_state(asset, now_utc):
    config = CONFIGS[asset]
    session_tz = pytz.timezone(config["session_tz"])
    now_s = now_utc.astimezone(session_tz)
    hhmm = now_s.hour*100+now_s.minute; dow = now_s.weekday()
    if not config["weekend"] and dow >= 5:
        return "WEEKEND", f"Markets closed — {now_s.strftime('%A')}"
    if config["weekend"] and config["session_open"]==0 and config["session_close"]==2359:
        if hhmm <= config["range_end"]:
            return "FORMING", f"Daily range forming"
        return "OPEN", None
    if hhmm < config["session_open"]:
        oh,om = config["session_open"]//100, config["session_open"]%100
        hl = oh-now_s.hour; ml = om-now_s.minute
        if ml<0: hl-=1; ml+=60
        return "PRE_MARKET", f"Session opens in {hl}h {ml}m"
    if hhmm > config["session_close"]:
        return "POST_MARKET", "Session ended for today"
    if hhmm <= config["range_end"]:
        return "FORMING", f"Opening range forming"
    return "OPEN", None

def get_session_progress(asset, now_utc):
    config = CONFIGS[asset]
    session_tz = pytz.timezone(config["session_tz"])
    now_s = now_utc.astimezone(session_tz)
    hhmm = now_s.hour*100+now_s.minute
    s_open = config["session_open"]; s_close = config["session_close"]
    if s_open == 0 and s_close == 2359: s_open = 0; s_close = 2359
    total = s_close - s_open
    if total <= 0: return 0
    elapsed = hhmm - s_open
    return max(0, min(100, round(elapsed/total*100)))

def get_current_window(asset, now_utc):
    config = CONFIGS[asset]
    if not config.get("windows"): return None, None
    cur = now_utc.astimezone(ET); hm = cur.hour*100+cur.minute
    for label, w in config["windows"].items():
        if w["start"] <= hm <= w["end"]: return label, w
    return None, None

def get_next_window(asset, now_utc):
    config = CONFIGS[asset]
    if not config.get("windows"): return None
    cur = now_utc.astimezone(ET); hm = cur.hour*100+cur.minute
    sw = sorted(config["windows"].items(), key=lambda x: x[1]["start"])
    for label, w in sw:
        if w["start"] > hm: return label
    return sw[0][0] if sw else None

# ═══════════════════════════════════════════════
# SCORING
# ═══════════════════════════════════════════════
def score_trade(asset, range_size, fvg_size, speed, direction, day_name, window=None):
    c = CONFIGS[asset]; score = 0; reasons = []
    if c["max_range"] and range_size > c["max_range"]:
        return {"score":0,"take_trade":False,"confidence":"REJECTED","reasons":["Range too wide"]}
    if c["max_fvg"] and fvg_size > c["max_fvg"]:
        return {"score":0,"take_trade":False,"confidence":"REJECTED","reasons":["FVG too large"]}
    if c["max_speed"] and speed > c["max_speed"]:
        return {"score":0,"take_trade":False,"confidence":"REJECTED","reasons":["Breakout too slow"]}
    if c.get("windows") and window and window in c["windows"]:
        w = c["windows"][window]; score += w["score"]
        reasons.append(f"{window} window ({w['wr']}) → +{w['score']}")
    for lo,hi,pts in c["range"]:
        if lo <= range_size <= hi:
            score += pts
            if pts > 0: reasons.append(f"Range ${lo}-${hi} → +{pts}")
            break
    for lo,hi,pts in c["fvg"]:
        if lo <= fvg_size <= hi:
            score += pts
            if pts > 0: reasons.append(f"FVG ${lo}-${hi} → +{pts}")
            break
    for lo,hi,pts in c["speed"]:
        if lo <= speed <= hi:
            score += pts
            if pts > 0: reasons.append(f"Speed {lo}-{hi} bars → +{pts}")
            break
    if c["best_day"] and day_name == c["best_day"][0]:
        score += c["best_day"][1]; reasons.append(f"{day_name} → +{c['best_day'][1]}")
    else:
        for gd, pts in c["good_days"]:
            if day_name == gd: score += pts; reasons.append(f"{day_name} → +{pts}"); break
    if c["worst_day"] and day_name == c["worst_day"][0]:
        score += c["worst_day"][1]; reasons.append(f"{day_name} → {c['worst_day'][1]} ⚠️")
    if c["bias"] and direction == c["bias"][0]:
        score += c["bias"][1]; reasons.append(f"{direction} bias → +{c['bias'][1]}")
    min_s = c.get("min_score", 5)
    if asset == "GOLD": conf = "HIGH" if score>=9 else "MEDIUM" if score>=7 else "LOW"
    else: conf = "HIGH" if score>=7 else "MEDIUM" if score>=5 else "LOW"
    return {"score":score,"take_trade":score>=min_s,"confidence":conf,"reasons":reasons}

def detect_fvg(c1, c2, c3, direction):
    if direction == "LONG":
        gap = c3['low']-c1['high']
        if gap > 0 and c2['close'] > c2['open']:
            return {"valid":True,"size":round(gap,2),"entry":c3['low']}
    elif direction == "SHORT":
        gap = c1['low']-c3['high']
        if gap > 0 and c2['close'] < c2['open']:
            return {"valid":True,"size":round(gap,2),"entry":c3['high']}
    return {"valid":False,"size":0,"entry":0}

# ═══════════════════════════════════════════════
# SCANNER
# ═══════════════════════════════════════════════
def run_scan(asset, scraped):
    config = CONFIGS[asset]
    now = datetime.now(TZ); now_utc = now.astimezone(pytz.UTC)
    current_window, window_info = get_current_window(asset, now_utc)
    next_window = get_next_window(asset, now_utc) if not current_window else None
    session_tz = pytz.timezone(config["session_tz"])
    now_session = now_utc.astimezone(session_tz)
    today_session = now_session.strftime("%Y-%m-%d")
    day_name = now_session.strftime("%A")
    session_progress = get_session_progress(asset, now_utc)

    base = {"asset":asset,"symbol":config["symbol"],"time":now.strftime("%H:%M:%S"),
        "day":day_name,"window":current_window,"next_window":next_window,
        "source":scraped.get("source","Railway Scraper"),
        "price":scraped.get("price"),"price_change":scraped.get("price_change"),
        "price_change_pct":scraped.get("price_change_pct"),"day_open":scraped.get("day_open"),
        "ma50":scraped.get("ma50"),"ma200":scraped.get("ma200"),
        "session_progress":session_progress,"session_time":now_session.strftime("%H:%M ET")}

    session_state, session_msg = get_session_state(asset, now_utc)
    if session_state in ("WEEKEND","PRE_MARKET","POST_MARKET"):
        return {**base,"status":"CLOSED","message":session_msg}
    if scraped["status"] == "ERROR":
        return {**base,"status":"ERROR","message":scraped.get("error","Scraper failed")}

    ma50 = scraped["ma50"]; ma200 = scraped["ma200"]
    trend = "BULLISH" if ma50 and ma200 and ma50>ma200 else "BEARISH" if ma50 and ma200 else "UNKNOWN"
    base["trend"] = trend
    candles = scraped["candles"]; price = scraped["price"]

    if not candles or len(candles) < 10:
        return {**base,"status":"ERROR","message":f"Not enough data ({len(candles) if candles else 0})"}

    today_candles = [c for c in candles if c.get("date_et")==today_session]
    if not today_candles:
        return {**base,"status":"FORMING","message":f"No candles for today's session yet"}

    or_candles = [c for c in today_candles if config["range_start"]<=c.get("time_hhmm_et",0)<=config["range_end"]]

    if session_state == "FORMING":
        count = len(or_candles); expected = config["range_end"]-config["range_start"]+1
        return {**base,"status":"FORMING","message":f"Opening range forming — {count}/{expected} candles",
            "range_progress":round(count/max(expected,1)*100)}

    if len(or_candles) == 0:
        return {**base,"status":"FORMING","message":"No opening range candles found"}

    rh = round(max(c['high'] for c in or_candles),2)
    rl = round(min(c['low'] for c in or_candles),2)
    rs = round(rh-rl,2)
    base["range_high"]=rh; base["range_low"]=rl; base["range_size"]=rs; base["range_candles"]=len(or_candles)

    if config["max_range"] and rs > config["max_range"]:
        return {**base,"status":"NO_TRADE","message":f"Range too wide (${rs} > max ${config['max_range']})"}

    post_candles = [c for c in today_candles if c.get("time_hhmm_et",0)>=config["post_range_start"]]
    if len(post_candles) < 3:
        return {**base,"status":"FORMING","message":f"Waiting for post-range candles ({len(post_candles)}/3)"}

    bias_dir = "LONG" if trend=="BULLISH" else "SHORT"
    best_signal = None

    for i in range(len(post_candles)-2):
        c1,c2,c3 = post_candles[i],post_candles[i+1],post_candles[i+2]
        if c2['close'] > rh:
            fvg = detect_fvg(c1,c2,c3,"LONG")
            if fvg['valid']:
                pred = score_trade(asset,rs,fvg['size'],i+1,"LONG",day_name,window=current_window)
                sig = {"direction":"LONG","entry":round(fvg['entry'],2),"stop":rl,
                    "target":round(fvg['entry']+(fvg['entry']-rl),2),"fvg_size":fvg['size'],
                    "speed":i+1,"score":pred["score"],"confidence":pred["confidence"],
                    "reasons":pred["reasons"],"take_trade":pred["take_trade"],
                    "fvg_detected":True,"fvg_time":c2.get("time_et",""),"aligned":bias_dir=="LONG"}
                if bias_dir=="LONG" or pred["score"]>=CONFIGS[asset]["min_score"]:
                    best_signal = sig
        if c2['close'] < rl:
            fvg = detect_fvg(c1,c2,c3,"SHORT")
            if fvg['valid']:
                pred = score_trade(asset,rs,fvg['size'],i+1,"SHORT",day_name,window=current_window)
                sig = {"direction":"SHORT","entry":round(fvg['entry'],2),"stop":rh,
                    "target":round(fvg['entry']-(rh-fvg['entry']),2),"fvg_size":fvg['size'],
                    "speed":i+1,"score":pred["score"],"confidence":pred["confidence"],
                    "reasons":pred["reasons"],"take_trade":pred["take_trade"],
                    "fvg_detected":True,"fvg_time":c2.get("time_et",""),"aligned":bias_dir=="SHORT"}
                if bias_dir=="SHORT" or pred["score"]>=CONFIGS[asset]["min_score"]:
                    best_signal = sig

    if best_signal:
        status = "TRADE" if best_signal["take_trade"] else "SKIP"
        return {**base,"status":status,
            "message":f"{best_signal['confidence']} {best_signal['direction']} — Score {best_signal['score']}/12" +
                (f" (FVG at {best_signal['fvg_time']} ET)" if best_signal.get('fvg_time') else ""),
            **best_signal}

    if price > rh: msg = f"Price ABOVE range (+${round(price-rh,2)}) — Waiting for FVG"
    elif price < rl: msg = f"Price BELOW range (-${round(rl-price,2)}) — Waiting for FVG"
    else: msg = "Price INSIDE range — No breakout yet"
    return {**base,"status":"SCANNING","message":msg,"fvg_detected":False}

# ═══════════════════════════════════════════════
# API
# ═══════════════════════════════════════════════
@app.get("/api/scan")
def api_scan():
    scraped = scrape_all()
    return JSONResponse({asset: run_scan(asset, scraped[asset]) for asset in CONFIGS})

@app.get("/api/debug")
def api_debug():
    scraped = scrape_all(); debug = {}
    for asset, d in scraped.items():
        config = CONFIGS[asset]; session_tz = pytz.timezone(config["session_tz"])
        now_s = datetime.now(pytz.UTC).astimezone(session_tz); today_str = now_s.strftime("%Y-%m-%d")
        ac = d.get("candles",[]); tc = [c for c in ac if c.get("date_et")==today_str]
        orc = [c for c in tc if config["range_start"]<=c.get("time_hhmm_et",0)<=config["range_end"]]
        pc = [c for c in tc if c.get("time_hhmm_et",0)>=config["post_range_start"]]
        debug[asset] = {"status":d["status"],"source":d.get("source"),"error":d.get("error"),
            "ma50":d.get("ma50"),"ma200":d.get("ma200"),"price":d.get("price"),
            "total_candles":len(ac),"today_candles":len(tc),"or_candles":len(orc),
            "post_candles":len(pc),"session_date":today_str,"session_time":now_s.strftime("%H:%M:%S %Z"),
            "range_window":f"{config['range_start']}-{config['range_end']}",
            "first_or":orc[0] if orc else None,"last_or":orc[-1] if orc else None}
    debug["_config"] = {"scraper_url":SCRAPER_URL,"display_tz":str(TZ)}
    return JSONResponse(debug)

@app.get("/api/scraper-test")
def api_scraper_test():
    results = {}
    for asset, cfg in CONFIGS.items():
        c, err = fetch_candles(cfg["symbol"], "1", 5)
        results[asset] = {"symbol":cfg["symbol"],"success":len(c)>0,"count":len(c),"error":err,
            "sample":c[:2] if c else None,"has_et":c[0].get("time_et") is not None if c else False}
    ok = all(r["success"] for r in results.values())
    return JSONResponse({"status":"OK" if ok else "PARTIAL","scraper_url":SCRAPER_URL,"results":results})

@app.get("/api/health")
def health():
    scraper_ok = False
    try: http_get(f"{SCRAPER_URL}/api/health"); scraper_ok = True
    except: pass
    return {"status":"ok","time":datetime.now(TZ).isoformat(),"scraper_connected":scraper_ok}

# ═══════════════════════════════════════════════
# ADVANCED RESPONSIVE UI
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
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700;800&family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
/* ═══ DESIGN SYSTEM ═══ */
:root{
  --bg:#09090b;--card:#111113;--card2:#18181b;--card3:#1c1c1f;
  --border:#1e1e22;--border2:#2a2a2e;--accent:#232326;
  --green:#22c55e;--red:#ef4444;--blue:#3b82f6;--purple:#a855f7;
  --yellow:#eab308;--orange:#f97316;--indigo:#818cf8;--cyan:#06b6d4;
  --text:#e4e4e7;--text2:#a1a1aa;--text3:#71717a;--text4:#52525b;
  --radius:16px;--radius-sm:10px;--radius-xs:6px;
  --font-sans:'Inter',system-ui,-apple-system,sans-serif;
  --font-mono:'JetBrains Mono','Fira Code',monospace;
  --ease:cubic-bezier(.4,0,.2,1);
  --ease-spring:cubic-bezier(.34,1.56,.64,1);
}
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html{font-family:var(--font-sans);-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale;scroll-behavior:smooth}
body{background:var(--bg);color:var(--text);min-height:100dvh;overscroll-behavior:none}

/* ═══ FLUID TYPOGRAPHY ═══ */
.f-xs{font-size:clamp(.5rem,.4rem + .3vw,.625rem)}
.f-sm{font-size:clamp(.625rem,.55rem + .3vw,.75rem)}
.f-base{font-size:clamp(.7rem,.6rem + .4vw,.875rem)}
.f-lg{font-size:clamp(.875rem,.75rem + .5vw,1.125rem)}
.f-xl{font-size:clamp(1rem,.85rem + .6vw,1.375rem)}
.f-2xl{font-size:clamp(1.25rem,1rem + 1vw,1.75rem)}
.f-3xl{font-size:clamp(1.5rem,1.1rem + 1.5vw,2.25rem)}
.f-price{font-size:clamp(1.5rem,1rem + 2vw,2.5rem)}

/* ═══ ANIMATIONS ═══ */
@keyframes pulse-dot{0%,100%{opacity:1}50%{opacity:.3}}
@keyframes fvg-glow{0%,100%{box-shadow:0 0 12px rgba(34,197,94,.35)}50%{box-shadow:0 0 28px rgba(34,197,94,.6)}}
@keyframes fvg-glow-red{0%,100%{box-shadow:0 0 12px rgba(239,68,68,.35)}50%{box-shadow:0 0 28px rgba(239,68,68,.6)}}
@keyframes trade-pulse{0%,100%{box-shadow:0 0 0 0 rgba(34,197,94,.25)}50%{box-shadow:0 0 0 6px rgba(34,197,94,0)}}
@keyframes flash-up{0%{color:var(--green);transform:scale(1.02)}100%{color:#fff;transform:scale(1)}}
@keyframes flash-dn{0%{color:var(--red);transform:scale(1.02)}100%{color:#fff;transform:scale(1)}}
@keyframes shimmer{0%{background-position:-200% 0}100%{background-position:200% 0}}
@keyframes slide-in{from{opacity:0;transform:translateY(12px) scale(.98)}to{opacity:1;transform:translateY(0) scale(1)}}
@keyframes fade-in{from{opacity:0}to{opacity:1}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes gauge-fill{from{stroke-dashoffset:251.2}to{stroke-dashoffset:var(--offset)}}
@keyframes scan-sweep{0%{left:-30%}100%{left:130%}}
@keyframes border-flow{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}
@keyframes number-pop{0%{transform:scale(1.08)}100%{transform:scale(1)}}

.live-dot{animation:pulse-dot 2s ease-in-out infinite}
.fvg-glow-l{animation:fvg-glow 2.5s ease-in-out infinite}
.fvg-glow-s{animation:fvg-glow-red 2.5s ease-in-out infinite}
.trade-pulse{animation:trade-pulse 2s ease-out infinite}
.flash-up{animation:flash-up .4s var(--ease)}
.flash-dn{animation:flash-dn .4s var(--ease)}
.number-pop{animation:number-pop .25s var(--ease-spring)}

.initial-load .card-wrap{animation:slide-in .4s var(--ease-spring) both}
.initial-load .card-wrap:nth-child(2){animation-delay:80ms}
.initial-load .card-wrap:nth-child(3){animation-delay:160ms}

.shimmer{background:linear-gradient(90deg,var(--card2) 25%,var(--accent) 50%,var(--card2) 75%);background-size:200% 100%;animation:shimmer 1.5s infinite;border-radius:var(--radius-xs)}

.glass{backdrop-filter:blur(16px) saturate(180%);-webkit-backdrop-filter:blur(16px) saturate(180%)}

/* scan sweep on SCANNING cards */
.scan-line{position:relative;overflow:hidden}
.scan-line::after{content:'';position:absolute;top:0;left:-30%;width:30%;height:100%;
  background:linear-gradient(90deg,transparent,rgba(59,130,246,.08),transparent);
  animation:scan-sweep 3s ease-in-out infinite}

/* ═══ SCROLLBAR ═══ */
::-webkit-scrollbar{width:4px;height:4px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border2);border-radius:4px}

/* ═══ LAYOUT ═══ */
.container{width:100%;max-width:1280px;margin:0 auto;padding-inline:clamp(.75rem,.5rem + 1vw,1.5rem)}

/* ═══ HEADER ═══ */
.hdr{position:sticky;top:0;z-index:50;border-bottom:1px solid var(--border);background:rgba(17,17,19,.85)}
.hdr-inner{display:flex;align-items:center;justify-content:space-between;gap:.5rem;
  padding-block:clamp(.5rem,.4rem + .4vw,.75rem)}

/* ═══ TICKER ═══ */
.ticker-wrap{border-bottom:1px solid var(--border);background:var(--bg);overflow:hidden}
.ticker-scroll{display:flex;gap:clamp(.5rem,.3rem + .5vw,1rem);overflow-x:auto;scroll-snap-type:x mandatory;
  padding-block:clamp(.4rem,.3rem + .3vw,.6rem);-ms-overflow-style:none;scrollbar-width:none}
.ticker-scroll::-webkit-scrollbar{display:none}
.ticker-item{scroll-snap-align:start;flex-shrink:0;display:flex;align-items:center;gap:.5rem;
  padding:clamp(.3rem,.25rem + .2vw,.5rem) clamp(.5rem,.4rem + .3vw,.75rem);
  border-radius:var(--radius-xs);border:1px solid var(--border);background:var(--card);
  transition:border-color .2s var(--ease),transform .15s var(--ease)}
.ticker-item:hover{border-color:var(--border2)}
.ticker-item:active{transform:scale(.98)}

/* ═══ STATS BAR ═══ */
.stats-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:clamp(.3rem,.2rem + .3vw,.5rem);
  padding-block:clamp(.5rem,.4rem + .3vw,.75rem)}
@media(min-width:640px){.stats-grid{grid-template-columns:repeat(4,1fr)}}
@media(min-width:1024px){.stats-grid{grid-template-columns:repeat(5,1fr)}}
.stat-box{background:var(--card);border:1px solid var(--border);border-radius:var(--radius-sm);
  padding:clamp(.4rem,.3rem + .3vw,.6rem) clamp(.5rem,.4rem + .3vw,.75rem);text-align:center;
  transition:border-color .2s var(--ease)}
.stat-box:hover{border-color:var(--border2)}

/* ═══ CARD GRID ═══ */
.card-grid{display:grid;gap:clamp(.5rem,.4rem + .5vw,.75rem);padding-block:clamp(.5rem,.4rem + .5vw,.75rem);
  grid-template-columns:1fr}
@media(min-width:700px){.card-grid{grid-template-columns:repeat(2,1fr)}}
@media(min-width:1100px){.card-grid{grid-template-columns:repeat(3,1fr)}}

/* ═══ CARD ═══ */
.card-wrap{container-type:inline-size;container-name:card}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  overflow:hidden;transition:border-color .3s var(--ease),box-shadow .3s var(--ease),transform .15s var(--ease);
  position:relative}
.card:hover{border-color:var(--border2)}
.card:active{transform:scale(.998)}
.card.st-trade{border-color:rgba(34,197,94,.3)}
.card.st-trade:hover{border-color:rgba(34,197,94,.5);box-shadow:0 0 20px rgba(34,197,94,.08)}
.card.st-skip{border-color:rgba(234,179,8,.25)}
.card.st-error{border-color:rgba(239,68,68,.25)}

/* gradient top line */
.card-accent{height:2px;width:100%}
.card-accent.a-trade{background:linear-gradient(90deg,var(--green),#4ade80)}
.card-accent.a-skip{background:linear-gradient(90deg,var(--yellow),var(--orange))}
.card-accent.a-scan{background:linear-gradient(90deg,var(--blue),var(--cyan));animation:border-flow 3s linear infinite;background-size:200% 200%}
.card-accent.a-form{background:linear-gradient(90deg,var(--indigo),var(--purple))}
.card-accent.a-closed{background:var(--border)}
.card-accent.a-error{background:var(--red)}

/* sections */
.card-header{display:flex;align-items:center;justify-content:space-between;
  padding:clamp(.6rem,.5rem + .3vw,.85rem) clamp(.75rem,.6rem + .5vw,1.1rem) clamp(.3rem,.2rem + .2vw,.5rem)}
.card-price{padding:0 clamp(.75rem,.6rem + .5vw,1.1rem) clamp(.6rem,.5rem + .3vw,.85rem);
  border-bottom:1px solid var(--border)}
.card-body{padding:clamp(.6rem,.5rem + .3vw,.85rem) clamp(.75rem,.6rem + .5vw,1.1rem)}

/* responsive stat grids inside card */
.inner-grid-2{display:grid;grid-template-columns:repeat(2,1fr);gap:clamp(.3rem,.2rem + .2vw,.4rem)}
.inner-grid-3{display:grid;grid-template-columns:repeat(2,1fr);gap:clamp(.3rem,.2rem + .2vw,.4rem)}
@container card (min-width:360px){.inner-grid-3{grid-template-columns:repeat(3,1fr)}}
.inner-grid-4{display:grid;grid-template-columns:repeat(2,1fr);gap:clamp(.3rem,.2rem + .2vw,.4rem)}
@container card (min-width:400px){.inner-grid-4{grid-template-columns:repeat(4,1fr)}}

.data-box{background:rgba(9,9,11,.6);border:1px solid var(--border);border-radius:var(--radius-xs);
  padding:clamp(.35rem,.3rem + .2vw,.5rem) clamp(.4rem,.35rem + .2vw,.6rem);min-width:0;
  transition:border-color .2s var(--ease)}
.data-box:hover{border-color:var(--border2)}

/* ═══ BADGE ═══ */
.badge{display:inline-flex;align-items:center;gap:.25rem;
  padding:clamp(.15rem,.1rem + .1vw,.25rem) clamp(.4rem,.3rem + .2vw,.6rem);
  border-radius:999px;font-weight:700;letter-spacing:.04em;
  font-size:clamp(.5rem,.45rem + .15vw,.6rem);line-height:1;border:1px solid}
.badge-trade{background:rgba(34,197,94,.1);color:var(--green);border-color:rgba(34,197,94,.25)}
.badge-skip{background:rgba(234,179,8,.1);color:var(--yellow);border-color:rgba(234,179,8,.25)}
.badge-scan{background:rgba(59,130,246,.1);color:var(--blue);border-color:rgba(59,130,246,.25)}
.badge-form{background:rgba(129,140,248,.1);color:var(--indigo);border-color:rgba(129,140,248,.25)}
.badge-closed{background:rgba(113,113,122,.1);color:var(--text3);border-color:rgba(113,113,122,.25)}
.badge-notrade{background:rgba(249,115,22,.1);color:var(--orange);border-color:rgba(249,115,22,.25)}
.badge-error{background:rgba(239,68,68,.1);color:var(--red);border-color:rgba(239,68,68,.25)}

/* ═══ FVG BLOCK ═══ */
.fvg-block{display:flex;align-items:center;gap:clamp(.5rem,.4rem + .3vw,.75rem);
  padding:clamp(.5rem,.4rem + .3vw,.7rem);border-radius:var(--radius-sm);border:1px solid;
  margin-top:clamp(.5rem,.4rem + .3vw,.75rem)}
.fvg-block.fvg-long{border-color:rgba(34,197,94,.25);background:rgba(34,197,94,.04)}
.fvg-block.fvg-short{border-color:rgba(239,68,68,.25);background:rgba(239,68,68,.04)}
.fvg-block.fvg-wait{border-color:var(--border);background:var(--card2)}

/* ═══ SCORE GAUGE (radial) ═══ */
.gauge-wrap{display:flex;align-items:center;gap:clamp(.5rem,.4rem + .3vw,.75rem);margin-top:clamp(.5rem,.4rem + .3vw,.75rem)}
.gauge-svg{width:clamp(52px,48px + 1vw,68px);height:clamp(52px,48px + 1vw,68px);transform:rotate(-90deg);flex-shrink:0}
.gauge-bg{fill:none;stroke:var(--border);stroke-width:5}
.gauge-fill{fill:none;stroke-width:5;stroke-linecap:round;transition:stroke-dashoffset .8s var(--ease);animation:gauge-fill .8s var(--ease) both}
.gauge-text{font-family:var(--font-mono);font-weight:800;fill:#fff;text-anchor:middle;dominant-baseline:central;
  font-size:clamp(13px,11px + .5vw,16px)}

/* ═══ SESSION TIMELINE ═══ */
.timeline{position:relative;height:clamp(6px,4px + .3vw,8px);background:var(--card2);border-radius:999px;
  overflow:hidden;margin-top:clamp(.4rem,.3rem + .2vw,.6rem)}
.timeline-fill{height:100%;border-radius:999px;transition:width .5s var(--ease);position:relative}
.timeline-fill::after{content:'';position:absolute;right:0;top:50%;transform:translateY(-50%);
  width:clamp(8px,6px + .3vw,12px);height:clamp(8px,6px + .3vw,12px);border-radius:50%;
  background:#fff;box-shadow:0 0 8px currentColor}

/* ═══ DETAILS/ACCORDION ═══ */
details.breakdown{margin-top:clamp(.5rem,.4rem + .3vw,.75rem);border-top:1px solid var(--border);
  padding-top:clamp(.4rem,.3rem + .2vw,.6rem)}
details.breakdown summary{cursor:pointer;display:flex;align-items:center;gap:.35rem;
  user-select:none;-webkit-user-select:none;transition:color .2s var(--ease)}
details.breakdown summary:hover{color:#fff}
details.breakdown summary .chevron{transition:transform .2s var(--ease)}
details.breakdown[open] summary .chevron{transform:rotate(90deg)}
details.breakdown .bd-content{padding-top:clamp(.3rem,.25rem + .2vw,.5rem);
  animation:fade-in .2s var(--ease)}

/* ═══ FOOTER LINKS ═══ */
.footer-links{display:flex;align-items:center;justify-content:center;gap:clamp(.5rem,.4rem + .3vw,.75rem);
  flex-wrap:wrap;padding-block:clamp(.75rem,.5rem + .5vw,1.25rem)}
.footer-links a{font-size:clamp(.55rem,.5rem + .15vw,.65rem);color:var(--text4);
  padding:.3rem .5rem;border-radius:var(--radius-xs);transition:all .2s var(--ease);
  text-decoration:none}
.footer-links a:hover{color:var(--blue);background:var(--card)}

/* ═══ RESPONSIVE HIDING ═══ */
.hide-mobile{display:none}
@media(min-width:640px){.hide-mobile{display:block}.show-mobile{display:none}}
@media(min-width:1100px){.hide-tablet{display:block}}
</style>
</head>
<body>

<!-- ═══ HEADER ═══ -->
<header class="hdr glass">
  <div class="container hdr-inner">
    <div style="min-width:0">
      <div style="display:flex;align-items:center;gap:.4rem">
        <span class="f-lg" style="font-weight:800;color:#fff">⟐ ORB</span>
        <span class="hide-mobile f-xs" style="padding:.15rem .4rem;border-radius:var(--radius-xs);
          background:rgba(34,197,94,.1);color:var(--green);border:1px solid rgba(34,197,94,.2);font-weight:600">
          <span style="display:inline-block;width:5px;height:5px;border-radius:50%;background:var(--green);margin-right:3px;vertical-align:middle"></span>RAILWAY
        </span>
      </div>
      <p class="f-xs" style="color:var(--text4);margin-top:1px">Africa/Gaborone · CAT</p>
    </div>
    <div style="display:flex;align-items:center;gap:clamp(.4rem,.3rem + .3vw,.75rem)">
      <div class="hide-mobile" style="text-align:right">
        <p class="f-base" style="color:#fff;font-family:var(--font-mono);font-weight:600" id="clock">--:--:--</p>
        <p class="f-xs" style="color:var(--text4)" id="date">Loading...</p>
      </div>
      <div style="display:flex;align-items:center;gap:.35rem;background:rgba(24,24,27,.6);border-radius:999px;
        padding:clamp(.2rem,.15rem + .1vw,.35rem) clamp(.4rem,.3rem + .2vw,.6rem);border:1px solid var(--border)">
        <span style="width:7px;height:7px;border-radius:50%;background:var(--green)" class="live-dot"></span>
        <span class="f-xs" style="color:var(--green);font-weight:700" id="status">...</span>
      </div>
    </div>
  </div>
</header>

<!-- ═══ TICKER ═══ -->
<div class="ticker-wrap">
  <div class="container">
    <div class="ticker-scroll" id="ticker">
      <span class="f-xs" style="color:var(--text4);padding:.3rem 0">Loading prices...</span>
    </div>
  </div>
</div>

<!-- ═══ STATS ═══ -->
<div class="container">
  <div class="stats-grid">
    <div class="stat-box">
      <p class="f-xs" style="color:var(--text4);text-transform:uppercase;letter-spacing:.06em">Markets</p>
      <p class="f-base" style="color:#fff;font-weight:700;margin-top:2px">3</p>
    </div>
    <div class="stat-box">
      <p class="f-xs" style="color:var(--text4);text-transform:uppercase;letter-spacing:.06em">Refresh</p>
      <p class="f-base" style="color:#fff;font-weight:700;margin-top:2px">5s</p>
    </div>
    <div class="stat-box">
      <p class="f-xs" style="color:var(--text4);text-transform:uppercase;letter-spacing:.06em">Updates</p>
      <p class="f-base" style="color:#fff;font-weight:700;font-family:var(--font-mono);margin-top:2px" id="n">0</p>
    </div>
    <div class="stat-box hide-mobile">
      <p class="f-xs" style="color:var(--text4);text-transform:uppercase;letter-spacing:.06em">Source</p>
      <p class="f-base" style="color:var(--green);font-weight:700;margin-top:2px">Railway</p>
    </div>
    <div class="stat-box hide-mobile" style="display:none" id="stat-et">
      <p class="f-xs" style="color:var(--text4);text-transform:uppercase;letter-spacing:.06em">ET Time</p>
      <p class="f-base" style="color:var(--purple);font-weight:700;font-family:var(--font-mono);margin-top:2px" id="et-clock">--:--</p>
    </div>
  </div>
</div>

<!-- ═══ CARDS ═══ -->
<main class="container">
  <div class="card-grid initial-load" id="cards">
    <div id="card-NAS100" class="card-wrap"><div class="card"><div class="card-accent a-closed"></div><div style="padding:clamp(.75rem,.6rem + .5vw,1.1rem)"><div class="shimmer" style="height:14px;width:60px;margin-bottom:12px"></div><div class="shimmer" style="height:28px;width:140px;margin-bottom:8px"></div><div class="shimmer" style="height:16px;width:100px"></div></div></div></div>
    <div id="card-BTCUSD" class="card-wrap"><div class="card"><div class="card-accent a-closed"></div><div style="padding:clamp(.75rem,.6rem + .5vw,1.1rem)"><div class="shimmer" style="height:14px;width:60px;margin-bottom:12px"></div><div class="shimmer" style="height:28px;width:140px;margin-bottom:8px"></div><div class="shimmer" style="height:16px;width:100px"></div></div></div></div>
    <div id="card-GOLD" class="card-wrap"><div class="card"><div class="card-accent a-closed"></div><div style="padding:clamp(.75rem,.6rem + .5vw,1.1rem)"><div class="shimmer" style="height:14px;width:60px;margin-bottom:12px"></div><div class="shimmer" style="height:28px;width:140px;margin-bottom:8px"></div><div class="shimmer" style="height:16px;width:100px"></div></div></div></div>
  </div>

  <div class="footer-links">
    <a href="/api/debug">Debug</a>
    <span style="color:var(--border)">·</span>
    <a href="/api/scraper-test">Test Scraper</a>
    <span style="color:var(--border)">·</span>
    <a href="/api/health">Health</a>
  </div>
</main>

<script>
/* ═══ CONSTANTS ═══ */
const ST={
  TRADE:{cls:'st-trade',accent:'a-trade',badge:'badge-trade',lb:'TRADE'},
  SKIP:{cls:'st-skip',accent:'a-skip',badge:'badge-skip',lb:'SKIP'},
  SCANNING:{cls:'',accent:'a-scan',badge:'badge-scan',lb:'SCANNING'},
  CLOSED:{cls:'',accent:'a-closed',badge:'badge-closed',lb:'CLOSED'},
  FORMING:{cls:'',accent:'a-form',badge:'badge-form',lb:'FORMING'},
  NO_TRADE:{cls:'',accent:'a-skip',badge:'badge-notrade',lb:'NO TRADE'},
  ERROR:{cls:'st-error',accent:'a-error',badge:'badge-error',lb:'ERROR'}
};
const ICONS={NAS100:'<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
  BTCUSD:'<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M11.767 19.089c4.924.868 6.14-6.025 1.216-6.894m-1.216 6.894L5.86 18.047m5.908 1.042-.347 1.97m1.563-8.864c4.924.869 6.14-6.025 1.215-6.893m-1.215 6.893-3.94-.694m5.155-6.2L8.29 4.26m5.908 1.042.348-1.97M7.48 20.364l3.126-17.727"/></svg>',
  GOLD:'<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>'};
const COLORS={NAS100:'var(--blue)',BTCUSD:'var(--orange)',GOLD:'var(--yellow)'};

/* ═══ FVG SVGs ═══ */
const FVGL=`<svg viewBox="0 0 56 36" class="fvg-icon"><rect x="4" y="8" width="7" height="18" fill="var(--red)" rx="1.5"/><line x1="7.5" y1="3" x2="7.5" y2="8" stroke="var(--red)" stroke-width="1.5"/><line x1="7.5" y1="26" x2="7.5" y2="32" stroke="var(--red)" stroke-width="1.5"/><rect x="20" y="3" width="9" height="26" fill="var(--green)" rx="1.5"/><line x1="24.5" y1="1" x2="24.5" y2="3" stroke="var(--green)" stroke-width="1.5"/><line x1="24.5" y1="29" x2="24.5" y2="34" stroke="var(--green)" stroke-width="1.5"/><rect x="38" y="5" width="7" height="14" fill="var(--green)" rx="1.5"/><line x1="41.5" y1="1" x2="41.5" y2="5" stroke="var(--green)" stroke-width="1.5"/><line x1="41.5" y1="19" x2="41.5" y2="26" stroke="var(--green)" stroke-width="1.5"/><rect x="11" y="7" width="27" height="5" fill="var(--green)" fill-opacity=".12" stroke="var(--green)" stroke-width=".8" stroke-dasharray="2,2" rx="2"/></svg>`;
const FVGS=`<svg viewBox="0 0 56 36" class="fvg-icon"><rect x="4" y="10" width="7" height="18" fill="var(--green)" rx="1.5"/><line x1="7.5" y1="5" x2="7.5" y2="10" stroke="var(--green)" stroke-width="1.5"/><line x1="7.5" y1="28" x2="7.5" y2="34" stroke="var(--green)" stroke-width="1.5"/><rect x="20" y="7" width="9" height="26" fill="var(--red)" rx="1.5"/><line x1="24.5" y1="3" x2="24.5" y2="7" stroke="var(--red)" stroke-width="1.5"/><line x1="24.5" y1="33" x2="24.5" y2="35" stroke="var(--red)" stroke-width="1.5"/><rect x="38" y="16" width="7" height="14" fill="var(--red)" rx="1.5"/><line x1="41.5" y1="10" x2="41.5" y2="16" stroke="var(--red)" stroke-width="1.5"/><line x1="41.5" y1="30" x2="41.5" y2="35" stroke="var(--red)" stroke-width="1.5"/><rect x="11" y="24" width="27" height="5" fill="var(--red)" fill-opacity=".12" stroke="var(--red)" stroke-width=".8" stroke-dasharray="2,2" rx="2"/></svg>`;
const FVGW=`<svg viewBox="0 0 56 36" class="fvg-icon" style="opacity:.35"><rect x="6" y="8" width="7" height="18" fill="var(--text4)" rx="1.5"/><line x1="9.5" y1="3" x2="9.5" y2="8" stroke="var(--text4)" stroke-width="1.5"/><line x1="9.5" y1="26" x2="9.5" y2="32" stroke="var(--text4)" stroke-width="1.5"/><rect x="22" y="6" width="8" height="22" fill="var(--text4)" rx="1.5"/><line x1="26" y1="2" x2="26" y2="6" stroke="var(--text4)" stroke-width="1.5"/><line x1="26" y1="28" x2="26" y2="34" stroke="var(--text4)" stroke-width="1.5"/><text x="42" y="22" font-size="14" fill="var(--text4)" font-weight="bold">?</text></svg>`;

/* ═══ HELPERS ═══ */
const fmt=p=>p==null?'—':Number(p).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});

function badge(s){const c=ST[s]||ST.ERROR;return `<span class="badge ${c.badge}">${c.lb}</span>`}

function box(l,v,c='#fff'){return `<div class="data-box"><p class="f-xs" style="color:var(--text4);text-transform:uppercase;letter-spacing:.05em;margin-bottom:2px">${l}</p><p class="f-sm" style="color:${c};font-weight:600;font-family:var(--font-mono);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${v}</p></div>`}

function gauge(score,max=12){
  const pct=Math.min(score/max,1);
  const r=40, circ=2*Math.PI*r;
  const offset=circ*(1-pct);
  const color=score>=9?'var(--green)':score>=7?'#84cc16':score>=5?'var(--yellow)':'var(--red)';
  return `<div class="gauge-wrap">
    <svg class="gauge-svg" viewBox="0 0 100 100">
      <circle class="gauge-bg" cx="50" cy="50" r="${r}"/>
      <circle class="gauge-fill" cx="50" cy="50" r="${r}" stroke="${color}" stroke-dasharray="${circ}" style="--offset:${offset};stroke-dashoffset:${offset}"/>
      <text class="gauge-text" x="50" y="50" transform="rotate(90 50 50)">${score}</text>
    </svg>
    <div style="min-width:0">
      <p class="f-xs" style="color:var(--text3)">Confidence Score</p>
      <p class="f-lg" style="font-weight:700;font-family:var(--font-mono);color:${color}">${score}<span class="f-sm" style="color:var(--text4)">/${max}</span></p>
      <p class="f-xs" style="color:${color};font-weight:600;margin-top:2px">${score>=9?'HIGH':score>=7?'GOOD':score>=5?'MEDIUM':'LOW'} CONFIDENCE</p>
    </div>
  </div>`
}

function sessionTimeline(d){
  const p=d.session_progress||0;
  const color=d.status==='TRADE'?'var(--green)':d.status==='SCANNING'?'var(--blue)':'var(--text4)';
  return `<div style="margin-top:clamp(.4rem,.3rem + .2vw,.6rem)">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
      <span class="f-xs" style="color:var(--text4)">Session Progress</span>
      <span class="f-xs" style="color:var(--text3);font-family:var(--font-mono)">${d.session_time||'--'}</span>
    </div>
    <div class="timeline"><div class="timeline-fill" style="width:${p}%;background:${color};color:${color}"></div></div>
  </div>`
}

function changeTag(d){
  if(d.price_change==null) return'';
  const up=d.price_change>=0;const s=up?'+':'';
  const cl=up?'var(--green)':'var(--red)';
  return `<span class="f-sm" style="color:${cl};font-weight:500">${up?'▲':'▼'} ${s}$${fmt(Math.abs(d.price_change))} <span style="opacity:.65">(${s}${d.price_change_pct||0}%)</span></span>`
}

function fvgBlock(d){
  if(d.fvg_detected&&d.direction){
    const isL=d.direction==='LONG';
    const cls=isL?'fvg-long fvg-glow-l':'fvg-short fvg-glow-s';
    const clr=isL?'var(--green)':'var(--red)';
    return `<div class="fvg-block ${cls}">
      ${isL?FVGL:FVGS}
      <div style="min-width:0">
        <p class="f-xs" style="color:var(--text3);text-transform:uppercase;letter-spacing:.05em">FVG Detected${d.fvg_time?' · '+d.fvg_time+' ET':''}</p>
        <p class="f-base" style="font-weight:700;color:${clr}">${d.direction} · $${d.fvg_size}</p>
      </div>
    </div>`
  }
  if(d.status==='SCANNING')
    return `<div class="fvg-block fvg-wait">${FVGW}<div><p class="f-xs" style="color:var(--text4);text-transform:uppercase;letter-spacing:.05em">Waiting for FVG</p><p class="f-xs" style="color:var(--text4)">Scanning post-range candles…</p></div></div>`;
  return ''
}

/* ═══ CARD BUILDER ═══ */
let prevP={};

function card(d){
  const s=ST[d.status]||ST.ERROR;
  const isTrade=d.status==='TRADE'||d.status==='SKIP';
  const isActive=['TRADE','SKIP','SCANNING','FORMING','NO_TRADE'].includes(d.status);
  const clr=COLORS[d.asset]||'var(--text)';
  const tc=d.trend==='BULLISH'?'var(--green)':d.trend==='BEARISH'?'var(--red)':'var(--text4)';
  const dc=d.direction==='LONG'?'var(--green)':'var(--red)';

  const prev=prevP[d.asset];
  const flash=prev&&d.price!==prev?(d.price>prev?'flash-up':'flash-dn'):'';
  prevP[d.asset]=d.price;

  let h=`<div class="card ${s.cls} ${d.status==='SCANNING'?'scan-line':''}">`;
  h+=`<div class="card-accent ${s.accent}"></div>`;

  // HEADER
  h+=`<div class="card-header">
    <div style="display:flex;align-items:center;gap:clamp(.3rem,.25rem + .2vw,.5rem);min-width:0">
      <span style="color:${clr};display:flex">${ICONS[d.asset]||'📊'}</span>
      <span class="f-base" style="font-weight:700;color:#fff">${d.asset}</span>
      ${d.window?`<span class="f-xs" style="color:var(--purple);background:rgba(168,85,247,.08);
        padding:.1rem .35rem;border-radius:var(--radius-xs);border:1px solid rgba(168,85,247,.2);
        white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:90px">${d.window}</span>`:''}
    </div>
    ${badge(d.status)}
  </div>`;

  // PRICE
  h+=`<div class="card-price">
    <div style="display:flex;align-items:flex-end;justify-content:space-between;gap:.5rem">
      <div style="min-width:0;flex:1">
        <p class="f-price ${flash}" style="font-weight:800;color:#fff;font-family:var(--font-mono);line-height:1.1">$${fmt(d.price)}</p>
        <div style="margin-top:4px">${changeTag(d)}</div>
      </div>
      <div style="text-align:right;flex-shrink:0">
        ${d.trend?`<p class="f-sm" style="font-weight:600;color:${tc}">${d.trend==='BULLISH'?'▲':'▼'} ${d.trend}</p>`:''}
        ${d.ma50?`<p class="f-xs" style="color:var(--text4);font-family:var(--font-mono)">MA50 ${fmt(d.ma50)}</p>`:''}
        ${d.ma200?`<p class="f-xs" style="color:var(--text4);font-family:var(--font-mono)">MA200 ${fmt(d.ma200)}</p>`:''}
      </div>
    </div>
    ${isActive&&d.session_progress!=null?sessionTimeline(d):''}
  </div>`;

  // BODY
  h+=`<div class="card-body">`;
  h+=`<p class="f-sm" style="color:var(--text);line-height:1.5">${d.message}</p>`;

  if(isTrade){
    h+=fvgBlock(d);
    h+=`<div class="inner-grid-2" style="margin-top:clamp(.4rem,.3rem + .2vw,.6rem)">
      ${box('Direction',(d.direction==='LONG'?'↑':'↓')+' '+d.direction,dc)}
      ${box('Confidence',d.confidence,d.confidence==='HIGH'?'var(--green)':d.confidence==='MEDIUM'?'var(--yellow)':'var(--orange)')}
    </div>`;
    h+=gauge(d.score);
    h+=`<div style="border-top:1px solid var(--border);margin:clamp(.5rem,.4rem + .3vw,.75rem) 0"></div>`;
    h+=`<div class="inner-grid-4">${box('Entry','$'+fmt(d.entry),dc)}${box('Stop','$'+fmt(d.stop),'var(--red)')}${box('Target','$'+fmt(d.target),'var(--green)')}${box('Range','$'+fmt(d.range_size))}</div>`;
    h+=`<div class="inner-grid-3" style="margin-top:clamp(.25rem,.2rem + .15vw,.35rem)">${box('FVG','$'+d.fvg_size)}${box('Speed',d.speed+' bar'+(d.speed>1?'s':''))}${box('Day',d.day||'—')}</div>`;

    if(d.reasons?.length){
      h+=`<details class="breakdown"><summary class="f-xs" style="color:var(--text3);font-weight:500">
        <svg class="chevron" width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"/></svg>
        Score Breakdown (${d.reasons.length} factors)</summary>
        <div class="bd-content" style="display:flex;flex-direction:column;gap:3px;padding-left:.75rem;border-left:2px solid var(--border)">`;
      d.reasons.forEach(r=>{
        const pos=r.includes('+');
        h+=`<p class="f-xs" style="color:${pos?'var(--green)':'var(--red)'};display:flex;align-items:center;gap:4px">
          <span style="width:14px;text-align:center">${pos?'✓':'✗'}</span>${r}</p>`;
      });
      h+=`</div></details>`;
    }
  } else if(['SCANNING','FORMING','NO_TRADE'].includes(d.status)){
    if(d.status==='SCANNING') h+=fvgBlock(d);
    if(d.range_progress!=null){
      h+=`<div style="margin-top:clamp(.5rem,.4rem + .3vw,.75rem)">
        <div style="display:flex;justify-content:space-between;margin-bottom:4px">
          <span class="f-xs" style="color:var(--text4)">Range Progress</span>
          <span class="f-xs" style="color:var(--indigo);font-family:var(--font-mono);font-weight:600">${d.range_progress}%</span>
        </div>
        <div class="timeline"><div class="timeline-fill" style="width:${d.range_progress}%;background:var(--indigo);color:var(--indigo)"></div></div>
      </div>`;
    }
    h+=`<div class="inner-grid-3" style="margin-top:clamp(.5rem,.4rem + .3vw,.75rem)">`;
    if(d.range_high) h+=box('High','$'+fmt(d.range_high));
    if(d.range_low) h+=box('Low','$'+fmt(d.range_low));
    if(d.range_size) h+=box('Range','$'+fmt(d.range_size));
    if(d.day_open) h+=box('Open','$'+fmt(d.day_open));
    if(d.next_window) h+=box('Next Window',d.next_window,'var(--purple)');
    if(d.day) h+=box('Day',d.day);
    h+=`</div>`;
  } else {
    h+=`<div class="inner-grid-2" style="margin-top:clamp(.5rem,.4rem + .3vw,.75rem)">`;
    if(d.trend) h+=box('Trend',d.trend,tc);
    if(d.day) h+=box('Day',d.day);
    if(d.next_window) h+=box('Next',d.next_window,'var(--purple)');
    if(d.day_open) h+=box('Open','$'+fmt(d.day_open));
    h+=`</div>`;
  }

  h+=`</div></div>`;
  return h;
}

/* ═══ TICKER ═══ */
function ticker(data){
  let h='';
  ['NAS100','BTCUSD','GOLD'].forEach(a=>{
    const d=data[a]; if(!d||!d.price) return;
    const up=(d.price_change||0)>=0;
    const clr=up?'var(--green)':'var(--red)';
    const bg=up?'rgba(34,197,94,.04)':'rgba(239,68,68,.04)';
    h+=`<div class="ticker-item" style="background:${bg}">
      <span style="color:${COLORS[a]};display:flex">${ICONS[a]}</span>
      <div style="display:flex;align-items:center;gap:clamp(.3rem,.2rem + .2vw,.5rem)">
        <span class="f-xs" style="color:var(--text3);font-weight:500">${a}</span>
        <span class="f-sm" style="font-weight:700;color:#fff;font-family:var(--font-mono)">$${fmt(d.price)}</span>
        ${d.price_change!=null?`<span class="f-xs" style="font-weight:600;color:${clr}">${up?'▲':'▼'}${Math.abs(d.price_change_pct||0)}%</span>`:''}
      </div>
    </div>`;
  });
  document.getElementById('ticker').innerHTML=h||'<span class="f-xs" style="color:var(--text4)">No prices</span>';
}

/* ═══ MAIN LOOP — DIFF UPDATES ═══ */
let n=0, errCount=0, prevData={}, firstLoad=true;

async function go(){
  const st=document.getElementById('status');
  try{
    st.innerHTML='<span style="display:inline-block;width:10px;height:10px;border:2px solid var(--blue);border-top-color:transparent;border-radius:50%;animation:spin .5s linear infinite"></span>';

    const r=await fetch('/api/scan');
    if(!r.ok) throw new Error('HTTP '+r.status);
    const d=await r.json();

    ['NAS100','BTCUSD','GOLD'].forEach(asset=>{
      const nh=JSON.stringify(d[asset]);
      const oh=JSON.stringify(prevData[asset]);
      if(nh!==oh||firstLoad){
        const el=document.getElementById('card-'+asset);
        if(el){
          const wasOpen=el.querySelector('details[open]')!==null;
          el.innerHTML=card(d[asset]);
          if(wasOpen){const det=el.querySelector('details');if(det)det.setAttribute('open','')}
        }
      }
    });

    prevData=JSON.parse(JSON.stringify(d));
    if(firstLoad){firstLoad=false;setTimeout(()=>document.getElementById('cards')?.classList.remove('initial-load'),500)}

    ticker(d);
    n++;errCount=0;
    document.getElementById('n').textContent=n;
    st.textContent='LIVE';st.style.color='var(--green)';

    // Show ET stat if available
    const etStat=document.getElementById('stat-et');
    const etClock=document.getElementById('et-clock');
    if(d.NAS100?.session_time&&etStat&&etClock){
      etStat.style.display='';etClock.textContent=d.NAS100.session_time;
    }
  }catch(e){
    errCount++;
    st.textContent=errCount>3?'OFFLINE':'RETRY';st.style.color='var(--red)';
    console.error('Scan:',e);
  }
}

function ck(){
  const d=new Date();
  const el=document.getElementById('clock');
  if(el) el.textContent=d.toLocaleTimeString('en-US',{timeZone:'Africa/Gaborone',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false})+' CAT';
  const de=document.getElementById('date');
  if(de) de.textContent=d.toLocaleDateString('en-US',{timeZone:'Africa/Gaborone',weekday:'short',month:'short',day:'numeric'});
}

go();ck();
setInterval(go,5000);
setInterval(ck,1000);
</script>

<style>
.fvg-icon{width:clamp(40px,36px + 1vw,52px);height:clamp(28px,24px + .7vw,36px);flex-shrink:0}
</style>
</body>
</html>"""