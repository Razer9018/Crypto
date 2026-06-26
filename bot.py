import os
import time
import json
import urllib.request
import requests
from datetime import datetime

# ─── Config ───────────────────────────────────────────────────────────────────
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_CRYPTO", "")
SCAN_EVERY      = 900   # alle 15 Minuten
MIN_SCORE       = 8     # mindestens 8/9 Punkte
MAX_SIGNALS     = 3     # max 3 Signale pro Scan
HEBEL           = 5     # 5x Hebel

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
    ("LINK-USD", "Chainlink"),
    ("ATOM-USD", "Cosmos"),
    ("XLM-USD",  "Stellar"),
    ("BCH-USD",  "Bitcoin Cash"),
    ("ALGO-USD", "Algorand"),
    ("VET-USD",  "VeChain"),
    ("FIL-USD",  "Filecoin"),
    ("ICP-USD",  "Internet Computer"),
    ("APT-USD",  "Aptos"),
    ("NEAR-USD", "NEAR Protocol"),
    ("AAVE-USD", "Aave"),
    ("MKR-USD",  "Maker"),
    ("SNX-USD",  "Synthetix"),
    ("CRV-USD",  "Curve"),
    ("LDO-USD",  "Lido"),
    ("INJ-USD",  "Injective"),
    ("EGLD-USD", "MultiversX"),
    ("FLOW-USD", "Flow"),
    ("SAND-USD", "The Sandbox"),
    ("MANA-USD", "Decentraland"),
    ("AXS-USD",  "Axie Infinity"),
    ("THETA-USD","Theta"),
    ("XTZ-USD",  "Tezos"),
    ("EOS-USD",  "EOS"),
    ("ENJ-USD",  "Enjin Coin"),
    ("CHZ-USD",  "Chiliz"),
    ("OP-USD",   "Optimism"),
    ("STX-USD",  "Stacks"),
    ("GRT-USD",  "The Graph"),
    ("1INCH-USD","1inch"),
    ("COMP-USD", "Compound"),
    ("ZEC-USD",  "Zcash"),
    ("DASH-USD", "Dash"),
    ("BAT-USD",  "Basic Attention"),
    ("ZIL-USD",  "Zilliqa"),
    ("ICX-USD",  "ICON"),
    ("ONT-USD",  "Ontology"),
    ("DGB-USD",  "DigiByte"),
]

TIMEFRAMES = [("15m", "M15"), ("1h", "H1"), ("4h", "H4")]

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
            if o and h and l and c:
                candles.append({"time": times[i], "open": o, "high": h, "low": l, "close": c, "volume": q.get("volume", [0]*len(times))[i] or 0})
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
    return (e12 - e26) if e12 and e26 else None

def rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains = losses = 0
    for i in range(1, period + 1):
        d = closes[i] - closes[i-1]
        if d > 0: gains  += d
        else:     losses -= d
    ag, al = gains / period, losses / period
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i-1]
        ag = (ag * (period-1) + max(d, 0))  / period
        al = (al * (period-1) + max(-d, 0)) / period
    return 100 - 100 / (1 + ag / al) if al != 0 else 100

def volume_rising(candles):
    if len(candles) < 10:
        return False
    recent = sum(c["volume"] for c in candles[-5:]) / 5
    prev   = sum(c["volume"] for c in candles[-10:-5]) / 5
    return prev > 0 and recent > prev * 1.2

# ─── Kerzenmuster (PFLICHT) ───────────────────────────────────────────────────
def is_doji(c):
    body   = abs(c["close"] - c["open"])
    range_ = c["high"] - c["low"]
    return range_ > 0 and body / range_ < 0.35

def detect_morning_star(candles):
    if len(candles) < 3:
        return False
    c1, c2, c3 = candles[-3], candles[-2], candles[-1]
    b1 = abs(c1["close"] - c1["open"])
    b3 = abs(c3["close"] - c3["open"])
    return (c1["close"] < c1["open"] and is_doji(c2) and
            c3["close"] > c3["open"] and b3 >= b1 * 0.5 and
            c3["close"] > (c1["open"] + c1["close"]) / 2)

def detect_evening_star(candles):
    if len(candles) < 3:
        return False
    c1, c2, c3 = candles[-3], candles[-2], candles[-1]
    b1 = abs(c1["close"] - c1["open"])
    b3 = abs(c3["close"] - c3["open"])
    return (c1["close"] > c1["open"] and is_doji(c2) and
            c3["close"] < c3["open"] and b3 >= b1 * 0.5 and
            c3["close"] < (c1["open"] + c1["close"]) / 2)

def detect_hammer(c):
    body  = abs(c["close"] - c["open"])
    upper = c["high"] - max(c["open"], c["close"])
    lower = min(c["open"], c["close"]) - c["low"]
    return body > 0 and lower >= body * 2 and upper <= body * 0.5

