# Save this as: api/index.py

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from datetime import datetime
import pytz
import urllib.request
import json

app = FastAPI()

CONFIGS = {
    "NAS100": {
        "tv": "OANDA:NAS100USD",
        "max_range": 80, "max_fvg": None, "max_speed": 30, "weekend": False,
        "range": [(30,45,3),(0,30,1),(45,60,1),(60,80,0)],
        "fvg": [(15,9999,2),(0,3,2),(7,15,1),(3,7,0)],
        "speed": [(0,10,3),(10,20,2),(20,30,1)],
        "best_day": ("Tuesday",3), "good_days": [("Thursday",1)],
        "worst_day": ("Wednesday",-2), "bias": ("LONG",1)
    },
    "BTCUSD": {
        "tv": "BITSTAMP:BTCUSD",
        "max_range": 750, "max_fvg": 200, "max_speed": None, "weekend": True,
        "range": [(350,500,3),(200,350,2),(0,200,1),(500,750,0)],
        "fvg": [(25,50,3),(0,25,2),(50,100,0),(100,200,0)],
        "speed": [(60,120,3),(30,60,2),(120,9999,1),(0,30,0)],
        "best_day": ("Sunday",3), "good_days": [("Saturday",2),("Tuesday",2),("Thursday",1)],
        "worst_day": ("Friday",-2), "bias": None
    },
    "GOLD": {
        "tv": "OANDA:XAUUSD",
        "max_range": None, "max_fvg": None, "max_speed": None, "weekend": False,
        "range": [(0,5,3),(10,15,2),(25,9999,2),(5,10,0),(15,25,0)],
        "fvg": [(3,5,3),(10,9999,3),(5,10,1),(0,3,0)],
        "speed": [(30,60,3),(120,9999,2),(10,30,1),(0,10,0),(60,120,0)],
        "best_day": ("Tuesday",3), "good_days": [("Thursday",1)],
        "worst_day": ("Monday",-1), "bias": ("SHORT",1)
    }
}


# ═══════════════════════════════════════════════
# WEB SCRAPER
# ═══════════════════════════════════════════════
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}

def http_get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    resp = urllib.request.urlopen(req, timeout=10)
    return json.loads(resp.read().decode())


def scrape_btc_candles(interval, limit):
    """Scrape BTC from Binance — free, no key, 1min and 15min"""
    iv = "1m" if interval == "1min" else "15m"
    url = f"https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval={iv}&limit={limit}"
    data = http_get(url)
    et = pytz.timezone('US/Eastern')
    candles = []
    for k in data:
        ts = int(k[0]) / 1000
        dt = datetime.fromtimestamp(ts, tz=et)
        candles.append({
            "time": dt.strftime("%H:%M"),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4])
        })
    return candles


def scrape_tradingview(symbol, exchange, interval, bars):
    """Scrape from TradingView scanner endpoint"""
    url = "https://scanner.tradingview.com/forex/scan"
    # TradingView scanner gives current price, not candles
    # Use their symbol search for basic data
    try:
        search_url = f"https://symbol-search.tradingview.com/symbol_search/v3/?text={symbol}&exchange={exchange}"
        data = http_get(search_url)
        return data
    except:
        return None


def scrape_investing(pair_id, interval, points):
    """Scrape candle data from Investing.com"""
    iv_map = {"1min": "60", "15min": "900"}
    url = f"https://tvc6.investing.com/57112963e0ad4/0/0/0/0/history?symbol={pair_id}&resolution={iv_map.get(interval, '60')}&from={int(datetime.now().timestamp()) - (points * 60 * 15)}&to={int(datetime.now().timestamp())}"
    try:
        data = http_get(url)
        et = pytz.timezone('US/Eastern')
        candles = []
        if 't' in data:
            for i in range(len(data['t'])):
                dt = datetime.fromtimestamp(data['t'][i], tz=et)
                candles.append({
                    "time": dt.strftime("%H:%M"),
                    "open": data['o'][i],
                    "high": data['h'][i],
                    "low": data['l'][i],
                    "close": data['c'][i]
                })
        return candles
    except:
        return []


def scrape_fcs(symbol, interval):
    """Scrape from FCS API — free forex/commodity data"""
    try:
        url = f"https://fcsapi.com/api-v3/forex/history?symbol={symbol}&period={interval}&access_key=API_KEY"
        return http_get(url)
    except:
        return None


