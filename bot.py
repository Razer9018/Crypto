import os
import time
import json
import urllib.request
from datetime import datetime

# ─── Config ───────────────────────────────────────────────────────────────────
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_CRYPTO", "")
SCAN_EVERY      = 900   # alle 15 Minuten
MIN_SCORE       = 7     # mindestens 7/9 für Alert

# Top 50 Kryptos (Yahoo Finance Symbole)
TOP_50_CRYPTOS = [
    ("BTC-USD",  "Bitcoin"),
    ("ETH-USD",  "Ethereum"),
    ("BNB-USD",  "BNB"),
    ("SOL-USD",  "Solana"),
    ("XRP-USD",  "XRP"),
    ("ADA-USD",  "Cardano"),
    ("AVAX-USD", "Avalanche"),
    ("DOGE-USD", "Dogecoin"),
    ("DOT-USD",  "Polkadot"),
    ("MATIC-USD","Polygon"),
    ("SHIB-USD", "Shiba Inu"),
    ("LTC-USD",  "Litecoin"),
    ("UNI7083-USD", "Uniswap"),
    ("LINK-USD", "Chainlink"),
    ("ATOM-USD", "Cosmos"),
    ("XLM-USD",  "Stellar"),
    ("BCH-USD",  "Bitcoin Cash"),
    ("ALGO-USD", "Algorand"),
    ("VET-USD",  "VeChain"),
    ("FIL-USD",  "Filecoin"),
    ("ICP-USD",  "Internet Computer"),
    ("APT-USD",  "Aptos"),
    ("ARB11841-USD", "Arbitrum"),
    ("OP-USD",   "Optimism"),
    ("NEAR-USD", "NEAR Protocol"),
    ("GRT6719-USD",  "The Graph"),
    ("AAVE-USD", "Aave"),
    ("MKR-USD",  "Maker"),
    ("SNX-USD",  "Synthetix"),
    ("CRV-USD",  "Curve"),
    ("LDO-USD",  "Lido"),
    ("IMX10603-USD", "Immutable"),
    ("INJ-USD",  "Injective"),
    ("SUI20947-USD",  "Sui"),
    ("SEI-USD",  "Sei"),
    ("TIA22861-USD",  "Celestia"),
    ("JUP29210-USD",  "Jupiter"),
    ("PYTH-USD", "Pyth Network"),
    ("STX4847-USD",  "Stacks"),
    ("EGLD-USD", "MultiversX"),
    ("FLOW-USD", "Flow"),
    ("SAND-USD", "The Sandbox"),
    ("MANA-USD", "Decentraland"),
    ("AXS-USD",  "Axie Infinity"),
    ("THETA-USD","Theta"),
    ("XTZ-USD",  "Tezos"),
    ("EOS-USD",  "EOS"),
    ("ZIL-USD",  "Zilliqa"),
    ("ENJ-USD",  "Enjin Coin"),
    ("CHZ-USD",  "Chiliz"),
]

TIMEFRAMES = [
    ("15m", "M15"),
    ("1h",  "H1"),
    ("4h",  "H4"),
]

# ─── Daten holen ──────────────────────────────────────────────────────────────
def get_candles(symbol, interval, period="7d"):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range={period}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        result = data["chart"]["result"][0]
        times  = result["timestamp"]
        q      = result["indicators"]["quote"][0]
        o, h, l, c, v = q["open"], q["high"], q["low"], q["close"], q.get("volume", [0]*len(times))
        candles = []
        for i in range(len(times)):
            if o[i] and h[i] and l[i] and c[i]:
                candles.append({
                    "time": times[i], "open": o[i], "high": h[i],
                    "low": l[i], "close": c[i], "volume": v[i] or 0
                })
        return candles
    except:
        return None

# ─── Indikatoren ──────────────────────────────────────────────────────────────
def ema(closes, period):
    if len(closes) < period:
        return None
    k   = 2 / (period + 1)
    val = sum(closes[:period]) / period
    for c in closes[period:]:
        val = c * k + val * (1 - k)
    return val

def sma(closes, period):
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period

