"""
BacktestEngine: 워크-포워드 방식 백테스트 엔진.

각 리밸런싱 시점에서 해당 날짜까지의 가격 데이터만 사용해
기술적 점수를 산출하고 포트폴리오를 구성합니다 (look-ahead bias 방지).
재무·밸류에이션 점수는 현재 수집된 값을 고정 사용합니다.
"""
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

from models.stock import Stock
from agents.analysis.fundamental import FundamentalAnalyzer, FundamentalScore
from agents.analysis.technical import TechnicalAnalyzer, TechnicalScore
from agents.analysis.valuation import ValuationAnalyzer, ValuationScore
from config.settings import BacktestConfig, AnalysisConfig
from backtesting.simulator import PortfolioSimulator, Trade
from backtesting.metrics import MetricsCalculator, BacktestMetrics
from backtesting.report import BacktestReportGenerator

logger = logging.getLogger(__name__)

# 백테스트 내 가중치: 감성 제외 후 재정규화 (F 35 / V 25 / T 40)
_W_F, _W_V, _W_T = 0.35, 0.25, 0.40


@dataclass
class BacktestResult:
    dates: List[date]
    equity_curve: List[float]
    benchmark_curve: List[float]
    trades: List[Trade]
    metrics: BacktestMetrics
    benchmark_metrics: BacktestMetrics
    report_text: str = ""

    def save_report(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.report_text)
        logger.info(f"[Backtest] 리포트 저장: {path}")


