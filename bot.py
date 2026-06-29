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

# Binance Symbole (USDT Paare)
TOP_CRYPTOS = [
    ("BTCUSDT",   "Bitcoin"),
    ("ETHUSDT",   "Ethereum"),
    ("BNBUSDT",   "BNB"),
    ("SOLUSDT",   "Solana"),
    ("XRPUSDT",   "XRP"),
    ("ADAUSDT",   "Cardano"),
    ("AVAXUSDT",  "Avalanche"),
    ("DOGEUSDT",  "Dogecoin"),
    ("DOTUSDT",   "Polkadot"),
    ("MATICUSDT", "Polygon"),
    ("LTCUSDT",   "Litecoin"),
    ("LINKUSDT",  "Chainlink"),
    ("ATOMUSDT",  "Cosmos"),
    ("XLMUSDT",   "Stellar"),
    ("BCHUSDT",   "Bitcoin Cash"),
    ("ALGOUSDT",  "Algorand"),
    ("FILUSDT",   "Filecoin"),
    ("ICPUSDT",   "Internet Computer"),
    ("APTUSDT",   "Aptos"),
    ("NEARUSDT",  "NEAR Protocol"),
    ("AAVEUSDT",  "Aave"),
    ("MKRUSDT",   "Maker"),
    ("INJUSDT",   "Injective"),
    ("EGLDUSDT",  "MultiversX"),
    ("FLOWUSDT",  "Flow"),
    ("SANDUSDT",  "The Sandbox"),
    ("MANAUSDT",  "Decentraland"),
    ("AXSUSDT",   "Axie Infinity"),
    ("THETAUSDT", "Theta"),
    ("XTZUSDT",   "Tezos"),
    ("EOSUSDT",   "EOS"),
    ("ENJUSDT",   "Enjin Coin"),
    ("CHZUSDT",   "Chiliz"),
    ("OPUSDT",    "Optimism"),
    ("GRTUSDT",   "The Graph"),
    ("COMPUSDT",  "Compound"),
    ("ZECUSDT",   "Zcash"),
    ("BATUSDT",   "Basic Attention"),
    ("ZILUSDT",   "Zilliqa"),
    ("1INCHUSDT", "1inch"),
    ("VETUSDT",   "VeChain"),
    ("STXUSDT",   "Stacks"),
    ("SNXUSDT",   "Synthetix"),
    ("CRVUSDT",   "Curve"),
    ("LDOUSDT",   "Lido"),
    ("DASHUSDT",  "Dash"),
    ("ICXUSDT",   "ICON"),
    ("ONTUSDT",   "Ontology"),
    ("DGBUSDT",   "DigiByte"),
    ("SHIBUSDT",  "Shiba Inu"),
]

# Binance Interval Mapping
INTERVALS = [("15m", "M15"), ("1h", "H1"), ("4h", "H4")]
PERIODS   = {"15m": 200, "1h": 200, "4h": 200}  # Anzahl Kerzen

# ─── Binance API (kostenlos, Echtzeit) ───────────────────────────────────────
def get_candles_binance(symbol, interval, limit=200):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        candles = []
        for k in data:
            candles.append({
                "time":   k[0],
                "open":   float(k[1]),
                "high":   float(k[2]),
                "low":    float(k[3]),
                "close":  float(k[4]),
                "volume": float(k[5]),
            })
        return candles
    except Exception as e:
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

def macd_calc(closes):
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
    k9     = 2 / (9 + 1)
    signal = sum(macd_vals[:9]) / 9
    for v in macd_vals[9:]:
        signal = v * k9 + signal * (1 - k9)
    macd_line = macd_vals[-1]
    histogram = macd_line - signal
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
    closes   = [c["close"] for c in candles]
    rsi_vals = [rsi(closes[:i+1]) for i in range(len(closes))]
    rsi_vals = [r for r in rsi_vals if r is not None]
    if len(rsi_vals) < period * 2:
        return None
    curr_low   = min(closes[-period:])
    prev_low   = min(closes[-period*2:-period])
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