def bollinger(closes, period=20, mult=2):
    if len(closes) < period:
        return None, None, None
    sl   = closes[-period:]
    mean = sum(sl) / period
    std  = (sum((x - mean) ** 2 for x in sl) / period) ** 0.5
    return mean + mult * std, mean, mean - mult * std

def macd(closes):
    e12 = ema(closes, 12)
    e26 = ema(closes, 26)
    if not e12 or not e26:
        return None, None
    m = e12 - e26
    # Signal line (9 EMA of MACD) — simplified
    return m, e12 - e26

def rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = 0, 0
    for i in range(1, period + 1):
        diff = closes[i] - closes[i-1]
        if diff > 0: gains  += diff
        else:        losses -= diff
    avg_gain = gains  / period
    avg_loss = losses / period
    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i-1]
        avg_gain = (avg_gain * (period-1) + max(diff, 0))  / period
        avg_loss = (avg_loss * (period-1) + max(-diff, 0)) / period
    if avg_loss == 0:
        return 100
    return 100 - 100 / (1 + avg_gain / avg_loss)

def atr(candles, period=14):
    if len(candles) < period + 1:
        return None
    trs = []
    for i in range(1, len(candles)):
        h, l, pc = candles[i]["high"], candles[i]["low"], candles[i-1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs[-period:]) / period

def volume_rising(candles, period=10):
    if len(candles) < period + 1:
        return False
    recent = sum(c["volume"] for c in candles[-5:])  / 5
    prev   = sum(c["volume"] for c in candles[-period:-5]) / (period - 5)
    return prev > 0 and recent > prev * 1.2

# ─── Kerzenmuster ─────────────────────────────────────────────────────────────
def bullish_candle_pattern(candles):
    if len(candles) < 3:
        return False, "—"
    c = candles[-1]
    body  = abs(c["close"] - c["open"])
    lower = min(c["open"], c["close"]) - c["low"]
    upper = c["high"] - max(c["open"], c["close"])
    # Hammer
    if body > 0 and lower >= body * 2 and upper <= body * 0.5:
        return True, "Hammer 🔨"
    # Bullish Engulfing
    prev = candles[-2]
    if (prev["close"] < prev["open"] and c["close"] > c["open"] and
            c["open"] < prev["close"] and c["close"] > prev["open"]):
        return True, "Bullish Engulfing 📈"
    # Morning Star
    c1, c2, c3 = candles[-3], candles[-2], candles[-1]
    b1 = abs(c1["close"] - c1["open"])
    b2 = abs(c2["close"] - c2["open"])
    b3 = abs(c3["close"] - c3["open"])
    if (c1["close"] < c1["open"] and b2 < b1 * 0.35 and
            c3["close"] > c3["open"] and b3 >= b1 * 0.5):
        return True, "Morning Star ⭐"
    return False, "—"

def bearish_candle_pattern(candles):
    if len(candles) < 3:
        return False, "—"
    c = candles[-1]
    body  = abs(c["close"] - c["open"])
    upper = c["high"] - max(c["open"], c["close"])
    lower = min(c["open"], c["close"]) - c["low"]
    # Inverted Hammer / Shooting Star
    if body > 0 and upper >= body * 2 and lower <= body * 0.5:
        return True, "Shooting Star 💫"
    # Bearish Engulfing
    prev = candles[-2]
    if (prev["close"] > prev["open"] and c["close"] < c["open"] and
            c["open"] > prev["close"] and c["close"] < prev["open"]):
        return True, "Bearish Engulfing 📉"
    # Evening Star
    c1, c2, c3 = candles[-3], candles[-2], candles[-1]
    b1 = abs(c1["close"] - c1["open"])
    b2 = abs(c2["close"] - c2["open"])
    b3 = abs(c3["close"] - c3["open"])
    if (c1["close"] > c1["open"] and b2 < b1 * 0.35 and
            c3["close"] < c3["open"] and b3 >= b1 * 0.5):
        return True, "Evening Star 🌙"
    return False, "—"

