import os
import time
import json
import urllib.request
import requests
from datetime import datetime

# ─── Config ───────────────────────────────────────────────────────────────────
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_CRYPTO", "")
SCAN_EVERY      = 900
MIN_SCORE       = 5
MAX_SIGNALS     = 3
HEBEL           = 5

# CoinGecko IDs
TOP_CRYPTOS = [
    ("bitcoin",          "BTCUSDT",  "Bitcoin"),
    ("ethereum",         "ETHUSDT",  "Ethereum"),
    ("binancecoin",      "BNBUSDT",  "BNB"),
    ("solana",           "SOLUSDT",  "Solana"),
    ("ripple",           "XRPUSDT",  "XRP"),
    ("cardano",          "ADAUSDT",  "Cardano"),
    ("avalanche-2",      "AVAXUSDT", "Avalanche"),
    ("dogecoin",         "DOGEUSDT", "Dogecoin"),
    ("polkadot",         "DOTUSDT",  "Polkadot"),
    ("matic-network",    "MATICUSDT","Polygon"),
    ("litecoin",         "LTCUSDT",  "Litecoin"),
    ("chainlink",        "LINKUSDT", "Chainlink"),
    ("cosmos",           "ATOMUSDT", "Cosmos"),
    ("stellar",          "XLMUSDT",  "Stellar"),
    ("bitcoin-cash",     "BCHUSDT",  "Bitcoin Cash"),
    ("algorand",         "ALGOUSDT", "Algorand"),
    ("filecoin",         "FILUSDT",  "Filecoin"),
    ("near",             "NEARUSDT", "NEAR Protocol"),
    ("aave",             "AAVEUSDT", "Aave"),
    ("maker",            "MKRUSDT",  "Maker"),
    ("injective-protocol","INJUSDT", "Injective"),
    ("the-sandbox",      "SANDUSDT", "The Sandbox"),
    ("axie-infinity",    "AXSUSDT",  "Axie Infinity"),
    ("theta-token",      "THETAUSDT","Theta"),
    ("tezos",            "XTZUSDT",  "Tezos"),
    ("eos",              "EOSUSDT",  "EOS"),
    ("chiliz",           "CHZUSDT",  "Chiliz"),
    ("optimism",         "OPUSDT",   "Optimism"),
    ("the-graph",        "GRTUSDT",  "The Graph"),
    ("compound-governance-token", "COMPUSDT", "Compound"),
    ("zcash",            "ZECUSDT",  "Zcash"),
    ("basic-attention-token", "BATUSDT", "Basic Attention"),
    ("zilliqa",          "ZILUSDT",  "Zilliqa"),
    ("1inch",            "1INCHUSDT","1inch"),
    ("vechain",          "VETUSDT",  "VeChain"),
    ("synthetix-network-token", "SNXUSDT", "Synthetix"),
    ("curve-dao-token",  "CRVUSDT",  "Curve"),
    ("lido-dao",         "LDOUSDT",  "Lido"),
]

# ─── CoinGecko OHLC Daten holen ──────────────────────────────────────────────
def get_ohlc_coingecko(coin_id, days=14):
    """
    CoinGecko /coins/{id}/ohlc endpoint
    days=1 → 30min Kerzen, days=7/14 → 4h Kerzen
    Kostenlos, kein API Key nötig
    """
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc?vs_currency=usd&days={days}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json"
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        candles = []
        for item in data:
            candles.append({
                "time":   item[0],
                "open":   float(item[1]),
                "high":   float(item[2]),
                "low":    float(item[3]),
                "close":  float(item[4]),
                "volume": 0,
            })
        return candles
    except Exception as e:
        print(f"      [CoinGecko Fehler {coin_id}]: {type(e).__name__}: {e}")
        return None

def get_market_data(coin_id):
    """Holt aktuellen Preis + Volumen von CoinGecko"""
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}?localization=false&tickers=false&community_data=false&developer_data=false"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json"
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        market = data.get("market_data", {})
        return {
            "price":       market.get("current_price", {}).get("usd", 0),
            "volume_24h":  market.get("total_volume",  {}).get("usd", 0),
            "change_24h":  market.get("price_change_percentage_24h", 0),
            "change_7d":   market.get("price_change_percentage_7d",  0),
            "change_1h":   market.get("price_change_percentage_1h_in_currency", {}).get("usd", 0),
        }
    except Exception as e:
        print(f"      [CoinGecko Market Fehler {coin_id}]: {e}")
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