def scrape_candles(asset, interval, limit):
    """Route to correct scraper per asset"""
    et = pytz.timezone('US/Eastern')
    
    if asset == "BTCUSD":
        return scrape_btc_candles(interval, limit)
    
    # For NAS100 and GOLD — use Yahoo chart endpoint (just urllib, no package)
    tickers = {"NAS100": "NQ=F", "GOLD": "GC=F"}
    ticker = tickers.get(asset)
    
    if not ticker:
        return []
    
    iv = "1m" if interval == "1min" else "15m"
    period = "1d" if interval == "1min" else "60d"
    
    urls = [
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval={iv}&range={period}",
        f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?interval={iv}&range={period}"
    ]
    
    for url in urls:
        try:
            data = http_get(url)
            r = data['chart']['result'][0]
            if 'timestamp' not in r:
                continue
            
            ts = r['timestamp']
            q = r['indicators']['quote'][0]
            candles = []
            
            for i in range(len(ts)):
                if q['open'][i] is None:
                    continue
                dt = datetime.fromtimestamp(ts[i], tz=et)
                candles.append({
                    "time": dt.strftime("%H:%M"),
                    "open": q['open'][i],
                    "high": q['high'][i],
                    "low": q['low'][i],
                    "close": q['close'][i]
                })
            
            return candles
        except:
            continue
    
    return []


def scrape_asset(asset):
    """Scrape all data needed for one asset"""
    result = {
        "asset": asset, "tv": CONFIGS[asset]["tv"],
        "status": "ERROR", "candles": [],
        "ma50": None, "ma200": None, "price": None, "error": None
    }
    
    try:
        # 15min for MAs
        candles_15 = scrape_candles(asset, "15min", 300)
        
        if len(candles_15) < 200:
            result["error"] = f"Only {len(candles_15)} bars of 15min data, need 200"
            return result
        
        closes = [c['close'] for c in candles_15]
        result["ma50"] = round(sum(closes[-50:]) / 50, 2)
        result["ma200"] = round(sum(closes[-200:]) / 200, 2)
        
        # 1min for candles
        candles_1 = scrape_candles(asset, "1min", 500)
        
        if not candles_1:
            result["error"] = "No 1min data — market likely closed"
            result["status"] = "NO_1MIN"
            return result
        
        result["candles"] = candles_1
        result["price"] = round(candles_1[-1]['close'], 2)
        result["status"] = "OK"
        result["candle_count"] = len(candles_1)
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


def scrape_all():
    results = {}
    for asset in ["NAS100", "BTCUSD", "GOLD"]:
        results[asset] = scrape_asset(asset)
    return results


# ═══════════════════════════════════════════════
# MODEL
# ═══════════════════════════════════════════════
def score_trade(asset, range_size, fvg_size, speed, direction, date):
    c = CONFIGS[asset]
    score = 0
    reasons = []
    if c["max_range"] and range_size > c["max_range"]:
        return {"score":0,"take_trade":False,"confidence":"REJECTED","reasons":["Range too wide"]}
    if c["max_fvg"] and fvg_size > c["max_fvg"]:
        return {"score":0,"take_trade":False,"confidence":"REJECTED","reasons":["FVG too large"]}
    if c["max_speed"] and speed > c["max_speed"]:
        return {"score":0,"take_trade":False,"confidence":"REJECTED","reasons":["Breakout too slow"]}
    for low,high,pts in c["range"]:
        if low <= range_size <= high:
            score += pts
            if pts > 0: reasons.append(f"Range {low}-{high} (+{pts})")
            break
    for low,high,pts in c["fvg"]:
        if low <= fvg_size <= high:
            score += pts
            if pts > 0: reasons.append(f"FVG {low}-{high} (+{pts})")
            break
    for low,high,pts in c["speed"]:
        if low <= speed <= high:
            score += pts
            if pts > 0: reasons.append(f"Speed {low}-{high} (+{pts})")
            break
    y,m,d = map(int,str(date).split('-')[:3])
    day = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'][datetime(y,m,d).weekday()]
    if c["best_day"] and day == c["best_day"][0]:
        score += c["best_day"][1]; reasons.append(f"{day} (+{c['best_day'][1]})")
    for gd,pts in c["good_days"]:
        if day == gd: score += pts; reasons.append(f"{day} (+{pts})"); break
    if c["worst_day"] and day == c["worst_day"][0]:
        score += c["worst_day"][1]; reasons.append(f"{day} ({c['worst_day'][1]})")
    if c["bias"] and direction == c["bias"][0]:
        score += c["bias"][1]; reasons.append(f"{direction} bias (+{c['bias'][1]})")
    confidence = "HIGH" if score >= 7 else "MEDIUM" if score >= 5 else "LOW"
    return {"score":score,"take_trade":score>=5,"confidence":confidence,"reasons":reasons}


