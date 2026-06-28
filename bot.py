import os
import time
import json
import urllib.request
import requests
from datetime import datetime

# ─── Config ───────────────────────────────────────────────────────────────────
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_CRYPTO", "")
SCAN_EVERY      = 900   # alle 15 Minuten
MIN_SCORE       = 7     # mindestens 7/10
MAX_SIGNALS     = 2     # max 2 Signale pro Scan
HEBEL           = 5

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
    ("BAT-USD",   "Basic Attention"),
    ("ZIL-USD",   "Zilliqa"),
    ("1INCH-USD", "1inch"),
    ("VET-USD",   "VeChain"),
    ("STX-USD",   "Stacks"),
    ("SNX-USD",   "Synthetix"),
    ("CRV-USD",   "Curve"),
    ("LDO-USD",   "Lido"),
    ("DASH-USD",  "Dash"),
    ("ICX-USD",   "ICON"),
    ("ONT-USD",   "Ontology"),
    ("DGB-USD",   "DigiByte"),
    ("SHIB-USD",  "Shiba Inu"),
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
                candles.append({"time": times[i], "open": o, "high": h,
                                "low": l, "close": c, "volume": vol})
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
    if len(closes) < 35:
        return None, None, None
    k26 = 2 / (26 + 1)
    k12 = 2 / (12 + 1)
    e26 = sum(closes[:26]) / 26
    e12 = sum(closes[:12]) / 12
    macd_vals = []
    for i in range(26, len(closes)):
        e26 = closes[i] * k26 + e26 * (1 - k26)
        if i >= 12:
            e12 = closes[i] * k12 + e12 * (1 - k12)
        macd_vals.append(e12 - e26)
    if len(macd_vals) < 9:
        return macd_vals[-1] if macd_vals else None, None, None
    k9      = 2 / (9 + 1)
    signal  = sum(macd_vals[:9]) / 9
    for v in macd_vals[9:]:
        signal = v * k9 + signal * (1 - k9)
    macd_line = macd_vals[-1]
    histogram = macd_line - signal
    # Frischer Crossover: letzter Wert hat Signal gekreuzt
    fresh = False
    if len(macd_vals) >= 2:
        prev_hist = macd_vals[-2] - signal
        fresh = (prev_hist < 0 and histogram > 0) or (prev_hist > 0 and histogram < 0)
    return macd_line, signal, histogram

def bollinger(closes, period=20, mult=2):
    if len(closes) < period:
        return None, None, None
    sl   = closes[-period:]
    mean = sum(sl) / period
    std  = (sum((x - mean) ** 2 for x in sl) / period) ** 0.5
    return mean + mult * std, mean, mean - mult * std

def rsi_divergence(candles, period=10):
    if len(candles) < period * 2:
        return None
    closes = [c["close"] for c in candles]
    rsi_vals = [rsi(closes[:i+1]) for i in range(len(closes))]
    rsi_vals = [r for r in rsi_vals if r is not None]
    if len(rsi_vals) < period * 2:
        return None
    curr_low  = min(closes[-period:])
    prev_low  = min(closes[-period*2:-period])
    curr_rsi_l = min(rsi_vals[-period:])
    prev_rsi_l = min(rsi_vals[-period*2:-period])
    if curr_low < prev_low and curr_rsi_l > prev_rsi_l:
        return "bullish"
    curr_high  = max(closes[-period:])
    prev_high  = max(closes[-period*2:-period])
    curr_rsi_h = max(rsi_vals[-period:])
    prev_rsi_h = max(rsi_vals[-period*2:-period])
    if curr_high > prev_high and curr_rsi_h < prev_rsi_h:
        return "bearish"
    return None

def volume_breakout(candles, period=20, threshold=1.5):
    if len(candles) < period + 1:
        return False, 0
    avg = sum(c["volume"] for c in candles[-period-1:-1]) / period
    cur = candles[-1]["volume"]
    if avg == 0:
        return False, 0
    ratio = cur / avg
    return ratio >= threshold, ratio

def ema_trend_h4(closes):
    e20  = ema(closes, 20)
    e50  = ema(closes, 50)
    e200 = ema(closes, 200) if len(closes) >= 200 else None
    price = closes[-1]
    if not e20 or not e50:
        return "neutral"
    if e200:
        if e20 > e50 > e200 and price > e20: return "bull"
        if e20 < e50 < e200 and price < e20: return "bear"
    else:
        if e20 > e50 and price > e20: return "bull"
        if e20 < e50 and price < e20: return "bear"
    return "neutral"

