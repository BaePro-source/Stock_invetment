"""
Step 2: Logical consistency check and Hype filtering.

Hype 징후:
  - 뉴스 감성 점수가 임계값 이상인 기사 비율이 높음
  - 재무제표와 주가 괴리 (PER 극단값)
  - 단기 급등 (최근 30일 수익률 이상치)
"""
import logging
from dataclasses import dataclass
from typing import List, Optional

from models.stock import Stock, FinancialStatement
from config.settings import PreprocessingConfig

logger = logging.getLogger(__name__)


@dataclass
class HypeReport:
    ticker: str
    is_hype_suspected: bool
    reasons: List[str]
    hype_score: float  # 0~1, 높을수록 hype 가능성


class HypeFilter:
    def __init__(self, cfg: PreprocessingConfig):
        self.cfg = cfg

    def process(self, stock: Stock) -> tuple[Stock, HypeReport]:
        reasons = []
        scores = []

        # 1. 뉴스 감성 hype 체크
        news_score = self._check_news_hype(stock, reasons)
        if news_score is not None:
            scores.append(news_score)

        # 2. 단기 급등 체크
        momentum_score = self._check_abnormal_momentum(stock, reasons)
        if momentum_score is not None:
            scores.append(momentum_score)

        # 3. 재무-주가 논리 일관성 체크
        consistency_score = self._check_financial_consistency(stock, reasons)
        if consistency_score is not None:
            scores.append(consistency_score)

        hype_score = sum(scores) / len(scores) if scores else 0.0
        is_hype = hype_score >= 0.5

        if is_hype:
            logger.warning(f"[Hype] {stock.ticker} hype 의심 (score={hype_score:.2f}): {reasons}")

        report = HypeReport(
            ticker=stock.ticker,
            is_hype_suspected=is_hype,
            reasons=reasons,
            hype_score=round(hype_score, 3),
        )
        return stock, report

    def _check_news_hype(self, stock: Stock, reasons: List[str]) -> Optional[float]:
        scored_news = [n for n in stock.news if n.sentiment_score is not None]
        if not scored_news:
            return None

        hype_count = sum(
            1 for n in scored_news
            if n.sentiment_score >= self.cfg.hype_sentiment_threshold
        )
        ratio = hype_count / len(scored_news)

        if ratio > 0.6:
            reasons.append(f"뉴스 {ratio*100:.0f}%가 극도로 긍정적 감성 (임계값={self.cfg.hype_sentiment_threshold})")

        return ratio

    def _check_abnormal_momentum(self, stock: Stock, reasons: List[str]) -> Optional[float]:
        bars = stock.price_history
        if len(bars) < 30:
            return None

        recent_close = bars[-1].close
        close_30d_ago = bars[-30].close

        if close_30d_ago == 0:
            return None

        return_30d = (recent_close - close_30d_ago) / close_30d_ago

        # 30일 수익률 50% 이상 = 급등 의심
        if return_30d > 0.5:
            reasons.append(f"30일 수익률 {return_30d*100:.1f}% 급등")
            return min(return_30d / 1.0, 1.0)  # 100%를 hype score 1.0으로 정규화

        return max(0.0, return_30d / 0.5)

    def _check_financial_consistency(self, stock: Stock, reasons: List[str]) -> Optional[float]:
        financials = stock.financials
        if not financials or not stock.price_history:
            return None

        latest_fs: FinancialStatement = max(financials, key=lambda f: f.fiscal_year)
        if not latest_fs.net_income or latest_fs.net_income <= 0:
            return None  # 적자 기업은 PER 체크 의미 없음

        # 시가총액 추정 (주가 * 발행주식수는 없으므로 주가만으로 상대 판단 생략)
        # 대신 순이익 성장률 급변 여부 체크
        if len(financials) >= 2:
            sorted_fs = sorted(financials, key=lambda f: f.fiscal_year)
            prev = sorted_fs[-2]
            curr = sorted_fs[-1]

            if prev.net_income and prev.net_income > 0 and curr.net_income:
                growth = (curr.net_income - prev.net_income) / abs(prev.net_income)
                # 순이익 YoY 500% 이상 성장은 일회성 항목 의심
                if growth > 5.0:
                    reasons.append(f"순이익 YoY {growth*100:.0f}% 급증 (일회성 항목 의심)")
                    return 0.7

        return 0.0
