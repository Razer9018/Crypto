import os
import time
import json
import urllib.request
import requests
from datetime import datetime

# ─── Config ───────────────────────────────────────────────────────────────────
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_CRYPTO", "")
SCAN_EVERY      = 900   # alle 15 Minuten
MIN_SCORE       = 7     # mindestens 7/10 Punkte
MAX_SIGNALS     = 3     # max 3 Signale pro Scan
HEBEL           = 5     # 5x Hebel

TOP_50_CRYPTOS = [
    ("BTC-USD",   "Bitcoin"),
    ("ETH-USD",   "Ethereum"),
    ("BNB-USD",   "BNB"),
    ("SOL-USD",   "Solana"),
    ("XRP-USD",   "XRP"),
    ("ADA-USD",   "Cardano"),
    ("AVAX-USD",  "Avalanche"),
    ("DOGE-USD",  "Dogecoin"),
    ("DOT-USD",   "Polkadot"),
    ("MATIC-USD", "Polygon"),
    ("LTC-USD",   "Litecoin"),
    ("LINK-USD",  "Chainlink"),
    ("ATOM-USD",  "Cosmos"),
    ("XLM-USD",   "Stellar"),
    ("BCH-USD",   "Bitcoin Cash"),
    ("ALGO-USD",  "Algorand"),
    ("FIL-USD",   "Filecoin"),
    ("ICP-USD",   "Internet Computer"),
    ("APT-USD",   "Aptos"),
    ("NEAR-USD",  "NEAR Protocol"),
    ("AAVE-USD",  "Aave"),
    ("MKR-USD",   "Maker"),
    ("SNX-USD",   "Synthetix"),
    ("CRV-USD",   "Curve"),
    ("LDO-USD",   "Lido"),
    ("INJ-USD",   "Injective"),
    ("EGLD-USD",  "MultiversX"),
    ("FLOW-USD",  "Flow"),
    ("SAND-USD",  "The Sandbox"),
    ("MANA-USD",  "Decentraland"),
    ("AXS-USD",   "Axie Infinity"),
    ("THETA-USD", "Theta"),
    ("XTZ-USD",   "Tezos"),
    ("EOS-USD",   "EOS"),
    ("ENJ-USD",   "Enjin Coin"),
    ("CHZ-USD",   "Chiliz"),
    ("OP-USD",    "Optimism"),
    ("GRT-USD",   "The Graph"),
    ("COMP-USD",  "Compound"),
    ("ZEC-USD",   "Zcash"),
    ("DASH-USD",  "Dash"),
    ("BAT-USD",   "Basic Attention"),
    ("ZIL-USD",   "Zilliqa"),
    ("1INCH-USD", "1inch"),
    ("ICX-USD",   "ICON"),
    ("ONT-USD",   "Ontology"),
    ("VET-USD",   "VeChain"),
    ("STX-USD",   "Stacks"),
    ("SHIB-USD",  "Shiba Inu"),
    ("DGB-USD",   "DigiByte"),
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
        candles = []
        for i in range(len(times)):
            o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
            vol = q.get("volume", [0]*len(times))[i] or 0
            if o and h and l and c:
                candles.append({"time": times[i], "open": o, "high": h, "low": l, "close": c, "volume": vol})
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

def rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains = losses = 0
    for i in range(1, period + 1):
        d = closes[i] - closes[i-1]
        if d > 0: gains  += d
        else:     losses -= d
    ag = gains / period
    al = losses / period
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i-1]
        ag = (ag * (period-1) + max(d, 0))  / period
        al = (al * (period-1) + max(-d, 0)) / period
    return 100 - 100 / (1 + ag / al) if al != 0 else 100

def macd_full(closes):
    """Gibt MACD Linie, Signal Linie und Histogram zurück"""
    if len(closes) < 35:
        return None, None, None
    e12 = ema(closes, 12)
    e26 = ema(closes, 26)
    if not e12 or not e26:
        return None, None, None
    macd_line = e12 - e26
    # Signal = 9 EMA des MACD (vereinfacht)
    macd_values = []
    k = 2 / (26 + 1)
    e = sum(closes[:26]) / 26
    e12_val = sum(closes[:12]) / 12
    for i in range(26, len(closes)):
        e  = closes[i] * k + e * (1 - k)
        k12 = 2 / (12 + 1)
        if i >= 12:
            e12_val = closes[i] * k12 + e12_val * (1 - k12)
        macd_values.append(e12_val - e)
    if len(macd_values) < 9:
        return macd_line, None, None
    signal = sum(macd_values[-9:]) / 9
    histogram = macd_line - signal
    return macd_line, signal, histogram