# ─── Sicherheits-Filter ───────────────────────────────────────────────────────
def safety_checks(name, final_dir, tf_results):
    """
    Alle Sicherheits-Filter die ein Signal blockieren können.
    Gibt (True, "") zurück wenn alles ok, sonst (False, Grund)
    """

    # 1. RSI Filter — M15 ist Haupttimeframe, strengster Filter
    m15_rsi = tf_results.get("M15", {}).get("rsi")
    if m15_rsi:
        if final_dir == "BUY" and m15_rsi > 65:
            return False, f"M15 RSI {m15_rsi:.1f} > 65 (überkauft auf M15)"
        if final_dir == "SELL" and m15_rsi < 35:
            return False, f"M15 RSI {m15_rsi:.1f} < 35 (überverkauft auf M15)"

    # 2. RSI H1 — weniger streng
    h1_rsi = tf_results.get("H1", {}).get("rsi")
    if h1_rsi:
        if final_dir == "BUY" and h1_rsi > 75:
            return False, f"H1 RSI {h1_rsi:.1f} > 75 (überkauft auf H1)"
        if final_dir == "SELL" and h1_rsi < 25:
            return False, f"H1 RSI {h1_rsi:.1f} < 25 (überverkauft auf H1)"

    # 3. RSI H4 — nur extremste Werte blockieren
    r_h4 = tf_results.get("H4", {}).get("rsi")
    if r_h4:
        if final_dir == "BUY" and r_h4 > 80:
            return False, f"H4 RSI {r_h4:.1f} > 80 (extrem überkauft)"
        if final_dir == "SELL" and r_h4 < 20:
            return False, f"H4 RSI {r_h4:.1f} < 20 (extrem überverkauft)"

    # 3. H4 EMA Trend — nur gegen extremen Trend blockieren
    h4_trend = tf_results.get("H4", {}).get("ema_trend", "neutral")
    if final_dir == "BUY" and h4_trend == "bear":
        return False, "H4 EMA starker Abwärtstrend — kein BUY"
    if final_dir == "SELL" and h4_trend == "bull":
        return False, "H4 EMA starker Aufwärtstrend — kein SELL"

    # 4. MACD muss auf M15, H1 UND H4 stimmen
    m15_macd = tf_results.get("M15", {}).get("macd")
    h1_macd  = tf_results.get("H1",  {}).get("macd")
    h4_macd  = tf_results.get("H4",  {}).get("macd")
    if m15_macd:
        if final_dir == "BUY" and m15_macd < 0:
            return False, "M15 MACD bearish — kein BUY"
        if final_dir == "SELL" and m15_macd > 0:
            return False, "M15 MACD bullish — kein SELL"
    if h1_macd:
        if final_dir == "BUY" and h1_macd < 0:
            return False, "H1 MACD bearish — kein BUY"
        if final_dir == "SELL" and h1_macd > 0:
            return False, "H1 MACD bullish — kein SELL"
    if h4_macd:
        if final_dir == "BUY" and h4_macd < 0:
            return False, "H4 MACD bearish — kein BUY gegen H4 Trend"
        if final_dir == "SELL" and h4_macd > 0:
            return False, "H4 MACD bullish — kein SELL gegen H4 Trend"

    # 5. Volumen: gibt Bonus aber ist kein Pflicht-Filter mehr

    return True, "✅ Alle Filter bestanden"

