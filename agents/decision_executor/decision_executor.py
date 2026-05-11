"""
DecisionExecutor: 전체 파이프라인의 최종 출력 담당.
AnalysisResult + RiskManagementResult → Recommendation 리스트 + 리포트
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from agents.analysis.analysis_agent import AnalysisResult
from agents.risk_management.risk_agent import RiskManagementResult
from agents.decision_executor.recommendation import Recommendation, RecommendationEngine, Decision
from agents.decision_executor.report import ReportGenerator

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    recommendations: List[Recommendation] = field(default_factory=list)
    report_text: str = ""
    generated_at: datetime = field(default_factory=datetime.now)

    @property
    def buys(self) -> List[Recommendation]:
        return [r for r in self.recommendations if r.decision == Decision.BUY]

    @property
    def sells(self) -> List[Recommendation]:
        return [r for r in self.recommendations if r.decision == Decision.SELL]

    @property
    def watchlist(self) -> List[Recommendation]:
        return [r for r in self.recommendations if r.decision == Decision.WATCH]


class DecisionExecutor:
    def __init__(self, report_save_path: Optional[str] = None):
        self.engine = RecommendationEngine()
        self.reporter = ReportGenerator()
        self.report_save_path = report_save_path

    def execute(
        self,
        analysis_results: List[AnalysisResult],
        risk_result: RiskManagementResult,
    ) -> ExecutionResult:

        logger.info("[Executor] 최종 결정 생성 중...")
        recommendations = self.engine.generate(analysis_results, risk_result)

        report_text = self.reporter.build(recommendations, risk_result)

        if self.report_save_path:
            self.reporter.save(report_text, self.report_save_path)
            logger.info(f"[Executor] 리포트 저장: {self.report_save_path}")

        result = ExecutionResult(
            recommendations=recommendations,
            report_text=report_text,
        )

        logger.info(
            f"[Executor] 완료 — 매수 {len(result.buys)}개 / "
            f"매도 {len(result.sells)}개 / 관심 {len(result.watchlist)}개"
        )
        return result
