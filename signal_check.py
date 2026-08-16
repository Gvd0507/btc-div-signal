import requests, math, os, time

TELEGRAM_TOKEN     = os.environ['TELEGRAM_TOKEN']
TELEGRAM_CHAT      = os.environ['TELEGRAM_CHAT']
CC_KEY             = os.environ['CRYPTO_COMPARE_KEY']

COINS       = ['ETH','SOL','BNB','AVAX','MATIC','ARB']
MAINT       = 0.004
MIN_CANDLES = 30

QUOTE_CURRENCIES = ['USDT', 'USD']

# ─── TELEGRAM ────────────────────────────────────────────────────────────────

def send(msg):
    try:
        r = requests.post(
            f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
            json={'chat_id': TELEGRAM_CHAT, 'text': msg, 'parse_mode': 'HTML'},
            timeout=15
        )
        print(f"Telegram: {r.status_code}")
    except Exception as e:
        print(f"Telegram error: {e}")

# ─── DATA ────────────────────────────────────────────────────────────────────

def get_candles(symbol, limit=60):
    try:
        for tsym in QUOTE_CURRENCIES:
            r = requests.get(
                'https://min-api.cryptocompare.com/data/v2/histohour',
                params={
                    'fsym':    symbol,
                    'tsym':    tsym,
                    'limit':   limit,
                    # Keep query param for compatibility with older examples.
                    'api_key': CC_KEY
                },
                headers={
                    # CryptoCompare's preferred auth mechanism.
                    'authorization': f'Apikey {CC_KEY}'
                },
                timeout=20
            )

            if r.status_code != 200:
                snippet = r.text[:200].replace('\n', ' ')
                print(f"CryptoCompare HTTP {r.status_code} {symbol}/{tsym}: {snippet}")
                continue

            data = r.json()
            if data.get('Response') != 'Success':
                msg = data.get('Message', 'unknown')
                print(f"CryptoCompare error {symbol}/{tsym}: {msg}")
                continue

            raw = data.get('Data', {}).get('Data', [])
            if not raw:
                print(f"CryptoCompare returned 0 rows for {symbol}/{tsym}")
                continue

            result = []
            for c in raw:
                try:
                    t  = int(c['time'])
                    o  = float(c['open'])
                    h  = float(c['high'])
                    l  = float(c['low'])
                    cl = float(c['close'])
                    v  = float(c.get('volumefrom', c.get('volumeto', 0.0)))
                    if cl <= 0 or h < l or v < 0:
                        continue
                    result.append({'t': t, 'o': o, 'h': h, 'l': l, 'c': cl, 'v': v})
                except (KeyError, ValueError, TypeError):
                    continue

            # Drop last row — current incomplete candle distorts ADX, beta, vol z-score
            complete = result[:-1] if len(result) > 1 else result
            print(f"  {symbol}/{tsym}: {len(complete)} complete candles")
            if complete:
                return complete

        # Fallback to Binance public klines when CryptoCompare quota is exhausted.
        try:
            pair = f"{symbol}USDT"
            r = requests.get(
                'https://api.binance.com/api/v3/klines',
                params={
                    'symbol': pair,
                    'interval': '1h',
                    'limit': limit + 1,
                },
                timeout=20
            )
            if r.status_code != 200:
                snippet = r.text[:200].replace('\n', ' ')
                print(f"Binance HTTP {r.status_code} {pair}: {snippet}")
                return []

            rows = r.json()
            if not isinstance(rows, list) or not rows:
                print(f"Binance returned 0 rows for {pair}")
                return []

            out = []
            for row in rows:
                try:
                    t = int(row[0]) // 1000
                    o = float(row[1])
                    h = float(row[2])
                    l = float(row[3])
                    c = float(row[4])
                    v = float(row[5])
                    if c <= 0 or h < l or v < 0:
                        continue
                    out.append({'t': t, 'o': o, 'h': h, 'l': l, 'c': c, 'v': v})
                except (ValueError, TypeError, IndexError):
                    continue

            complete = out[:-1] if len(out) > 1 else out
            print(f"  {pair} via Binance fallback: {len(complete)} complete candles")
            return complete
        except Exception as be:
            print(f"Binance fallback error {symbol}: {be}")
            return []
    except Exception as e:
        print(f"get_candles error {symbol}: {e}")
        return []

# ─── MATH ────────────────────────────────────────────────────────────────────

def log_ret(candles):
    result = []
    for i in range(1, len(candles)):
        try:
            p, c = candles[i-1]['c'], candles[i]['c']
            result.append(math.log(c / p) if p > 0 and c > 0 else 0.0)
        except Exception:
            result.append(0.0)
    return result

