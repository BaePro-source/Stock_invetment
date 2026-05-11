from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, List
from enum import Enum


class Market(Enum):
    KR_KOSPI = "KOSPI"
    KR_KOSDAQ = "KOSDAQ"
    US_NYSE = "NYSE"
    US_NASDAQ = "NASDAQ"


class Sector(Enum):
    TECH = "tech"
    BIO = "bio"
    OTHER = "other"


@dataclass
class PriceBar:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    adj_close: Optional[float] = None


@dataclass
class FinancialStatement:
    """연간 재무제표 핵심 지표"""
    fiscal_year: int
    revenue: Optional[float] = None          # 매출액
    operating_income: Optional[float] = None  # 영업이익
    net_income: Optional[float] = None        # 당기순이익
    total_assets: Optional[float] = None      # 총자산
    total_equity: Optional[float] = None      # 자기자본
    total_debt: Optional[float] = None        # 총부채
    cash: Optional[float] = None              # 현금 및 현금성 자산
    operating_cash_flow: Optional[float] = None  # 영업현금흐름
    capex: Optional[float] = None             # 설비투자

    @property
    def roe(self) -> Optional[float]:
        if self.net_income and self.total_equity and self.total_equity != 0:
            return self.net_income / self.total_equity
        return None

    @property
    def debt_ratio(self) -> Optional[float]:
        if self.total_debt and self.total_equity and self.total_equity != 0:
            return self.total_debt / self.total_equity
        return None

    @property
    def operating_margin(self) -> Optional[float]:
        if self.operating_income and self.revenue and self.revenue != 0:
            return self.operating_income / self.revenue
        return None


@dataclass
class BioMetrics:
    """Bio 섹터 전용 지표"""
    pipeline_stage: Optional[str] = None       # Phase 1/2/3/NDA
    monthly_burn_rate: Optional[float] = None  # 월 현금 소진액
    cash_runway_months: Optional[float] = None # 현금 런웨이 (개월)
    loa_score: Optional[float] = None          # Likelihood of Approval (0~1)
    primary_indication: Optional[str] = None   # 주요 적응증


@dataclass
class NewsItem:
    source: str
    title: str
    published_at: datetime
    url: str
    summary: Optional[str] = None
    sentiment_score: Optional[float] = None    # -1 ~ +1, LLM이 채울 필드
    is_hype_flagged: bool = False


@dataclass
class Stock:
    ticker: str
    name: str
    market: Market
    sector: Sector
    price_history: List[PriceBar] = field(default_factory=list)
    financials: List[FinancialStatement] = field(default_factory=list)
    news: List[NewsItem] = field(default_factory=list)
    bio_metrics: Optional[BioMetrics] = None   # Bio 섹터만 사용
    collected_at: Optional[datetime] = None

    @property
    def latest_price(self) -> Optional[PriceBar]:
        return self.price_history[-1] if self.price_history else None

    @property
    def latest_financials(self) -> Optional[FinancialStatement]:
        if not self.financials:
            return None
        return max(self.financials, key=lambda f: f.fiscal_year)
