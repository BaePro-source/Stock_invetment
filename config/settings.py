import os
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

load_dotenv()


@dataclass
class CollectorConfig:
    dart_api_key: str = field(default_factory=lambda: os.getenv("DART_API_KEY", ""))

    # 한국 주식 수집 대상 섹터 코드 (KOSPI/KOSDAQ)
    kr_sectors: List[str] = field(default_factory=lambda: ["tech", "bio"])

    # 미국 주식 수집 대상 티커 (초기 유니버스)
    us_tickers: List[str] = field(default_factory=lambda: [
        "AAPL", "MSFT", "GOOGL", "NVDA", "META",   # Tech
        "MRNA", "GILD", "REGN", "VRTX", "BIIB",    # Bio
    ])

    # 뉴스 수집 기간 (일)
    news_lookback_days: int = 30

    # 재무 데이터 기간 (연)
    financial_years: int = 5


@dataclass
class PreprocessingConfig:
    # 이상치 제거 IQR 배수
    iqr_multiplier: float = 1.5

    # Hype 필터: 뉴스 감성 점수 임계값 (이 이상이면 hype 의심)
    hype_sentiment_threshold: float = 0.85

    # 최소 거래량 (노이즈 제거)
    min_volume_kr: int = 10_000
    min_volume_us: int = 50_000


@dataclass
class AnalysisConfig:
    # 펀더멘털 스크리닝 임계값
    min_roe: float = 0.10          # ROE 10% 이상
    max_debt_ratio: float = 2.0    # 부채비율 200% 이하
    min_current_ratio: float = 1.0 # 유동비율 1.0 이상

    # 기술적 분석 이동평균 기간
    ma_short: int = 20
    ma_long: int = 60

    # Bio 섹터 특수 지표
    min_cash_runway_months: int = 18  # 현금 소진까지 최소 18개월


@dataclass
class NewsConfig:
    naver_client_id: str = field(default_factory=lambda: os.getenv("NAVER_CLIENT_ID", ""))
    naver_client_secret: str = field(default_factory=lambda: os.getenv("NAVER_CLIENT_SECRET", ""))
    # 종목당 수집할 최대 뉴스 기사 수
    max_articles_per_stock: int = 10
    # 뉴스 검색 기간 (일)
    lookback_days: int = 30


@dataclass
class LLMConfig:
    model: str = "llama3.1:8b"
    base_url: str = "http://localhost:11434"
    # 뉴스 기사 한 번에 처리할 배치 크기
    batch_size: int = 5
    # 응답 최대 토큰 (점수 숫자만 받으므로 작게)
    max_tokens: int = 16
    # 요청 타임아웃 (초)
    timeout: int = 30


@dataclass
class RiskConfig:
    # 포트폴리오 총 자본 (원화 기준, 시뮬레이션용)
    total_capital: float = 10_000_000.0

    # 종목당 최대 비중
    max_position_pct: float = 0.15        # 15%
    # 섹터당 최대 비중
    max_sector_pct: float = 0.40          # 40%
    # 단일 종목 최소 비중 (이하면 편입 의미 없음)
    min_position_pct: float = 0.02        # 2%

    # 손절 기준
    stop_loss_pct: float = 0.15           # 매입가 대비 -15%
    trailing_stop_pct: float = 0.20       # 고점 대비 -20%

    # 리밸런싱 트리거: 목표 비중 대비 이 이상 이탈 시
    rebalance_threshold_pct: float = 0.05  # 5%p

    # 리스크 지표 계산 기간 (거래일)
    volatility_window: int = 60
    mdd_window: int = 252                 # 1년


@dataclass
class AppConfig:
    collector: CollectorConfig = field(default_factory=CollectorConfig)
    preprocessing: PreprocessingConfig = field(default_factory=PreprocessingConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    news: NewsConfig = field(default_factory=NewsConfig)


# 싱글턴 설정 인스턴스
config = AppConfig()
