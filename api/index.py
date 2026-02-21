from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from datetime import datetime
import pytz
import yfinance as yf
import pandas as pd

app = FastAPI(title="ORB Model V1.0")


class ORBModel:
    def __init__(self):
        self.rules = {
            'max_candles': 30,
            'max_range': 80,
            'min_score': 5,
            'range_sweet_spot': (30, 45),
            'best_day': 'Tuesday',
            'worst_day': 'Wednesday',
            'target_rr': 1.0
        }

    def score_trade(self, range_size, fvg_size, candles_to_break, direction, date):
        score = 0
        reasons = []

        if candles_to_break > self.rules['max_candles']:
            return {"score": 0, "take_trade": False, "confidence": "REJECTED", "reasons": ["Breakout too slow"]}
        if range_size > self.rules['max_range']:
            return {"score": 0, "take_trade": False, "confidence": "REJECTED", "reasons": ["Range too wide"]}

        if self.rules['range_sweet_spot'][0] <= range_size <= self.rules['range_sweet_spot'][1]:
            score += 3
            reasons.append("Sweet spot range (30-45)")
        elif range_size < 30:
            score += 1
            reasons.append("Tight range (<30)")
        elif range_size <= 60:
            score += 1
            reasons.append("Acceptable range (45-60)")

        if candles_to_break <= 10:
            score += 3
            reasons.append("Fast breakout (<=10)")
        elif candles_to_break <= 20:
            score += 2
            reasons.append("Moderate breakout (<=20)")
        elif candles_to_break <= 30:
            score += 1
            reasons.append("Slow breakout (<=30)")

        if fvg_size >= 15:
            score += 2
            reasons.append("Large FVG (>=15)")
        elif fvg_size <= 3:
            score += 2
            reasons.append("Tiny FVG (<=3)")
        elif fvg_size >= 7:
            score += 1
            reasons.append("Medium FVG (7-15)")

        day = pd.to_datetime(date).day_name()
        if day == self.rules['best_day']:
            score += 3
            reasons.append("Tuesday (best day)")
        elif day == 'Thursday':
            score += 1
            reasons.append("Thursday")
        elif day == self.rules['worst_day']:
            score -= 2
            reasons.append("Wednesday (worst day)")

        if direction == "LONG":
            score += 1
            reasons.append("Long bias")

        if score >= 7:
            confidence = "HIGH"
        elif score >= 5:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        return {
            "score": score,
            "take_trade": score >= self.rules['min_score'],
            "confidence": confidence,
            "reasons": reasons
        }

    def detect_fvg(self, c1, c2, c3, direction):
        if direction == "LONG":
            fvg = c3['low'] - c1['high']
            if fvg > 0 and c2['close'] > c2['open']:
                return {"valid": True, "size": fvg, "entry": c3['low']}
        elif direction == "SHORT":
            fvg = c1['low'] - c3['high']
            if fvg > 0 and c2['close'] < c2['open']:
                return {"valid": True, "size": fvg, "entry": c3['high']}
        return {"valid": False, "size": 0, "entry": 0}

    def scan(self, candles, ma_50, ma_200, date):
        or_candles = [c for c in candles if 930 <= int(c['time'].replace(':', '')) <= 944]
        if len(or_candles) == 0:
            return None

        range_high = max(c['high'] for c in or_candles)
        range_low = min(c['low'] for c in or_candles)
        range_size = range_high - range_low
        trend = "LONG" if ma_50 > ma_200 else "SHORT"
        post = [c for c in candles if int(c['time'].replace(':', '')) >= 945]

        if len(post) < 3:
            return None

        for i in range(len(post) - 2):
            c1, c2, c3 = post[i], post[i + 1], post[i + 2]

            if trend == "LONG" and c2['close'] > range_high:
                fvg = self.detect_fvg(c1, c2, c3, "LONG")
                if fvg['valid']:
                    prediction = self.score_trade(range_size, fvg['size'], i + 1, "LONG", date)
                    return {
                        "direction": "LONG",
                        "entry": round(fvg['entry'], 2),
                        "stop": round(range_low, 2),
                        "target": round(fvg['entry'] + (fvg['entry'] - range_low), 2),
                        "range_high": round(range_high, 2),
                        "range_low": round(range_low, 2),
                        "range_size": round(range_size, 2),
                        "fvg_size": round(fvg['size'], 2),
                        "candles_to_break": i + 1,
                        "prediction": prediction
                    }

            if trend == "SHORT" and c2['close'] < range_low:
                fvg = self.detect_fvg(c1, c2, c3, "SHORT")
                if fvg['valid']:
                    prediction = self.score_trade(range_size, fvg['size'], i + 1, "SHORT", date)
                    return {
                        "direction": "SHORT",
                        "entry": round(fvg['entry'], 2),
                        "stop": round(range_high, 2),
                        "target": round(fvg['entry'] - (range_high - fvg['entry']), 2),
                        "range_high": round(range_high, 2),
                        "range_low": round(range_low, 2),
                        "range_size": round(range_size, 2),
                        "fvg_size": round(fvg['size'], 2),
                        "candles_to_break": i + 1,
                        "prediction": prediction
                    }

        return None