# ─── Einzelnen Timeframe analysieren ─────────────────────────────────────────
def analyze_timeframe(candles):
    if not candles or len(candles) < 50:
        return None
    closes = [c["close"] for c in candles]
    price  = closes[-1]

    # Indikatoren berechnen
    ema20_val  = ema(closes, 20)
    ema50_val  = ema(closes, 50)
    ema200_val = ema(closes, 200) if len(closes) >= 200 else None
    macd_val, _ = macd(closes)
    rsi_val    = rsi(closes)
    bb_u, bb_m, bb_l = bollinger(closes)
    vol_rising = volume_rising(candles)
    bull_pat, bull_name = bullish_candle_pattern(candles)
    bear_pat, bear_name = bearish_candle_pattern(candles)

    bull_signals = 0
    bear_signals = 0

    # EMA 20/50 Crossover
    if ema20_val and ema50_val:
        if ema20_val > ema50_val: bull_signals += 1
        else:                     bear_signals += 1

    # EMA 200 (Trend-Filter)
    if ema200_val:
        if price > ema200_val: bull_signals += 1
        else:                  bear_signals += 1

    # MACD
    if macd_val:
        if macd_val > 0: bull_signals += 1
        else:            bear_signals += 1

    # RSI
    if rsi_val:
        if rsi_val < 40:   bull_signals += 1
        elif rsi_val > 60: bear_signals += 1

    # Bollinger Bands
    if bb_l and bb_u:
        if price <= bb_l * 1.002:  bull_signals += 1
        elif price >= bb_u * 0.998: bear_signals += 1

    # Volumen
    if vol_rising:
        if bull_signals >= bear_signals: bull_signals += 1
        else:                            bear_signals += 1

    # Kerzenmuster
    if bull_pat: bull_signals += 1
    if bear_pat: bear_signals += 1

    direction = "BUY" if bull_signals > bear_signals else "SELL" if bear_signals > bull_signals else "NEUTRAL"

    return {
        "direction":   direction,
        "bull":        bull_signals,
        "bear":        bear_signals,
        "rsi":         rsi_val,
        "macd":        macd_val,
        "ema20":       ema20_val,
        "ema50":       ema50_val,
        "ema200":      ema200_val,
        "bb_upper":    bb_u,
        "bb_lower":    bb_l,
        "vol_rising":  vol_rising,
        "pattern":     bull_name if bull_pat else bear_name if bear_pat else "—",
        "price":       price,
    }

# ─── Multi-Timeframe Analyse ──────────────────────────────────────────────────
def analyze_coin(symbol, name):
    results = {}
    for interval, label in TIMEFRAMES:
        period = "30d" if interval in ["4h"] else "7d"
        candles = get_candles(symbol, interval, period)
        if candles:
            r = analyze_timeframe(candles)
            if r:
                results[label] = r

    if len(results) < 2:
        return None

    # Alle Timeframes müssen übereinstimmen
    directions = [results[tf]["direction"] for tf in results]
    if directions.count("BUY") == len(directions):
        final_dir = "BUY"
    elif directions.count("SELL") == len(directions):
        final_dir = "SELL"
    else:
        return None  # Kein klares Signal

    # Score = Summe aller Bull/Bear Signale über alle Timeframes
    total_bull = sum(results[tf]["bull"] for tf in results)
    total_bear = sum(results[tf]["bear"] for tf in results)
    score = total_bull if final_dir == "BUY" else total_bear

    # ATR für SL/TP
    candles_h1 = get_candles(symbol, "1h", "7d")
    atr_val = atr(candles_h1) if candles_h1 else None
    price   = list(results.values())[0]["price"]
    sl_dist = atr_val * 1.5 if atr_val else price * 0.02
    tp_dist = sl_dist * 3
    sl = price - sl_dist if final_dir == "BUY" else price + sl_dist
    tp = price + tp_dist if final_dir == "BUY" else price - tp_dist

    pattern = next((results[tf]["pattern"] for tf in results if results[tf]["pattern"] != "—"), "—")

    return {
        "symbol":    symbol,
        "name":      name,
        "direction": final_dir,
        "score":     score,
        "price":     price,
        "tp":        tp,
        "sl":        sl,
        "crv":       3,
        "pattern":   pattern,
        "timeframes": results,
    }

