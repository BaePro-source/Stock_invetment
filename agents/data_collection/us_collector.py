"""
US stock data collector using yfinance (OHLCV + financials).
"""
import logging
from datetime import date, datetime, timedelta
from typing import List, Optional

from models.stock import Stock, PriceBar, FinancialStatement, BioMetrics, ValuationMetrics, NewsItem, Market, Sector
from config.settings import CollectorConfig

logger = logging.getLogger(__name__)

# 미국 Bio 섹터 티커 목록 (섹터 판별용)
US_BIO_TICKERS = {
    "MRNA", "GILD", "REGN", "VRTX", "BIIB", "AMGN", "ABBV",
    "BMY", "PFE", "JNJ", "INCY", "ALNY", "SRPT", "BLUE",
}


class USDataCollector:
    def __init__(self, cfg: CollectorConfig):
        self.cfg = cfg

    def collect_universe(self, tickers: Optional[List[str]] = None) -> List[Stock]:
        tickers = tickers or self.cfg.us_tickers
        stocks = []
        for ticker in tickers:
            try:
                stock = self.collect_stock(ticker)
                stocks.append(stock)
                logger.info(f"[US] 수집 완료: {ticker}")
            except Exception as e:
                logger.warning(f"[US] 수집 실패: {ticker} — {e}")
        return stocks

    def collect_stock(self, ticker: str) -> Stock:
        try:
            import yfinance as yf
        except ImportError:
            raise ImportError("pip install yfinance 를 먼저 실행하세요.")

        yf_ticker = yf.Ticker(ticker)
        info = yf_ticker.info or {}

        name = info.get("longName") or info.get("shortName") or ticker
        exchange = info.get("exchange", "")
        sector_str = info.get("sector", "").lower()

        market = Market.US_NASDAQ if "NAS" in exchange.upper() else Market.US_NYSE
        sector = self._classify_sector(ticker, sector_str)

        stock = Stock(
            ticker=ticker,
            name=name,
            market=market,
            sector=sector,
            collected_at=datetime.now(),
        )

        stock.price_history = self._fetch_prices(yf_ticker)
        stock.financials = self._fetch_financials(yf_ticker)

        if sector == Sector.BIO:
            stock.bio_metrics = self._fetch_bio_metrics(yf_ticker, info)

        stock.valuation = self._fetch_valuation(info)

        return stock

    def _classify_sector(self, ticker: str, sector_str: str) -> Sector:
        if ticker.upper() in US_BIO_TICKERS:
            return Sector.BIO
        if any(kw in sector_str for kw in ["biotech", "pharma", "healthcare", "drug"]):
            return Sector.BIO
        if any(kw in sector_str for kw in ["tech", "software", "semiconductor", "internet"]):
            return Sector.TECH
        return Sector.OTHER

    def _fetch_prices(self, yf_ticker, lookback_days: int = 365) -> List[PriceBar]:
        end = date.today()
        start = end - timedelta(days=lookback_days)

        df = yf_ticker.history(start=start.isoformat(), end=end.isoformat(), auto_adjust=True)
        if df.empty:
            return []

        bars = []
        for idx, row in df.iterrows():
            bars.append(PriceBar(
                date=idx.date() if hasattr(idx, "date") else idx,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=int(row["Volume"]),
                adj_close=float(row["Close"]),  # auto_adjust=True이므로 동일
            ))
        return bars

    def _fetch_financials(self, yf_ticker) -> List[FinancialStatement]:
        statements = []

        try:
            income = yf_ticker.financials          # 연간 손익계산서
            balance = yf_ticker.balance_sheet      # 연간 대차대조표
            cashflow = yf_ticker.cashflow          # 연간 현금흐름표
        except Exception as e:
            logger.warning(f"[US] 재무제표 수집 실패: {e}")
            return []

        if income is None or income.empty:
            return []

        for col in income.columns:
            fiscal_year = col.year if hasattr(col, "year") else int(str(col)[:4])

            def _safe(df, key: str) -> Optional[float]:
                try:
                    if df is not None and key in df.index and col in df.columns:
                        val = df.loc[key, col]
                        return float(val) if val is not None and str(val) != "nan" else None
                except Exception:
                    return None
                return None

            stmt = FinancialStatement(
                fiscal_year=fiscal_year,
                revenue=_safe(income, "Total Revenue"),
                operating_income=_safe(income, "Operating Income"),
                net_income=_safe(income, "Net Income"),
                total_assets=_safe(balance, "Total Assets"),
                total_equity=_safe(balance, "Stockholders Equity"),
                total_debt=_safe(balance, "Total Debt"),
                cash=_safe(balance, "Cash And Cash Equivalents"),
                operating_cash_flow=_safe(cashflow, "Operating Cash Flow"),
                capex=_safe(cashflow, "Capital Expenditure"),
                current_assets=_safe(balance, "Current Assets"),
                current_liabilities=_safe(balance, "Current Liabilities"),
            )
            statements.append(stmt)

        return statements

    def _fetch_valuation(self, info: dict) -> Optional[ValuationMetrics]:
        def _f(key: str) -> Optional[float]:
            val = info.get(key)
            try:
                return float(val) if val is not None and str(val) not in ("nan", "None", "Infinity") else None
            except (TypeError, ValueError):
                return None

        market_cap = _f("marketCap")
        if not market_cap:
            return None

        pe = _f("trailingPE")
        pb = _f("priceToBook")
        ev = _f("enterpriseValue")
        ebitda = _f("ebitda")
        ev_ebitda = _f("enterpriseToEbitda")

        # yfinance가 ev_ebitda를 주지 않으면 직접 계산
        if ev_ebitda is None and ev and ebitda and ebitda > 0:
            ev_ebitda = ev / ebitda

        return ValuationMetrics(
            market_cap=market_cap, pe_ratio=pe, pb_ratio=pb,
            ev=ev, ebitda=ebitda, ev_ebitda=ev_ebitda,
        )

    def _fetch_bio_metrics(self, yf_ticker, info: dict) -> BioMetrics:
        """Bio 섹터 전용 지표 추출 (가용한 데이터 범위 내)"""
        cash = None
        burn_rate = None
        runway = None

        try:
            balance = yf_ticker.balance_sheet
            cashflow = yf_ticker.cashflow

            if balance is not None and not balance.empty:
                col = balance.columns[0]
                if "Cash And Cash Equivalents" in balance.index:
                    cash = float(balance.loc["Cash And Cash Equivalents", col])

            if cashflow is not None and not cashflow.empty:
                col = cashflow.columns[0]
                if "Operating Cash Flow" in cashflow.index:
                    annual_cf = float(cashflow.loc["Operating Cash Flow", col])
                    # 음수 = 현금 소진 중
                    if annual_cf < 0:
                        burn_rate = abs(annual_cf) / 12
                        if cash and burn_rate > 0:
                            runway = cash / burn_rate
        except Exception as e:
            logger.debug(f"[US] Bio 지표 추출 실패: {e}")

        return BioMetrics(
            monthly_burn_rate=burn_rate,
            cash_runway_months=runway,
        )