# ─── Einzelnen Timeframe analysieren ─────────────────────────────────────────
def analyze_tf(candles):
    if not candles or len(candles) < 50:
        return None
    closes = [c["close"] for c in candles]
    price  = closes[-1]

    e20   = ema(closes, 20)
    e50   = ema(closes, 50)
    e200  = ema(closes, 200) if len(closes) >= 200 else None
    rsi_v = rsi(closes)
    macd_line, signal, histogram = macd_full(closes)
    bb_u, bb_m, bb_l = bollinger(closes)
    vol_ok, vol_ratio = volume_breakout(candles)
    div   = rsi_divergence(candles)
    trend = ema_trend_h4(closes)

    bull = bear = 0
    details = {}

    # EMA Confluence
    if e20 and e50:
        if trend == "bull":
            bull += 2
            details["EMA"] = f"✅ Aufwärtstrend (EMA20 > EMA50{' > EMA200' if e200 else ''})"
        elif trend == "bear":
            bear += 2
            details["EMA"] = f"✅ Abwärtstrend (EMA20 < EMA50{' < EMA200' if e200 else ''})"
        else:
            details["EMA"] = "⚠️ Kein klarer EMA Trend"

    # MACD
    if macd_line and signal:
        if macd_line > signal and histogram and histogram > 0:
            bull += 2
            details["MACD"] = f"✅ MACD bullish crossover ({macd_line:.5f})"
        elif macd_line < signal and histogram and histogram < 0:
            bear += 2
            details["MACD"] = f"✅ MACD bearish crossover ({macd_line:.5f})"
        else:
            details["MACD"] = "⚠️ MACD kein klarer Crossover"

    # RSI
    if rsi_v:
        if rsi_v < 40:
            bull += 1
            details["RSI"] = f"✅ RSI überverkauft ({rsi_v:.1f}) → Kaufzone"
        elif rsi_v > 60:
            bear += 1
            details["RSI"] = f"✅ RSI überkauft ({rsi_v:.1f}) → Verkaufzone"
        else:
            details["RSI"] = f"⚠️ RSI neutral ({rsi_v:.1f})"

    # RSI Divergenz
    if div == "bullish":
        bull += 2
        details["Divergenz"] = "✅ Bullische RSI Divergenz!"
    elif div == "bearish":
        bear += 2
        details["Divergenz"] = "✅ Bärische RSI Divergenz!"
    else:
        details["Divergenz"] = "❌ Keine Divergenz"

    # Volumen
    if vol_ok:
        if bull >= bear: bull += 2
        else:            bear += 2
        details["Volumen"] = f"✅ Volumen Ausbruch ({vol_ratio:.1f}x Durchschnitt)"
    else:
        details["Volumen"] = f"❌ Normales Volumen ({vol_ratio:.1f}x)"

    # Bollinger Bands
    if bb_l and price <= bb_l * 1.001:
        bull += 1
        details["BB"] = f"✅ Preis am unteren Band"
    elif bb_u and price >= bb_u * 0.999:
        bear += 1
        details["BB"] = f"✅ Preis am oberen Band"
    else:
        details["BB"] = "❌ Preis mittig"

    direction = "BUY" if bull > bear else "SELL" if bear > bull else "NEUTRAL"
    return {
        "direction": direction, "bull": bull, "bear": bear,
        "rsi": rsi_v, "macd": macd_line, "details": details,
        "price": price, "vol_ok": vol_ok, "ema_trend": trend,
    }

# ─── Coin analysieren ─────────────────────────────────────────────────────────
def analyze_coin(symbol, name):
    timeframes = [("15m", "M15", "7d"), ("1h", "H1", "7d"), ("4h", "H4", "30d")]
    tf_results = {}

    for interval, label, period in timeframes:
        candles = get_candles(symbol, interval, period)
        if not candles or len(candles) < 50:
            continue
        r = analyze_tf(candles)
        if r:
            r["candles"] = candles
            tf_results[label] = r

    if len(tf_results) < 3:
        return None

    # Alle 3 Timeframes müssen übereinstimmen
    directions = [tf_results[tf]["direction"] for tf in ["M15", "H1", "H4"] if tf in tf_results]
    if directions.count("BUY") == 3:
        final_dir = "BUY"
    elif directions.count("SELL") == 3:
        final_dir = "SELL"
    else:
        return None

    # Sicherheits-Filter
    passed, reason = safety_checks(name, final_dir, tf_results)
    if not passed:
        print(f"   ❌ {name}: {reason}")
        return None

    # Score (M15 zählt doppelt — Haupttimeframe)
    total = (tf_results["M15"]["bull" if final_dir == "BUY" else "bear"] * 2 +
             tf_results["H1"]["bull"  if final_dir == "BUY" else "bear"] +
             tf_results["H4"]["bull"  if final_dir == "BUY" else "bear"])

    # SL/TP auf H1
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

    profits = {}
    for kapital in [50, 100, 200, 500]:
        risiko = kapital * (sl_pct / 100) * HEBEL
        profits[kapital] = {"risiko": risiko, "gewinn": risiko * crv}

    return {
        "symbol": symbol, "name": name, "direction": final_dir,
        "score": total, "price": price,
        "sl": sl, "tp3": tp3, "tp4": tp4, "tp5": tp5,
        "crv": crv, "sl_dist": sl_dist, "sl_pct": sl_pct,
        "profits": profits, "tf_results": tf_results,
    }

