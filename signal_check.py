import requests, json, math, os, time

TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
TELEGRAM_CHAT  = os.environ['TELEGRAM_CHAT']
COINS = ['ETHUSDT','SOLUSDT','BNBUSDT','AVAXUSDT','MATICUSDT','ARBUSDT']
MAINT = 0.004

def send(msg):
    requests.post(
        f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage',
        json={'chat_id': TELEGRAM_CHAT, 'text': msg, 'parse_mode': 'HTML'}
    )

def get_candles(symbol, interval='1h', limit=50):
    r = requests.get(
        f'https://fapi.binance.com/fapi/v1/klines',
        params={'symbol': symbol, 'interval': interval, 'limit': limit}
    )
    return [{'t':c[0],'o':float(c[1]),'h':float(c[2]),'l':float(c[3]),'c':float(c[4]),'v':float(c[5])} for c in r.json()]

def log_ret(candles):
    return [math.log(candles[i]['c']/candles[i-1]['c']) for i in range(1,len(candles))]

def rolling_beta(btc_r, alt_r, w=4):
    b, a = btc_r[-w:], alt_r[-w:]
    bm = sum(b)/w; am = sum(a)/w
    cov = sum((b[i]-bm)*(a[i]-am) for i in range(w))
    var = sum((b[i]-bm)**2 for i in range(w))
    return cov/var if var else 0

def adx(candles, p=14):
    tr_sum = dm_p = dm_m = 0
    for i in range(len(candles)-p, len(candles)):
        c, prev = candles[i], candles[i-1]
        tr = max(c['h']-c['l'], abs(c['h']-prev['c']), abs(c['l']-prev['c']))
        dp = max(c['h']-prev['h'], 0)
        dm = max(prev['l']-c['l'], 0)
        tr_sum += tr
        dm_p += dp if dp > dm else 0
        dm_m += dm if dm > dp else 0
    if tr_sum == 0: return 20
    di_p = 100*dm_p/tr_sum; di_m = 100*dm_m/tr_sum
    return 100*abs(di_p-di_m)/(di_p+di_m) if (di_p+di_m) else 0

def swing_low(candles, n=3):
    for i in range(len(candles)-n-1, n-1, -1):
        c = candles[i]
        before_ok = all(candles[j]['l'] > c['l'] for j in range(i-n, i))
        after_ok  = all(candles[j]['l'] > c['l'] for j in range(i+1, min(i+n+1, len(candles))))
        if before_ok and after_ok:
            return {'price': c['l'], 'idx': i}
    return None

def vol_zscore(candles, w=24):
    vols = [c['v'] for c in candles[-w-1:-1]]
    mean = sum(vols)/len(vols)
    std  = math.sqrt(sum((v-mean)**2 for v in vols)/len(vols))
    return (candles[-1]['v']-mean)/std if std else 0

def btc_swing_forming(btc_candles):
    # Check if a swing low formed in the last 4 candles (not yet confirmed)
    n = 3
    for i in range(len(btc_candles)-n-1, len(btc_candles)-n+2):
        if i < n or i >= len(btc_candles): continue
        c = btc_candles[i]
        before_ok = all(btc_candles[j]['l'] > c['l'] for j in range(max(0,i-n), i))
        if before_ok and i >= len(btc_candles)-n:
            return c['l']
    return None

# Main scan
btc = get_candles('BTCUSDT')
btc_r = log_ret(btc)
btc_adx = adx(btc)
regime = 'RANGING' if btc_adx < 25 else 'TRENDING'
btc_swing = swing_low(btc)
btc_forming = btc_swing_forming(btc)

# Alert 1 — BTC swing forming (early warning)
if btc_forming and regime == 'RANGING':
    watching = []
    for coin in COINS:
        try:
            alt = get_candles(coin)
            alt_swing = swing_low(alt)
            last = alt[-1]['l']
            held = alt_swing and last > alt_swing['price']
            watching.append(f"  {coin.replace('USDT','')} — {'holding ✓' if held else 'followed BTC ✗'}")
        except: pass

    msg = (
        f"⚠️ <b>WATCH — BTC swing low forming</b>\n\n"
        f"BTC low: ${btc_forming:,.2f}\n"
        f"Waiting for 3-candle confirmation (~3h)\n"
        f"Regime: {regime} (ADX {btc_adx:.0f})\n\n"
        f"Alt status:\n" + "\n".join(watching) +
        f"\n\n<i>Do not enter yet. Confirmation alert follows if conditions met.</i>"
    )
    send(msg)

# Alert 2 — Full confirmed signals
if btc_swing and regime == 'RANGING':
    for coin in COINS:
        try:
            alt = get_candles(coin)
            alt_r = log_ret(alt)
            n = min(len(btc_r), len(alt_r))

            beta4h  = rolling_beta(btc_r[-n:], alt_r[-n:], 4)
            beta24h = rolling_beta(btc_r[-n:], alt_r[-n:], min(24,n))
            vz      = vol_zscore(alt)
            btc_vz  = vol_zscore(btc)
            alt_swing = swing_low(alt)
            alt_last  = alt[-1]

            c1 = beta4h < 0.3 and beta24h > 0.8
            c2 = True  # btc_swing confirmed above
            c3 = alt_swing and alt_last['l'] > alt_swing['price']
            c4 = vz > 1.0
            c5 = btc_vz < 0.5

            if not (c1 and c3 and c4): continue

            # Scores
            beta_s   = min((0.3-beta4h)/0.3, 1.0)*30
            oi_s     = min((vz-1.0)/2.0, 1.0)*30
            reg_s    = 25
            fund_s   = 15
            conf     = beta_s+oi_s+reg_s+fund_s
            tier     = 'A' if conf>=75 else 'B' if conf>=55 else 'C'
            if tier == 'C': continue

            entry     = alt_last['c']
            stop      = alt_swing['price']*0.995
            stop_dist = (entry-stop)/entry
            if stop_dist <= 0: continue
            btc_mag   = abs(btc[-1]['c']-btc_swing['price'])/btc_swing['price']
            target    = entry + max(stop_dist*entry*1.5, entry*btc_mag*1.5)
            rr        = (target-entry)/(entry-stop)
            if rr < 1.5: continue

            ideal_lev = 0.25/stop_dist
            max_safe  = int(1/(stop_dist+MAINT))
            lev       = min(int(ideal_lev), max_safe, 100)
            if lev < 1: continue

            icon = '🟢' if tier=='A' else '🔵'
            msg = (
                f"{icon} <b>SIGNAL CONFIRMED — {coin.replace('USDT','')}USDT LONG</b>\n\n"
                f"Score: <b>{tier} — {conf:.0f}/100</b>\n"
                f"{'─'*32}\n"
                f"Entry      ${entry:.4f}\n"
                f"Stop       ${stop:.4f}  (−{stop_dist*100:.2f}%)\n"
                f"Target     ${target:.4f}  (+{(target-entry)/entry*100:.2f}%)\n"
                f"Leverage   {lev}x  (at 25% risk)\n"
                f"R:R        1 : {rr:.2f}\n"
                f"{'─'*32}\n"
                f"Regime     RANGING ✓  (ADX {btc_adx:.0f})\n"
                f"OI Score   {vz:.2f}σ ✓\n"
                f"Beta 4h    {beta4h:.2f} ✓  (from {beta24h:.1f})\n"
                f"{'─'*32}\n"
                f"<i>Expires in 4h. Invalidates below ${stop:.4f}</i>"
            )
            send(msg)
            time.sleep(1)

        except Exception as e:
            pass

print("Scan complete")