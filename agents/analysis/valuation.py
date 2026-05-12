"""
Valuation analysis: PER, PBR, EV/EBITDA 기반 적정가치 평가.

섹터별 기준:
  Tech  — 성장 프리미엄 허용, P/E 40배까지 보통 수준으로 평가
  Bio   — 적자기업 많아 P/E 생략, P/B + EV/EBITDA 위주
  기타  — 전통 기준 (P/E 20배 이하 저평가)
"""
import logging
from dataclasses import dataclass
from typing import Optional

from models.stock import Stock, Sector, ValuationMetrics

logger = logging.getLogger(__name__)


@dataclass
class ValuationScore:
    ticker: str
    pe_ratio: Optional[float] = None
    pb_ratio: Optional[float] = None
    ev_ebitda: Optional[float] = None
    score: float = 0.0          # 0~100
    verdict: str = "N/A"        # cheap / fair / expensive / N/A


class ValuationAnalyzer:
    def analyze(self, stock: Stock) -> ValuationScore:
        result = ValuationScore(ticker=stock.ticker)
        vm = stock.valuation

        if vm is None:
            logger.debug(f"[Valuation] {stock.ticker}: 밸류에이션 데이터 없음")
            return result

        result.pe_ratio = vm.pe_ratio
        result.pb_ratio = vm.pb_ratio
        result.ev_ebitda = vm.ev_ebitda

        result.score = self._calculate_score(vm, stock.sector)
        result.verdict = self._verdict(result.score)

        logger.debug(
            f"[Valuation] {stock.ticker}: "
            f"P/E={vm.pe_ratio} P/B={vm.pb_ratio} EV/EBITDA={vm.ev_ebitda} "
            f"→ {result.score:.1f} ({result.verdict})"
        )
        return result

    # ── 점수 산출 ──────────────────────────────────────────────

    def _calculate_score(self, vm: ValuationMetrics, sector: Sector) -> float:
        """
        각 지표를 0~100으로 환산 후 가용 지표 가중 평균.
        가중치: P/E 40% · P/B 30% · EV/EBITDA 30%
        Bio는 P/E 제외 → P/B 50% · EV/EBITDA 50%
        """
        scores: dict[str, tuple[float, float]] = {}  # key: (점수, 가중치)

        # P/E
        if sector != Sector.BIO and vm.pe_ratio is not None:
            scores["pe"] = (self._score_pe(vm.pe_ratio, sector), 0.40)

        # P/B
        if vm.pb_ratio is not None:
            pb_w = 0.50 if sector == Sector.BIO else 0.30
            scores["pb"] = (self._score_pb(vm.pb_ratio), pb_w)

        # EV/EBITDA
        if vm.ev_ebitda is not None and vm.ev_ebitda > 0:
            ev_w = 0.50 if sector == Sector.BIO else 0.30
            scores["ev"] = (self._score_ev_ebitda(vm.ev_ebitda), ev_w)

        if not scores:
            return 0.0

        # 가중치 정규화 후 가중 평균
        total_weight = sum(w for _, w in scores.values())
        weighted = sum(s * w for s, w in scores.values())
        return round(weighted / total_weight, 2)

    @staticmethod
    def _score_pe(pe: float, sector: Sector) -> float:
        if pe <= 0:
            return 0.0
        if sector == Sector.TECH:
            # 성장주 프리미엄 반영
            if pe < 20:  return 100.0
            if pe < 30:  return 80.0
            if pe < 40:  return 60.0
            if pe < 60:  return 30.0
            return 10.0
        else:
            if pe < 12:  return 100.0
            if pe < 20:  return 75.0
            if pe < 30:  return 50.0
            if pe < 40:  return 25.0
            return 10.0

    @staticmethod
    def _score_pb(pb: float) -> float:
        if pb <= 0:
            return 50.0   # 음수 자본 = 불확실
        if pb < 1.0: return 100.0
        if pb < 2.0: return 80.0
        if pb < 4.0: return 60.0
        if pb < 8.0: return 30.0
        return 10.0

    @staticmethod
    def _score_ev_ebitda(ev_ebitda: float) -> float:
        if ev_ebitda < 8:   return 100.0
        if ev_ebitda < 15:  return 70.0
        if ev_ebitda < 20:  return 45.0
        if ev_ebitda < 30:  return 20.0
        return 5.0

    @staticmethod
    def _verdict(score: float) -> str:
        if score == 0.0:  return "N/A"
        if score >= 75:   return "저평가"
        if score >= 50:   return "적정"
        if score >= 25:   return "고평가"
        return "매우고평가"