def detect_fvg(c1, c2, c3, direction):
    if direction == "LONG":
        fvg = c3['low'] - c1['high']
        if fvg > 0 and c2['close'] > c2['open']:
            return {"valid":True,"size":fvg,"entry":c3['low']}
    elif direction == "SHORT":
        fvg = c1['low'] - c3['high']
        if fvg > 0 and c2['close'] < c2['open']:
            return {"valid":True,"size":fvg,"entry":c3['high']}
    return {"valid":False,"size":0,"entry":0}


def run_scan(asset, scraped):
    config = CONFIGS[asset]
    et = pytz.timezone('US/Eastern')
    now = datetime.now(et)
    base = {"asset": asset, "tv": config["tv"], "time": now.strftime("%H:%M:%S"), "day": now.strftime("%A")}

    if not config["weekend"] and now.weekday() >= 5:
        return {**base, "status": "CLOSED", "message": "Weekend — markets closed"}
    if not config["weekend"] and (now.hour < 9 or (now.hour == 9 and now.minute < 30)):
        h = 9 - now.hour; m = 30 - now.minute
        if m < 0: h -= 1; m += 60
        return {**base, "status": "PRE_MARKET", "message": f"NY opens in {h}h {m}m"}
    if not config["weekend"] and now.hour >= 16:
        return {**base, "status": "CLOSED", "message": "NY session ended"}

    if scraped["status"] == "ERROR":
        return {**base, "status": "ERROR", "message": scraped.get("error", "Scraper failed")}

    ma50 = scraped["ma50"]
    ma200 = scraped["ma200"]
    trend = "BULLISH" if ma50 > ma200 else "BEARISH"

    if scraped["status"] in ["NO_1MIN", "NO_CANDLES"]:
        return {**base, "status": "CLOSED", "message": scraped["error"], "trend": trend, "ma50": ma50, "ma200": ma200}

    candles = scraped["candles"]
    price = scraped["price"]

    oc = [c for c in candles if 930 <= int(c['time'].replace(':','')) <= 944]
    if not oc:
        return {**base, "status": "WAITING", "message": "Waiting for opening range (9:30-9:44 ET)", "trend": trend, "price": price, "ma50": ma50, "ma200": ma200}

    rh = round(max(c['high'] for c in oc), 2)
    rl = round(min(c['low'] for c in oc), 2)
    rs = round(rh - rl, 2)

    if config["max_range"] and rs > config["max_range"]:
        return {**base, "status": "NO_TRADE", "message": f"Range too wide ({rs})", "trend": trend, "price": price, "range_high": rh, "range_low": rl, "range_size": rs}

    post = [c for c in candles if int(c['time'].replace(':','')) >= 945]
    if len(post) < 3:
        return {**base, "status": "FORMING", "message": "Waiting for post-range candles", "trend": trend, "price": price, "range_high": rh, "range_low": rl, "range_size": rs}

    today = now.strftime("%Y-%m-%d")
    t = "LONG" if ma50 > ma200 else "SHORT"

    for i in range(len(post) - 2):
        c1, c2, c3 = post[i], post[i+1], post[i+2]
        if t == "LONG" and c2['close'] > rh:
            fvg = detect_fvg(c1, c2, c3, "LONG")
            if fvg['valid']:
                pred = score_trade(asset, rs, fvg['size'], i+1, "LONG", today)
                return {**base, "status": "TRADE" if pred["take_trade"] else "SKIP",
                    "message": f"{pred['confidence']} LONG — {'TAKE TRADE' if pred['take_trade'] else 'SKIP'}",
                    "direction": "LONG", "entry": round(fvg['entry'],2), "stop": rl,
                    "target": round(fvg['entry']+(fvg['entry']-rl),2), "trend": trend,
                    "price": price, "range_high": rh, "range_low": rl, "range_size": rs,
                    "fvg_size": round(fvg['size'],2), "speed": i+1,
                    "score": pred["score"], "confidence": pred["confidence"],
                    "reasons": pred["reasons"], "ma50": ma50, "ma200": ma200}
        if t == "SHORT" and c2['close'] < rl:
            fvg = detect_fvg(c1, c2, c3, "SHORT")
            if fvg['valid']:
                pred = score_trade(asset, rs, fvg['size'], i+1, "SHORT", today)
                return {**base, "status": "TRADE" if pred["take_trade"] else "SKIP",
                    "message": f"{pred['confidence']} SHORT — {'TAKE TRADE' if pred['take_trade'] else 'SKIP'}",
                    "direction": "SHORT", "entry": round(fvg['entry'],2), "stop": rh,
                    "target": round(fvg['entry']-(rh-fvg['entry']),2), "trend": trend,
                    "price": price, "range_high": rh, "range_low": rl, "range_size": rs,
                    "fvg_size": round(fvg['size'],2), "speed": i+1,
                    "score": pred["score"], "confidence": pred["confidence"],
                    "reasons": pred["reasons"], "ma50": ma50, "ma200": ma200}

    if price > rh: pm = "Price ABOVE range — Waiting for FVG"
    elif price < rl: pm = "Price BELOW range — Waiting for FVG"
    else: pm = "Price INSIDE range — No breakout"

    return {**base, "status": "SCANNING", "message": pm, "trend": trend, "price": price,
        "range_high": rh, "range_low": rl, "range_size": rs, "ma50": ma50, "ma200": ma200}


