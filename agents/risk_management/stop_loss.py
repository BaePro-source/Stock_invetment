"""
Stop-loss monitoring: fixed stop-loss and trailing stop.
"""
import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from models.stock import Stock
from config.settings import RiskConfig

logger = logging.getLogger(__name__)


class StopLossAction(Enum):
    HOLD = "보유"
    STOP_FIXED = "고정손절"      # 매입가 대비 -N%
    STOP_TRAILING = "트레일링손절"  # 고점 대비 -N%


@dataclass
class StopLossSignal:
    ticker: str
    action: StopLossAction

    current_price: float = 0.0
    entry_price: float = 0.0      # 매입가 (없으면 최초 수집가 기준)
    peak_price: float = 0.0       # 보유 기간 고점

    drawdown_from_entry: float = 0.0   # 매입가 대비 수익률
    drawdown_from_peak: float = 0.0    # 고점 대비 낙폭

    stop_fixed_price: float = 0.0      # 고정 손절가
    stop_trailing_price: float = 0.0   # 트레일링 손절가


class StopLossMonitor:
    def __init__(self, cfg: RiskConfig):
        self.cfg = cfg

    def check(self, stock: Stock, entry_price: Optional[float] = None) -> StopLossSignal:
        """
        entry_price: 실제 매입가. None이면 가격 히스토리 첫 번째 봉 종가 사용.
        """
        bars = stock.price_history
        if not bars:
            return StopLossSignal(ticker=stock.ticker, action=StopLossAction.HOLD)

        current_price = bars[-1].close
        ep = entry_price if entry_price is not None else bars[0].close
        peak_price = max(b.close for b in bars)

        drawdown_from_entry = (current_price - ep) / ep if ep > 0 else 0.0
        drawdown_from_peak = (current_price - peak_price) / peak_price if peak_price > 0 else 0.0

        stop_fixed_price = ep * (1 - self.cfg.stop_loss_pct)
        stop_trailing_price = peak_price * (1 - self.cfg.trailing_stop_pct)

        # 트레일링 손절 우선 (더 타이트한 경우가 많음)
        action = StopLossAction.HOLD
        if current_price <= stop_trailing_price:
            action = StopLossAction.STOP_TRAILING
        elif current_price <= stop_fixed_price:
            action = StopLossAction.STOP_FIXED

        signal = StopLossSignal(
            ticker=stock.ticker,
            action=action,
            current_price=current_price,
            entry_price=ep,
            peak_price=peak_price,
            drawdown_from_entry=round(drawdown_from_entry, 4),
            drawdown_from_peak=round(drawdown_from_peak, 4),
            stop_fixed_price=round(stop_fixed_price, 2),
            stop_trailing_price=round(stop_trailing_price, 2),
        )

        if action != StopLossAction.HOLD:
            logger.warning(
                f"[StopLoss] {stock.ticker} {action.value} 발동 | "
                f"현재가={current_price:,.0f} / 손절가={stop_trailing_price:,.0f} "
                f"(고점 대비 {drawdown_from_peak*100:.1f}%)"
            )

        return signal

    def check_all(self, stocks: List[Stock]) -> List[StopLossSignal]:
        signals = [self.check(s) for s in stocks]
        triggered = [s for s in signals if s.action != StopLossAction.HOLD]
        logger.info(f"[StopLoss] {len(triggered)}/{len(stocks)}개 손절 발동")
        return signals
