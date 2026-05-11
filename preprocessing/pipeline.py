"""
Double Preprocessing Pipeline: NoiseRemover → HypeFilter
"""
import logging
from typing import List, Tuple

from models.stock import Stock
from preprocessing.noise_removal import NoiseRemover
from preprocessing.hype_filter import HypeFilter, HypeReport
from config.settings import PreprocessingConfig

logger = logging.getLogger(__name__)


class PreprocessingPipeline:
    def __init__(self, cfg: PreprocessingConfig):
        self.noise_remover = NoiseRemover(cfg)
        self.hype_filter = HypeFilter(cfg)

    def run(self, stocks: List[Stock]) -> Tuple[List[Stock], List[HypeReport]]:
        """
        Returns:
            clean_stocks: hype 의심 제외된 정제 종목 리스트
            hype_reports: 전체 종목 hype 분석 결과 (hype 의심 포함)
        """
        clean_stocks = []
        hype_reports = []

        for stock in stocks:
            # Step 1: 수치 노이즈 제거
            stock = self.noise_remover.process(stock)

            # Step 2: 논리 일관성 + Hype 필터
            stock, report = self.hype_filter.process(stock)
            hype_reports.append(report)

            if report.is_hype_suspected:
                logger.warning(f"[Pipeline] {stock.ticker} hype 의심으로 분석 제외")
            else:
                clean_stocks.append(stock)

        logger.info(
            f"[Pipeline] 완료: 전체 {len(stocks)}개 → "
            f"정제 {len(clean_stocks)}개 / Hype 제외 {len(stocks)-len(clean_stocks)}개"
        )
        return clean_stocks, hype_reports