def bollinger(closes, period=20, mult=2):
    if len(closes) < period:
        return None, None, None
    sl   = closes[-period:]
    mean = sum(sl) / period
    std  = (sum((x - mean) ** 2 for x in sl) / period) ** 0.5
    return mean + mult * std, mean, mean - mult * std

def rsi_divergence(candles, rsi_values, period=5):
    """
    Bullische Divergenz: Kurs macht tieferes Tief, RSI macht höheres Tief
    Bärische Divergenz: Kurs macht höheres Hoch, RSI macht tieferes Hoch
    """
    if len(candles) < period * 2 or len(rsi_values) < period * 2:
        return None
    closes = [c["close"] for c in candles]
    # Letzter Bereich vs vorheriger Bereich
    curr_close = min(closes[-period:])
    prev_close = min(closes[-period*2:-period])
    curr_rsi   = min(r for r in rsi_values[-period:] if r)
    prev_rsi   = min(r for r in rsi_values[-period*2:-period] if r)

    if curr_close < prev_close and curr_rsi > prev_rsi:
        return "bullish"  # Bullische Divergenz → BUY Signal
    curr_close_h = max(closes[-period:])
    prev_close_h = max(closes[-period*2:-period])
    curr_rsi_h   = max(r for r in rsi_values[-period:] if r)
    prev_rsi_h   = max(r for r in rsi_values[-period*2:-period] if r)
    if curr_close_h > prev_close_h and curr_rsi_h < prev_rsi_h:
        return "bearish"  # Bärische Divergenz → SELL Signal
    return None

def volume_breakout(candles, period=20):
    """Volumen Ausbruch: aktuelles Volumen > 1.5x Durchschnitt"""
    if len(candles) < period + 1:
        return False, 0
    avg_vol = sum(c["volume"] for c in candles[-period-1:-1]) / period
    curr_vol = candles[-1]["volume"]
    if avg_vol == 0:
        return False, 0
    ratio = curr_vol / avg_vol
    return ratio >= 1.5, ratio

def ema_confluence(closes):
    """
    EMA Confluence: EMA20 > EMA50 > EMA200 = starker Aufwärtstrend
    EMA20 < EMA50 < EMA200 = starker Abwärtstrend
    """
    e20  = ema(closes, 20)
    e50  = ema(closes, 50)
    e200 = ema(closes, 200) if len(closes) >= 200 else None
    price = closes[-1]

    if not e20 or not e50:
        return None, None

    if e200:
        bull = e20 > e50 > e200 and price > e20
        bear = e20 < e50 < e200 and price < e20
    else:
        bull = e20 > e50 and price > e20
        bear = e20 < e50 and price < e20

    if bull: return "bull", {"ema20": e20, "ema50": e50, "ema200": e200}
    if bear: return "bear", {"ema20": e20, "ema50": e50, "ema200": e200}
    return "neutral", {"ema20": e20, "ema50": e50, "ema200": e200}

