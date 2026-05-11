"""
RiskManagementAgent: PortfolioManager + StopLossMonitor + RiskMetricsCalculator 통합.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional

from models.stock import Stock
from agents.analysis.analysis_agent import AnalysisResult
from agents.risk_management.portfolio import PortfolioManager, PortfolioAllocation
from agents.risk_management.stop_loss import StopLossMonitor, StopLossSignal, StopLossAction
from agents.risk_management.risk_metrics import RiskMetricsCalculator, PortfolioRiskReport, StockRiskProfile
from config.settings import RiskConfig

logger = logging.getLogger(__name__)


@dataclass
class RiskManagementResult:
    allocation: Optional[PortfolioAllocation] = None
    stop_loss_signals: List[StopLossSignal] = field(default_factory=list)
    risk_report: Optional[PortfolioRiskReport] = None

    # 최종 액션 요약
    action_items: List[str] = field(default_factory=list)


class RiskManagementAgent:
    def __init__(self, cfg: RiskConfig):
        self.cfg = cfg
        self.portfolio_mgr = PortfolioManager(cfg)
        self.stop_loss = StopLossMonitor(cfg)
        self.metrics = RiskMetricsCalculator(cfg)

    def run(
        self,
        analysis_results: List[AnalysisResult],
        stocks: List[Stock],
    ) -> RiskManagementResult:
        stock_map: Dict[str, Stock] = {s.ticker: s for s in stocks}
        result = RiskManagementResult()

        # 1. 포트폴리오 배분
        logger.info("[Risk] 포트폴리오 배분 계산 중...")
        result.allocation = self.portfolio_mgr.allocate(analysis_results, stock_map)

        # 2. 손절 모니터링 (투자적합 종목 + 현재 포지션 대상)
        logger.info("[Risk] 손절 모니터링 중...")
        target_tickers = {p.ticker for p in result.allocation.positions}
        target_stocks = [s for s in stocks if s.ticker in target_tickers]
        result.stop_loss_signals = self.stop_loss.check_all(target_stocks)

        # 3. 리스크 지표 계산
        logger.info("[Risk] 리스크 지표 계산 중...")
        report = PortfolioRiskReport()
        current_prices = {
            s.ticker: s.latest_price.close
            for s in stocks if s.latest_price
        }

        for stock in target_stocks:
            profile = self.metrics.calc_stock_risk(stock)
            report.stock_profiles.append(profile)

            # 고위험 종목 경고
            if profile.mdd is not None and profile.mdd < -0.40:
                report.warnings.append(
                    f"{stock.ticker}: MDD {profile.mdd*100:.1f}% — 고변동성 주의"
                )
            if profile.volatility_annual is not None and profile.volatility_annual > 0.60:
                report.warnings.append(
                    f"{stock.ticker}: 연간 변동성 {profile.volatility_annual*100:.1f}%"
                )

        report.rebalance_signals = self.metrics.check_rebalance(result.allocation, current_prices)
        result.risk_report = report

        # 4. 액션 아이템 정리
        result.action_items = self._build_action_items(result)

        return result

    def _build_action_items(self, result: RiskManagementResult) -> List[str]:
        items = []

        # 손절 발동 종목
        for sig in result.stop_loss_signals:
            if sig.action != StopLossAction.HOLD:
                items.append(
                    f"[{sig.action.value}] {sig.ticker} — "
                    f"현재가 {sig.current_price:,.0f} / "
                    f"고점 대비 {sig.drawdown_from_peak*100:.1f}%"
                )

        # 리밸런싱 필요 종목
        if result.risk_report:
            for sig in result.risk_report.rebalance_signals:
                if sig.action != "유지":
                    items.append(
                        f"[리밸런싱-{sig.action}] {sig.ticker} — "
                        f"현재 {sig.current_pct*100:.1f}% → 목표 {sig.target_pct*100:.1f}% "
                        f"({sig.amount:,.0f}원)"
                    )

        # 포트폴리오 경고
        if result.allocation:
            for w in result.allocation.warnings:
                items.append(f"[경고] {w}")

        if result.risk_report:
            for w in result.risk_report.warnings:
                items.append(f"[경고] {w}")

        return items
