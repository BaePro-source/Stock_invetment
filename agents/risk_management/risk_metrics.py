"""
Risk metrics: MDD, annualized volatility, Sharpe ratio, rebalancing check.
"""
import logging
import math
from dataclasses import dataclass, field
from typing import List, Optional, Dict

from models.stock import Stock
from agents.risk_management.portfolio import PortfolioAllocation, Position
from config.settings import RiskConfig

logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252


@dataclass
class StockRiskProfile:
    ticker: str
    mdd: Optional[float] = None               # 최대 낙폭 (0~1, 음수)
    volatility_annual: Optional[float] = None  # 연간 변동성
    sharpe_ratio: Optional[float] = None       # 샤프 비율 (무위험 이자율 3% 가정)
    avg_daily_return: Optional[float] = None


@dataclass
class RebalanceSignal:
    ticker: str
    current_pct: float     # 현재 비중 (시장가 반영)
    target_pct: float      # 목표 비중
    drift: float           # 이탈 폭 (current - target)
    action: str            # "매수" / "매도" / "유지"
    amount: float          # 조정 금액


@dataclass
class PortfolioRiskReport:
    stock_profiles: List[StockRiskProfile] = field(default_factory=list)
    rebalance_signals: List[RebalanceSignal] = field(default_factory=list)
    portfolio_volatility: Optional[float] = None
    warnings: List[str] = field(default_factory=list)


class RiskMetricsCalculator:
    def __init__(self, cfg: RiskConfig):
        self.cfg = cfg

    def calc_stock_risk(self, stock: Stock) -> StockRiskProfile:
        profile = StockRiskProfile(ticker=stock.ticker)
        bars = stock.price_history

        window = min(self.cfg.volatility_window, len(bars))
        if window < 5:
            return profile

        closes = [b.close for b in bars[-window:]]
        daily_returns = self._daily_returns(closes)

        if not daily_returns:
            return profile

        profile.avg_daily_return = sum(daily_returns) / len(daily_returns)
        profile.volatility_annual = self._annualized_vol(daily_returns)
        profile.sharpe_ratio = self._sharpe(daily_returns)
        profile.mdd = self._mdd(closes)

        return profile

    def check_rebalance(
        self,
        allocation: PortfolioAllocation,
        current_prices: Dict[str, float],
    ) -> List[RebalanceSignal]:
        """
        current_prices: {ticker: 현재가}
        현재 보유 포지션의 시장가 반영 비중 vs 목표 비중 비교.
        (실제 보유 수량 없이 목표 수량 기준으로 시뮬레이션)
        """
        signals = []
        total_market_value = sum(
            p.target_shares * current_prices.get(p.ticker, p.current_price)
            for p in allocation.positions
        )
        if total_market_value <= 0:
            return signals

        for pos in allocation.positions:
            cur_price = current_prices.get(pos.ticker, pos.current_price)
            market_value = pos.target_shares * cur_price
            current_pct = market_value / total_market_value
            drift = current_pct - pos.target_pct

            if abs(drift) < self.cfg.rebalance_threshold_pct:
                action = "유지"
                amount = 0.0
            elif drift > 0:
                action = "매도"
                amount = abs(drift) * total_market_value
            else:
                action = "매수"
                amount = abs(drift) * total_market_value

            signals.append(RebalanceSignal(
                ticker=pos.ticker,
                current_pct=round(current_pct, 4),
                target_pct=pos.target_pct,
                drift=round(drift, 4),
                action=action,
                amount=round(amount, 0),
            ))

        triggered = [s for s in signals if s.action != "유지"]
        if triggered:
            logger.info(f"[Rebalance] {len(triggered)}개 리밸런싱 필요")

        return signals

    # ── 지표 계산 ──────────────────────────────────────────

    @staticmethod
    def _daily_returns(closes: List[float]) -> List[float]:
        returns = []
        for i in range(1, len(closes)):
            if closes[i - 1] > 0:
                returns.append((closes[i] - closes[i - 1]) / closes[i - 1])
        return returns

    @staticmethod
    def _annualized_vol(daily_returns: List[float]) -> float:
        if len(daily_returns) < 2:
            return 0.0
        mean = sum(daily_returns) / len(daily_returns)
        variance = sum((r - mean) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
        return math.sqrt(variance * TRADING_DAYS_PER_YEAR)

    @staticmethod
    def _sharpe(daily_returns: List[float], risk_free_annual: float = 0.03) -> float:
        if not daily_returns:
            return 0.0
        rf_daily = risk_free_annual / TRADING_DAYS_PER_YEAR
        excess = [r - rf_daily for r in daily_returns]
        mean_excess = sum(excess) / len(excess)
        if len(excess) < 2:
            return 0.0
        std = math.sqrt(sum((r - mean_excess) ** 2 for r in excess) / (len(excess) - 1))
        return (mean_excess / std * math.sqrt(TRADING_DAYS_PER_YEAR)) if std > 0 else 0.0

    @staticmethod
    def _mdd(closes: List[float]) -> float:
        peak = closes[0]
        max_drawdown = 0.0
        for c in closes:
            if c > peak:
                peak = c
            dd = (c - peak) / peak
            if dd < max_drawdown:
                max_drawdown = dd
        return round(max_drawdown, 4)
