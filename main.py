"""btc-race-24h-20261123-0511 entry bot: trend-following, long only, one asset.

The bot trades CBBTC against USDC on 1-minute bars under the
agent-fun/bars-replay/v1 protocol, spoken for it by the kit's Python shim
(vendor/makefun_bars.py, a byte-for-byte copy of the kit SDK, which the
rules leave out of the authorship counts). This file holds only the
strategy: when to be in the market, when to be out, and how much to risk.

Idea, kept deliberately plain. A round trip costs roughly 26 bps in fees,
slippage and pool impact, so the bot only trades when a move is actually
under way, and it stays in while the move lasts instead of churning. (An
EMA-crossover version of this bot was tried first and tuned on the dev
window: on 1-minute bars it sold every shallow pullback and re-bought
higher, and lost money on a rising window. The shipped rules are the
ones below.)

  - Entry: flat, and the trailing return over the lookback span is at
    least the entry threshold — the asset has already moved up by more
    than a round trip costs — with the close also above a long EMA
    regime filter when that EMA has seeded. The buy spends a fixed
    share of the cash, capped by the harness's own weight room.
  - Exit: the whole position when the close falls a trailing-stop
    distance under the highest close since the position opened, or a
    hard stop under the average entry price, or on a drawdown halt that
    then keeps the bot in cash for the rest of the window (the
    guardrail caps drawdown at 25%; the halt trips far below that).
    No indicator cross sells: pullbacks inside the stop are ridden out.

Everything is a function of the bars the harness feeds: no clock, no
environment, no randomness, so the two graded executions agree byte for
byte. Orders decided on one bar fill at the next bar's open; a sell the
market refuses is simply decided again on the next bar while its reason
still holds, because the exit checks run on every bar.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"

# Strategy parameters (bars are 1 minute). Tuned on the kit's dev window
# for a robust plateau, not a knife edge; see STATE.md in the work dir.
LOOKBACK = 60           # trailing-return span for the entry signal, minutes
ENTRY_RET = 0.003       # entry needs at least this trailing return (0.3%)
TREND_SPAN = 240        # regime EMA, minutes (4 hours)
TRAIL_STOP = 0.025      # exit this far under the best close since entry
HARD_STOP = 0.03        # exit this far under the average entry price
SIZE_SHARE = 0.95       # share of cash a buy spends
DD_HALT = 0.10          # flatten and stop for good this far under peak equity
COOLDOWN_BARS = 20      # bars to sit out after an exit before re-entering
LATE_CUTOFF = 1420      # no new entries this many scored bars in (window is 1440)
MAX_SLIPPAGE_BPS = 200  # refuse a fill priced over 2% past the deciding close


class Ema:
    """One exponential moving average, seeded with the mean of its first span."""

    def __init__(self, span):
        self.span = span
        self.warm = []
        self.value = None

    def push(self, x):
        if self.value is None:
            self.warm.append(x)
            if len(self.warm) == self.span:
                self.value = sum(self.warm) / self.span
                self.warm = []
            return self.value
        k = 2.0 / (self.span + 1)
        self.value += k * (x - self.value)
        return self.value


class Strategy:
    """The bot's whole memory: recent closes, the regime EMA, risk state."""

    def __init__(self):
        self.trend = Ema(TREND_SPAN)
        self.closes = []           # recent closes, newest last, capped
        self.peak_close = None     # best close since the position opened
        self.peak_equity = None    # highest equity marked so far
        self.halted = False        # drawdown halt: cash for the rest of the run
        self.last_exit_seq = -10 ** 9

    def note_bar(self, close):
        """Feed one close into the history and the regime EMA."""
        self.closes.append(close)
        cap = max(LOOKBACK, TREND_SPAN) + 2
        if len(self.closes) > cap:
            del self.closes[: len(self.closes) - cap]
        return self.trend.push(close)


    def entry_price(self, state, holding):
        """The position's average entry price, in the bar's raw price units."""
        s = state.symbols[SYMBOL]
        denom = holding.qty * 10 ** state.hello["capital"]["quote_scale"]
        if denom == 0:
            return None
        return holding.cost * 10 ** (s["qty_scale"] + s["price_scale"]) / denom

    def decide(self, state):
        """The orders for this batch: at most one, a buy or a full sell."""
        close = state.close(SYMBOL)
        if close is None:
            return []
        trend = self.note_bar(close)

        # Risk bookkeeping runs on every bar, trading or not.
        if self.peak_equity is None or state.equity > self.peak_equity:
            self.peak_equity = state.equity
        holding = state.positions.get(SYMBOL)
        scored_seq = state.seq - state.warmup_bars

        if holding is not None and holding.qty > 0:
            if self.peak_close is None or close > self.peak_close:
                self.peak_close = close
            entry = self.entry_price(state, holding)
            trail_hit = close <= self.peak_close * (1.0 - TRAIL_STOP)
            hard_hit = entry is not None and close <= entry * (1.0 - HARD_STOP)
            dd_hit = (
                self.peak_equity is not None
                and state.equity <= self.peak_equity * (1.0 - DD_HALT)
            )
            if trail_hit or hard_hit or dd_hit:
                if dd_hit:
                    self.halted = True
                self.last_exit_seq = state.seq
                self.peak_close = None
                return [{
                    "side": "sell",
                    "symbol": SYMBOL,
                    "qty": holding.qty,
                    "max_slippage_bps": MAX_SLIPPAGE_BPS,
                }]
            return []

        self.peak_close = None
        # Flat: look for an entry, subject to every gate.
        if state.warming_up or self.halted:
            return []
        if scored_seq >= LATE_CUTOFF:
            return []
        if state.seq - self.last_exit_seq < COOLDOWN_BARS:
            return []
        if len(self.closes) <= LOOKBACK:
            return []
        if trend is not None and close <= trend:
            return []
        trailing = close / self.closes[-1 - LOOKBACK] - 1.0
        if trailing < ENTRY_RET:
            return []
        notional = min(int(state.cash * SIZE_SHARE), state.weight_room(SYMBOL))
        min_notional = int(state.hello["fees"]["min_notional_quote_units"])
        if notional < min_notional:
            return []
        return [{
            "side": "buy",
            "symbol": SYMBOL,
            "notional_quote_units": notional,
            "max_slippage_bps": MAX_SLIPPAGE_BPS,
        }]


STRATEGY = Strategy()


def on_batch(state, batch):
    return STRATEGY.decide(state)


if __name__ == "__main__":
    makefun_bars.run(on_batch)