def detect_inverted_hammer(c):
    body  = abs(c["close"] - c["open"])
    upper = c["high"] - max(c["open"], c["close"])
    lower = min(c["open"], c["close"]) - c["low"]
    return body > 0 and upper >= body * 2 and lower <= body * 0.5

def detect_bullish_engulfing(candles):
    if len(candles) < 2:
        return False
    p, c = candles[-2], candles[-1]
    return (p["close"] < p["open"] and c["close"] > c["open"] and
            c["open"] < p["close"] and c["close"] > p["open"])

def detect_bearish_engulfing(candles):
    if len(candles) < 2:
        return False
    p, c = candles[-2], candles[-1]
    return (p["close"] > p["open"] and c["close"] < c["open"] and
            c["open"] > p["close"] and c["close"] < p["open"])

def get_pattern(candles, direction):
    if direction == "BUY":
        if detect_morning_star(candles):    return "Morning Star ⭐"
        if detect_hammer(candles[-1]):      return "Hammer 🔨"
        if detect_bullish_engulfing(candles): return "Bullish Engulfing 📈"
    else:
        if detect_evening_star(candles):    return "Evening Star 🌙"
        if detect_inverted_hammer(candles[-1]): return "Umg. Hammer 🔨"
        if detect_bearish_engulfing(candles): return "Bearish Engulfing 📉"
    return "—"

# ─── Einzelnen Timeframe analysieren ─────────────────────────────────────────
def analyze_tf(candles):
    if not candles or len(candles) < 50:
        return None
    closes = [c["close"] for c in candles]
    price  = closes[-1]

    ema20  = ema(closes, 20)
    ema50  = ema(closes, 50)
    ema200 = ema(closes, 200) if len(closes) >= 200 else None
    macd_v = macd(closes)
    rsi_v  = rsi(closes)
    bb_u, _, bb_l = bollinger(closes)
    vol    = volume_rising(candles)

    bull = bear = 0
    if ema20 and ema50:
        if ema20 > ema50: bull += 1
        else:             bear += 1
    if ema200:
        if price > ema200: bull += 1
        else:              bear += 1
    if macd_v:
        if macd_v > 0: bull += 1
        else:          bear += 1
    if rsi_v:
        if rsi_v < 40:   bull += 1
        elif rsi_v > 60: bear += 1
    if bb_l and price <= bb_l * 1.002: bull += 1
    if bb_u and price >= bb_u * 0.998: bear += 1
    if vol:
        if bull >= bear: bull += 1
        else:            bear += 1

    direction = "BUY" if bull > bear else "SELL" if bear > bull else "NEUTRAL"
    return {"direction": direction, "bull": bull, "bear": bear, "rsi": rsi_v, "macd": macd_v, "price": price}

# ─── SL / TP ──────────────────────────────────────────────────────────────────
def calc_sl_tp(candles, direction):
    price  = candles[-1]["close"]
    recent = candles[-20:]
    puffer = price * 0.005  # 0.5% Puffer

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
    tp  = price + sl_dist * crv if direction == "BUY" else price - sl_dist * crv

    return sl, tp, tp3, tp4, tp5, crv, sl_dist, sl_pct

# ─── Gewinn Rechner ───────────────────────────────────────────────────────────
def calc_profit(sl_pct, crv):
    kapitale = [50, 100, 200, 500]
    results  = {}
    for kapital in kapitale:
        risiko = kapital * (sl_pct / 100) * HEBEL
        gewinn = risiko * crv
        results[kapital] = {"risiko": risiko, "gewinn": gewinn}
    return results

# ─── Coin analysieren ─────────────────────────────────────────────────────────
def analyze_coin(symbol, name):
    results = {}
    for interval, label in TIMEFRAMES:
        period  = "30d" if interval == "4h" else "7d"
        candles = get_candles(symbol, interval, period)
        if candles:
            r = analyze_tf(candles)
            if r:
                results[label] = {"data": r, "candles": candles}

    if len(results) < 3:
        return None

    # Alle 3 Timeframes müssen übereinstimmen
    directions = [results[tf]["data"]["direction"] for tf in results]
    if directions.count("BUY") == 3:
        final_dir = "BUY"
    elif directions.count("SELL") == 3:
        final_dir = "SELL"
    else:
        return None

    # Kerzenmuster auf H1 prüfen (PFLICHT!)
    h1_candles = results["H1"]["candles"]
    pattern    = get_pattern(h1_candles, final_dir)
    if pattern == "—":
        print(f"   {name}: kein Kerzenmuster → kein Alert")
        return None

    # Score berechnen
    total = sum(results[tf]["data"]["bull"] if final_dir == "BUY"
                else results[tf]["data"]["bear"] for tf in results)

    price = results["H1"]["data"]["price"]
    candles_h1 = results["H1"]["candles"]
    sl, tp, tp3, tp4, tp5, crv, sl_dist, sl_pct = calc_sl_tp(candles_h1, final_dir)
    profits = calc_profit(sl_pct, crv)

    tf_info = {}
    for tf in results:
        d = results[tf]["data"]
        tf_info[tf] = {"direction": d["direction"], "rsi": d["rsi"], "macd": d["macd"]}

    return {
        "symbol": symbol, "name": name, "direction": final_dir,
        "score": total, "pattern": pattern,
        "price": price, "sl": sl, "tp": tp,
        "tp3": tp3, "tp4": tp4, "tp5": tp5,
        "crv": crv, "sl_dist": sl_dist, "sl_pct": sl_pct,
        "profits": profits, "tf_info": tf_info,
    }

