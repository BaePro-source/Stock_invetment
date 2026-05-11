"""
Sentiment analysis interface + Llama (Ollama) 구현체.

사용법:
    analyzer = NullSentimentAnalyzer()              # LLM 없이 실행
    analyzer = LlamaSentimentAnalyzer(config.llm)   # Ollama llama3.1:8b
"""
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

from models.stock import NewsItem
from config.settings import LLMConfig

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """\
You are a financial analyst evaluating news for long-term stock investment.

News headline: {title}
Summary: {summary}

From a long-term investor's perspective, rate the sentiment of this news.
Reply with ONLY a single decimal number between -1.0 (very negative) and +1.0 (very positive).
Examples of valid replies: -0.8  0.3  0.7  -0.2
Do not add any explanation."""


@dataclass
class SentimentResult:
    ticker: str
    avg_score: Optional[float] = None    # -1(매우 부정) ~ +1(매우 긍정)
    article_count: int = 0
    scored_count: int = 0


class SentimentAnalyzer(ABC):

    @abstractmethod
    def score_news(self, news_items: List[NewsItem]) -> List[NewsItem]:
        """각 NewsItem의 sentiment_score를 채워서 반환"""

    def analyze(self, ticker: str, news_items: List[NewsItem]) -> SentimentResult:
        if not news_items:
            return SentimentResult(ticker=ticker)

        scored_items = self.score_news(news_items)
        scored = [n for n in scored_items if n.sentiment_score is not None]
        avg = sum(n.sentiment_score for n in scored) / len(scored) if scored else None

        return SentimentResult(
            ticker=ticker,
            avg_score=round(avg, 3) if avg is not None else None,
            article_count=len(news_items),
            scored_count=len(scored),
        )


class NullSentimentAnalyzer(SentimentAnalyzer):
    """LLM 미연동 시 사용 — 점수를 채우지 않음"""

    def score_news(self, news_items: List[NewsItem]) -> List[NewsItem]:
        return news_items


class LlamaSentimentAnalyzer(SentimentAnalyzer):
    """Ollama로 실행 중인 Llama 모델을 이용한 감성 분석기"""

    def __init__(self, cfg: LLMConfig):
        self.cfg = cfg
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import ollama
                self._client = ollama.Client(host=self.cfg.base_url)
                # 연결 확인
                self._client.list()
                logger.info(f"[Sentiment] Ollama 연결 성공: {self.cfg.base_url}")
            except ImportError:
                raise ImportError("pip install ollama 를 먼저 실행하세요.")
            except Exception as e:
                raise RuntimeError(
                    f"Ollama 서버에 연결할 수 없습니다 ({self.cfg.base_url}). "
                    f"'ollama serve' 가 실행 중인지 확인하세요. 오류: {e}"
                )
        return self._client

    def score_news(self, news_items: List[NewsItem]) -> List[NewsItem]:
        client = self._get_client()

        for i, item in enumerate(news_items):
            try:
                score = self._score_one(client, item)
                item.sentiment_score = score
                logger.debug(f"[Sentiment] {item.title[:40]}... → {score}")
            except Exception as e:
                logger.warning(f"[Sentiment] 기사 {i+1} 점수 실패: {e}")

        scored = sum(1 for n in news_items if n.sentiment_score is not None)
        logger.info(f"[Sentiment] {scored}/{len(news_items)}개 기사 점수 완료")
        return news_items

    def _score_one(self, client, item: NewsItem) -> Optional[float]:
        prompt = _PROMPT_TEMPLATE.format(
            title=item.title,
            summary=item.summary or "N/A",
        )

        response = client.generate(
            model=self.cfg.model,
            prompt=prompt,
            options={
                "num_predict": self.cfg.max_tokens,
                "temperature": 0.0,   # 결정론적 출력
            },
        )

        raw = response.get("response", "").strip()
        return self._parse_score(raw)

    @staticmethod
    def _parse_score(text: str) -> Optional[float]:
        """응답에서 -1.0 ~ 1.0 사이 숫자 추출"""
        match = re.search(r"-?\d+\.?\d*", text)
        if not match:
            return None
        try:
            val = float(match.group())
            return max(-1.0, min(1.0, val))   # 범위 클램핑
        except ValueError:
            return None
