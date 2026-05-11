"""
Fundamental analysis: ROE, MOAT proxy, financial health, sector-specific metrics.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional, List

from models.stock import Stock, FinancialStatement, Sector
from config.settings import AnalysisConfig

logger = logging.getLogger(__name__)


@dataclass
class MoatSignals:
    """MOAT 간접 지표 — 수치로 측정 가능한 부분만"""
    revenue_growth_consistency: Optional[float] = None  # 매출 성장 일관성 (0~1)
    margin_stability: Optional[float] = None            # 영업이익률 안정성 (0~1)
    roe_trend: Optional[float] = None                   # ROE 추세 (양수=개선)
    capex_efficiency: Optional[float] = None            # FCF/매출 (높을수록 자본효율)


@dataclass
class FundamentalScore:
    ticker: str
    passed_screening: bool

    # 핵심 지표
    latest_roe: Optional[float] = None
    latest_debt_ratio: Optional[float] = None
    latest_operating_margin: Optional[float] = None
    cash_runway_months: Optional[float] = None   # Bio 전용

    # MOAT
    moat: MoatSignals = field(default_factory=MoatSignals)

    # 최종 점수 (0~100)
    score: float = 0.0
    fail_reasons: List[str] = field(default_factory=list)


class FundamentalAnalyzer:
    def __init__(self, cfg: AnalysisConfig):
        self.cfg = cfg

    def analyze(self, stock: Stock) -> FundamentalScore:
        fs_list = sorted(stock.financials, key=lambda f: f.fiscal_year)
        latest = fs_list[-1] if fs_list else None

        result = FundamentalScore(ticker=stock.ticker, passed_screening=False)

        if not latest:
            result.fail_reasons.append("재무 데이터 없음")
            return result

        result.latest_roe = latest.roe
        result.latest_debt_ratio = latest.debt_ratio
        result.latest_operating_margin = latest.operating_margin

        # --- 1차 스크리닝 (하드 필터) ---
        if not self._passes_screening(stock, latest, result):
            return result

        result.passed_screening = True

        # --- MOAT 분석 ---
        result.moat = self._analyze_moat(fs_list)

        # --- Bio 전용 지표 ---
        if stock.sector == Sector.BIO and stock.bio_metrics:
            result.cash_runway_months = stock.bio_metrics.cash_runway_months
            if (
                result.cash_runway_months is not None
                and result.cash_runway_months < self.cfg.min_cash_runway_months
            ):
                result.fail_reasons.append(
                    f"현금 런웨이 {result.cash_runway_months:.1f}개월 "
                    f"(최소 {self.cfg.min_cash_runway_months}개월)"
                )
                result.passed_screening = False
                return result

        # --- 최종 점수 산출 ---
        result.score = self._calculate_score(result)
        logger.debug(f"[Fundamental] {stock.ticker}: score={result.score:.1f}")
        return result

    def _passes_screening(
        self, stock: Stock, latest: FinancialStatement, result: FundamentalScore
    ) -> bool:
        passed = True

        # ROE — Bio는 개발 단계 기업 많으므로 면제
        if stock.sector != Sector.BIO:
            if latest.roe is None or latest.roe < self.cfg.min_roe:
                roe_str = f"{latest.roe*100:.1f}%" if latest.roe is not None else "N/A"
                result.fail_reasons.append(
                    f"ROE {roe_str} < 최소 {self.cfg.min_roe*100:.0f}%"
                )
                passed = False

        # 부채비율
        if latest.debt_ratio is not None and latest.debt_ratio > self.cfg.max_debt_ratio:
            result.fail_reasons.append(
                f"부채비율 {latest.debt_ratio*100:.0f}% > 최대 {self.cfg.max_debt_ratio*100:.0f}%"
            )
            passed = False

        return passed

    def _analyze_moat(self, fs_list: List[FinancialStatement]) -> MoatSignals:
        moat = MoatSignals()
        if len(fs_list) < 2:
            return moat

        # 매출 성장 일관성: 연속 성장한 비율
        revenues = [f.revenue for f in fs_list if f.revenue is not None]
        if len(revenues) >= 2:
            growth_flags = [revenues[i] > revenues[i - 1] for i in range(1, len(revenues))]
            moat.revenue_growth_consistency = sum(growth_flags) / len(growth_flags)

        # 영업이익률 안정성: 표준편차 역수 기반 (변동 적을수록 높음)
        margins = [f.operating_margin for f in fs_list if f.operating_margin is not None]
        if len(margins) >= 2:
            mean = sum(margins) / len(margins)
            variance = sum((m - mean) ** 2 for m in margins) / len(margins)
            std = variance ** 0.5
            # std가 0에 가까울수록 1에 가까운 안정성 점수
            moat.margin_stability = 1.0 / (1.0 + std * 10)

        # ROE 추세: 최근 - 과거 평균
        roes = [f.roe for f in fs_list if f.roe is not None]
        if len(roes) >= 2:
            moat.roe_trend = roes[-1] - (sum(roes[:-1]) / len(roes[:-1]))

        # 자본 효율: FCF(영업현금흐름 - capex) / 매출
        latest = fs_list[-1]
        if latest.operating_cash_flow and latest.capex and latest.revenue and latest.revenue > 0:
            fcf = latest.operating_cash_flow - abs(latest.capex)
            moat.capex_efficiency = fcf / latest.revenue

        return moat

    def _calculate_score(self, result: FundamentalScore) -> float:
        score = 0.0

        # ROE (30점)
        if result.latest_roe is not None:
            score += min(result.latest_roe / 0.30, 1.0) * 30  # 30% ROE = 만점

        # 영업이익률 (20점)
        if result.latest_operating_margin is not None:
            score += min(result.latest_operating_margin / 0.20, 1.0) * 20

        # MOAT (30점)
        moat = result.moat
        moat_score = 0.0
        moat_count = 0
        for val in [moat.revenue_growth_consistency, moat.margin_stability]:
            if val is not None:
                moat_score += val
                moat_count += 1
        if moat_count > 0:
            score += (moat_score / moat_count) * 30

        # 부채비율 역수 (20점) — 부채 낮을수록 높은 점수
        if result.latest_debt_ratio is not None:
            debt_score = max(0.0, 1.0 - result.latest_debt_ratio / self.cfg.max_debt_ratio)
            score += debt_score * 20

        return round(score, 2)