def ema_trend(closes):
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
    # 1. RSI M15 und H1 — beide müssen unter 65 (BUY) bzw über 35 (SELL)
    for tf in ["M15", "H1"]:
        r = tf_results.get(tf, {}).get("rsi")
        if r:
            if final_dir == "BUY" and r > 65:
                return False, f"{tf} RSI {r:.1f} > 65 — überkauft"
            if final_dir == "SELL" and r < 35:
                return False, f"{tf} RSI {r:.1f} < 35 — überverkauft"

    # 2. RSI H4 — nur extreme Werte blockieren
    r_h4 = tf_results.get("H4", {}).get("rsi")
    if r_h4:
        if final_dir == "BUY" and r_h4 > 80:
            return False, f"H4 RSI {r_h4:.1f} > 80 — extrem überkauft"
        if final_dir == "SELL" and r_h4 < 20:
            return False, f"H4 RSI {r_h4:.1f} < 20 — extrem überverkauft"

    # 3. H4 EMA muss klar in Signal-Richtung zeigen — KEIN neutraler Trend
    h4_trend = tf_results.get("H4", {}).get("ema_trend", "neutral")
    if final_dir == "BUY" and h4_trend != "bull":
        return False, f"H4 EMA kein Aufwärtstrend ({h4_trend})"
    if final_dir == "SELL" and h4_trend != "bear":
        return False, f"H4 EMA kein Abwärtstrend ({h4_trend})"

    # 4. MACD muss auf M15, H1 UND H4 stimmen
    for tf in ["M15", "H1", "H4"]:
        m = tf_results.get(tf, {}).get("macd")
        if m is not None:
            if final_dir == "BUY" and m < 0:
                return False, f"{tf} MACD bearish — kein BUY"
            if final_dir == "SELL" and m > 0:
                return False, f"{tf} MACD bullish — kein SELL"

    return True, "✅ Alle Filter bestanden"

# ─── Einzelnen Timeframe analysieren ─────────────────────────────────────────
def analyze_tf(candles):
    if not candles or len(candles) < 50:
        return None
    closes  = [c["close"] for c in candles]
    price   = closes[-1]
    e_trend = ema_trend(closes)
    rsi_v   = rsi(closes)
    macd_l, signal, hist = macd_calc(closes)
    bb_u, bb_m, bb_l = bollinger(closes)
    vol_ok, vol_ratio = volume_breakout(candles)
    div     = rsi_divergence(candles)

    bull = bear = 0
    details = {}

    # EMA Trend (2 Punkte)
    if e_trend == "bull":
        bull += 2
        details["EMA"] = "✅ Aufwärtstrend (EMA20 > EMA50 > EMA200)"
    elif e_trend == "bear":
        bear += 2
        details["EMA"] = "✅ Abwärtstrend (EMA20 < EMA50 < EMA200)"
    else:
        details["EMA"] = "⚠️ Kein klarer EMA Trend"

    # MACD (2 Punkte)
    if macd_l is not None and signal is not None:
        if macd_l > signal and hist and hist > 0:
            bull += 2
            details["MACD"] = f"✅ MACD bullish ({macd_l:.6f})"
        elif macd_l < signal and hist and hist < 0:
            bear += 2
            details["MACD"] = f"✅ MACD bearish ({macd_l:.6f})"
        else:
            details["MACD"] = "⚠️ MACD kein klarer Crossover"

    # RSI (1 Punkt)
    if rsi_v:
        if rsi_v < 40:
            bull += 1
            details["RSI"] = f"✅ RSI überverkauft ({rsi_v:.1f})"
        elif rsi_v > 60:
            bear += 1
            details["RSI"] = f"✅ RSI überkauft ({rsi_v:.1f})"
        else:
            details["RSI"] = f"⚠️ RSI neutral ({rsi_v:.1f})"

    # RSI Divergenz (2 Punkte)
    if div == "bullish":
        bull += 2
        details["Divergenz"] = "✅ Bullische RSI Divergenz!"
    elif div == "bearish":
        bear += 2
        details["Divergenz"] = "✅ Bärische RSI Divergenz!"
    else:
        details["Divergenz"] = "❌ Keine Divergenz"

    # Volumen (2 Punkte)
    if vol_ok:
        if bull >= bear: bull += 2
        else:            bear += 2
        details["Volumen"] = f"✅ Volumen Ausbruch ({vol_ratio:.1f}x)"
    else:
        details["Volumen"] = f"❌ Normales Volumen ({vol_ratio:.1f}x)"

    # Bollinger Bands (1 Punkt)
    if bb_l and price <= bb_l * 1.001:
        bull += 1
        details["BB"] = "✅ Preis am unteren Band"
    elif bb_u and price >= bb_u * 0.999:
        bear += 1
        details["BB"] = "✅ Preis am oberen Band"
    else:
        details["BB"] = "❌ Preis mittig"

    direction = "BUY" if bull > bear else "SELL" if bear > bull else "NEUTRAL"
    return {
        "direction": direction, "bull": bull, "bear": bear,
        "rsi": rsi_v, "macd": macd_l, "details": details,
        "price": price, "vol_ok": vol_ok, "ema_trend": e_trend,
    }

