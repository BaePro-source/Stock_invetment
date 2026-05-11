"""
Report generator: console output and plain-text file export.
"""
from datetime import datetime
from typing import List, Optional

from agents.decision_executor.recommendation import Recommendation, Decision, DECISION_TAG
from agents.risk_management.risk_agent import RiskManagementResult


class ReportGenerator:

    def build(
        self,
        recommendations: List[Recommendation],
        risk_result: RiskManagementResult,
        generated_at: Optional[datetime] = None,
    ) -> str:
        ts = (generated_at or datetime.now()).strftime("%Y-%m-%d %H:%M")
        lines = []

        lines += self._header(ts)
        lines += self._section_decisions(recommendations)
        lines += self._section_portfolio(risk_result)
        lines += self._section_risk(risk_result)
        lines += self._section_action_items(risk_result)
        lines += ["=" * 60]

        return "\n".join(lines)

    # ── 섹션별 ────────────────────────────────────────────

    def _header(self, ts: str) -> List[str]:
        return [
            "=" * 60,
            f"  주식 투자 에이전트 리포트",
            f"  생성 시각: {ts}",
            "=" * 60,
            "",
        ]

    def _section_decisions(self, recs: List[Recommendation]) -> List[str]:
        lines = ["[ 투자 결정 ]", ""]

        for decision in [Decision.BUY, Decision.HOLD, Decision.WATCH, Decision.SELL, Decision.PASS]:
            group = [r for r in recs if r.decision == decision]
            if not group:
                continue

            lines.append(f"  {DECISION_TAG[decision]}  ({len(group)}개)")
            for r in group:
                price_str = f"{r.current_price:>10,.0f}원" if r.current_price else "         N/A"
                pct_str = f"{r.target_pct*100:4.1f}%" if r.target_pct else "   -"
                lines.append(
                    f"    {r.ticker:<10} {r.name[:14]:<14} "
                    f"점수 {r.analysis_score:5.1f}  {price_str}  비중 {pct_str}"
                )
                for reason in r.reasons:
                    lines.append(f"      └ {reason}")
            lines.append("")

        return lines

    def _section_portfolio(self, risk_result: RiskManagementResult) -> List[str]:
        alloc = risk_result.allocation
        if not alloc or not alloc.positions:
            return []

        lines = [
            "[ 포트폴리오 배분 ]",
            f"  총 자본: {alloc.total_capital:>14,.0f}원",
            f"  투자:   {alloc.invested_pct*100:5.1f}%   현금: {alloc.cash_pct*100:5.1f}%",
            "",
            f"  {'티커':<10} {'종목명':<14} {'비중':>5}  {'금액':>14}  {'주수':>6}  {'현재가':>10}",
            f"  {'-'*9} {'-'*14} {'-'*5}  {'-'*14}  {'-'*6}  {'-'*10}",
        ]

        for p in sorted(alloc.positions, key=lambda x: -x.target_pct):
            lines.append(
                f"  {p.ticker:<10} {p.name[:14]:<14} "
                f"{p.target_pct*100:5.1f}%  {p.target_amount:>14,.0f}  "
                f"{p.target_shares:>6}주  {p.current_price:>10,.0f}원"
            )

        sector_line = "  섹터: " + " / ".join(
            f"{k} {v*100:.1f}%" for k, v in alloc.sector_weights.items()
        )
        lines += ["", sector_line, ""]
        return lines

    def _section_risk(self, risk_result: RiskManagementResult) -> List[str]:
        rpt = risk_result.risk_report
        if not rpt or not rpt.stock_profiles:
            return []

        lines = [
            "[ 리스크 지표 ]",
            f"  {'티커':<10} {'MDD':>8}  {'연간변동성':>10}  {'Sharpe':>8}",
            f"  {'-'*9} {'-'*8}  {'-'*10}  {'-'*8}",
        ]

        for p in rpt.stock_profiles:
            mdd = f"{p.mdd*100:7.1f}%" if p.mdd is not None else "     N/A"
            vol = f"{p.volatility_annual*100:9.1f}%" if p.volatility_annual else "       N/A"
            sharpe = f"{p.sharpe_ratio:8.2f}" if p.sharpe_ratio else "     N/A"
            lines.append(f"  {p.ticker:<10} {mdd}  {vol}  {sharpe}")

        lines.append("")
        return lines

    def _section_action_items(self, risk_result: RiskManagementResult) -> List[str]:
        items = risk_result.action_items
        if not items:
            return []

        lines = ["[ 액션 아이템 ]"]
        for i, item in enumerate(items, 1):
            lines.append(f"  {i:2}. {item}")
        lines.append("")
        return lines

    def save(self, report_text: str, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(report_text)
