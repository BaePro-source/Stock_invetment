"""
BacktestReportGenerator: 백테스트 결과를 텍스트 리포트로 변환.
"""
from datetime import datetime
from typing import List

from backtesting.metrics import BacktestMetrics
from backtesting.simulator import Trade
from config.settings import BacktestConfig
from models.stock import Stock


class BacktestReportGenerator:

    def build(
        self,
        metrics: BacktestMetrics,
        benchmark: BacktestMetrics,
        trades: List[Trade],
        cfg: BacktestConfig,
        stocks: List[Stock],
    ) -> str:
        lines: List[str] = []
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")

        lines += self._header(ts, cfg, stocks)
        lines += self._section_performance(metrics, benchmark)
        lines += self._section_trade_stats(metrics, trades)
        lines += self._section_top_trades(trades)
        lines += self._section_caveats()
        lines += ["=" * 60]

        return "\n".join(lines)

    # ── 섹션 ──────────────────────────────────────────────────

    def _header(self, ts: str, cfg: BacktestConfig, stocks: List[Stock]) -> List[str]:
        period = cfg.rebalance_period
        return [
            "=" * 60,
            "  백테스트 결과 리포트",
            f"  생성 시각: {ts}",
            f"  유니버스: {len(stocks)}개 종목  |  리밸런싱: {period}  |  "
            f"수수료: {cfg.commission_pct*100:.1f}%",
            f"  초기 자본: {cfg.initial_capital:>14,.0f}원",
            "=" * 60,
            "",
        ]

    def _section_performance(
        self, m: BacktestMetrics, bm: BacktestMetrics
    ) -> List[str]:
        alpha = m.annualized_return - bm.annualized_return

        lines = [
            "[ 성과 요약 ]",
            "",
            f"  {'지표':<20} {'전략':>12}  {'벤치마크':>12}  {'차이':>10}",
            f"  {'-'*19} {'-'*12}  {'-'*12}  {'-'*10}",
            self._row("총 수익률",
                      f"{m.total_return*100:+.2f}%",
                      f"{bm.total_return*100:+.2f}%",
                      f"{(m.total_return - bm.total_return)*100:+.2f}%"),
            self._row("연간 수익률",
                      f"{m.annualized_return*100:+.2f}%",
                      f"{bm.annualized_return*100:+.2f}%",
                      f"{alpha*100:+.2f}%"),
            self._row("Sharpe Ratio",
                      f"{m.sharpe_ratio:.3f}",
                      f"{bm.sharpe_ratio:.3f}",
                      f"{m.sharpe_ratio - bm.sharpe_ratio:+.3f}"),
            self._row("최대 낙폭(MDD)",
                      f"{m.max_drawdown*100:.2f}%",
                      f"{bm.max_drawdown*100:.2f}%",
                      f"{(m.max_drawdown - bm.max_drawdown)*100:+.2f}%"),
            "",
            f"  최종 자산:  {m.final_equity:>14,.0f}원",
            f"  총 수수료:  {m.total_commission:>14,.0f}원",
            f"  분석 기간:  {m.trading_days}거래일",
            "",
        ]
        return lines

    def _section_trade_stats(self, m: BacktestMetrics, trades: List[Trade]) -> List[str]:
        sell_trades = [t for t in trades if t.action == "SELL" and t.return_pct is not None]

        # 종목별 거래 횟수
        ticker_counts: dict = {}
        for t in sell_trades:
            ticker_counts[t.ticker] = ticker_counts.get(t.ticker, 0) + 1
        most_traded = sorted(ticker_counts.items(), key=lambda x: -x[1])[:3]

        lines = [
            "[ 거래 통계 ]",
            "",
            f"  총 거래 횟수:   {m.total_trades:>5}건  (매수 {m.total_trades - m.completed_trades} / 매도 {m.completed_trades})",
            f"  승률:           {m.win_rate*100:>5.1f}%  ({m.win_trades}/{m.completed_trades}건)",
            f"  평균 보유 기간: {m.avg_holding_days:>5.0f}일",
        ]

        if most_traded:
            traded_str = "  |  ".join(f"{t}({c}회)" for t, c in most_traded)
            lines.append(f"  다빈도 종목:    {traded_str}")

        lines.append("")
        return lines

    def _section_top_trades(self, trades: List[Trade]) -> List[str]:
        sell_trades = [t for t in trades if t.action == "SELL" and t.return_pct is not None]
        if not sell_trades:
            return []

        best = sorted(sell_trades, key=lambda t: -(t.return_pct or 0))[:5]
        worst = sorted(sell_trades, key=lambda t: (t.return_pct or 0))[:5]

        lines = ["[ 개별 거래 (상위/하위 5건) ]", ""]
        lines.append(f"  {'수익 상위':<40}  {'손실 하위'}")
        lines.append(f"  {'-'*39}  {'-'*39}")

        for i in range(max(len(best), len(worst))):
            b = best[i] if i < len(best) else None
            w = worst[i] if i < len(worst) else None
            b_str = (f"{b.ticker:<8} {b.return_pct*100:>+7.1f}%  "
                     f"{b.entry_date}→{b.trade_date}") if b else ""
            w_str = (f"{w.ticker:<8} {w.return_pct*100:>+7.1f}%  "
                     f"{w.entry_date}→{w.trade_date}") if w else ""
            lines.append(f"  {b_str:<40}  {w_str}")

        lines.append("")
        return lines

    def _section_caveats(self) -> List[str]:
        return [
            "[ 유의사항 ]",
            "",
            "  ※ 재무 데이터는 현재 값 고정 사용 (과거 재무제표 미반영)",
            "  ※ 감성 분석 제외 (LLM 비용 문제)",
            "  ※ 시장 충격(슬리피지) 미반영",
            "  ※ 본 결과는 참고용이며 실제 수익을 보장하지 않습니다",
            "",
        ]

    @staticmethod
    def _row(label: str, strategy: str, benchmark: str, diff: str) -> str:
        return f"  {label:<20} {strategy:>12}  {benchmark:>12}  {diff:>10}"

    def save(self, report_text: str, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(report_text)