def rolling_beta(btc_r, alt_r, w):
    w = min(w, len(btc_r), len(alt_r))
    if w < 2:
        return 0.0
    b, a   = btc_r[-w:], alt_r[-w:]
    bm, am = sum(b)/w, sum(a)/w
    cov = sum((b[i]-bm)*(a[i]-am) for i in range(w))
    var = sum((b[i]-bm)**2 for i in range(w))
    return cov/var if var != 0 else 0.0

def compute_adx(candles, p=14):
    # Proper Wilder-smoothed ADX — matches TradingView output
    if len(candles) < p * 2 + 1:
        return 20.0
    trs, dps, dms = [], [], []
    for i in range(1, len(candles)):
        c, prev = candles[i], candles[i-1]
        tr   = max(c['h']-c['l'], abs(c['h']-prev['c']), abs(c['l']-prev['c']))
        up   = c['h'] - prev['h']
        down = prev['l'] - c['l']
        trs.append(tr)
        dps.append(up   if up   > down and up   > 0 else 0)
        dms.append(down if down > up   and down > 0 else 0)
    atr = sum(trs[:p])
    adp = sum(dps[:p])
    adm = sum(dms[:p])
    dx_vals = []
    for i in range(p, len(trs)):
        atr = atr - atr/p + trs[i]
        adp = adp - adp/p + dps[i]
        adm = adm - adm/p + dms[i]
        if atr == 0:
            dx_vals.append(0.0)
            continue
        dip   = 100.0 * adp / atr
        dim   = 100.0 * adm / atr
        denom = dip + dim
        dx_vals.append(100.0 * abs(dip-dim)/denom if denom else 0.0)
    if len(dx_vals) < p:
        return 20.0
    adx_val = sum(dx_vals[:p]) / p
    for dx in dx_vals[p:]:
        adx_val = (adx_val * (p-1) + dx) / p
    return adx_val

def swing_low(candles, n=3):
    if len(candles) < 2*n+1:
        return None
    for i in range(len(candles)-n-1, n-1, -1):
        c = candles[i]
        if (all(candles[j]['l'] > c['l'] for j in range(i-n, i)) and
            all(candles[j]['l'] > c['l'] for j in range(i+1, min(i+n+1, len(candles))))):
            return {'price': c['l'], 'idx': i}
    return None

def swing_forming(candles, n=3):
    if len(candles) < n+2:
        return None
    for offset in range(1, n):
        i = len(candles)-1-offset
        if i < n: continue
        c = candles[i]
        if (all(candles[j]['l'] > c['l'] for j in range(max(0,i-n), i)) and
            all(candles[j]['l'] > c['l'] for j in range(i+1, len(candles)))):
            return c['l']
    return None

def vol_zscore(candles, w=24):
    w = min(w, len(candles)-1)
    if w < 2: return 0.0
    vols = [c['v'] for c in candles[-(w+1):-1]]
    if not vols: return 0.0
    mean = sum(vols)/len(vols)
    std  = math.sqrt(sum((v-mean)**2 for v in vols)/len(vols))
    return (candles[-1]['v']-mean)/std if std else 0.0

# ─── MAIN SCAN ───────────────────────────────────────────────────────────────

print("=== BTC-Alt Divergence Scan ===")
print("Fetching BTC...")
btc = get_candles('BTC', limit=60)

if len(btc) < MIN_CANDLES:
    send(
        f"⚠️ <b>Scanner error</b>\n"
        f"Got only {len(btc)} BTC candles from CryptoCompare.\n"
        f"Check that CRYPTO_COMPARE_KEY secret is set correctly."
    )
    print(f"Only {len(btc)} BTC candles. Exiting.")
    exit(0)

btc_r       = log_ret(btc)
btc_adx     = compute_adx(btc)
regime      = 'RANGING' if btc_adx < 25 else 'TRENDING'
btc_swing   = swing_low(btc)
btc_forming = swing_forming(btc)
btc_vz      = vol_zscore(btc)

print(f"BTC price=${btc[-1]['c']:,.2f} ADX={btc_adx:.1f} Regime={regime}")
print(f"Swing confirmed={btc_swing is not None} Forming={btc_forming is not None}")

# ─── ALERT 1: EARLY WARNING ───────────────────────────────────────────────────

if btc_forming is not None and regime == 'RANGING':
    print("Swing forming — building early alert...")
    watching = []
    for coin in COINS:
        try:
            alt  = get_candles(coin, limit=60)
            time.sleep(0.4)
            if len(alt) < MIN_CANDLES: continue
            sw   = swing_low(alt)
            held = sw is not None and alt[-1]['l'] > sw['price']
            watching.append(f"  {coin}/USDT — {'holding ✓' if held else 'followed BTC ✗'}")
        except Exception as e:
            print(f"  Watch error {coin}: {e}")
    watch_text = "\n".join(watching) if watching else "  (no data)"
    send(
        f"⚠️ <b>WATCH — BTC swing low forming</b>\n\n"
        f"BTC potential low: ${btc_forming:,.4f}\n"
        f"Regime: RANGING (ADX {btc_adx:.0f})\n"
        f"Waiting ~3h for confirmation\n\n"
        f"Alt watch:\n{watch_text}\n\n"
        f"<i>Do not enter yet. Confirmation alert follows.</i>"
    )
    print("Early alert sent.")

