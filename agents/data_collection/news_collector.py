"""
News collector:
  - 한국 종목: 네이버 뉴스 검색 API
  - 미국 종목: yfinance 내장 뉴스
"""
import logging
import re
from datetime import datetime, timedelta
from typing import List

import requests

from models.stock import Stock, NewsItem, Market
from config.settings import NewsConfig

logger = logging.getLogger(__name__)

NAVER_SEARCH_URL = "https://openapi.naver.com/v1/search/news.json"


class NewsCollector:
    def __init__(self, cfg: NewsConfig):
        self.cfg = cfg

    def collect(self, stocks: List[Stock]) -> List[Stock]:
        for stock in stocks:
            try:
                if stock.market in (Market.KR_KOSPI, Market.KR_KOSDAQ):
                    stock.news = self._fetch_kr_news(stock.name, stock.ticker)
                else:
                    stock.news = self._fetch_us_news(stock.ticker)

                logger.info(f"[News] {stock.ticker} {stock.name}: {len(stock.news)}개 수집")
            except Exception as e:
                logger.warning(f"[News] {stock.ticker} 수집 실패: {e}")

        return stocks

    # ── 한국: 네이버 뉴스 검색 API ────────────────────────

    def _fetch_kr_news(self, name: str, ticker: str) -> List[NewsItem]:
        if not self.cfg.naver_client_id or not self.cfg.naver_client_secret:
            logger.warning("[News] 네이버 API 키 없음 — 한국 뉴스 수집 건너뜀")
            return []

        headers = {
            "X-Naver-Client-Id": self.cfg.naver_client_id,
            "X-Naver-Client-Secret": self.cfg.naver_client_secret,
        }
        params = {
            "query": f"{name} 주식",
            "display": self.cfg.max_articles_per_stock,
            "sort": "date",
        }

        resp = requests.get(NAVER_SEARCH_URL, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        items = resp.json().get("items", [])

        news = []
        for item in items:
            news.append(NewsItem(
                source="naver",
                title=self._strip_html(item.get("title", "")),
                published_at=self._parse_naver_date(item.get("pubDate", "")),
                url=item.get("originallink") or item.get("link", ""),
                summary=self._strip_html(item.get("description", "")),
            ))
        return news

    # ── 미국: yfinance 내장 뉴스 ──────────────────────────

    def _fetch_us_news(self, ticker: str) -> List[NewsItem]:
        try:
            import yfinance as yf
        except ImportError:
            raise ImportError("pip install yfinance 를 먼저 실행하세요.")

        raw_news = yf.Ticker(ticker).news or []
        cutoff = datetime.now() - timedelta(days=self.cfg.lookback_days)

        news = []
        for item in raw_news[:self.cfg.max_articles_per_stock]:
            # yfinance는 Unix timestamp 반환
            pub_ts = item.get("providerPublishTime") or item.get("publishedAt", 0)
            pub_dt = datetime.fromtimestamp(pub_ts) if pub_ts else datetime.now()

            if pub_dt < cutoff:
                continue

            # yfinance 0.2.x 이후 구조
            content = item.get("content") or {}
            title = (
                item.get("title")
                or content.get("title")
                or ""
            )
            summary = (
                item.get("summary")
                or content.get("summary")
                or ""
            )
            url = (
                item.get("link")
                or content.get("canonicalUrl", {}).get("url")
                or ""
            )

            if not title:
                continue

            news.append(NewsItem(
                source=item.get("publisher") or "yahoo",
                title=title,
                published_at=pub_dt,
                url=url,
                summary=summary,
            ))

        return news

    # ── 유틸 ──────────────────────────────────────────────

    @staticmethod
    def _strip_html(text: str) -> str:
        return re.sub(r"<[^>]+>", "", text).strip()

    @staticmethod
    def _parse_naver_date(date_str: str) -> datetime:
        # 네이버 날짜 형식: "Mon, 12 May 2025 10:30:00 +0900"
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(date_str).replace(tzinfo=None)
        except Exception:
            return datetime.now()