def momentum_score(closes, candles):
    """
    Berechnet Momentum Score (0-10):
    - EMA Confluence
    - MACD Crossover
    - RSI Bereich
    - RSI Divergenz
    - Volumen Ausbruch
    - Preis über/unter BB
    """
    score_bull = 0
    score_bear = 0
    details    = {}

    # 1. EMA Confluence (2 Punkte — stärkster Indikator)
    ema_trend, ema_vals = ema_confluence(closes)
    if ema_trend == "bull":
        score_bull += 2
        details["EMA Confluence"] = "✅ EMA20 > EMA50 > EMA200 (Aufwärtstrend)"
    elif ema_trend == "bear":
        score_bear += 2
        details["EMA Confluence"] = "✅ EMA20 < EMA50 < EMA200 (Abwärtstrend)"
    else:
        details["EMA Confluence"] = "❌ Kein klarer Trend"

    # 2. MACD Crossover (2 Punkte)
    macd_line, signal_line, histogram = macd_full(closes)
    if macd_line and signal_line:
        if macd_line > signal_line and histogram and histogram > 0:
            score_bull += 2
            details["MACD Crossover"] = f"✅ MACD bullish ({macd_line:.4f} > Signal)"
        elif macd_line < signal_line and histogram and histogram < 0:
            score_bear += 2
            details["MACD Crossover"] = f"✅ MACD bearish ({macd_line:.4f} < Signal)"
        else:
            details["MACD Crossover"] = "❌ Kein klarer MACD Crossover"
    else:
        details["MACD Crossover"] = "❌ Nicht genug Daten"

    # 3. RSI Zone (1 Punkt)
    rsi_vals = []
    for i in range(15, len(closes)):
        rsi_vals.append(rsi(closes[:i+1]))
    rsi_current = rsi(closes)
    if rsi_current:
        if 40 <= rsi_current <= 60:
            details["RSI"] = f"⚠️ RSI neutral ({rsi_current:.1f})"
        elif rsi_current < 35:
            score_bull += 1
            details["RSI"] = f"✅ RSI überverkauft ({rsi_current:.1f}) → BUY"
        elif rsi_current > 65:
            score_bear += 1
            details["RSI"] = f"✅ RSI überkauft ({rsi_current:.1f}) → SELL"
        else:
            details["RSI"] = f"⚠️ RSI ({rsi_current:.1f}) — neutral"
    else:
        details["RSI"] = "❌ RSI nicht berechenbar"

    # 4. RSI Divergenz (2 Punkte — sehr starkes Signal)
    if len(rsi_vals) >= 10:
        div = rsi_divergence(candles, rsi_vals)
        if div == "bullish":
            score_bull += 2
            details["RSI Divergenz"] = "✅ Bullische Divergenz erkannt!"
        elif div == "bearish":
            score_bear += 2
            details["RSI Divergenz"] = "✅ Bärische Divergenz erkannt!"
        else:
            details["RSI Divergenz"] = "❌ Keine Divergenz"
    else:
        details["RSI Divergenz"] = "❌ Nicht genug Daten"

    # 5. Volumen Ausbruch (2 Punkte)
    vol_break, vol_ratio = volume_breakout(candles)
    if vol_break:
        if score_bull >= score_bear:
            score_bull += 2
        else:
            score_bear += 2
        details["Volumen Ausbruch"] = f"✅ Volumen {vol_ratio:.1f}x über Durchschnitt!"
    else:
        details["Volumen Ausbruch"] = f"❌ Normales Volumen ({vol_ratio:.1f}x)"

    # 6. Bollinger Bands (1 Punkt)
    bb_u, bb_m, bb_l = bollinger(closes)
    price = closes[-1]
    if bb_l and price <= bb_l * 1.001:
        score_bull += 1
        details["Bollinger Bands"] = f"✅ Preis am unteren Band (${price:.4f})"
    elif bb_u and price >= bb_u * 0.999:
        score_bear += 1
        details["Bollinger Bands"] = f"✅ Preis am oberen Band (${price:.4f})"
    else:
        bb_pct = ((price - bb_l) / (bb_u - bb_l) * 100) if bb_u and bb_l else 50
        details["Bollinger Bands"] = f"❌ Preis mittig in BB ({bb_pct:.0f}%)"

    return score_bull, score_bear, details, rsi_current, macd_line

