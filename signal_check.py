import requests, math, os, time

TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
TELEGRAM_CHAT  = os.environ['TELEGRAM_CHAT']
COINS  = ['ETHUSDT','SOLUSDT','BNBUSDT','AVAXUSDT','MATICUSDT','ARBUSDT']
MAINT  = 0.004
MIN_CANDLES = 30  # minimum candles needed for any calculation

# ─── TELEGRAM ────────────────────────────────────────────────────────────────

def send(msg):
    try:
        requests.post(
            f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
            json={'chat_id': TELEGRAM_CHAT, 'text': msg, 'parse_mode': 'HTML'},
            timeout=10
        )
    except Exception as e:
        print(f"Telegram error: {e}")

# ─── DATA ────────────────────────────────────────────────────────────────────

def get_candles(symbol, interval='1h', limit=60):
    try:
        r = requests.get(
            'https://fapi.binance.com/fapi/v1/klines',
            params={'symbol': symbol, 'interval': interval, 'limit': limit},
            timeout=15
        )
        r.raise_for_status()
        result = []
        for c in r.json():
            try:
                t = int(c[0])
                o = float(c[1])
                h = float(c[2])
                l = float(c[3])
                cl = float(c[4])
                v = float(c[5])
                # sanity check — skip rows where values are clearly wrong
                if h < l or cl <= 0 or v < 0:
                    continue
                result.append({'t': t, 'o': o, 'h': h, 'l': l, 'c': cl, 'v': v})
            except (ValueError, TypeError, IndexError):
                continue
        return result
    except Exception as e:
        print(f"get_candles error {symbol}: {e}")
        return []

# ─── MATH ────────────────────────────────────────────────────────────────────

def log_ret(candles):
    if len(candles) < 2:
        return []
    result = []
    for i in range(1, len(candles)):
        try:
            prev = candles[i-1]['c']
            curr = candles[i]['c']
            if prev > 0 and curr > 0:
                result.append(math.log(curr / prev))
            else:
                result.append(0.0)
        except Exception:
            result.append(0.0)
    return result

def rolling_beta(btc_r, alt_r, w=4):
    if len(btc_r) < w or len(alt_r) < w:
        return 0.0
    b = btc_r[-w:]
    a = alt_r[-w:]
    bm = sum(b) / w
    am = sum(a) / w
    cov = sum((b[i] - bm) * (a[i] - am) for i in range(w))
    var = sum((b[i] - bm) ** 2 for i in range(w))
    return cov / var if var != 0 else 0.0

def rolling_corr(btc_r, alt_r, w=24):
    w = min(w, len(btc_r), len(alt_r))
    if w < 4:
        return 0.0
    b = btc_r[-w:]
    a = alt_r[-w:]
    bm = sum(b) / w
    am = sum(a) / w
    num = sum((b[i] - bm) * (a[i] - am) for i in range(w))
    db  = sum((b[i] - bm) ** 2 for i in range(w))
    da  = sum((a[i] - am) ** 2 for i in range(w))
    if db == 0 or da == 0:
        return 0.0
    return num / math.sqrt(db * da)

def compute_adx(candles, p=14):
    # Need at least p+1 candles
    if len(candles) < p + 1:
        return 20.0
    tr_sum = 0.0
    dm_p   = 0.0
    dm_m   = 0.0
    # Use last p candles, each needing its previous candle
    start = len(candles) - p
    for i in range(start, len(candles)):
        c    = candles[i]
        prev = candles[i - 1]
        tr   = max(
            c['h'] - c['l'],
            abs(c['h'] - prev['c']),
            abs(c['l'] - prev['c'])
        )
        up   = c['h'] - prev['h']
        down = prev['l'] - c['l']
        tr_sum += tr
        if up > down and up > 0:
            dm_p += up
        if down > up and down > 0:
            dm_m += down
    if tr_sum == 0:
        return 20.0
    di_p = 100.0 * dm_p / tr_sum
    di_m = 100.0 * dm_m / tr_sum
    denom = di_p + di_m
    if denom == 0:
        return 20.0
    return 100.0 * abs(di_p - di_m) / denom