# ═══════════════════════════════════════════════
# ENDPOINTS
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
            "error": data.get("error"),
            "ma50": data.get("ma50"),
            "ma200": data.get("ma200"),
            "price": data.get("price"),
            "candle_count": data.get("candle_count", 0),
            "first_candle": data["candles"][0] if data["candles"] else None,
            "last_candle": data["candles"][-1] if data["candles"] else None,
            "source": "Binance" if asset == "BTCUSD" else "Web Scraper"
        }
    return JSONResponse(content=debug)


@app.get("/", response_class=HTMLResponse)
def home():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ORB Scanner</title>
<script src="https://cdn.tailwindcss.com"></script>
<script>tailwind.config={theme:{extend:{colors:{bg:'#09090b',card:'#111113',border:'#1e1e22'}}}}</script>
</head>
<body class="bg-bg text-gray-300 min-h-screen p-4">
<div class="max-w-7xl mx-auto">

  <div class="text-center mb-6 border-b border-border pb-4">
    <h1 class="text-xl font-bold text-white">ORB Model V1.0</h1>
    <p class="text-xs text-gray-600 mt-1">NAS100 · BTCUSD · GOLD</p>
    <div class="flex items-center justify-center gap-3 mt-2">
      <p class="text-xs text-gray-600" id="clock"></p>
      <span class="text-xs px-2 py-0.5 rounded-full bg-green-500/10 border border-green-500/30 text-green-400" id="dot">LIVE</span>
    </div>
  </div>

  <div class="grid grid-cols-1 md:grid-cols-3 gap-4" id="dash">
    <div class="bg-card border border-border rounded-lg p-6 animate-pulse"><div class="h-4 bg-border rounded w-24 mb-3"></div><div class="h-8 bg-border rounded w-32"></div></div>
    <div class="bg-card border border-border rounded-lg p-6 animate-pulse"><div class="h-4 bg-border rounded w-24 mb-3"></div><div class="h-8 bg-border rounded w-32"></div></div>
    <div class="bg-card border border-border rounded-lg p-6 animate-pulse"><div class="h-4 bg-border rounded w-24 mb-3"></div><div class="h-8 bg-border rounded w-32"></div></div>
  </div>

  <div class="text-center mt-4"><p class="text-[10px] text-gray-700" id="upd"></p></div>