# ─── Multi-Timeframe Analyse ──────────────────────────────────────────────────
def analyze_coin(symbol, name):
    timeframes = [("15m", "M15", "7d"), ("1h", "H1", "7d"), ("4h", "H4", "30d")]
    tf_results = {}

    for interval, label, period in timeframes:
        candles = get_candles(symbol, interval, period)
        if not candles or len(candles) < 50:
            continue
        closes = [c["close"] for c in candles]
        bull, bear, details, rsi_v, macd_v = momentum_score(closes, candles)
        direction = "BUY" if bull > bear else "SELL" if bear > bull else "NEUTRAL"
        tf_results[label] = {
            "direction": direction, "bull": bull, "bear": bear,
            "details": details, "rsi": rsi_v, "macd": macd_v,
            "candles": candles, "closes": closes
        }

    if len(tf_results) < 3:
        return None

    # Alle 3 Timeframes müssen übereinstimmen
    directions = [tf_results[tf]["direction"] for tf in tf_results]
    if directions.count("BUY") == 3:
        final_dir = "BUY"
    elif directions.count("SELL") == 3:
        final_dir = "SELL"
    else:
        return None

    # Gesamtscore (H4 zählt doppelt da wichtigster TF)
    total_bull = (tf_results["M15"]["bull"] +
                  tf_results["H1"]["bull"] +
                  tf_results["H4"]["bull"] * 2)
    total_bear = (tf_results["M15"]["bear"] +
                  tf_results["H1"]["bear"] +
                  tf_results["H4"]["bear"] * 2)
    total = total_bull if final_dir == "BUY" else total_bear

    # SL/TP auf H1 Basis
    h1_candles = tf_results["H1"]["candles"]
    price      = h1_candles[-1]["close"]
    recent     = h1_candles[-20:]
    puffer     = price * 0.005

    if final_dir == "BUY":
        sl      = min(c["low"] for c in recent) - puffer
        sl_dist = max(price - sl, price * 0.01)
    else:
        sl      = max(c["high"] for c in recent) + puffer
        sl_dist = max(sl - price, price * 0.01)

    sl_pct = (sl_dist / price) * 100
    crv    = 5 if sl_pct <= 2 else 4 if sl_pct <= 4 else 3

    tp3 = price + sl_dist * 3 if final_dir == "BUY" else price - sl_dist * 3
    tp4 = price + sl_dist * 4 if final_dir == "BUY" else price - sl_dist * 4
    tp5 = price + sl_dist * 5 if final_dir == "BUY" else price - sl_dist * 5

    # Gewinn Rechner
    profits = {}
    for kapital in [50, 100, 200, 500]:
        risiko = kapital * (sl_pct / 100) * HEBEL
        profits[kapital] = {"risiko": risiko, "gewinn": risiko * crv}

    # RSI Filter — kein BUY wenn RSI > 70, kein SELL wenn RSI < 30
    h1_rsi = tf_results["H1"]["rsi"]
    if h1_rsi:
        if final_dir == "BUY" and h1_rsi > 70:
            print(f"   {name}: RSI {h1_rsi:.1f} überkauft → BUY blockiert!")
            return None
        if final_dir == "SELL" and h1_rsi < 30:
            print(f"   {name}: RSI {h1_rsi:.1f} überverkauft → SELL blockiert!")
            return None

    # EMA Trend Filter — niemals gegen den großen Trend traden
    # BUY nur wenn H4 EMA nicht bearish (EMA20 < EMA50 < EMA200)
    # SELL nur wenn H4 EMA nicht bullish (EMA20 > EMA50 > EMA200)
    h4_details = tf_results["H4"]["details"]
    h4_ema_text = h4_details.get("EMA Confluence", "")
    if final_dir == "BUY" and "Abwärtstrend" in h4_ema_text:
        print(f"   {name}: H4 EMA Abwärtstrend → BUY gegen Trend blockiert!")
        return None
    if final_dir == "SELL" and "Aufwärtstrend" in h4_ema_text:
        print(f"   {name}: H4 EMA Aufwärtstrend → SELL gegen Trend blockiert!")
        return None

    return {
        "symbol": symbol, "name": name, "direction": final_dir,
        "score": total, "price": price,
        "sl": sl, "tp3": tp3, "tp4": tp4, "tp5": tp5, "crv": crv,
        "sl_dist": sl_dist, "sl_pct": sl_pct, "profits": profits,
        "tf_results": {tf: {"direction": tf_results[tf]["direction"],
                            "bull": tf_results[tf]["bull"],
                            "bear": tf_results[tf]["bear"],
                            "rsi": tf_results[tf]["rsi"],
                            "macd": tf_results[tf]["macd"],
                            "details": tf_results[tf]["details"]}
                       for tf in tf_results},
    }