# ─── Coin analysieren ─────────────────────────────────────────────────────────
def analyze_coin(symbol, name):
    tf_data = {}
    candle_store = {}

    for interval, label in INTERVALS:
        candles = get_candles_binance(symbol, interval, limit=200)
        if not candles or len(candles) < 50:
            continue
        r = analyze_tf(candles)
        if r:
            r["candles"] = candles
            tf_data[label] = r
            candle_store[label] = candles

    if len(tf_data) < 3:
        return None

    directions = [tf_data[tf]["direction"] for tf in ["M15", "H1", "H4"] if tf in tf_data]
    if directions.count("BUY") == 3:
        final_dir = "BUY"
    elif directions.count("SELL") == 3:
        final_dir = "SELL"
    else:
        return None

    passed, reason = safety_checks(name, final_dir, tf_data)
    if not passed:
        print(f"   ❌ {reason}")
        return None

    # Score — M15 zählt doppelt
    total = (tf_data["M15"]["bull" if final_dir == "BUY" else "bear"] * 2 +
             tf_data["H1"]["bull"  if final_dir == "BUY" else "bear"] +
             tf_data["H4"]["bull"  if final_dir == "BUY" else "bear"])

    # SL/TP auf H1 Basis
    h1_candles = candle_store["H1"]
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
        "profits": profits, "tf_data": tf_data,
    }

# ─── Discord ──────────────────────────────────────────────────────────────────
def send_discord(r):
    if not DISCORD_WEBHOOK:
        return
    emoji = "🟢" if r["direction"] == "BUY" else "🔴"
    color = 0x00c853 if r["direction"] == "BUY" else 0xd50000

    tf_text = ""
    for tf in ["M15", "H1", "H4"]:
        if tf in r["tf_data"]:
            d = r["tf_data"][tf]
            arrow = "📈" if d["direction"] == "BUY" else "📉"
            rsi_v = f"{d['rsi']:.1f}" if d["rsi"] else "N/A"
            macd_a = "▲" if d["macd"] and d["macd"] > 0 else "▼"
            label = "🎯(Haupt)" if tf == "M15" else "(Bestätigung)" if tf == "H1" else "(Trend)"
            tf_text += f"{arrow} **{tf} {label}**: RSI {rsi_v} | MACD {macd_a} | Vol {'✅' if d['vol_ok'] else '❌'}\n"

    m15_details = r["tf_data"].get("M15", {}).get("details", {})
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
            f"✅ RSI unter 65 auf M15 + H1\n"
            f"✅ MACD M15 + H1 + H4 alle bestätigt\n"
            f"✅ H4 EMA Trend klar in Signal-Richtung\n"
            f"✅ Echtzeit Daten von Binance"
        ),
        "fields": [
            {"name": "📊 Multi-Timeframe",           "value": tf_text,      "inline": False},
            {"name": "🔍 M15 Indikator Details",     "value": detail_text,  "inline": False},
            {"name": "💰 Einstieg",                  "value": f"${r['price']:.4f}", "inline": True},
            {"name": "🛑 Stop Loss",                 "value": f"${r['sl']:.4f} (-{r['sl_pct']:.1f}%)", "inline": True},
            {"name": "🎯 Take Profits",              "value": tp_text,      "inline": False},
            {"name": "💵 Gewinn/Verlust (5x Hebel)", "value": profit_text,  "inline": False},
            {"name": "⚠️ Hinweis",                  "value": "Kein Finanzrat. Immer eigenes Risikomanagement verwenden!", "inline": False},
        ],
        "footer": {"text": "Crypto Bot • Binance Echtzeit API • M15+H1+H4"},
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
    print("  Crypto Signal Bot — Binance Echtzeit API")
    print(f"  {len(TOP_CRYPTOS)} Coins | Min Score: {MIN_SCORE} | Max {MAX_SIGNALS} Signale")
    print("  Keine Verzögerung — Echtzeit Daten!")
    print("=" * 55)

    last_signals = {}

    while True:
        now = datetime.utcnow().strftime("%H:%M:%S UTC")
        print(f"\n[{now}] Scanne {len(TOP_CRYPTOS)} Coins...")
        strong = []

        for symbol, name in TOP_CRYPTOS:
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
                    score = result["score"] if result else 0
                    print(f"Score {score} — gefiltert")
                time.sleep(0.5)  # Binance Rate Limit
            except Exception as e:
                print(f"Fehler: {e}")

        if strong:
            strong.sort(key=lambda x: x["score"], reverse=True)
            top = strong[:MAX_SIGNALS]
            print(f"\n🚨 {len(top)} Signal(e) — sende Discord Alerts...")
            for r in top:
                send_discord(r)
        else:
            print("\n😴 Keine Signale die alle Filter bestehen.")

        print(f"\nNächster Scan in {SCAN_EVERY // 60} Min...")
        time.sleep(SCAN_EVERY)

if __name__ == "__main__":
    main()