# ─── Discord Alert ────────────────────────────────────────────────────────────
def send_discord(r):
    if not DISCORD_WEBHOOK:
        print("Kein Webhook!")
        return

    emoji = "🟢" if r["direction"] == "BUY" else "🔴"
    color = 0x00c853 if r["direction"] == "BUY" else 0xd50000

    tf_text = ""
    for tf, d in r["tf_info"].items():
        arrow = "📈" if d["direction"] == "BUY" else "📉"
        rsi_v = f"{d['rsi']:.0f}" if d["rsi"] else "N/A"
        macd_arrow = "▲" if d["macd"] and d["macd"] > 0 else "▼"
        tf_text += f"{arrow} **{tf}**: {d['direction']} (RSI: {rsi_v} | MACD: {macd_arrow})\n"

    tp_text = (
        f"3:1 → ${r['tp3']:.4f}\n"
        f"4:1 → ${r['tp4']:.4f}\n"
        f"5:1 → ${r['tp5']:.4f}"
    )

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
            f"Muster: **{r['pattern']}**\n"
            f"Score: **{r['score']} Punkte**"
        ),
        "fields": [
            {"name": "📊 Timeframe Analyse",  "value": tf_text,               "inline": False},
            {"name": "💰 Einstieg",           "value": f"${r['price']:.4f}",  "inline": True},
            {"name": "🛑 Stop Loss",          "value": f"${r['sl']:.4f} (-{r['sl_pct']:.1f}%)", "inline": True},
            {"name": "🎯 Alle Take Profits",  "value": tp_text,               "inline": False},
            {"name": f"⭐ Empfohlenes CRV: {r['crv']}:1", "value": f"SL = {r['sl_pct']:.1f}% → {'kleiner' if r['sl_pct'] <= 2 else 'mittlerer' if r['sl_pct'] <= 4 else 'größerer'} SL", "inline": False},
            {"name": "💵 Gewinn/Verlust (5x Hebel)", "value": profit_text,   "inline": False},
            {"name": "⚠️ Hinweis",           "value": "Kein Finanzrat. Eigenes Risikomanagement verwenden.", "inline": False},
        ],
        "footer": {"text": "Crypto Signal Bot • M15 + H1 + H4 • Kerzenmuster Pflicht"},
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }]}
    try:
        res = requests.post(DISCORD_WEBHOOK, json=embed, timeout=10)
        print(f"Discord gesendet: {r['name']} {r['direction']} ({res.status_code})")
        time.sleep(1.5)
    except Exception as e:
        print(f"Discord Fehler: {e}")

# ─── Hauptloop ────────────────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  Crypto Signal Bot gestartet")
    print(f"  {len(TOP_50_CRYPTOS)} Coins | M15+H1+H4 | Min Score: {MIN_SCORE}")
    print(f"  Kerzenmuster: PFLICHT | Max {MAX_SIGNALS} Signale pro Scan")
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
                        print(f"SIGNAL! {result['direction']} | Score: {result['score']} | {result['pattern']}")
                    else:
                        print(f"bereits gesendet")
                else:
                    if result:
                        print(f"Score {result['score']} zu niedrig")
                    else:
                        print(f"kein Signal")
                time.sleep(2)
            except Exception as e:
                print(f"Fehler: {e}")

        # Nur die stärksten MAX_SIGNALS senden
        if strong:
            strong.sort(key=lambda x: x["score"], reverse=True)
            top = strong[:MAX_SIGNALS]
            print(f"\n{len(top)} starke Signale gefunden! Sende Discord Alerts...")
            for r in top:
                send_discord(r)
        else:
            print("\nKeine starken Signale mit Kerzenmuster.")

        print(f"\nNaechster Scan in {SCAN_EVERY // 60} Minuten...")
        time.sleep(SCAN_EVERY)

if __name__ == "__main__":
    main()