# ─── Discord Alert ────────────────────────────────────────────────────────────
def send_discord(r):
    if not DISCORD_WEBHOOK:
        print("Kein Webhook!")
        return

    emoji = "🟢" if r["direction"] == "BUY" else "🔴"
    color = 0x00c853 if r["direction"] == "BUY" else 0xd50000

    # Timeframe Übersicht
    tf_text = ""
    for tf in ["M15", "H1", "H4"]:
        if tf in r["tf_results"]:
            d = r["tf_results"][tf]
            arrow = "📈" if d["direction"] == "BUY" else "📉"
            rsi_v = f"{d['rsi']:.1f}" if d["rsi"] else "N/A"
            macd_arrow = "▲" if d["macd"] and d["macd"] > 0 else "▼"
            weight = " (2x)" if tf == "H4" else ""
            tf_text += f"{arrow} **{tf}{weight}**: {d['bull']} Bull / {d['bear']} Bear | RSI: {rsi_v} | MACD: {macd_arrow}\n"

    # Beste Indikator-Details von H4
    h4_details = r["tf_results"].get("H4", {}).get("details", {})
    detail_text = "\n".join(f"{v}" for v in list(h4_details.values())[:4])

    # TP Übersicht
    tp_text = (
        f"3:1 → ${r['tp3']:.4f}\n"
        f"4:1 → ${r['tp4']:.4f}\n"
        f"5:1 → ${r['tp5']:.4f}"
    )

    # Gewinn Rechner
    p = r["profits"]
    profit_text = (
        f"💼 $50  → Risiko: ${p[50]['risiko']:.2f} | Gewinn: ${p[50]['gewinn']:.2f}\n"
        f"💼 $100 → Risiko: ${p[100]['risiko']:.2f} | Gewinn: ${p[100]['gewinn']:.2f}\n"
        f"💼 $200 → Risiko: ${p[200]['risiko']:.2f} | Gewinn: ${p[200]['gewinn']:.2f}\n"
        f"💼 $500 → Risiko: ${p[500]['risiko']:.2f} | Gewinn: ${p[500]['gewinn']:.2f}\n"
        f"📊 SL: -{r['sl_pct']*HEBEL:.1f}% | TP: +{r['sl_pct']*HEBEL*r['crv']:.1f}% (5x Hebel)"
    )

    embed = {"embeds": [{"title": f"{emoji} {r['name']} ({r['symbol']}) — {r['direction']} Signal",
        "color": color,
        "description": (
            f"**Starkes {r['direction']} Signal auf allen 3 Timeframes!**\n"
            f"Score: **{r['score']} Punkte** | CRV: **{r['crv']}:1**"
        ),
        "fields": [
            {"name": "📊 Multi-Timeframe Analyse",    "value": tf_text,       "inline": False},
            {"name": "🔍 H4 Indikator Details",       "value": detail_text,   "inline": False},
            {"name": "💰 Einstieg",                   "value": f"${r['price']:.4f}", "inline": True},
            {"name": "🛑 Stop Loss",                  "value": f"${r['sl']:.4f} (-{r['sl_pct']:.1f}%)", "inline": True},
            {"name": "🎯 Take Profits",               "value": tp_text,       "inline": False},
            {"name": "💵 Gewinn/Verlust (5x Hebel)",  "value": profit_text,   "inline": False},
            {"name": "⚠️ Hinweis",                   "value": "Kein Finanzrat. Eigenes Risikomanagement verwenden.", "inline": False},
        ],
        "footer": {"text": "Crypto Signal Bot • EMA + MACD + RSI Divergenz + Volumen • M15+H1+H4"},
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }]}
    try:
        res = requests.post(DISCORD_WEBHOOK, json=embed, timeout=10)
        print(f"Discord: {r['name']} {r['direction']} Score:{r['score']} ({res.status_code})")
        time.sleep(1.5)
    except Exception as e:
        print(f"Discord Fehler: {e}")

# ─── Hauptloop ────────────────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  Crypto Signal Bot — Profi Strategie")
    print(f"  {len(TOP_50_CRYPTOS)} Coins | M15+H1+H4 | Min Score: {MIN_SCORE}")
    print(f"  EMA Confluence + MACD Crossover + RSI Divergenz + Volumen")
    print("=" * 55)

    last_signals = {}

    while True:
        now = datetime.utcnow().strftime("%H:%M:%S UTC")
        print(f"\n[{now}] Scanne {len(TOP_50_CRYPTOS)} Coins...")
        strong = []

        for symbol, name in TOP_50_CRYPTOS:
            try:
                print(f"   {name}...", end=" ", flush=True)
                result = analyze_coin(symbol, name)
                if result and result["score"] >= MIN_SCORE:
                    sig_key = f"{symbol}_{result['direction']}"
                    if sig_key != last_signals.get(symbol):
                        strong.append(result)
                        last_signals[symbol] = sig_key
                        print(f"SIGNAL! {result['direction']} Score:{result['score']}")
                    else:
                        print(f"bereits gesendet")
                else:
                    score = result["score"] if result else 0
                    print(f"Score {score} — zu schwach")
                time.sleep(2)
            except Exception as e:
                print(f"Fehler: {e}")

        # Nur Top MAX_SIGNALS senden
        if strong:
            strong.sort(key=lambda x: x["score"], reverse=True)
            top = strong[:MAX_SIGNALS]
            print(f"\n{len(top)} starke Signale! Sende Discord Alerts...")
            for r in top:
                send_discord(r)
        else:
            print("\nKeine starken Signale gefunden.")

        print(f"\nNaechster Scan in {SCAN_EVERY // 60} Minuten...")
        time.sleep(SCAN_EVERY)

if __name__ == "__main__":
    main()