# ─── ALERT 2: FULL CONFIRMED SIGNAL ──────────────────────────────────────────

if btc_swing is not None and regime == 'RANGING':
    print(f"\nSwing confirmed at ${btc_swing['price']:.4f} — scanning alts...")

    for coin in COINS:
        try:
            print(f"\nScanning {coin}...")
            alt = get_candles(coin, limit=60)
            time.sleep(0.4)

            if len(alt) < MIN_CANDLES:
                print(f"  Only {len(alt)} candles, skipping")
                continue

            alt_r   = log_ret(alt)
            n       = min(len(btc_r), len(alt_r))
            if n < 4:
                print(f"  Return data too short ({n}), skipping")
                continue

            beta4h  = rolling_beta(btc_r[-n:], alt_r[-n:], 4)
            beta24h = rolling_beta(btc_r[-n:], alt_r[-n:], min(24, n))
            vz      = vol_zscore(alt)
            alt_sw  = swing_low(alt)
            last    = alt[-1]

            c1 = beta4h < 0.3 and beta24h > 0.8
            c3 = alt_sw is not None and last['l'] > alt_sw['price']
            c4 = vz > 1.0

            print(f"  beta4h={beta4h:.3f} beta24h={beta24h:.3f} vz={vz:.2f} c1={c1} c3={c3} c4={c4}")

            if not (c1 and c3 and c4):
                print(f"  Conditions not met, skipping")
                continue

            beta_s = min((0.3-beta4h)/0.3, 1.0)*30 if beta4h < 0.3 else 0
            oi_s   = min((vz-1.0)/2.0, 1.0)*30 if vz > 1.0 else 0
            conf   = beta_s + oi_s + 25 + 15
            tier   = 'A' if conf >= 75 else 'B' if conf >= 55 else 'C'

            if tier == 'C':
                print(f"  Tier C (conf={conf:.0f}), skipping")
                continue

            entry     = last['c']
            stop      = alt_sw['price'] * 0.995
            stop_dist = (entry - stop) / entry

            if stop_dist <= 0 or stop >= entry:
                print(f"  Invalid stop, skipping")
                continue

            btc_mag    = abs(btc[-1]['c']-btc_swing['price'])/btc_swing['price'] if btc_swing['price'] > 0 else 0
            target     = entry + max(stop_dist*entry*1.5, entry*btc_mag*1.5)
            rr         = (target-entry)/(entry-stop)

            if rr < 1.5:
                print(f"  R:R={rr:.2f} < 1.5, skipping")
                continue

            ideal_lev = 0.25 / stop_dist
            max_safe  = int(1.0 / (stop_dist + MAINT))
            lev       = min(int(ideal_lev), max_safe, 100)

            if lev < 1:
                print(f"  Leverage < 1, skipping")
                continue

            icon = '🟢' if tier == 'A' else '🔵'
            send(
                f"{icon} <b>SIGNAL — {coin}/USDT LONG</b>\n\n"
                f"Score: <b>{tier} — {conf:.0f}/100</b>\n"
                f"{'─'*28}\n"
                f"Entry      ${entry:.4f}\n"
                f"Stop       ${stop:.4f}  (−{stop_dist*100:.2f}%)\n"
                f"Target     ${target:.4f}  (+{(target-entry)/entry*100:.2f}%)\n"
                f"Leverage   {lev}x  (25% risk)\n"
                f"R:R        1 : {rr:.2f}\n"
                f"{'─'*28}\n"
                f"Regime     RANGING ✓  (ADX {btc_adx:.0f})\n"
                f"Vol score  {vz:.2f}σ ✓\n"
                f"Beta 4h    {beta4h:.3f} ✓  (baseline {beta24h:.2f})\n"
                f"{'─'*28}\n"
                f"<i>Expires 4h. Invalidates below ${stop:.4f}</i>"
            )
            print(f"  Signal sent — {tier} tier conf={conf:.0f} lev={lev}x")
            time.sleep(1)

        except Exception as e:
            print(f"  Unexpected error {coin}: {e}")
            continue

elif btc_swing is None:
    print("\nNo confirmed BTC swing low.")
elif regime == 'TRENDING':
    print(f"\nBTC trending (ADX {btc_adx:.1f}) — signals filtered.")

print("\n=== Scan complete ===")