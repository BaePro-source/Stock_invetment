"""
Korean stock data collector using pykrx (OHLCV) and OpenDartReader (financials).
"""
import logging
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict

from models.stock import Stock, PriceBar, FinancialStatement, NewsItem, Market, Sector
from config.settings import CollectorConfig

logger = logging.getLogger(__name__)

# 섹터별 KOSPI/KOSDAQ 주요 종목 (초기 유니버스)
KR_UNIVERSE: Dict[str, Dict[str, str]] = {
    "tech": {
        "005930": "삼성전자",
        "000660": "SK하이닉스",
        "035420": "NAVER",
        "035720": "카카오",
        "066570": "LG전자",
        "003670": "포스코퓨처엠",
        "247540": "에코프로비엠",
        "086520": "에코프로",
    },
    "bio": {
        "068270": "셀트리온",
        "207940": "삼성바이오로직스",
        "128940": "한미약품",
        "326030": "SK바이오팜",
        "145020": "휴젤",
        "196170": "알테오젠",
        "237690": "에스티팜",
    },
}


class KRDataCollector:
    def __init__(self, cfg: CollectorConfig):
        self.cfg = cfg
        self._dart = None  # lazy init

    def _get_dart(self):
        if self._dart is None:
            try:
                import opendartreader
                if not self.cfg.dart_api_key:
                    raise ValueError("DART API key가 설정되지 않았습니다. config.dart_api_key를 설정하세요.")
                self._dart = opendartreader.OpenDartReader(self.cfg.dart_api_key)
            except ImportError:
                raise ImportError("pip install OpenDartReader 를 먼저 실행하세요.")
        return self._dart

    def collect_universe(self, sectors: Optional[List[str]] = None) -> List[Stock]:
        sectors = sectors or self.cfg.kr_sectors
        stocks = []
        for sector in sectors:
            tickers = KR_UNIVERSE.get(sector, {})
            for ticker, name in tickers.items():
                try:
                    stock = self.collect_stock(ticker, name, sector)
                    stocks.append(stock)
                    logger.info(f"[KR] 수집 완료: {ticker} {name}")
                except Exception as e:
                    logger.warning(f"[KR] 수집 실패: {ticker} {name} — {e}")
        return stocks

    def collect_stock(self, ticker: str, name: str, sector_str: str) -> Stock:
        sector = Sector.TECH if sector_str == "tech" else Sector.BIO

        # 시장 구분 (6자리 코드: KOSPI vs KOSDAQ)
        market = self._resolve_market(ticker)

        stock = Stock(
            ticker=ticker,
            name=name,
            market=market,
            sector=sector,
            collected_at=datetime.now(),
        )

        stock.price_history = self._fetch_prices(ticker)
        stock.financials = self._fetch_financials(ticker)

        return stock

    def _resolve_market(self, ticker: str) -> Market:
        try:
            from pykrx import stock as pykrx_stock
            market_str = pykrx_stock.get_market_ticker_name(ticker)
            # pykrx로 KOSPI/KOSDAQ 구분
            kospi_tickers = pykrx_stock.get_market_ticker_list(market="KOSPI")
            return Market.KR_KOSPI if ticker in kospi_tickers else Market.KR_KOSDAQ
        except Exception:
            return Market.KR_KOSPI  # 기본값

    def _fetch_prices(self, ticker: str, lookback_days: int = 365) -> List[PriceBar]:
        try:
            from pykrx import stock as pykrx_stock
        except ImportError:
            raise ImportError("pip install pykrx 를 먼저 실행하세요.")

        end = date.today()
        start = end - timedelta(days=lookback_days)

        df = pykrx_stock.get_market_ohlcv(
            start.strftime("%Y%m%d"),
            end.strftime("%Y%m%d"),
            ticker,
        )

        if df.empty:
            logger.warning(f"[KR] 가격 데이터 없음: {ticker}")
            return []

        bars = []
        for idx, row in df.iterrows():
            bars.append(PriceBar(
                date=idx.date() if hasattr(idx, "date") else idx,
                open=float(row.get("시가", 0)),
                high=float(row.get("고가", 0)),
                low=float(row.get("저가", 0)),
                close=float(row.get("종가", 0)),
                volume=int(row.get("거래량", 0)),
            ))
        return bars

    def _fetch_financials(self, ticker: str) -> List[FinancialStatement]:
        try:
            dart = self._get_dart()
        except (ValueError, ImportError) as e:
            logger.warning(f"[KR] DART 재무 수집 건너뜀 ({ticker}): {e}")
            return []

        statements = []
        current_year = date.today().year

        for year in range(current_year - self.cfg.financial_years, current_year):
            try:
                fs = dart.finstate_all(ticker, year, reprt_code="11011")  # 사업보고서
                if fs is None or fs.empty:
                    continue

                stmt = self._parse_dart_fs(fs, year)
                if stmt:
                    statements.append(stmt)
            except Exception as e:
                logger.debug(f"[KR] {ticker} {year}년 재무 파싱 실패: {e}")

        return statements

    def _parse_dart_fs(self, df, fiscal_year: int) -> Optional[FinancialStatement]:
        """DART 재무제표 DataFrame → FinancialStatement"""

        def _get_value(account_name: str) -> Optional[float]:
            row = df[df["account_nm"].str.contains(account_name, na=False)]
            if row.empty:
                return None
            try:
                val = row.iloc[0].get("thstrm_amount", None)
                return float(str(val).replace(",", "")) if val else None
            except (ValueError, TypeError):
                return None

        stmt = FinancialStatement(
            fiscal_year=fiscal_year,
            revenue=_get_value("매출액"),
            operating_income=_get_value("영업이익"),
            net_income=_get_value("당기순이익"),
            total_assets=_get_value("자산총계"),
            total_equity=_get_value("자본총계"),
            total_debt=_get_value("부채총계"),
            cash=_get_value("현금및현금성자산"),
        )
        return stmt
