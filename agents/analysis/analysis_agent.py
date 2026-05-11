"""
AnalysisAgent: FundamentalAnalyzer + TechnicalAnalyzer + SentimentAnalyzer 통합.
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from models.stock import Stock, Sector
from agents.analysis.fundamental import FundamentalAnalyzer, FundamentalScore
from agents.analysis.technical import TechnicalAnalyzer, TechnicalScore
from agents.analysis.sentiment import SentimentAnalyzer, NullSentimentAnalyzer, SentimentResult
from config.settings import AnalysisConfig

logger = logging.getLogger(__name__)

# 가중치: 펀더멘털 50 / 기술적 30 / 감성 20
WEIGHT_FUNDAMENTAL = 0.50
WEIGHT_TECHNICAL = 0.30
WEIGHT_SENTIMENT = 0.20


@dataclass
class AnalysisResult:
    ticker: str
    name: str
    sector: Sector

    fundamental: Optional[FundamentalScore] = None
    technical: Optional[TechnicalScore] = None
    sentiment: Optional[SentimentResult] = None

    # 종합 점수 (0~100)
    total_score: float = 0.0
    is_investable: bool = False   # 스크리닝 통과 + 최소 점수 이상

    summary: str = ""


class AnalysisAgent:
    def __init__(
        self,
        cfg: AnalysisConfig,
        sentiment_analyzer: Optional[SentimentAnalyzer] = None,
    ):
        self.fundamental = FundamentalAnalyzer(cfg)
        self.technical = TechnicalAnalyzer(cfg)
        self.sentiment = sentiment_analyzer or NullSentimentAnalyzer()

    def analyze_all(self, stocks: List[Stock]) -> List[AnalysisResult]:
        results = []
        for stock in stocks:
            result = self.analyze(stock)
            results.append(result)

        # 점수 높은 순 정렬
        results.sort(key=lambda r: r.total_score, reverse=True)
        logger.info(f"[Analysis] 분석 완료: {len(results)}개 종목")
        return results

    def analyze(self, stock: Stock) -> AnalysisResult:
        result = AnalysisResult(
            ticker=stock.ticker,
            name=stock.name,
            sector=stock.sector,
        )

        # 1. 펀더멘털
        result.fundamental = self.fundamental.analyze(stock)

        # 스크리닝 탈락 시 나머지 분석 생략
        if not result.fundamental.passed_screening:
            result.summary = "펀더멘털 스크리닝 탈락: " + ", ".join(result.fundamental.fail_reasons)
            logger.info(f"[Analysis] {stock.ticker} 탈락 — {result.summary}")
            return result

        # 2. 기술적
        result.technical = self.technical.analyze(stock)

        # 3. 감성 (뉴스 있을 때만)
        if stock.news:
            result.sentiment = self.sentiment.analyze(stock.ticker, stock.news)

        # 4. 종합 점수
        result.total_score = self._combine_scores(result)
        result.is_investable = result.total_score >= 50.0
        result.summary = self._make_summary(result)

        logger.info(
            f"[Analysis] {stock.ticker} {stock.name}: "
            f"total={result.total_score:.1f} investable={result.is_investable}"
        )
        return result

    def _combine_scores(self, result: AnalysisResult) -> float:
        f_score = result.fundamental.score if result.fundamental else 0.0
        t_score = result.technical.score if result.technical else 0.0

        # 감성 점수: -1~+1 → 0~100 변환
        s_score = 50.0  # 감성 데이터 없으면 중립
        if result.sentiment and result.sentiment.avg_score is not None:
            s_score = (result.sentiment.avg_score + 1) / 2 * 100

        # 감성 데이터 없으면 가중치 재분배
        if result.sentiment is None or result.sentiment.avg_score is None:
            total = (
                f_score * (WEIGHT_FUNDAMENTAL / (WEIGHT_FUNDAMENTAL + WEIGHT_TECHNICAL))
                + t_score * (WEIGHT_TECHNICAL / (WEIGHT_FUNDAMENTAL + WEIGHT_TECHNICAL))
            )
        else:
            total = (
                f_score * WEIGHT_FUNDAMENTAL
                + t_score * WEIGHT_TECHNICAL
                + s_score * WEIGHT_SENTIMENT
            )

        return round(total, 2)

    def _make_summary(self, result: AnalysisResult) -> str:
        parts = []

        f = result.fundamental
        if f:
            roe_str = f"{f.latest_roe*100:.1f}%" if f.latest_roe else "N/A"
            parts.append(f"ROE={roe_str}")
            if f.moat.revenue_growth_consistency is not None:
                parts.append(f"매출일관성={f.moat.revenue_growth_consistency*100:.0f}%")

        t = result.technical
        if t:
            rsi_str = f"{t.rsi:.0f}" if t.rsi else "N/A"
            parts.append(f"RSI={rsi_str}")
            if t.trend.golden_cross:
                parts.append("골든크로스")
            if t.return_3m is not None:
                parts.append(f"3M수익={t.return_3m*100:.1f}%")

        # Bio 런웨이
        if f and f.cash_runway_months:
            parts.append(f"런웨이={f.cash_runway_months:.0f}개월")

        verdict = "투자적합" if result.is_investable else "보류"
        return f"[{verdict}] {', '.join(parts)}"