def swing_low(candles, n=3):
    # Need at least 2n+1 candles for a valid swing low
    if len(candles) < 2 * n + 1:
        return None
    # Search from most recent backwards, confirming n candles after
    # Stop at index n so there's always n candles before
    for i in range(len(candles) - n - 1, n - 1, -1):
        c = candles[i]
        before_ok = all(candles[j]['l'] > c['l'] for j in range(i - n, i))
        after_ok  = all(
            candles[j]['l'] > c['l']
            for j in range(i + 1, min(i + n + 1, len(candles)))
        )
        if before_ok and after_ok:
            return {'price': c['l'], 'idx': i}
    return None

def btc_swing_forming(candles, n=3):
    # A potential swing low that has n bars before but fewer than n bars after
    # (not yet confirmed) — fires the early alert
    if len(candles) < n + 2:
        return None
    # Check the candle at position len-2 (second to last)
    # It has n bars before and 1 bar after — potential forming swing
    for offset in range(1, n + 1):
        i = len(candles) - 1 - offset
        if i < n:
            continue
        c = candles[i]
        before_ok = all(candles[j]['l'] > c['l'] for j in range(max(0, i - n), i))
        # Only 'offset' bars after exist — not yet fully confirmed
        after_existing = all(candles[j]['l'] > c['l'] for j in range(i + 1, len(candles)))
        if before_ok and after_existing and offset < n:
            return c['l']
    return None

def vol_zscore(candles, w=24):
    # Need w+1 candles: w for the distribution, 1 for current
    if len(candles) < w + 1:
        w = len(candles) - 1
    if w < 2:
        return 0.0
    vols = [c['v'] for c in candles[-(w + 1):-1]]
    if not vols:
        return 0.0
    mean = sum(vols) / len(vols)
    var  = sum((v - mean) ** 2 for v in vols) / len(vols)
    std  = math.sqrt(var) if var > 0 else 0.0
    if std == 0:
        return 0.0
    return (candles[-1]['v'] - mean) / std

# ─── MAIN SCAN ───────────────────────────────────────────────────────────────

print("Fetching BTC data...")
btc = get_candles('BTCUSDT', limit=60)

if len(btc) < MIN_CANDLES:
    send("⚠️ Signal scanner error: Could not fetch enough BTC candles from Binance.")
    print(f"Only got {len(btc)} BTC candles, need {MIN_CANDLES}. Exiting.")
    exit(0)

btc_r       = log_ret(btc)
btc_adx     = compute_adx(btc)
regime      = 'RANGING' if btc_adx < 25 else 'TRENDING'
btc_swing   = swing_low(btc)
btc_forming = btc_swing_forming(btc)
btc_vz      = vol_zscore(btc)

print(f"BTC: {len(btc)} candles | ADX {btc_adx:.1f} | Regime {regime}")
print(f"BTC swing confirmed: {btc_swing is not None} | Forming: {btc_forming is not None}")

# ─── ALERT 1: BTC SWING FORMING (early warning) ──────────────────────────────

if btc_forming is not None and regime == 'RANGING':
    print("BTC swing forming — sending early alert...")
    watching = []
    for coin in COINS:
        try:
            alt       = get_candles(coin, limit=60)
            if len(alt) < MIN_CANDLES:
                continue
            alt_swing = swing_low(alt)
            last_low  = alt[-1]['l']
            held      = alt_swing is not None and last_low > alt_swing['price']
            label     = 'holding ✓' if held else 'followed BTC ✗'
            watching.append(f"  {coin.replace('USDT','')} — {label}")
        except Exception as e:
            print(f"  Watch error {coin}: {e}")

    watch_text = "\n".join(watching) if watching else "  (no data)"
    msg = (
        f"⚠️ <b>WATCH — BTC swing low forming</b>\n\n"
        f"BTC potential low: ${btc_forming:,.4f}\n"
        f"Waiting for 3-candle confirmation (~3h)\n"
        f"Regime: {regime} (ADX {btc_adx:.0f})\n\n"
        f"Alt status:\n{watch_text}\n\n"
        f"<i>Do not enter yet. Confirmation alert will follow if all conditions met.</i>"
    )
    send(msg)
    print("Early alert sent.")

# ─── ALERT 2: FULL CONFIRMED SIGNALS ─────────────────────────────────────────