model = ORBModel()


def base_html(title, content):
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{title}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: -apple-system, sans-serif; background: #0a0a0a; color: #e0e0e0; padding: 20px; }}
            .container {{ max-width: 600px; margin: 0 auto; }}
            .header {{ text-align: center; padding: 20px 0; border-bottom: 1px solid #222; margin-bottom: 20px; }}
            .header h1 {{ font-size: 20px; color: #fff; }}
            .header p {{ font-size: 13px; color: #666; margin-top: 5px; }}
            .card {{ background: #111; border: 1px solid #222; border-radius: 8px; padding: 20px; margin-bottom: 15px; }}
            .status {{ display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; margin-bottom: 15px; }}
            .status-trade {{ background: #0a3d0a; color: #4ade80; border: 1px solid #166534; }}
            .status-skip {{ background: #3d2a0a; color: #fbbf24; border: 1px solid #854d0e; }}
            .status-scanning {{ background: #0a2a3d; color: #60a5fa; border: 1px solid #1e3a5f; }}
            .status-closed {{ background: #1a1a1a; color: #666; border: 1px solid #333; }}
            .status-waiting {{ background: #1a1a2a; color: #818cf8; border: 1px solid #312e81; }}
            .status-error {{ background: #3d0a0a; color: #f87171; border: 1px solid #7f1d1d; }}
            .message {{ font-size: 16px; color: #fff; margin-bottom: 15px; }}
            .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
            .grid-item {{ background: #0a0a0a; border: 1px solid #222; border-radius: 6px; padding: 12px; }}
            .grid-item .label {{ font-size: 11px; color: #666; text-transform: uppercase; }}
            .grid-item .value {{ font-size: 18px; color: #fff; font-weight: 600; margin-top: 4px; }}
            .long {{ color: #4ade80; }}
            .short {{ color: #f87171; }}
            .reasons {{ margin-top: 15px; }}
            .reason {{ background: #0a0a0a; border: 1px solid #222; border-radius: 4px; padding: 8px 12px; margin-bottom: 5px; font-size: 13px; }}
            .reason:before {{ content: "✓ "; color: #4ade80; }}
            .score-bar {{ background: #222; border-radius: 4px; height: 8px; margin-top: 8px; }}
            .score-fill {{ height: 8px; border-radius: 4px; }}
            .divider {{ border-top: 1px solid #222; margin: 15px 0; }}
            .footer {{ text-align: center; font-size: 11px; color: #444; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>ORB Model V1.0</h1>
                <p>NAS100 Opening Range Breakout Scanner</p>
            </div>
            {content}
            <div class="footer">Auto-refreshes on page reload</div>
        </div>
    </body>
    </html>
    """


@app.get("/", response_class=HTMLResponse)
def health():
    et = pytz.timezone('US/Eastern')
    now = datetime.now(et)
    content = f"""
    <div class="card">
        <span class="status status-scanning">ONLINE</span>
        <p class="message">Scanner is running</p>
        <div class="grid">
            <div class="grid-item">
                <div class="label">Time (ET)</div>
                <div class="value">{now.strftime("%H:%M:%S")}</div>
            </div>
            <div class="grid-item">
                <div class="label">Date</div>
                <div class="value">{now.strftime("%A %b %d")}</div>
            </div>
        </div>
    </div>
    <div class="card">
        <p style="font-size: 13px; color: #666;">Hit <span style="color: #fff;">/scan</span> to run the scanner</p>
    </div>
    """
    return base_html("ORB Model V1.0", content)


@app.get("/scan", response_class=HTMLResponse)
def scan():
    et = pytz.timezone('US/Eastern')
    now = datetime.now(et)
    today = now.strftime("%Y-%m-%d")
    day_name = now.strftime("%A")
    current_time = now.strftime("%H:%M:%S")

    # Weekend
    if now.weekday() >= 5:
        content = f"""
        <div class="card">
            <span class="status status-closed">CLOSED</span>
            <p class="message">Markets closed — {day_name}</p>
            <div class="grid">
                <div class="grid-item">
                    <div class="label">Time (ET)</div>
                    <div class="value">{current_time}</div>
                </div>
                <div class="grid-item">
                    <div class="label">Next Open</div>
                    <div class="value">Monday 9:30</div>
                </div>
            </div>
        </div>
        """
        return base_html("ORB — Closed", content)

    # Pre-market
    if now.hour < 9 or (now.hour == 9 and now.minute < 30):
        hours_left = 9 - now.hour
        mins_left = 30 - now.minute
        if mins_left < 0:
            hours_left -= 1
            mins_left += 60
        content = f"""
        <div class="card">
            <span class="status status-waiting">PRE-MARKET</span>
            <p class="message">NY session opens in {hours_left}h {mins_left}m</p>
            <div class="grid">
                <div class="grid-item">
                    <div class="label">Time (ET)</div>
                    <div class="value">{current_time}</div>
                </div>
                <div class="grid-item">
                    <div class="label">Day</div>
                    <div class="value">{day_name}</div>
                </div>
            </div>
        </div>
        """
        return base_html("ORB — Pre-Market", content)

    # Post-market
    if now.hour >= 16:
        content = f"""
        <div class="card">
            <span class="status status-closed">CLOSED</span>
            <p class="message">NY session ended for today</p>
            <div class="grid">
                <div class="grid-item">
                    <div class="label">Time (ET)</div>
                    <div class="value">{current_time}</div>
                </div>
                <div class="grid-item">
                    <div class="label">Day</div>
                    <div class="value">{day_name}</div>
                </div>
            </div>
        </div>
        """
        return base_html("ORB — Closed", content)

    # Fetch data
    ticker = yf.Ticker("NQ=F")
    data_15min = ticker.history(period="60d", interval="15m")

    if len(data_15min) == 0:
        content = """
        <div class="card">
            <span class="status status-error">ERROR</span>
            <p class="message">Failed to fetch market data</p>
        </div>
        """
        return base_html("ORB — Error", content)

    data_15min['MA_50'] = data_15min['Close'].rolling(50).mean()
    data_15min['MA_200'] = data_15min['Close'].rolling(200).mean()
    ma_50 = data_15min['MA_50'].iloc[-1]
    ma_200 = data_15min['MA_200'].iloc[-1]

    if pd.isna(ma_50) or pd.isna(ma_200):
        content = """
        <div class="card">
            <span class="status status-error">ERROR</span>
            <p class="message">Not enough data for MA calculation</p>
        </div>
        """
        return base_html("ORB — Error", content)

    trend = "BULLISH" if ma_50 > ma_200 else "BEARISH"
    trend_color = "long" if trend == "BULLISH" else "short"

    data_1min = ticker.history(period="1d", interval="1m")

    if len(data_1min) == 0:
        content = f"""
        <div class="card">
            <span class="status status-waiting">NO DATA</span>
            <p class="message">No 1min data available</p>
            <div class="divider"></div>
            <div class="grid">
                <div class="grid-item">
                    <div class="label">Trend</div>
                    <div class="value {trend_color}">{trend}</div>
                </div>
                <div class="grid-item">
                    <div class="label">MA Gap</div>
                    <div class="value">{round(abs(ma_50 - ma_200), 2)}</div>
                </div>
            </div>
        </div>
        """
        return base_html("ORB — No Data", content)

    data_1min.index = data_1min.index.tz_convert(et)
    candles = []
    for idx, row in data_1min.iterrows():
        candles.append({
            "time": idx.strftime("%H:%M"),
            "open": row['Open'],
            "high": row['High'],
            "low": row['Low'],
            "close": row['Close']
        })

    current_price = round(data_1min['Close'].iloc[-1], 2)
    or_candles = [c for c in candles if 930 <= int(c['time'].replace(':', '')) <= 944]

    # Waiting for range
    if len(or_candles) == 0:
        content = f"""
        <div class="card">
            <span class="status status-waiting">WAITING</span>
            <p class="message">Waiting for opening range (9:30-9:44 ET)</p>
            <div class="divider"></div>
            <div class="grid">
                <div class="grid-item">
                    <div class="label">Trend</div>
                    <div class="value {trend_color}">{trend}</div>
                </div>
                <div class="grid-item">
                    <div class="label">Price</div>
                    <div class="value">{current_price}</div>
                </div>
            </div>
        </div>
        """
        return base_html("ORB — Waiting", content)

    # Range forming
    if len(or_candles) < 15 and now.hour == 9 and now.minute < 45:
        content = f"""
        <div class="card">
            <span class="status status-waiting">FORMING</span>
            <p class="message">Opening range forming — {len(or_candles)}/15 candles</p>
            <div class="score-bar">
                <div class="score-fill" style="width: {int(len(or_candles)/15*100)}%; background: #818cf8;"></div>
            </div>
            <div class="divider"></div>
            <div class="grid">
                <div class="grid-item">
                    <div class="label">Trend</div>
                    <div class="value {trend_color}">{trend}</div>
                </div>
                <div class="grid-item">
                    <div class="label">Price</div>
                    <div class="value">{current_price}</div>
                </div>
            </div>
        </div>
        """
        return base_html("ORB — Forming", content)

    range_high = round(max(c['high'] for c in or_candles), 2)
    range_low = round(min(c['low'] for c in or_candles), 2)
    range_size = round(range_high - range_low, 2)

    # Range too wide
    if range_size > 80:
        content = f"""
        <div class="card">
            <span class="status status-skip">NO TRADE</span>
            <p class="message">Range too wide — Skipping today</p>
            <div class="divider"></div>
            <div class="grid">
                <div class="grid-item">
                    <div class="label">Range Size</div>
                    <div class="value short">{range_size} pts</div>
                </div>
                <div class="grid-item">
                    <div class="label">Max Allowed</div>
                    <div class="value">80 pts</div>
                </div>
                <div class="grid-item">
                    <div class="label">Range High</div>
                    <div class="value">{range_high}</div>
                </div>
                <div class="grid-item">
                    <div class="label">Range Low</div>
                    <div class="value">{range_low}</div>
                </div>
            </div>
        </div>
        """
        return base_html("ORB — No Trade", content)

    # Run scan
    result = model.scan(candles, ma_50, ma_200, today)

    # No breakout yet
    if result is None:
        if current_price > range_high:
            price_msg = "Price ABOVE range — Waiting for FVG"
            price_color = "long"
        elif current_price < range_low:
            price_msg = "Price BELOW range — Waiting for FVG"
            price_color = "short"
        else:
            price_msg = "Price INSIDE range — No breakout"
            price_color = ""

        range_label = "Sweet Spot ✓" if 30 <= range_size <= 45 else f"{range_size} pts"

        content = f"""
        <div class="card">
            <span class="status status-scanning">SCANNING</span>
            <p class="message">{price_msg}</p>
            <div class="divider"></div>
            <div class="grid">
                <div class="grid-item">
                    <div class="label">Price</div>
                    <div class="value {price_color}">{current_price}</div>
                </div>
                <div class="grid-item">
                    <div class="label">Trend</div>
                    <div class="value {trend_color}">{trend}</div>
                </div>
                <div class="grid-item">
                    <div class="label">Range High</div>
                    <div class="value">{range_high}</div>
                </div>
                <div class="grid-item">
                    <div class="label">Range Low</div>
                    <div class="value">{range_low}</div>
                </div>
                <div class="grid-item">
                    <div class="label">Range Size</div>
                    <div class="value">{range_label}</div>
                </div>
                <div class="grid-item">
                    <div class="label">Day</div>
                    <div class="value">{day_name}</div>
                </div>
            </div>
        </div>
        """
        return base_html("ORB — Scanning", content)

    # Signal found
    pred = result['prediction']
    direction = result['direction']
    dir_color = "long" if direction == "LONG" else "short"
    score = pred['score']
    score_pct = min(int(score / 11 * 100), 100)
    score_color = "#4ade80" if score >= 7 else "#fbbf24" if score >= 5 else "#f87171"

    if pred['take_trade']:
        status_class = "status-trade"
        status_label = "TRADE"
        title = f"ORB — {pred['confidence']} {direction}"
        msg = f"{pred['confidence']} confidence {direction} — TAKE TRADE"
    else:
        status_class = "status-skip"
        status_label = "SKIP"
        title = "ORB — Skip"
        msg = f"Score too low ({score}) — SKIP THIS TRADE"

    reasons_html = ""
    for r in pred['reasons']:
        reasons_html += f'<div class="reason">{r}</div>'

    content = f"""
    <div class="card">
        <span class="status {status_class}">{status_label}</span>
        <p class="message">{msg}</p>
        <div class="divider"></div>
        <div class="grid">
            <div class="grid-item">
                <div class="label">Direction</div>
                <div class="value {dir_color}">{"📈 " + direction if direction == "LONG" else "📉 " + direction}</div>
            </div>
            <div class="grid-item">
                <div class="label">Score</div>
                <div class="value" style="color: {score_color}">{score}/11</div>
            </div>
        </div>
        <div class="score-bar">
            <div class="score-fill" style="width: {score_pct}%; background: {score_color};"></div>
        </div>
    </div>

    <div class="card">
        <div class="grid">
            <div class="grid-item">
                <div class="label">Entry</div>
                <div class="value {dir_color}">{result['entry']}</div>
            </div>
            <div class="grid-item">
                <div class="label">Stop Loss</div>
                <div class="value short">{result['stop']}</div>
            </div>
            <div class="grid-item">
                <div class="label">Target (1R)</div>
                <div class="value long">{result['target']}</div>
            </div>
            <div class="grid-item">
                <div class="label">Current Price</div>
                <div class="value">{current_price}</div>
            </div>
        </div>
    </div>

    <div class="card">
        <div class="grid">
            <div class="grid-item">
                <div class="label">Range High</div>
                <div class="value">{result['range_high']}</div>
            </div>
            <div class="grid-item">
                <div class="label">Range Low</div>
                <div class="value">{result['range_low']}</div>
            </div>
            <div class="grid-item">
                <div class="label">Range Size</div>
                <div class="value">{result['range_size']} pts</div>
            </div>
            <div class="grid-item">
                <div class="label">FVG Size</div>
                <div class="value">{result['fvg_size']} pts</div>
            </div>
            <div class="grid-item">
                <div class="label">Breakout Speed</div>
                <div class="value">{result['candles_to_break']} candles</div>
            </div>
            <div class="grid-item">
                <div class="label">Trend</div>
                <div class="value {trend_color}">{trend}</div>
            </div>
        </div>
    </div>

    <div class="card">
        <div class="label" style="margin-bottom: 10px;">REASONS</div>
        {reasons_html}
    </div>
    """
    return base_html(title, content)