import os
import time
import json
import urllib.request
import requests
from datetime import datetime

# ─── Config ───────────────────────────────────────────────────────────────────
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_CRYPTO", "")
SCAN_EVERY      = 900   # alle 15 Minuten
MIN_SCORE       = 6     # mindestens 6/10
MAX_SIGNALS     = 2     # max 2 Signale pro Scan
HEBEL           = 5

# Bybit USDT Perpetual Symbole
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
    ("NEARUSDT",  "NEAR Protocol"),
    ("AAVEUSDT",  "Aave"),
    ("MKRUSDT",   "Maker"),
    ("INJUSDT",   "Injective"),
    ("SANDUSDT",  "The Sandbox"),
    ("AXSUSDT",   "Axie Infinity"),
    ("THETAUSDT", "Theta"),
    ("XTZUSDT",   "Tezos"),
    ("EOSUSDT",   "EOS"),
    ("CHZUSDT",   "Chiliz"),
    ("OPUSDT",    "Optimism"),
    ("GRTUSDT",   "The Graph"),
    ("COMPUSDT",  "Compound"),
    ("BATUSDT",   "Basic Attention"),
    ("ZILUSDT",   "Zilliqa"),
    ("1INCHUSDT", "1inch"),
    ("VETUSDT",   "VeChain"),
    ("SNXUSDT",   "Synthetix"),
    ("CRVUSDT",   "Curve"),
    ("LDOUSDT",   "Lido"),
    ("ICXUSDT",   "ICON"),
    ("ENJUSDT",   "Enjin Coin"),
    ("ZECUSDT",   "Zcash"),
]

TIMEFRAMES = [
    ("15",  "M15",  200),  # 15 Minuten — Haupttimeframe
    ("60",  "H1",   200),  # 1 Stunde — Bestätigung
    ("240", "H4",   200),  # 4 Stunden — Trend
]

# ─── Bybit API ────────────────────────────────────────────────────────────────
def get_candles_bybit(symbol, interval, limit=200):
    """
    Bybit V5 API — kostenlos, kein API Key nötig, funktioniert auf Cloud-Servern
    interval: "15" = 15min, "60" = 1h, "240" = 4h
    """
    try:
        url = f"https://api.bybit.com/v5/market/kline?symbol={symbol}&interval={interval}&limit={limit}&category=linear"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())

        if data.get("retCode") != 0:
            print(f"      [Bybit Error {symbol}]: {data.get('retMsg')}")
            return None

        result = data["result"]["list"]
        candles = []
        for k in reversed(result):  # Bybit gibt neueste zuerst
            candles.append({
                "time":   int(k[0]),
                "open":   float(k[1]),
                "high":   float(k[2]),
                "low":    float(k[3]),
                "close":  float(k[4]),
                "volume": float(k[5]),
            })
        return candles
    except Exception as e:
        print(f"      [Bybit Fehler {symbol} {interval}]: {type(e).__name__}: {e}")
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

def volume_rising(candles, period=10):
    if len(candles) < period + 1:
        return False, 0
    avg = sum(c["volume"] for c in candles[-period-1:-1]) / period
    cur = candles[-1]["volume"]
    if avg == 0:
        return False, 0
    ratio = cur / avg
    return ratio >= 1.3, ratio

def rsi_divergence(candles, period=8):
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