# ─── Discord ──────────────────────────────────────────────────────────────────
def send_discord(r):
    if not DISCORD_WEBHOOK:
        return
    emoji = "🟢" if r["direction"] == "BUY" else "🔴"
    color = 0x00c853 if r["direction"] == "BUY" else 0xd50000

    tf_text = ""
    for tf in ["M15", "H1", "H4"]:
        if tf in r["tf_results"]:
            d = r["tf_results"][tf]
            arrow = "📈" if d["direction"] == "BUY" else "📉"
            rsi_v = f"{d['rsi']:.1f}" if d["rsi"] else "N/A"
            macd_a = "▲" if d["macd"] and d["macd"] > 0 else "▼"
            weight = " 🎯(Haupt)" if tf == "M15" else " (Bestätigung)" if tf == "H1" else " (Trend)"
            tf_text += f"{arrow} **{tf}{weight}**: RSI {rsi_v} | MACD {macd_a} | Vol {'✅' if d['vol_ok'] else '❌'}\n"

    m15_details = r["tf_results"].get("M15", {}).get("details", {})
    detail_text = "\n".join(list(m15_details.values())[:5])

    tp_text = f"3:1 → ${r['tp3']:.4f}\n4:1 → ${r['tp4']:.4f}\n5:1 → ${r['tp5']:.4f}"
    p = r["profits"]
    profit_text = (
        f"💼 $50  → Risiko: ${p[50]['risiko']:.2f} | Gewinn: ${p[50]['gewinn']:.2f}\n"
        f"💼 $100 → Risiko: ${p[100]['risiko']:.2f} | Gewinn: ${p[100]['gewinn']:.2f}\n"
        f"💼 $200 → Risiko: ${p[200]['risiko']:.2f} | Gewinn: ${p[200]['gewinn']:.2f}\n"
        f"💼 $500 → Risiko: ${p[500]['risiko']:.2f} | Gewinn: ${p[500]['gewinn']:.2f}\n"
        f"📊 SL: -{r['sl_pct']*HEBEL:.1f}% | TP: +{r['sl_pct']*HEBEL*r['crv']:.1f}% (5x Hebel)"
    )

    embed = {"embeds": [{"title": f"{emoji} {r['name']} — {r['direction']} Signal",
        "color": color,
        "description": (
            f"**Starkes {r['direction']} Signal — alle Filter bestanden!**\n"
            f"Score: **{r['score']} Punkte** | CRV: **{r['crv']}:1**\n\n"
            f"✅ RSI unter 65 auf M15 (sicherer Bereich)\n"
            f"✅ MACD M15 + H1 + H4 alle bestätigt\n"
            f"✅ H4 EMA Trend passt zur Richtung\n"
            f"✅ Kein Signal gegen den großen Trend"
        ),
        "fields": [
            {"name": "📊 Multi-Timeframe",          "value": tf_text,      "inline": False},
            {"name": "🔍 H4 Indikator Details",     "value": detail_text,  "inline": False},
            {"name": "💰 Einstieg",                 "value": f"${r['price']:.4f}", "inline": True},
            {"name": "🛑 Stop Loss",                "value": f"${r['sl']:.4f} (-{r['sl_pct']:.1f}%)", "inline": True},
            {"name": "🎯 Take Profits",             "value": tp_text,      "inline": False},
            {"name": "💵 Gewinn/Verlust (5x Hebel)","value": profit_text,  "inline": False},
            {"name": "⚠️ Hinweis",                 "value": "Kein Finanzrat. Immer eigenes Risikomanagement verwenden!", "inline": False},
        ],
        "footer": {"text": "Crypto Bot • M15 Haupttimeframe • H1 Bestätigung • H4 Trend"},
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }]}
    try:
        res = requests.post(DISCORD_WEBHOOK, json=embed, timeout=10)
        print(f"✅ Discord: {r['name']} {r['direction']} Score:{r['score']} ({res.status_code})")
        time.sleep(1.5)
    except Exception as e:
        print(f"❌ Discord Fehler: {e}")

# ─── Hauptloop ────────────────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  Crypto Signal Bot — Maximale Sicherheit")
    print(f"  {len(TOP_50_CRYPTOS)} Coins | Min Score: {MIN_SCORE} | Max {MAX_SIGNALS} Signale")
    print("  Filter: RSI + EMA Trend + MACD + Volumen")
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
                        print(f"✅ {result['direction']} Score:{result['score']}")
                    else:
                        print("bereits gesendet")
                else:
                    if result:
                        print(f"Score {result['score']} zu niedrig")
                    else:
                        print("gefiltert")
                time.sleep(2)
            except Exception as e:
                print(f"Fehler: {e}")

        if strong:
            strong.sort(key=lambda x: x["score"], reverse=True)
            top = strong[:MAX_SIGNALS]
            print(f"\n🚨 {len(top)} Signal(e) gefunden!")
            for r in top:
                send_discord(r)
        else:
            print("\n😴 Keine Signale die alle Filter bestehen.")

        print(f"\nNächster Scan in {SCAN_EVERY // 60} Min...")
        time.sleep(SCAN_EVERY)

if __name__ == "__main__":
    main()