</div>
<script>
const ST={TRADE:{bg:'bg-green-500/10',b:'border-green-500/30',t:'text-green-400',l:'TRADE'},SKIP:{bg:'bg-yellow-500/10',b:'border-yellow-500/30',t:'text-yellow-400',l:'SKIP'},SCANNING:{bg:'bg-blue-500/10',b:'border-blue-500/30',t:'text-blue-400',l:'SCANNING'},CLOSED:{bg:'bg-gray-500/10',b:'border-gray-500/30',t:'text-gray-500',l:'CLOSED'},PRE_MARKET:{bg:'bg-purple-500/10',b:'border-purple-500/30',t:'text-purple-400',l:'PRE-MARKET'},WAITING:{bg:'bg-purple-500/10',b:'border-purple-500/30',t:'text-purple-400',l:'WAITING'},FORMING:{bg:'bg-purple-500/10',b:'border-purple-500/30',t:'text-purple-400',l:'FORMING'},NO_TRADE:{bg:'bg-yellow-500/10',b:'border-yellow-500/30',t:'text-yellow-400',l:'NO TRADE'},ERROR:{bg:'bg-red-500/10',b:'border-red-500/30',t:'text-red-400',l:'ERROR'}};
function bd(s){const x=ST[s]||ST.ERROR;return`<span class="inline-block px-2.5 py-0.5 rounded-full text-[10px] font-bold ${x.bg} ${x.b} ${x.t} border uppercase tracking-wide">${x.l}</span>`}
function gi(l,v,c='text-white'){return`<div class="bg-bg border border-border rounded px-3 py-2"><div class="text-[9px] text-gray-600 uppercase tracking-wide">${l}</div><div class="text-sm font-semibold mt-0.5 ${c}">${v}</div></div>`}
function br(s){const p=Math.min(Math.round(s/12*100),100),c=s>=7?'#4ade80':s>=5?'#fbbf24':'#f87171';return`<div class="bg-gray-800 rounded h-1 mt-2"><div class="h-1 rounded" style="width:${p}%;background:${c}"></div></div>`}
function render(d){let h=`<div class="bg-card border border-border rounded-lg p-4"><div class="flex items-center justify-between mb-3"><span class="text-[10px] text-gray-600 uppercase tracking-widest font-medium">${d.asset} · ${d.tv}</span>${bd(d.status)}</div><p class="text-sm text-white mb-3">${d.message}</p>`;
if(d.status==='TRADE'||d.status==='SKIP'){const dc=d.direction==='LONG'?'text-green-400':'text-red-400',ic=d.direction==='LONG'?'↑':'↓',sc=d.score>=7?'text-green-400':d.score>=5?'text-yellow-400':'text-red-400';
h+=`<div class="grid grid-cols-2 gap-1.5 mb-2">${gi('Direction',`${ic} ${d.direction}`,dc)}${gi('Score',`${d.score}/12`,sc)}</div>${br(d.score)}<div class="border-t border-border my-3"></div><div class="grid grid-cols-2 gap-1.5">${gi('Entry',d.entry,dc)}${gi('Stop',d.stop,'text-red-400')}${gi('Target',d.target,'text-green-400')}${gi('Price',d.price)}${gi('Range',d.range_size)}${gi('FVG',d.fvg_size)}${gi('Speed',`${d.speed} candles`)}${gi('Trend',d.trend,d.trend==='BULLISH'?'text-green-400':'text-red-400')}</div>`;
if(d.reasons&&d.reasons.length){h+=`<div class="border-t border-border my-3"></div>`;d.reasons.forEach(r=>{h+=`<div class="text-[11px] text-gray-400 py-0.5"><span class="text-green-400 mr-1">✓</span>${r}</div>`})}}
else if(['SCANNING','WAITING','FORMING','NO_TRADE'].includes(d.status)){const tc=d.trend==='BULLISH'?'text-green-400':d.trend==='BEARISH'?'text-red-400':'';h+=`<div class="grid grid-cols-2 gap-1.5">`;if(d.price)h+=gi('Price',d.price);if(d.trend)h+=gi('Trend',d.trend,tc);if(d.range_high)h+=gi('High',d.range_high);if(d.range_low)h+=gi('Low',d.range_low);if(d.range_size)h+=gi('Range',d.range_size);if(d.ma50&&d.ma200)h+=gi('MA Gap',Math.abs(d.ma50-d.ma200).toFixed(2));h+=`</div>`}
else if(d.trend){const tc=d.trend==='BULLISH'?'text-green-400':'text-red-400';h+=`<div class="grid grid-cols-2 gap-1.5">${gi('Trend',d.trend,tc)}`;if(d.ma50&&d.ma200)h+=gi('MA Gap',Math.abs(d.ma50-d.ma200).toFixed(2));h+=`</div>`}
h+=`</div>`;return h}
let n=0;
async function go(){const dot=document.getElementById('dot');try{dot.textContent='⟳';dot.className='text-xs px-2 py-0.5 rounded-full bg-blue-500/10 border border-blue-500/30 text-blue-400';const r=await fetch('/api/scan'),d=await r.json();document.getElementById('dash').innerHTML=render(d.NAS100)+render(d.BTCUSD)+render(d.GOLD);n++;document.getElementById('upd').textContent=`Refresh #${n} · ${new Date().toLocaleTimeString()}`;dot.textContent='LIVE';dot.className='text-xs px-2 py-0.5 rounded-full bg-green-500/10 border border-green-500/30 text-green-400'}catch(e){dot.textContent='ERROR';dot.className='text-xs px-2 py-0.5 rounded-full bg-red-500/10 border border-red-500/30 text-red-400';document.getElementById('upd').textContent=`Error: ${e.message}`}}
function ck(){const now=new Date(),et=now.toLocaleString('en-US',{timeZone:'America/New_York',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}),day=now.toLocaleString('en-US',{timeZone:'America/New_York',weekday:'long',month:'short',day:'numeric'});document.getElementById('clock').textContent=`${day} · ${et} ET`}
go();setInterval(go,2000);setInterval(ck,1000);ck();
</script>
</body>
</html>"""