class BacktestEngine:
    def __init__(self, cfg: BacktestConfig, analysis_cfg: AnalysisConfig):
        self.cfg = cfg
        self.fundamental = FundamentalAnalyzer(analysis_cfg)
        self.technical = TechnicalAnalyzer(analysis_cfg)
        self.valuation = ValuationAnalyzer()

    def run(self, stocks: List[Stock]) -> BacktestResult:
        logger.info(
            f"[Backtest] 시작 — {len(stocks)}개 종목 / "
            f"초기 자본 {self.cfg.initial_capital:,.0f}원 / "
            f"리밸런싱 {self.cfg.rebalance_period}"
        )

        # 1. 가격 테이블 및 공통 날짜 목록 구성
        price_table, all_dates = self._build_price_table(stocks)
        if len(all_dates) < 30:
            raise ValueError(
                f"백테스트 최소 30거래일 필요. 현재 {len(all_dates)}일."
            )

        # 2. 재무·밸류에이션 점수 사전 계산 (변하지 않음)
        f_scores: Dict[str, FundamentalScore] = {}
        v_scores: Dict[str, ValuationScore] = {}
        for stock in stocks:
            f_scores[stock.ticker] = self.fundamental.analyze(stock)
            v_scores[stock.ticker] = self.valuation.analyze(stock)

        screened = [s for s in stocks if f_scores[s.ticker].passed_screening]
        logger.info(
            f"[Backtest] 펀더멘털 스크리닝 통과: {len(screened)}/{len(stocks)}개"
        )

        # 3. 리밸런싱 날짜 목록
        rebalance_dates = set(self._rebalance_dates(all_dates))
        logger.info(f"[Backtest] 리밸런싱 {len(rebalance_dates)}회")

        # 4. 시뮬레이션
        strategy = PortfolioSimulator(self.cfg.initial_capital, self.cfg.commission_pct)
        benchmark = PortfolioSimulator(self.cfg.initial_capital, 0.0)

        # 벤치마크: 첫 거래일에 스크리닝 통과 종목 균등 매수 후 보유
        first_prices = {
            s.ticker: price_table[s.ticker][all_dates[0]]
            for s in screened
            if all_dates[0] in price_table.get(s.ticker, {})
        }
        if first_prices:
            eq_w = 1.0 / len(first_prices)
            benchmark.rebalance(all_dates[0], {t: eq_w for t in first_prices}, first_prices)

        for i, d in enumerate(all_dates):
            prices_today = {
                t: price_table[t][d]
                for t in price_table
                if d in price_table[t]
            }

            if d in rebalance_dates:
                scores = self._score_at_date(screened, f_scores, v_scores, d)
                weights = self._build_weights(scores)
                strategy.rebalance(d, weights, prices_today)

            strategy.mark_to_market(d, prices_today)
            benchmark.mark_to_market(d, prices_today)

        # 5. 마지막 날 청산
        last_prices = {
            t: price_table[t][all_dates[-1]]
            for t in price_table
            if all_dates[-1] in price_table[t]
        }
        strategy.liquidate(all_dates[-1], last_prices)

        # 6. 성과 계산 및 리포트
        calc = MetricsCalculator(self.cfg.risk_free_rate)
        metrics = calc.calculate(strategy.equity_curve, strategy.trades)
        bm_metrics = calc.calculate(benchmark.equity_curve, [])

        report = BacktestReportGenerator().build(metrics, bm_metrics, strategy.trades, self.cfg, stocks)

        logger.info(
            f"[Backtest] 완료 — 전략 {metrics.total_return*100:+.1f}% / "
            f"벤치마크 {bm_metrics.total_return*100:+.1f}% / "
            f"Sharpe {metrics.sharpe_ratio:.2f} / MDD {metrics.max_drawdown*100:.1f}%"
        )

        return BacktestResult(
            dates=all_dates,
            equity_curve=strategy.equity_curve,
            benchmark_curve=benchmark.equity_curve,
            trades=strategy.trades,
            metrics=metrics,
            benchmark_metrics=bm_metrics,
            report_text=report,
        )

    # ── 가격 테이블 ───────────────────────────────────────────

    def _build_price_table(
        self, stocks: List[Stock]
    ) -> Tuple[Dict[str, Dict[date, float]], List[date]]:
        price_table: Dict[str, Dict[date, float]] = {}
        date_set = set()

        for stock in stocks:
            daily: Dict[date, float] = {}
            for bar in stock.price_history:
                if bar.close > 0:
                    daily[bar.date] = bar.close
                    date_set.add(bar.date)
            price_table[stock.ticker] = daily

        all_dates = sorted(date_set)

        # Forward-fill: 거래 없는 날 직전 가격 유지
        for daily in price_table.values():
            prev: Optional[float] = None
            for d in all_dates:
                if d in daily:
                    prev = daily[d]
                elif prev is not None:
                    daily[d] = prev

        return price_table, all_dates

    # ── 리밸런싱 날짜 ─────────────────────────────────────────

    def _rebalance_dates(self, all_dates: List[date]) -> List[date]:
        result: List[date] = []
        prev_key = None

        for d in all_dates:
            if self.cfg.rebalance_period == "weekly":
                key = (d.year, d.isocalendar()[1])
            elif self.cfg.rebalance_period == "quarterly":
                key = (d.year, (d.month - 1) // 3)
            else:  # monthly
                key = (d.year, d.month)

            if key != prev_key:
                result.append(d)
                prev_key = key

        return result

    # ── 시점별 점수 산출 ──────────────────────────────────────

    def _score_at_date(
        self,
        stocks: List[Stock],
        f_scores: Dict[str, FundamentalScore],
        v_scores: Dict[str, ValuationScore],
        cutoff: date,
    ) -> Dict[str, float]:
        scores: Dict[str, float] = {}

        for stock in stocks:
            # 해당 시점까지의 가격만 사용 (look-ahead 방지)
            sliced = [b for b in stock.price_history if b.date <= cutoff]
            if len(sliced) < 60:  # MA60 최소 데이터 요구
                continue

            # 임시 Stock으로 기술적 분석만 재산출
            tmp = Stock(
                ticker=stock.ticker, name=stock.name,
                market=stock.market, sector=stock.sector,
                price_history=sliced,
            )
            t_result = self.technical.analyze(tmp)

            f = f_scores[stock.ticker].score
            t = t_result.score
            v_obj = v_scores.get(stock.ticker)
            v = v_obj.score if v_obj and v_obj.score > 0 else None

            if v is not None:
                total = f * _W_F + v * _W_V + t * _W_T
            else:
                w_sum = _W_F + _W_T
                total = f * (_W_F / w_sum) + t * (_W_T / w_sum)

            scores[stock.ticker] = round(total, 2)

        return scores

    # ── 포트폴리오 비중 산출 ──────────────────────────────────

    def _build_weights(self, scores: Dict[str, float]) -> Dict[str, float]:
        eligible = {t: s for t, s in scores.items() if s >= self.cfg.min_score}
        if not eligible:
            return {}

        top = sorted(eligible.items(), key=lambda x: -x[1])[: self.cfg.top_n_stocks]

        # 점수 제곱 비례 가중치
        score_sq = {t: s ** 2 for t, s in top}
        total_sq = sum(score_sq.values())
        weights = {t: sq / total_sq for t, sq in score_sq.items()}

        # 종목당 15% 상한 반복 적용
        for _ in range(10):
            over = {t for t, w in weights.items() if w > 0.15}
            if not over:
                break
            excess = sum(weights[t] - 0.15 for t in over)
            under = {t for t in weights if t not in over}
            for t in over:
                weights[t] = 0.15
            if under:
                add_each = excess / len(under)
                for t in under:
                    weights[t] = min(weights[t] + add_each, 0.15)

        total = sum(weights.values())
        return {t: w / total for t, w in weights.items()} if total > 0 else {}
