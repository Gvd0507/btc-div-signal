# BTC-Alt Divergence Signal System

A systematic signal generator that monitors the rolling correlation and beta between Bitcoin perpetual futures and a basket of altcoin perpetual futures. When an altcoin refuses to follow BTC into a swing low while open interest is rising on that alt, the system flags a potential long entry and delivers an alert to Telegram with the full trade plan.

This is not a trading bot. It does not touch your exchange account. It watches the market, spots setups, and tells you about them. You decide whether to trade.

---

## What It Does

Every 10 minutes, the system fetches the latest 1-hour candles from CryptoCompare for BTC and six altcoins. It computes rolling 4-hour and 24-hour beta and Pearson correlation between BTC log returns and each alt's log returns. When the following five conditions align simultaneously within the same window, a signal fires:

1. Rolling 4h beta drops below 0.3 from a prior baseline above 0.8
2. BTC forms a confirmed swing low (held for at least 3 subsequent candles — no look-ahead)
3. The alt does not form a corresponding swing low — it holds above its own recent low
4. Alt volume z-score exceeds 1.0 standard deviation above its 30-day mean (proxy for OI rising)
5. BTC volume is flat or falling (proxy for BTC OI unwinding)

Each signal gets a confidence score from 0 to 100 based on how strongly each condition holds. Signals scoring above 75 are tier A. Above 55 are tier B. The system only sends Telegram alerts for A and B tier signals — C tier is silently discarded.

For every alert, the system calculates a suggested leverage based on your risk tolerance. If you are willing to lose 25% of your trade capital on a stop hit, and the stop is 2% away from entry, the required leverage is 12.5x — rounded down to 12x for safety. The system also computes the liquidation price at that leverage and verifies it sits below the stop level, so your stop fires before you get liquidated.

---

## Alert Format

**Alert 1 — Early Warning (swing forming, not yet confirmed)**

```
⚠️ WATCH — BTC swing low forming

BTC potential low: $83,240.00
Regime: RANGING (ADX 19)
Waiting ~3h for confirmation

Alt watch:
  SOL/USDT — holding above swing ✓
  ETH/USDT — holding above swing ✓
  BNB/USDT — followed BTC down ✗
  AVAX/USDT — holding above swing ✓

Do not enter yet. Confirmation alert follows.
```

**Alert 2 — Full Signal (all conditions confirmed)**

```
🟢 SIGNAL — SOL/USDT LONG

Score: A — 81/100
──────────────────────────────
Entry      $142.3000
Stop       $139.8000  (−1.75%)
Target     $147.2000  (+3.44%)
Leverage   14x  (25% risk)
R:R        1 : 1.97
──────────────────────────────
Regime     RANGING ✓  (ADX 19)
Vol score  2.1σ ✓
Beta 4h    0.180 ✓  (baseline 1.40)
──────────────────────────────
Expires 4h. Invalidates below $139.8000
```

---

## Backtesting Results

Backtest period: **February 2023 — December 2024** (23 months)
Data source: Binance Futures historical OHLCV via data.binance.vision
Coins: ETH, SOL, BNB, AVAX, MATIC, ARB vs BTC
Timeframe: 1-hour candles
Risk model: 25% of trade capital per stop hit, leverage derived from stop distance
Slippage: 8 bps entry + 8 bps exit
Fees: 0.04% taker each side

### Signal Distribution

| Metric | Value |
|---|---|
| Total signals detected | 175 |
| Tier A (confidence ≥ 75) | 51 |
| Tier B (confidence 55–74) | 63 |
| Tier C (confidence < 55) | 61 |
| Signals in ranging regime | 93 |
| Signals in trending regime | 82 |
| Average stop distance | 3.9% |
| Average suggested leverage | 13.1x |

### Equity Simulation — Starting Capital $100

Each trade uses 100% of current capital as margin. Profits and losses compound. No additional funds added.

| Filter | Trades | Final Capital | Return | Peak | Max Drawdown |
|---|---|---|---|---|---|
| All signals (no filter) | 175 | $0.08 | −99.9% | $178 | 100% |
| Tier A only | 51 | $517 | +417% | $580 | 77.5% |
| Tier A + ranging regime | 48 | $536 | +436% | $600 | 75% |
| Tier A + B, ranging only | 86 | $14 | −86% | $302 | 96% |

The clearest finding: **signal quality collapses outside Tier A in ranging markets.** Tier B signals drag the result significantly negative over a 2-year sample. Tier A signals in ranging conditions are the only filter that produces consistent positive expectancy.

### Win Rates by Holding Period (Tier A, Ranging Only)

| Hold Period | Closed Trades | Win Rate | Notes |
|---|---|---|---|
| 4 hours | 15 | 60.0% | Strongest — most setups resolve quickly |
| 12 hours | 24 | 50.0% | Decay visible, thesis weakens |
| 24 hours | 32 | 56.2% | Primary reporting window |

The 4-hour window shows the highest win rate, consistent with the signal having a shelf life. Signals that haven't resolved by 12 hours are more likely noise than edge.

### Per-Coin Results (Tier A, Ranging, 24h Window)

| Coin | Signals | Win Rate | Avg Leveraged PnL |
|---|---|---|---|
| AVAX/USDT | 8 | 75% | +15.0% |
| MATIC/USDT | 3 | 33% | +18.6% |
| SOL/USDT | 8 | 62% | +10.6% |
| BNB/USDT | 7 | 57% | +7.4% |
| ETH/USDT | 2 | 50% | +1.4% |
| ARB/USDT | 4 | 25% | −4.1% |

AVAX and SOL are the strongest performers. ARB should be watched carefully or filtered out — small sample but poor win rate. MATIC has high average PnL despite low win rate, driven by one outsized winner (+83% leveraged). ETH produces very few signals because it is the most correlated to BTC and rarely diverges enough to trigger all five conditions.