# ─── Analyse ──────────────────────────────────────────────────────────────────
def analyze_candles(candles):
    if not candles or len(candles) < 30:
        return None
    closes  = [c["close"] for c in candles]
    price   = closes[-1]
    rsi_v   = rsi(closes)
    macd_l, sig, hist = macd_calc(closes)
    bb_u, bb_m, bb_l  = bollinger(closes)
    trend   = ema_trend(closes)
    e20     = ema(closes, 20)
    e50     = ema(closes, 50)

    bull = bear = 0
    details = {}

    # EMA Trend (2 Punkte)
    if trend == "bull":
        bull += 2
        details["EMA"] = "✅ Aufwärtstrend"
    elif trend == "bear":
        bear += 2
        details["EMA"] = "✅ Abwärtstrend"
    else:
        details["EMA"] = "⚠️ Kein klarer Trend"

    # MACD (2 Punkte)
    if macd_l is not None and sig is not None:
        if macd_l > sig and hist and hist > 0:
            bull += 2
            details["MACD"] = f"✅ MACD bullish"
        elif macd_l < sig and hist and hist < 0:
            bear += 2
            details["MACD"] = f"✅ MACD bearish"
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
        "price": price, "ema_trend": trend,
    }

# ─── Coin analysieren ─────────────────────────────────────────────────────────
def analyze_coin(coin_id, symbol, name):
    # Kurzfristig (1 Tag = 30min Kerzen)
    candles_short = get_ohlc_coingecko(coin_id, days=1)
    time.sleep(1.5)  # CoinGecko Rate Limit
    # Mittelfristig (7 Tage = 4h Kerzen)
    candles_mid = get_ohlc_coingecko(coin_id, days=7)
    time.sleep(1.5)
    # Langfristig (30 Tage = 4h Kerzen)
    candles_long = get_ohlc_coingecko(coin_id, days=30)
    time.sleep(1.5)
    # Marktdaten
    market = get_market_data(coin_id)
    time.sleep(1.5)

    if not candles_short or not candles_mid or not candles_long:
        return None

    r_short = analyze_candles(candles_short)
    r_mid   = analyze_candles(candles_mid)
    r_long  = analyze_candles(candles_long)

    if not r_short or not r_mid or not r_long:
        return None

    # Alle 3 müssen übereinstimmen
    dirs = [r_short["direction"], r_mid["direction"], r_long["direction"]]
    if dirs.count("BUY") == 3:
        final_dir = "BUY"
    elif dirs.count("SELL") == 3:
        final_dir = "SELL"
    else:
        return None

    # RSI Filter
    rsi_short = r_short["rsi"]
    rsi_mid   = r_mid["rsi"]
    if rsi_short:
        if final_dir == "BUY" and rsi_short > 75:
            print(f"   RSI kurzfristig {rsi_short:.1f} > 75 — blockiert")
            return None
        if final_dir == "SELL" and rsi_short < 25:
            print(f"   RSI kurzfristig {rsi_short:.1f} < 25 — blockiert")
            return None

    # H4 MACD Filter
    macd_long = r_long["macd"]
    if macd_long is not None:
        if final_dir == "BUY" and macd_long < 0:
            print(f"   Langfrist MACD bearish — BUY blockiert")
            return None
        if final_dir == "SELL" and macd_long > 0:
            print(f"   Langfrist MACD bullish — SELL blockiert")
            return None

    # EMA Trend Filter
    long_trend = r_long["ema_trend"]
    if final_dir == "BUY" and long_trend == "bear":
        print(f"   Langfrist EMA Abwärtstrend — BUY blockiert")
        return None
    if final_dir == "SELL" and long_trend == "bull":
        print(f"   Langfrist EMA Aufwärtstrend — SELL blockiert")
        return None

    # Score
    total = (r_short["bull" if final_dir == "BUY" else "bear"] * 2 +
             r_mid["bull"   if final_dir == "BUY" else "bear"] +
             r_long["bull"  if final_dir == "BUY" else "bear"])

    # Preis + SL/TP
    price = market["price"] if market else r_short["price"]
    sl_pct = 3.0 if final_dir == "BUY" else 3.0
    crv    = 4
    sl     = price * (1 - sl_pct/100) if final_dir == "BUY" else price * (1 + sl_pct/100)
    tp3    = price * (1 + sl_pct/100 * 3) if final_dir == "BUY" else price * (1 - sl_pct/100 * 3)
    tp4    = price * (1 + sl_pct/100 * 4) if final_dir == "BUY" else price * (1 - sl_pct/100 * 4)
    tp5    = price * (1 + sl_pct/100 * 5) if final_dir == "BUY" else price * (1 - sl_pct/100 * 5)

    profits = {}
    for kapital in [50, 100, 200, 500]:
        risiko = kapital * (sl_pct / 100) * HEBEL
        profits[kapital] = {"risiko": risiko, "gewinn": risiko * crv}

    return {
        "coin_id": coin_id, "symbol": symbol, "name": name,
        "direction": final_dir, "score": total, "price": price,
        "sl": sl, "tp3": tp3, "tp4": tp4, "tp5": tp5,
        "crv": crv, "sl_pct": sl_pct, "profits": profits,
        "r_short": r_short, "r_mid": r_mid, "r_long": r_long,
        "market": market,
    }

