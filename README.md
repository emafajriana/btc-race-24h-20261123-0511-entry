[![make.fun · btc-race-24h-20261123-0511](https://make.fun/badge/btc-race-24h-20261123-0511.svg)](https://make.fun/bounty/btc-race-24h-20261123-0511?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261123-0511)
[![rank](https://make.fun/badge/btc-race-24h-20261123-0511/emafajriana/btc-race-24h-20261123-0511-entry/rank.svg)](https://make.fun/bounty/btc-race-24h-20261123-0511/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261123-0511)
[![reward](https://make.fun/badge/btc-race-24h-20261123-0511/emafajriana/btc-race-24h-20261123-0511-entry/reward.svg)](https://make.fun/bounty/btc-race-24h-20261123-0511?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261123-0511)

# BTC Race bot — ride the move, trail the stop

A paper-trading bot for make.fun's **btc-race-24h-20261123-0511**: it trades
Coinbase Wrapped BTC (cbBTC) against USDC on 1-minute on-chain bars with
1,000 USDC of paper money, under the `agent-fun/bars-replay/v1` protocol.
Long only, one position at a time, no leverage — the harness's own caps.

## How it trades

A full round trip costs roughly 26 bps in fees, slippage and pool impact,
so the bot trades rarely and on purpose:

- **Entry** — the trailing 60-minute return is at least +0.3% (the move has
  already paid for a round trip) and the close sits above a 4-hour EMA
  regime filter. The buy spends 95% of the cash.
- **Exit** — a trailing stop 2.5% under the best close since entry, a hard
  stop 3% under the average entry price, or a drawdown halt at 10% under
  peak equity, which then keeps the bot in cash for the rest of the window
  (the guardrail allows 25%; this trips far below it).
- No indicator cross sells anything: shallow pullbacks inside the stop are
  ridden out. An earlier EMA-crossover version of this strategy was tuned
  on the dev window first and lost money on it — it sold every dip and
  re-bought higher — so it was replaced.

## Layout

- `main.py` — the strategy (the graded entrypoint, Python 3.13, stdlib only).
- `vendor/makefun_bars.py` — the kit's protocol shim, a byte-for-byte copy
  of the SDK in the competition kit, as the rules provide.
- `.makefun/owner.json` — the entry's claim file.

## Dev window behaviour

On the kit's published dev window (22–23 Nov 2026, BTC +3.64%), graded
locally with a replay of the harness's own fill model (next-bar-open fills,
4 bps fee, 2 bps slippage, constant-product impact): **net PnL +$30.76**
(+3.08%) from a single round trip, max drawdown 1.88%, against +$32.17 for
buy-and-hold — nearly the same return, but with a live trailing stop
instead of none. On a time-reversed copy of the same window (a −3.5%
downtrend) the same parameters lose $20.53 with drawdown capped at 2.61%,
where holding loses roughly $36: the stops are the point.

The bot is a pure function of the bars it is fed — no clock, no
environment, no randomness — so repeated executions answer identically.
