"""
Portfolio management: position sizing and sector concentration checks.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional

from models.stock import Stock, Sector, Market
from agents.analysis.analysis_agent import AnalysisResult
from config.settings import RiskConfig

_US_MARKETS = {Market.US_NYSE, Market.US_NASDAQ}


def _fetch_usd_krw() -> float:
    """USD/KRW 환율 실시간 조회. 실패 시 fallback 1300 사용."""
    try:
        import yfinance as yf
        hist = yf.Ticker("KRW=X").history(period="1d")
        if not hist.empty:
            rate = float(hist["Close"].iloc[-1])
            logger.info(f"[Portfolio] USD/KRW 환율: {rate:.1f}")
            return rate
    except Exception as e:
        logger.warning(f"[Portfolio] 환율 조회 실패, fallback 1300 사용: {e}")
    return 1300.0

logger = logging.getLogger(__name__)


@dataclass
class Position:
    ticker: str
    name: str
    sector: Sector
    analysis_score: float

    target_pct: float = 0.0       # 목표 비중 (0~1)
    target_amount: float = 0.0    # 목표 금액 (원)
    target_shares: int = 0        # 목표 주수 (현재가 기준)
    current_price: float = 0.0


@dataclass
class PortfolioAllocation:
    positions: List[Position] = field(default_factory=list)
    total_capital: float = 0.0
    invested_pct: float = 0.0     # 실제 투자 비중 합계
    cash_pct: float = 1.0         # 현금 비중

    sector_weights: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


class PortfolioManager:
    def __init__(self, cfg: RiskConfig):
        self.cfg = cfg

    def allocate(self, results: List[AnalysisResult], stocks: Dict[str, Stock]) -> PortfolioAllocation:
        """
        AnalysisResult 점수 기반으로 포트폴리오 비중 산출.
        stocks: ticker → Stock 매핑 (현재가 조회용)
        """
        usd_krw = _fetch_usd_krw()
        alloc = PortfolioAllocation(total_capital=self.cfg.total_capital)

        # 투자적합 종목만 대상
        investable = [r for r in results if r.is_investable]
        if not investable:
            alloc.warnings.append("투자적합 종목 없음 — 전액 현금 보유")
            return alloc

        # 1. 점수 기반 상대 비중 산출
        raw_weights = self._score_to_weights(investable)

        # 2. 종목별 한도 적용
        capped_weights = self._apply_position_cap(raw_weights)

        # 3. 섹터 한도 적용
        capped_weights = self._apply_sector_cap(capped_weights, investable)

        # 4. 최소 비중 미만 종목 제거 후 재정규화
        capped_weights = {
            t: w for t, w in capped_weights.items()
            if w >= self.cfg.min_position_pct
        }
        total = sum(capped_weights.values())
        if total > 0:
            capped_weights = {t: w / total for t, w in capped_weights.items()}

        # 5. Position 객체 생성
        result_map = {r.ticker: r for r in investable}
        for ticker, weight in capped_weights.items():
            r = result_map[ticker]
            stock = stocks.get(ticker)
            price = stock.latest_price.close if stock and stock.latest_price else 0.0
            # US 주식은 USD → KRW 변환
            price_krw = price * usd_krw if stock and stock.market in _US_MARKETS else price
            amount = self.cfg.total_capital * weight
            shares = int(amount / price_krw) if price_krw > 0 else 0

            alloc.positions.append(Position(
                ticker=ticker,
                name=r.name,
                sector=r.sector,
                analysis_score=r.total_score,
                target_pct=round(weight, 4),
                target_amount=round(amount, 0),
                target_shares=shares,
                current_price=price,
            ))

        alloc.invested_pct = round(sum(p.target_pct for p in alloc.positions), 4)
        alloc.cash_pct = round(1.0 - alloc.invested_pct, 4)
        alloc.sector_weights = self._calc_sector_weights(alloc.positions)
        alloc.warnings += self._check_warnings(alloc)

        logger.info(
            f"[Portfolio] {len(alloc.positions)}개 종목 배분 완료 "
            f"(투자 {alloc.invested_pct*100:.1f}% / 현금 {alloc.cash_pct*100:.1f}%)"
        )
        return alloc

    # ── 내부 헬퍼 ──────────────────────────────────────────

    def _score_to_weights(self, results: List[AnalysisResult]) -> Dict[str, float]:
        """점수를 비중으로 변환 (점수 제곱 비례 — 고점수 종목 우대)"""
        score_sq = {r.ticker: r.total_score ** 2 for r in results}
        total = sum(score_sq.values())
        return {t: s / total for t, s in score_sq.items()}

    def _apply_position_cap(self, weights: Dict[str, float]) -> Dict[str, float]:
        capped = {t: min(w, self.cfg.max_position_pct) for t, w in weights.items()}
        total = sum(capped.values())
        return {t: w / total for t, w in capped.items()} if total > 0 else capped

    def _apply_sector_cap(
        self, weights: Dict[str, float], results: List[AnalysisResult]
    ) -> Dict[str, float]:
        sector_map = {r.ticker: r.sector for r in results}
        sector_totals: Dict[str, float] = {}
        for ticker, w in weights.items():
            s = sector_map.get(ticker, Sector.OTHER).value
            sector_totals[s] = sector_totals.get(s, 0.0) + w

        # 섹터 초과 비중 비율 계산 후 해당 섹터 종목 균등 축소
        adjusted = dict(weights)
        for sector_val, total in sector_totals.items():
            if total > self.cfg.max_sector_pct:
                ratio = self.cfg.max_sector_pct / total
                for ticker in adjusted:
                    if sector_map.get(ticker, Sector.OTHER).value == sector_val:
                        adjusted[ticker] *= ratio

        total = sum(adjusted.values())
        return {t: w / total for t, w in adjusted.items()} if total > 0 else adjusted

    def _calc_sector_weights(self, positions: List[Position]) -> Dict[str, float]:
        result: Dict[str, float] = {}
        for p in positions:
            key = p.sector.value
            result[key] = round(result.get(key, 0.0) + p.target_pct, 4)
        return result

    def _check_warnings(self, alloc: PortfolioAllocation) -> List[str]:
        warnings = []
        for sector, w in alloc.sector_weights.items():
            if w > self.cfg.max_sector_pct:
                warnings.append(f"{sector} 섹터 비중 {w*100:.1f}% > 한도 {self.cfg.max_sector_pct*100:.0f}%")
        if alloc.cash_pct > 0.5:
            warnings.append(f"현금 비중 {alloc.cash_pct*100:.1f}% — 투자적합 종목 부족")
        return warnings
