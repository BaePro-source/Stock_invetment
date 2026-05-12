"""
PortfolioSimulator: 매수/매도/수수료를 반영한 포트폴리오 시뮬레이터.
"""
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    ticker: str
    action: str              # BUY / SELL
    trade_date: date
    price: float
    shares: int
    amount: float            # 거래 금액 (수수료 제외)
    commission: float
    entry_date: Optional[date] = None    # SELL 시 진입일
    entry_price: Optional[float] = None  # SELL 시 진입가
    return_pct: Optional[float] = None   # SELL 시 수익률


@dataclass
class _Position:
    ticker: str
    shares: int
    entry_price: float
    entry_date: date


class PortfolioSimulator:
    def __init__(self, initial_capital: float, commission_pct: float):
        self.initial_capital = initial_capital
        self.commission_pct = commission_pct
        self.cash = initial_capital
        self._positions: Dict[str, _Position] = {}
        self.trades: List[Trade] = []
        self.equity_curve: List[float] = []

    # ── 외부 인터페이스 ──────────────────────────────────────

    def rebalance(
        self, trade_date: date, target_weights: Dict[str, float], prices: Dict[str, float]
    ) -> None:
        """목표 비중으로 포트폴리오 재편성. 먼저 제거 종목 매도 후 비중 조정."""
        # 1. 목표에 없는 종목 전량 매도
        for ticker in list(self._positions.keys()):
            if ticker not in target_weights:
                self._sell_all(ticker, prices.get(ticker), trade_date)

        # 2. 현재 포트폴리오 가치 기준으로 목표 금액 계산 후 매수/조정
        pv = self._portfolio_value(prices)
        for ticker, weight in target_weights.items():
            price = prices.get(ticker)
            if not price or price <= 0:
                continue
            target_amount = pv * weight
            current_shares = self._positions[ticker].shares if ticker in self._positions else 0
            diff = target_amount - current_shares * price

            if diff >= price * (1 + self.commission_pct):
                # 매수 가능 주수 (수수료 포함)
                buyable = int(diff / (price * (1 + self.commission_pct)))
                if buyable > 0:
                    self._buy(ticker, buyable, price, trade_date)
            elif diff <= -price:
                # 과잉 보유 → 일부 매도
                to_sell = min(int(-diff / price), current_shares)
                if to_sell > 0:
                    self._sell(ticker, to_sell, price, trade_date)

    def mark_to_market(self, d: date, prices: Dict[str, float]) -> None:
        self.equity_curve.append(self._portfolio_value(prices))

    def liquidate(self, trade_date: date, prices: Dict[str, float]) -> None:
        for ticker in list(self._positions.keys()):
            self._sell_all(ticker, prices.get(ticker, self._positions[ticker].entry_price), trade_date)

    # ── 내부 ─────────────────────────────────────────────────

    def _portfolio_value(self, prices: Dict[str, float]) -> float:
        value = self.cash
        for ticker, pos in self._positions.items():
            value += pos.shares * prices.get(ticker, pos.entry_price)
        return value

    def _buy(self, ticker: str, shares: int, price: float, trade_date: date) -> None:
        amount = shares * price
        commission = amount * self.commission_pct
        if amount + commission > self.cash:
            shares = int(self.cash / (price * (1 + self.commission_pct)))
            if shares <= 0:
                return
            amount = shares * price
            commission = amount * self.commission_pct

        self.cash -= amount + commission

        if ticker in self._positions:
            pos = self._positions[ticker]
            total = pos.shares + shares
            avg_price = (pos.shares * pos.entry_price + shares * price) / total
            self._positions[ticker] = _Position(ticker, total, avg_price, pos.entry_date)
        else:
            self._positions[ticker] = _Position(ticker, shares, price, trade_date)

        self.trades.append(Trade(
            ticker=ticker, action="BUY", trade_date=trade_date,
            price=price, shares=shares, amount=amount, commission=commission,
        ))

    def _sell(self, ticker: str, shares: int, price: float, trade_date: date) -> None:
        if ticker not in self._positions:
            return
        pos = self._positions[ticker]
        shares = min(shares, pos.shares)
        if shares <= 0:
            return

        amount = shares * price
        commission = amount * self.commission_pct
        self.cash += amount - commission

        ret = (price - pos.entry_price) / pos.entry_price if pos.entry_price > 0 else None
        self.trades.append(Trade(
            ticker=ticker, action="SELL", trade_date=trade_date,
            price=price, shares=shares, amount=amount, commission=commission,
            entry_date=pos.entry_date, entry_price=pos.entry_price, return_pct=ret,
        ))

        remaining = pos.shares - shares
        if remaining > 0:
            self._positions[ticker] = _Position(ticker, remaining, pos.entry_price, pos.entry_date)
        else:
            del self._positions[ticker]

    def _sell_all(self, ticker: str, price: Optional[float], trade_date: date) -> None:
        if ticker not in self._positions or not price:
            return
        self._sell(ticker, self._positions[ticker].shares, price, trade_date)