# ─── Discord ──────────────────────────────────────────────────────────────────
def send_discord(r):
    if not DISCORD_WEBHOOK:
        return
    emoji = "🟢" if r["direction"] == "BUY" else "🔴"
    color = 0x00c853 if r["direction"] == "BUY" else 0xd50000

    def tf_line(label, data):
        arrow = "📈" if data["direction"] == "BUY" else "📉"
        rsi_v = f"{data['rsi']:.1f}" if data["rsi"] else "N/A"
        macd_a = "▲" if data["macd"] and data["macd"] > 0 else "▼"
        return f"{arrow} **{label}**: RSI {rsi_v} | MACD {macd_a} | EMA {data['ema_trend']}\n"

    tf_text = (tf_line("Kurzfristig (30m)", r["r_short"]) +
               tf_line("Mittelfristig (4h)", r["r_mid"]) +
               tf_line("Langfristig (30T)", r["r_long"]))

    details = r["r_short"]["details"]
    detail_text = "\n".join(list(details.values())[:4])

    market = r["market"] or {}
    market_text = (
        f"1h: {market.get('change_1h', 0):+.2f}% | "
        f"24h: {market.get('change_24h', 0):+.2f}% | "
        f"7d: {market.get('change_7d', 0):+.2f}%"
    )

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
            f"**Starkes {r['direction']} Signal auf allen Timeframes!**\n"
            f"Score: **{r['score']} Punkte** | CRV: **{r['crv']}:1**"
        ),
        "fields": [
            {"name": "📊 Multi-Timeframe",            "value": tf_text,      "inline": False},
            {"name": "📈 Markt Performance",          "value": market_text,  "inline": False},
            {"name": "🔍 Indikator Details",          "value": detail_text,  "inline": False},
            {"name": "💰 Einstieg",                   "value": f"${r['price']:.4f}", "inline": True},
            {"name": "🛑 Stop Loss",                  "value": f"${r['sl']:.4f} (-{r['sl_pct']:.1f}%)", "inline": True},
            {"name": "🎯 Take Profits",               "value": tp_text,      "inline": False},
            {"name": "💵 Gewinn/Verlust (5x Hebel)",  "value": profit_text,  "inline": False},
            {"name": "⚠️ Hinweis",                   "value": "Kein Finanzrat. Immer eigenes Risikomanagement verwenden!", "inline": False},
        ],
        "footer": {"text": "Crypto Bot • CoinGecko API • 30m + 4h + 30T Analyse"},
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
    print("  Crypto Signal Bot — CoinGecko API")
    print(f"  {len(TOP_CRYPTOS)} Coins | Min Score: {MIN_SCORE}")
    print("  30min + 4h + 30 Tage Analyse")
    print("=" * 55)

    last_signals = {}

    while True:
        now = datetime.utcnow().strftime("%H:%M:%S UTC")
        print(f"\n[{now}] Scanne {len(TOP_CRYPTOS)} Coins...")
        strong = []

        for coin_id, symbol, name in TOP_CRYPTOS:
            try:
                print(f"   {name}...", end=" ", flush=True)
                result = analyze_coin(coin_id, symbol, name)
                if result and result["score"] >= MIN_SCORE:
                    sig_key = f"{coin_id}_{result['direction']}"
                    if sig_key != last_signals.get(coin_id):
                        strong.append(result)
                        last_signals[coin_id] = sig_key
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
            print(f"\n🚨 {len(top)} Signal(e)!")
            for r in top:
                send_discord(r)
        else:
            print("\n😴 Keine Signale.")

        print(f"\nNächster Scan in {SCAN_EVERY // 60} Min...")
        time.sleep(SCAN_EVERY)

if __name__ == "__main__":
    main()
