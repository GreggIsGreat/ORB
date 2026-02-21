import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin


class ORBModel(BaseEstimator, ClassifierMixin):
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

    def detect_opening_range(self, candles_1min):
        opening = [c for c in candles_1min if 930 <= int(c['time'].replace(':', '')) <= 944]
        if len(opening) == 0:
            return None
        range_high = max(c['high'] for c in opening)
        range_low = min(c['low'] for c in opening)
        return {
            "range_high": range_high,
            "range_low": range_low,
            "range_size": range_high - range_low
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

    def scan(self, candles_1min, ma_50, ma_200, date):
        orb = self.detect_opening_range(candles_1min)
        if orb is None:
            return {"signal": False, "reason": "No opening range data"}

        trend = "LONG" if ma_50 > ma_200 else "SHORT"

        post_range = [c for c in candles_1min if int(c['time'].replace(':', '')) >= 945]
        if len(post_range) < 3:
            return {"signal": False, "reason": "Not enough post-range data"}

        for i in range(len(post_range) - 2):
            c1, c2, c3 = post_range[i], post_range[i + 1], post_range[i + 2]

            if trend == "LONG" and c2['close'] > orb['range_high']:
                fvg = self.detect_fvg(c1, c2, c3, "LONG")
                if fvg['valid']:
                    prediction = self.score_trade(orb['range_size'], fvg['size'], i + 1, "LONG", date)
                    return {
                        "signal": prediction['take_trade'],
                        "direction": "LONG",
                        "entry": fvg['entry'],
                        "stop": orb['range_low'],
                        "target": fvg['entry'] + (fvg['entry'] - orb['range_low']),
                        "range_high": orb['range_high'],
                        "range_low": orb['range_low'],
                        "range_size": round(orb['range_size'], 2),
                        "fvg_size": round(fvg['size'], 2),
                        "candles_to_break": i + 1,
                        "trend": f"BULLISH (50MA: {round(ma_50, 2)} > 200MA: {round(ma_200, 2)})",
                        "prediction": prediction
                    }

            if trend == "SHORT" and c2['close'] < orb['range_low']:
                fvg = self.detect_fvg(c1, c2, c3, "SHORT")
                if fvg['valid']:
                    prediction = self.score_trade(orb['range_size'], fvg['size'], i + 1, "SHORT", date)
                    return {
                        "signal": prediction['take_trade'],
                        "direction": "SHORT",
                        "entry": fvg['entry'],
                        "stop": orb['range_high'],
                        "target": fvg['entry'] - (orb['range_high'] - fvg['entry']),
                        "range_high": orb['range_high'],
                        "range_low": orb['range_low'],
                        "range_size": round(orb['range_size'], 2),
                        "fvg_size": round(fvg['size'], 2),
                        "candles_to_break": i + 1,
                        "trend": f"BEARISH (50MA: {round(ma_50, 2)} < 200MA: {round(ma_200, 2)})",
                        "prediction": prediction
                    }

        return {"signal": False, "reason": "No valid breakout + FVG found"}