# ─── Einzelnen Timeframe analysieren ─────────────────────────────────────────
def analyze_tf(candles):
    if not candles or len(candles) < 50:
        return None
    closes  = [c["close"] for c in candles]
    price   = closes[-1]
    trend   = ema_trend(closes)
    rsi_v   = rsi(closes)
    macd_l, sig, hist = macd_calc(closes)
    bb_u, bb_m, bb_l  = bollinger(closes)
    vol_ok, vol_ratio = volume_rising(candles)
    div     = rsi_divergence(candles)

    bull = bear = 0
    details = {}

    # EMA Trend (2 Punkte)
    if trend == "bull":
        bull += 2
        details["EMA"] = "✅ Aufwärtstrend (EMA20>50>200)"
    elif trend == "bear":
        bear += 2
        details["EMA"] = "✅ Abwärtstrend (EMA20<50<200)"
    else:
        details["EMA"] = "⚠️ Kein klarer EMA Trend"

    # MACD (2 Punkte)
    if macd_l is not None and sig is not None:
        if macd_l > sig and hist and hist > 0:
            bull += 2
            details["MACD"] = f"✅ MACD bullish ({macd_l:.5f})"
        elif macd_l < sig and hist and hist < 0:
            bear += 2
            details["MACD"] = f"✅ MACD bearish ({macd_l:.5f})"
        else:
            details["MACD"] = "⚠️ MACD neutral"

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

    # Volumen (1 Punkt)
    if vol_ok:
        if bull >= bear: bull += 1
        else:            bear += 1
        details["Volumen"] = f"✅ Erhöhtes Volumen ({vol_ratio:.1f}x)"
    else:
        details["Volumen"] = f"❌ Normales Volumen ({vol_ratio:.1f}x)"

    # Bollinger (1 Punkt)
    if bb_l and price <= bb_l * 1.002:
        bull += 1
        details["BB"] = "✅ Preis am unteren Band"
    elif bb_u and price >= bb_u * 0.998:
        bear += 1
        details["BB"] = "✅ Preis am oberen Band"
    else:
        details["BB"] = "❌ Preis mittig"

    direction = "BUY" if bull > bear else "SELL" if bear > bull else "NEUTRAL"
    return {
        "direction": direction, "bull": bull, "bear": bear,
        "rsi": rsi_v, "macd": macd_l, "details": details,
        "price": price, "vol_ok": vol_ok, "ema_trend": trend,
        "candles": candles,
    }

# ─── SL/TP aus echtem Chart ──────────────────────────────────────────────────
def calc_sl_tp(candles, direction):
    price  = candles[-1]["close"]
    recent = candles[-20:]
    puffer = price * 0.004  # 0.4% Puffer

    if direction == "BUY":
        sl      = min(c["low"] for c in recent) - puffer
        sl_dist = max(price - sl, price * 0.01)
    else:
        sl      = max(c["high"] for c in recent) + puffer
        sl_dist = max(sl - price, price * 0.01)

    sl_pct = (sl_dist / price) * 100
    crv    = 5 if sl_pct <= 2 else 4 if sl_pct <= 4 else 3

    tp3 = price + sl_dist * 3 if direction == "BUY" else price - sl_dist * 3
    tp4 = price + sl_dist * 4 if direction == "BUY" else price - sl_dist * 4
    tp5 = price + sl_dist * 5 if direction == "BUY" else price - sl_dist * 5

    return sl, tp3, tp4, tp5, crv, sl_pct

# ─── Sicherheits-Filter ───────────────────────────────────────────────────────
def safety_checks(name, final_dir, tf_results):
    # 1. RSI M15 — nicht überkauft/überverkauft
    m15_rsi = tf_results.get("M15", {}).get("rsi")
    if m15_rsi:
        if final_dir == "BUY" and m15_rsi > 72:
            return False, f"M15 RSI {m15_rsi:.1f} > 72 überkauft"
        if final_dir == "SELL" and m15_rsi < 28:
            return False, f"M15 RSI {m15_rsi:.1f} < 28 überverkauft"

    # 2. H1 RSI
    h1_rsi = tf_results.get("H1", {}).get("rsi")
    if h1_rsi:
        if final_dir == "BUY" and h1_rsi > 75:
            return False, f"H1 RSI {h1_rsi:.1f} > 75 überkauft"
        if final_dir == "SELL" and h1_rsi < 25:
            return False, f"H1 RSI {h1_rsi:.1f} < 25 überverkauft"

    # 3. H4 EMA Trend — neutral ist OK, nur klarer Gegentrend blockiert
    h4_trend = tf_results.get("H4", {}).get("ema_trend", "neutral")
    if final_dir == "BUY" and h4_trend == "bear":
        return False, "H4 EMA klarer Abwärtstrend — kein BUY"
    if final_dir == "SELL" and h4_trend == "bull":
        return False, "H4 EMA klarer Aufwärtstrend — kein SELL"

    # 4. H4 MACD muss stimmen
    h4_macd = tf_results.get("H4", {}).get("macd")
    if h4_macd is not None:
        if final_dir == "BUY" and h4_macd < 0:
            return False, "H4 MACD bearish — kein BUY"
        if final_dir == "SELL" and h4_macd > 0:
            return False, "H4 MACD bullish — kein SELL"

    return True, "✅ Alle Filter bestanden"