if btc_swing is not None and regime == 'RANGING':
    print("BTC swing confirmed — scanning alts for divergence signals...")

    for coin in COINS:
        try:
            alt = get_candles(coin, limit=60)
            if len(alt) < MIN_CANDLES:
                print(f"  {coin}: not enough candles ({len(alt)}), skipping")
                continue

            alt_r = log_ret(alt)
            if len(alt_r) < 4:
                continue

            n        = min(len(btc_r), len(alt_r))
            beta4h   = rolling_beta(btc_r[-n:], alt_r[-n:], min(4, n))
            beta24h  = rolling_beta(btc_r[-n:], alt_r[-n:], min(24, n))
            vz       = vol_zscore(alt)
            alt_sw   = swing_low(alt)
            alt_last = alt[-1]

            # Five conditions
            c1 = beta4h < 0.3 and beta24h > 0.8
            c3 = alt_sw is not None and alt_last['l'] > alt_sw['price']
            c4 = vz > 1.0
            c5 = btc_vz < 0.5

            print(f"  {coin}: beta4h={beta4h:.2f} beta24h={beta24h:.2f} vz={vz:.2f} c1={c1} c3={c3} c4={c4}")

            if not (c1 and c3 and c4):
                continue

            # Confidence score
            beta_s = min((0.3 - beta4h) / 0.3, 1.0) * 30 if beta4h < 0.3 else 0
            oi_s   = min((vz - 1.0) / 2.0, 1.0) * 30 if vz > 1.0 else 0
            reg_s  = 25  # already confirmed ranging
            fund_s = 15  # neutral default
            conf   = beta_s + oi_s + reg_s + fund_s
            tier   = 'A' if conf >= 75 else 'B' if conf >= 55 else 'C'

            if tier == 'C':
                print(f"  {coin}: tier C (conf {conf:.0f}), skipping")
                continue

            # Trade levels
            entry     = alt_last['c']
            stop      = alt_sw['price'] * 0.995
            stop_dist = (entry - stop) / entry

            if stop_dist <= 0 or stop >= entry:
                print(f"  {coin}: invalid stop ({stop:.4f} >= entry {entry:.4f}), skipping")
                continue

            btc_mag = abs(btc[-1]['c'] - btc_swing['price']) / btc_swing['price'] if btc_swing['price'] > 0 else 0
            target  = entry + max(stop_dist * entry * 1.5, entry * btc_mag * 1.5)
            rr      = (target - entry) / (entry - stop)

            if rr < 1.5:
                print(f"  {coin}: R:R {rr:.2f} < 1.5, skipping")
                continue

            # Leverage
            ideal_lev = 0.25 / stop_dist
            max_safe  = int(1.0 / (stop_dist + MAINT))
            lev       = min(int(ideal_lev), max_safe, 100)

            if lev < 1:
                print(f"  {coin}: leverage < 1, skipping")
                continue

            icon = '🟢' if tier == 'A' else '🔵'
            msg = (
                f"{icon} <b>SIGNAL CONFIRMED — {coin.replace('USDT','')}USDT LONG</b>\n\n"
                f"Score: <b>{tier} — {conf:.0f}/100</b>\n"
                f"{'─' * 30}\n"
                f"Entry      ${entry:.4f}\n"
                f"Stop       ${stop:.4f}  (−{stop_dist*100:.2f}%)\n"
                f"Target     ${target:.4f}  (+{(target-entry)/entry*100:.2f}%)\n"
                f"Leverage   {lev}x  (at 25% risk)\n"
                f"R:R        1 : {rr:.2f}\n"
                f"{'─' * 30}\n"
                f"Regime     RANGING ✓  (ADX {btc_adx:.0f})\n"
                f"OI zscore  {vz:.2f}σ ✓\n"
                f"Beta 4h    {beta4h:.2f} ✓  (baseline {beta24h:.2f})\n"
                f"{'─' * 30}\n"
                f"<i>Expires in 4h. Invalidates below ${stop:.4f}</i>"
            )
            send(msg)
            print(f"  {coin}: signal sent — tier {tier} conf {conf:.0f}")
            time.sleep(1)

        except Exception as e:
            print(f"  {coin}: unexpected error — {e}")
            continue

elif btc_swing is None:
    print("No confirmed BTC swing low — no signals to evaluate.")
elif regime == 'TRENDING':
    print(f"BTC trending (ADX {btc_adx:.1f}) — signals filtered out.")

print("Scan complete.")