### Regime Dependency

This is the most important finding in the backtest. Signals in trending markets (ADX > 25) are nearly worthless:

| Regime | Signals | Win Rate | Avg Lev PnL |
|---|---|---|---|
| RANGING (ADX < 25) | 25 | 56.0% | +9.3% |
| TRENDING (ADX > 25) | 7 | 28.6% | −8.1% |

*(Tier A only, 24h window)*

BTC trending with ADX above 25 eventually overwhelms any alt divergence. The alt that held its swing low in hour 1 typically capitulates to BTC's trend by hour 12. **If you trade only when ADX is below 25, the strategy works. If you trade during trends, it doesn't.**

The system enforces this automatically — ADX above 25 drops the regime score to zero, making it nearly impossible for a signal to reach Tier A confidence.

### Worst and Best Individual Signals

**Worst 3 (Tier A, Ranging)**

| Date | Coin | Outcome | Leverage | Leveraged PnL |
|---|---|---|---|---|
| Sep 2024 | AVAX | Stop | 86x | −45.5% |
| Jun 2024 | ETH | Stop | 21x | −29.4% |
| May 2024 | MATIC | Stop | 19x | −28.6% |

The September 2024 AVAX loss is instructive. The 86x leverage was a consequence of a very tight stop distance (0.29%). At that leverage, a small adverse move hits the stop before the position has time to develop. **Tighter stops are not safer at high leverage — they are more vulnerable.** A maximum leverage cap of 20x–25x would have limited this loss to −5% to −8% on the same setup.

**Best 3 (Tier A, Ranging)**

| Date | Coin | Outcome | Leverage | Leveraged PnL |
|---|---|---|---|---|
| Jul 2023 | AVAX | Target | 6x | +34.1% |
| Nov 2023 | AVAX | Target | 8x | +34.6% |
| Jul 2024 | MATIC | Target | 33x | +83.4% |

### Monthly Signal Frequency

Signal frequency varies significantly with market regime. High-frequency months (March 2024: 20 signals, June 2024: 17 signals) typically correspond to choppy, high-volatility BTC environments where correlations break down frequently. Low-frequency months (August 2024: 1 signal) correspond to strong directional BTC trends where alts follow closely and divergence never materialises.

```
2023  Feb ██ 2        Aug ██████████ 10
      Mar █ 1         Sep █████████ 9
      Apr ███ 3        Oct █████████ 9
      May ███ 3        Nov ████████ 8
      Jun ██████ 6     Dec ███████████████ 15
      Jul ████████████ 12
      
2024  Jan ██████ 6    Jul █████████ 9
      Feb ███ 3        Aug █ 1
      Mar ████████████████████ 20   Sep █████████ 9
      Apr █████ 5      Oct █████ 5
      May ████████████ 12   Nov ██ 2
      Jun █████████████████ 17   Dec ████████ 8
```

---

## What This Is Not

This system has not been independently validated. The backtest covers 23 months of one specific market cycle. Crypto markets in 2023–2024 were unusually favourable for momentum and divergence strategies due to the post-FTX recovery and ETF-driven bull market. Performance in a prolonged bear market or a highly correlated crash environment may differ significantly.

The volume z-score used as a proxy for open interest is an approximation. Real OI data from exchange archives was not used in this backtest because historical OI beyond 30 days requires paid data sources. The proxy correlation is reasonable but not identical to true OI divergence.

The 77.5% maximum drawdown on the Tier A equity curve is real. Starting with $100 and seeing it fall to $31 before recovering is psychologically difficult. Most traders would abandon the strategy at the bottom. If you cannot hold through a 75%+ drawdown, this approach is not suitable at the leverage levels modelled here.

---

## How to Use

**Prerequisites**
- A free CryptoCompare API key from [cryptocompare.com](https://www.cryptocompare.com/cryptopian/api-keys)
- A Telegram bot token from [@BotFather](https://t.me/botfather)
- A GitHub account

**Setup**

1. Fork or clone this repository
2. Open `index.html` and paste your CryptoCompare API key:
   ```js
   const CC_KEY = 'your-key-here';
   ```
3. In your GitHub repo, go to Settings → Secrets → Actions and add:
   ```
   TELEGRAM_TOKEN    your bot token
   TELEGRAM_CHAT     your chat ID
   CRYPTO_COMPARE_KEY  your CC key
   ```
4. Enable GitHub Pages: Settings → Pages → Deploy from main branch
5. The workflow in `.github/workflows/scan.yml` runs automatically every 10 minutes

**Manual Trade Execution Checklist**

When an alert fires, before entering:

- [ ] BTC ADX < 25 (visible in the alert regime tag)
- [ ] BTC swing confirmed (alert only fires after confirmation)
- [ ] Alt held above its swing low (shown in alert)
- [ ] Volume z-score > 1.0 (shown in alert)
- [ ] Signal is Tier A or B
- [ ] Funding rate on the alt is not strongly positive

Entry: market or limit at current price. Stop: 0.5% below alt's recent swing low. Target: entry + 1.5× stop distance minimum. Leverage: use the suggested leverage in the alert. Set stop-loss order immediately after entry fills.

Close the trade manually if it has not hit stop or target within 4 hours.

---

## Stack

| Component | Technology |
|---|---|
| Signal computation | GitHub Actions (Python) |
| Data source | CryptoCompare public API |
| Alerts | Telegram Bot API |
| Dashboard | Single-file HTML + JavaScript |
| Hosting | GitHub Pages |
| Cost | $0/month |

---

## License

MIT. Use freely. Trade at your own risk.

---

*Built as a personal learning project in systematic crypto trading. Not financial advice.*