# ─── Coin analysieren ─────────────────────────────────────────────────────────
def analyze_coin(symbol, name):
    tf_results = {}

    for interval, label, limit in TIMEFRAMES:
        candles = get_candles_bybit(symbol, interval, limit)
        if candles and len(candles) >= 50:
            r = analyze_tf(candles)
            if r:
                tf_results[label] = r
        time.sleep(0.3)

    if len(tf_results) < 3:
        return None

    # Alle 3 Timeframes müssen übereinstimmen
    dirs = [tf_results[tf]["direction"] for tf in ["M15", "H1", "H4"]]
    if dirs.count("BUY") == 3:
        final_dir = "BUY"
    elif dirs.count("SELL") == 3:
        final_dir = "SELL"
    else:
        return None

    # Sicherheits-Filter
    passed, reason = safety_checks(name, final_dir, tf_results)
    if not passed:
        print(f"   ❌ {reason}")
        return None

    # Score — M15 zählt doppelt
    key = "bull" if final_dir == "BUY" else "bear"
    total = (tf_results["M15"][key] * 2 +
             tf_results["H1"][key] +
             tf_results["H4"][key])

    # SL/TP aus echtem H1 Chart
    h1_candles = tf_results["H1"]["candles"]
    sl, tp3, tp4, tp5, crv, sl_pct = calc_sl_tp(h1_candles, final_dir)
    price = h1_candles[-1]["close"]

    profits = {}
    for kapital in [50, 100, 200, 500]:
        risiko = kapital * (sl_pct / 100) * HEBEL
        profits[kapital] = {"risiko": risiko, "gewinn": risiko * crv}

    return {
        "symbol": symbol, "name": name, "direction": final_dir,
        "score": total, "price": price,
        "sl": sl, "tp3": tp3, "tp4": tp4, "tp5": tp5,
        "crv": crv, "sl_pct": sl_pct, "profits": profits,
        "tf_results": tf_results,
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
            label = "🎯(Haupt)" if tf == "M15" else "(Bestätigung)" if tf == "H1" else "(Trend)"
            tf_text += f"{arrow} **{tf} {label}**: RSI {rsi_v} | MACD {macd_a} | EMA {d['ema_trend']} | Vol {'✅' if d['vol_ok'] else '❌'}\n"

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
            f"**Starkes {r['direction']} Signal auf allen 3 Timeframes!**\n"
            f"Score: **{r['score']} Punkte** | CRV: **{r['crv']}:1**\n\n"
            f"✅ Bybit Echtzeit Daten\n"
            f"✅ Echter SL aus Chart (letztes Swing High/Low)\n"
            f"✅ Alle Sicherheitsfilter bestanden"
        ),
        "fields": [
            {"name": "📊 Multi-Timeframe (M15+H1+H4)", "value": tf_text,     "inline": False},
            {"name": "🔍 M15 Indikator Details",        "value": detail_text, "inline": False},
            {"name": "💰 Einstieg",  "value": f"${r['price']:.4f}",           "inline": True},
            {"name": "🛑 Stop Loss", "value": f"${r['sl']:.4f} (-{r['sl_pct']:.1f}%)", "inline": True},
            {"name": "🎯 Take Profits",              "value": tp_text,        "inline": False},
            {"name": "💵 Gewinn/Verlust (5x Hebel)", "value": profit_text,    "inline": False},
            {"name": "⚠️ Hinweis",  "value": "Kein Finanzrat. Immer eigenes Risikomanagement verwenden!", "inline": False},
        ],
        "footer": {"text": "Crypto Bot • Bybit Echtzeit API • M15 + H1 + H4"},
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }]}
    try:
        res = requests.post(DISCORD_WEBHOOK, json=embed, timeout=10)
        print(f"✅ Discord: {r['name']} {r['direction']} Score:{r['score']} ({res.status_code})")
        time.sleep(2)
    except Exception as e:
        print(f"❌ Discord Fehler: {e}")

# ─── Hauptloop ────────────────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  Crypto Signal Bot — Bybit Echtzeit API")
    print(f"  {len(TOP_CRYPTOS)} Coins | M15 + H1 + H4 | Min Score: {MIN_SCORE}")
    print("  Echter SL aus Chart | Alle Sicherheitsfilter")
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
