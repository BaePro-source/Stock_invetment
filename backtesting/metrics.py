"""
BacktestMetrics: 총수익률, 연간수익률, Sharpe, MDD, 승률 등 성과 지표.
"""
import math
import logging
from dataclasses import dataclass
from typing import List

from backtesting.simulator import Trade

logger = logging.getLogger(__name__)

TRADING_DAYS = 252


@dataclass
class BacktestMetrics:
    initial_capital: float
    final_equity: float
    total_return: float          # 총 수익률
    annualized_return: float     # 연간 환산 수익률
    sharpe_ratio: float
    max_drawdown: float          # MDD (음수)
    total_trades: int            # BUY + SELL 합계
    completed_trades: int        # 완료된 매도 건수
    win_trades: int              # 수익 실현 건수
    win_rate: float              # 승률
    avg_holding_days: float      # 평균 보유 기간
    total_commission: float      # 총 수수료 지출
    trading_days: int


class MetricsCalculator:
    def __init__(self, risk_free_rate: float = 0.03):
        self.rf = risk_free_rate

    def calculate(self, equity_curve: List[float], trades: List[Trade]) -> BacktestMetrics:
        if not equity_curve:
            return self._empty()

        initial = equity_curve[0]
        final = equity_curve[-1]
        n = len(equity_curve)

        total_ret = (final - initial) / initial if initial > 0 else 0.0
        ann_ret = (1 + total_ret) ** (TRADING_DAYS / n) - 1 if n > 1 else 0.0

        daily_rets = [
            (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
            for i in range(1, n)
            if equity_curve[i - 1] > 0
        ]

        sharpe = self._sharpe(daily_rets)
        mdd = self._mdd(equity_curve)

        sell_trades = [t for t in trades if t.action == "SELL" and t.return_pct is not None]
        win = sum(1 for t in sell_trades if t.return_pct > 0)
        win_rate = win / len(sell_trades) if sell_trades else 0.0

        holding_days = [
            (t.trade_date - t.entry_date).days
            for t in sell_trades if t.entry_date
        ]
        avg_hold = sum(holding_days) / len(holding_days) if holding_days else 0.0

        total_commission = sum(t.commission for t in trades)

        return BacktestMetrics(
            initial_capital=initial,
            final_equity=final,
            total_return=round(total_ret, 4),
            annualized_return=round(ann_ret, 4),
            sharpe_ratio=round(sharpe, 3),
            max_drawdown=round(mdd, 4),
            total_trades=len(trades),
            completed_trades=len(sell_trades),
            win_trades=win,
            win_rate=round(win_rate, 4),
            avg_holding_days=round(avg_hold, 1),
            total_commission=round(total_commission, 0),
            trading_days=n,
        )

    def _sharpe(self, daily_rets: List[float]) -> float:
        if len(daily_rets) < 2:
            return 0.0
        rf_daily = self.rf / TRADING_DAYS
        excess = [r - rf_daily for r in daily_rets]
        mean = sum(excess) / len(excess)
        variance = sum((r - mean) ** 2 for r in excess) / (len(excess) - 1)
        std = math.sqrt(variance)
        return (mean / std * math.sqrt(TRADING_DAYS)) if std > 0 else 0.0

    @staticmethod
    def _mdd(equity: List[float]) -> float:
        peak = equity[0]
        mdd = 0.0
        for v in equity:
            if v > peak:
                peak = v
            dd = (v - peak) / peak if peak > 0 else 0.0
            if dd < mdd:
                mdd = dd
        return mdd

    def _empty(self) -> BacktestMetrics:
        return BacktestMetrics(
            initial_capital=0, final_equity=0, total_return=0, annualized_return=0,
            sharpe_ratio=0, max_drawdown=0, total_trades=0, completed_trades=0,
            win_trades=0, win_rate=0, avg_holding_days=0, total_commission=0, trading_days=0,
        )
