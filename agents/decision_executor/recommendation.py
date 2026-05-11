"""
Final recommendation logic: BUY / HOLD / SELL / WATCH decision.
"""
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from models.stock import Sector
from agents.analysis.analysis_agent import AnalysisResult
from agents.risk_management.risk_agent import RiskManagementResult
from agents.risk_management.stop_loss import StopLossAction

logger = logging.getLogger(__name__)


class Decision(Enum):
    BUY = "매수"
    HOLD = "보유"
    SELL = "매도"
    WATCH = "관심"
    PASS = "제외"


# 결정별 색상 태그 (리포트 출력용)
DECISION_TAG = {
    Decision.BUY:   "[매수]",
    Decision.HOLD:  "[보유]",
    Decision.SELL:  "[매도]",
    Decision.WATCH: "[관심]",
    Decision.PASS:  "[제외]",
}


@dataclass
class Recommendation:
    ticker: str
    name: str
    sector: Sector
    decision: Decision

    analysis_score: float = 0.0
    target_pct: float = 0.0        # 포트폴리오 목표 비중
    target_amount: float = 0.0     # 목표 금액
    target_shares: int = 0
    current_price: float = 0.0

    # 결정 근거
    reasons: List[str] = field(default_factory=list)

    # 분석 요약 (AnalysisResult.summary 에서 복사)
    analysis_summary: str = ""


class RecommendationEngine:
    # 매수 최소 점수
    BUY_THRESHOLD = 60.0
    WATCH_THRESHOLD = 40.0

    def generate(
        self,
        analysis_results: List[AnalysisResult],
        risk_result: RiskManagementResult,
    ) -> List[Recommendation]:

        stop_map = {
            s.ticker: s for s in risk_result.stop_loss_signals
        }
        position_map = {
            p.ticker: p
            for p in (risk_result.allocation.positions if risk_result.allocation else [])
        }

        recommendations = []
        for ar in analysis_results:
            rec = self._decide(ar, stop_map.get(ar.ticker), position_map.get(ar.ticker))
            recommendations.append(rec)
            logger.debug(f"[Decision] {ar.ticker}: {rec.decision.value} (score={ar.total_score:.1f})")

        # BUY > HOLD > WATCH > SELL > PASS 순, 같은 결정 내에선 점수 내림차순
        order = [Decision.BUY, Decision.HOLD, Decision.WATCH, Decision.SELL, Decision.PASS]
        recommendations.sort(key=lambda r: (order.index(r.decision), -r.analysis_score))
        return recommendations

    def _decide(self, ar: AnalysisResult, stop_signal, position) -> Recommendation:
        reasons: List[str] = []

        # 포지션 정보 채우기
        target_pct = position.target_pct if position else 0.0
        target_amount = position.target_amount if position else 0.0
        target_shares = position.target_shares if position else 0
        current_price = position.current_price if position else 0.0

        # 1. 손절 발동 → 무조건 SELL
        if stop_signal and stop_signal.action != StopLossAction.HOLD:
            reasons.append(f"{stop_signal.action.value} 발동 (고점 대비 {stop_signal.drawdown_from_peak*100:.1f}%)")
            return Recommendation(
                ticker=ar.ticker, name=ar.name, sector=ar.sector,
                decision=Decision.SELL,
                analysis_score=ar.total_score,
                target_pct=target_pct, target_amount=target_amount,
                target_shares=target_shares, current_price=current_price,
                reasons=reasons, analysis_summary=ar.summary,
            )

        # 2. 펀더멘털 스크리닝 탈락 → PASS
        if not ar.fundamental or not ar.fundamental.passed_screening:
            fail = ar.fundamental.fail_reasons if ar.fundamental else ["분석 데이터 없음"]
            reasons += fail
            return Recommendation(
                ticker=ar.ticker, name=ar.name, sector=ar.sector,
                decision=Decision.PASS,
                analysis_score=ar.total_score,
                reasons=reasons, analysis_summary=ar.summary,
            )

        # 3. 점수 기반 결정
        if ar.total_score >= self.BUY_THRESHOLD and position:
            decision = Decision.BUY
            reasons.append(f"종합 점수 {ar.total_score:.1f}점 (기준 {self.BUY_THRESHOLD}점)")
            if ar.technical and ar.technical.trend.golden_cross:
                reasons.append("골든크로스 확인")
            if ar.fundamental.moat.revenue_growth_consistency:
                c = ar.fundamental.moat.revenue_growth_consistency
                reasons.append(f"매출 성장 일관성 {c*100:.0f}%")

        elif ar.total_score >= self.BUY_THRESHOLD and not position:
            # 점수는 충분하나 포트폴리오 한도로 배분 제외
            decision = Decision.WATCH
            reasons.append(f"점수 {ar.total_score:.1f}점 — 포트폴리오 비중 한도 초과로 미편입")

        elif ar.total_score >= self.WATCH_THRESHOLD:
            decision = Decision.WATCH
            reasons.append(f"종합 점수 {ar.total_score:.1f}점 (관심 기준 {self.WATCH_THRESHOLD}점)")

        else:
            decision = Decision.PASS
            reasons.append(f"종합 점수 {ar.total_score:.1f}점 — 기준 미달")

        # Bio 런웨이 경고
        if ar.sector == Sector.BIO and ar.fundamental.cash_runway_months:
            months = ar.fundamental.cash_runway_months
            if months < 24:
                reasons.append(f"현금 런웨이 {months:.0f}개월 — 단기 자금조달 위험")

        return Recommendation(
            ticker=ar.ticker, name=ar.name, sector=ar.sector,
            decision=decision,
            analysis_score=ar.total_score,
            target_pct=target_pct, target_amount=target_amount,
            target_shares=target_shares, current_price=current_price,
            reasons=reasons, analysis_summary=ar.summary,
        )