# ─── Discord Alert ────────────────────────────────────────────────────────────
def send_discord(signals):
    if not DISCORD_WEBHOOK:
        print("⚠️  Kein DISCORD_WEBHOOK_CRYPTO gesetzt!")
        return
    if not signals:
        return

    for r in signals:
        emoji = "🟢" if r["direction"] == "BUY" else "🔴"
        color = 0x00c853 if r["direction"] == "BUY" else 0xd50000

        # Timeframe Übersicht
        tf_text = ""
        for tf, data in r["timeframes"].items():
            arrow = "📈" if data["direction"] == "BUY" else "📉"
            tf_text += f"{arrow} **{tf}**: {data['direction']} (RSI: {data['rsi']:.0f} | MACD: {'▲' if data['macd'] and data['macd'] > 0 else '▼'})\n"

        embed = {"embeds": [{"title": f"{emoji} {r['name']} ({r['symbol']}) — {r['direction']} Signal",
            "color": color,
            "description": (
                f"**Starkes {r['direction']} Signal auf allen Timeframes!**\n"
                f"Muster: **{r['pattern']}**"
            ),
            "fields": [
                {"name": "📊 Timeframe Analyse", "value": tf_text,              "inline": False},
                {"name": "💰 Kurs",  "value": f"${r['price']:.4f}",             "inline": True},
                {"name": "🎯 TP",    "value": f"${r['tp']:.4f}",                "inline": True},
                {"name": "🛑 SL",    "value": f"${r['sl']:.4f}",                "inline": True},
                {"name": "📐 CRV",   "value": "3:1",                            "inline": True},
                {"name": "🔥 Score", "value": f"{r['score']} Punkte",           "inline": True},
                {"name": "⚠️ Hinweis", "value": "Kein Finanzrat. Eigenes Risikomanagement verwenden.", "inline": False},
            ],
            "footer": {"text": "Crypto Signal Bot • Multi-Timeframe Analyse • M15 + H1 + H4"},
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }]}
        try:
            import requests
            res = requests.post(DISCORD_WEBHOOK, json=embed, timeout=10)
            print(f"✅ Alert gesendet: {r['name']} {r['direction']} ({res.status_code})")
            time.sleep(1)  # Rate limit vermeiden
        except Exception as e:
            print(f"❌ Discord Fehler: {e}")

# ─── Hauptloop ────────────────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  🚀 Crypto Signal Bot gestartet")
    print(f"  📊 Überwacht: {len(TOP_50_CRYPTOS)} Kryptos")
    print(f"  ⏱  Timeframes: M15 + H1 + H4")
    print(f"  🔁 Scan alle {SCAN_EVERY // 60} Minuten")
    print("=" * 55)

    last_signals = {}

    while True:
        now = datetime.utcnow().strftime("%H:%M:%S UTC")
        print(f"\n🔍 [{now}] Scanne {len(TOP_50_CRYPTOS)} Kryptos...")
        strong_signals = []

        for symbol, name in TOP_50_CRYPTOS:
            try:
                print(f"   Prüfe {name}...", end=" ")
                result = analyze_coin(symbol, name)
                if result and result["score"] >= MIN_SCORE:
                    sig_key = f"{symbol}_{result['direction']}"
                    if sig_key != last_signals.get(symbol):
                        strong_signals.append(result)
                        last_signals[symbol] = sig_key
                        print(f"🚨 {result['direction']} Signal! Score: {result['score']}")
                    else:
                        print(f"⏭ Bereits gesendet")
                else:
                    if result:
                        print(f"→ {result['direction']} (Score: {result['score']}) — zu schwach")
                    else:
                        print("→ Kein klares Signal")
                time.sleep(2)  # API Rate limit
            except Exception as e:
                print(f"❌ Fehler: {e}")

        if strong_signals:
            print(f"\n🚨 {len(strong_signals)} starke Signale gefunden! Sende Discord Alerts...")
            send_discord(strong_signals)
        else:
            print("\n😴 Keine starken Signale gefunden.")

        print(f"\n⏳ Nächster Scan in {SCAN_EVERY // 60} Minuten...")
        time.sleep(SCAN_EVERY)

if __name__ == "__main__":
    main()
