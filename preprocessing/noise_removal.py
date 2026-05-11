"""
Step 1: Noise removal — numerical outlier filtering and volume-based filtering.
"""
import logging
import statistics
from typing import List

from models.stock import Stock, PriceBar, Market
from config.settings import PreprocessingConfig

logger = logging.getLogger(__name__)


class NoiseRemover:
    def __init__(self, cfg: PreprocessingConfig):
        self.cfg = cfg

    def process(self, stock: Stock) -> Stock:
        stock.price_history = self._filter_prices(stock)
        return stock

    def _filter_prices(self, stock: Stock) -> List[PriceBar]:
        bars = stock.price_history
        if not bars:
            return bars

        min_volume = (
            self.cfg.min_volume_kr
            if stock.market in (Market.KR_KOSPI, Market.KR_KOSDAQ)
            else self.cfg.min_volume_us
        )

        # 1차: 거래량 0 또는 최소 거래량 미만 제거
        bars = [b for b in bars if b.volume >= min_volume]

        # 2차: 종가 IQR 이상치 제거
        bars = self._remove_price_outliers(bars)

        removed = len(stock.price_history) - len(bars)
        if removed > 0:
            logger.debug(f"[Noise] {stock.ticker}: {removed}개 캔들 제거")

        return bars

    def _remove_price_outliers(self, bars: List[PriceBar]) -> List[PriceBar]:
        if len(bars) < 10:
            return bars

        closes = [b.close for b in bars]
        q1 = self._percentile(closes, 25)
        q3 = self._percentile(closes, 75)
        iqr = q3 - q1
        lower = q1 - self.cfg.iqr_multiplier * iqr
        upper = q3 + self.cfg.iqr_multiplier * iqr

        return [b for b in bars if lower <= b.close <= upper]

    @staticmethod
    def _percentile(data: List[float], pct: float) -> float:
        sorted_data = sorted(data)
        k = (len(sorted_data) - 1) * pct / 100
        f = int(k)
        c = f + 1
        if c >= len(sorted_data):
            return sorted_data[f]
        return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])
