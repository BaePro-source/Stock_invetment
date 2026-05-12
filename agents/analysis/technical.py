"""
Technical analysis: moving averages, RSI, momentum, trend signals.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional, List

from models.stock import Stock, PriceBar
from config.settings import AnalysisConfig

logger = logging.getLogger(__name__)


@dataclass
class TrendSignal:
    golden_cross: bool = False   # MA단기 > MA장기 (상승 추세)
    dead_cross: bool = False     # MA단기 < MA장기 (하락 추세)
    above_ma_long: bool = False  # 현재가 > MA장기 (지지선 위)


@dataclass
class TechnicalScore:
    ticker: str

    # 이동평균
    ma_short: Optional[float] = None
    ma_long: Optional[float] = None

    # 모멘텀 수익률
    return_1m: Optional[float] = None   # 1개월
    return_3m: Optional[float] = None   # 3개월
    return_6m: Optional[float] = None   # 6개월

    # RSI (14일)
    rsi: Optional[float] = None

    # 추세 신호
    trend: TrendSignal = field(default_factory=TrendSignal)

    # 최종 점수 (0~100)
    score: float = 0.0


class TechnicalAnalyzer:
    def __init__(self, cfg: AnalysisConfig):
        self.cfg = cfg

    def analyze(self, stock: Stock) -> TechnicalScore:
        result = TechnicalScore(ticker=stock.ticker)
        bars = stock.price_history

        if len(bars) < self.cfg.ma_long:
            logger.debug(f"[Technical] {stock.ticker}: 데이터 부족 ({len(bars)}개 < {self.cfg.ma_long})")
            return result

        closes = [b.close for b in bars]

        result.ma_short = self._sma(closes, self.cfg.ma_short)
        result.ma_long = self._sma(closes, self.cfg.ma_long)
        result.rsi = self._rsi(closes, period=14)

        result.return_1m = self._return(closes, 21)
        result.return_3m = self._return(closes, 63)
        result.return_6m = self._return(closes, 126)

        result.trend = self._trend_signal(closes, result.ma_short, result.ma_long)
        result.score = self._calculate_score(result)

        logger.debug(f"[Technical] {stock.ticker}: score={result.score:.1f}, RSI={result.rsi:.1f}")
        return result

    # ── 지표 계산 ──────────────────────────────────────────

    @staticmethod
    def _sma(closes: List[float], period: int) -> Optional[float]:
        if len(closes) < period:
            return None
        return sum(closes[-period:]) / period

    @staticmethod
    def _rsi(closes: List[float], period: int = 14) -> Optional[float]:
        if len(closes) < period + 1:
            return None

        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]

        # 첫 period개로 초기 단순 평균
        avg_gain = sum(max(d, 0) for d in deltas[:period]) / period
        avg_loss = sum(abs(min(d, 0)) for d in deltas[:period]) / period

        # 이후 Wilder's EMA 적용
        for d in deltas[period:]:
            avg_gain = (avg_gain * (period - 1) + max(d, 0)) / period
            avg_loss = (avg_loss * (period - 1) + abs(min(d, 0))) / period

        if avg_loss == 0:
            return 100.0
        return round(100 - (100 / (1 + avg_gain / avg_loss)), 2)

    @staticmethod
    def _return(closes: List[float], lookback: int) -> Optional[float]:
        if len(closes) < lookback + 1:
            return None
        past = closes[-lookback - 1]
        if past == 0:
            return None
        return (closes[-1] - past) / past

    def _trend_signal(
        self,
        closes: List[float],
        ma_short: Optional[float],
        ma_long: Optional[float],
    ) -> TrendSignal:
        signal = TrendSignal()
        if ma_short is None or ma_long is None:
            return signal

        signal.above_ma_long = closes[-1] > ma_long

        # 골든/데드 크로스: 오늘 vs 어제의 MA 관계 비교
        if len(closes) >= self.cfg.ma_short + 1:
            prev_ma_short = self._sma(closes[:-1], self.cfg.ma_short)
            prev_ma_long = self._sma(closes[:-1], self.cfg.ma_long)
            if prev_ma_short and prev_ma_long:
                was_below = prev_ma_short < prev_ma_long
                is_above = ma_short > ma_long
                signal.golden_cross = was_below and is_above
                signal.dead_cross = (not was_below) and (not is_above)

        return signal

    # ── 점수 산출 ──────────────────────────────────────────

    def _calculate_score(self, result: TechnicalScore) -> float:
        score = 0.0

        # RSI (25점) — 40~60 중립, 50~70 매수 우호, 30 이하 과매도 반등 기대
        if result.rsi is not None:
            if 50 <= result.rsi <= 70:
                score += 25
            elif 40 <= result.rsi < 50:
                score += 15
            elif result.rsi < 30:
                score += 20   # 과매도 구간: 반등 기대
            elif result.rsi > 80:
                score += 5    # 과매수 주의

        # 모멘텀 (30점) — 3개월 수익률 기준
        if result.return_3m is not None:
            if result.return_3m > 0.15:
                score += 30
            elif result.return_3m > 0.05:
                score += 20
            elif result.return_3m > 0:
                score += 10
            # 음수 모멘텀은 점수 없음

        # 추세 (30점)
        if result.trend.golden_cross:
            score += 30
        elif result.trend.above_ma_long:
            score += 20
        elif result.trend.dead_cross:
            score += 0
        else:
            score += 10

        # 6개월 vs 1개월 모멘텀 가속 여부 (15점)
        if result.return_1m is not None and result.return_6m is not None:
            monthly_avg_6m = result.return_6m / 6
            if result.return_1m > monthly_avg_6m:  # 최근 모멘텀 가속 중
                score += 15

        return round(min(score, 100.0), 2)
