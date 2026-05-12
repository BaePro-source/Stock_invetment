"""
Stock Investment Agent - Entry Point

실행 흐름:
  DataCollection → Preprocessing → AnalysisAgent → RiskManagementAgent → DecisionExecutor
"""
import io
import logging
import sys
from datetime import datetime

# Windows cp949 콘솔에서 유니코드 출력 강제
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from config import config
from agents.data_collection import KRDataCollector, USDataCollector, NewsCollector
from agents.analysis import AnalysisAgent
from agents.analysis.sentiment import LlamaSentimentAnalyzer
from agents.risk_management import RiskManagementAgent
from agents.decision_executor import DecisionExecutor
from backtesting import BacktestEngine

from preprocessing import PreprocessingPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def run(report_path: str = "report.txt"):
    ts = datetime.now().strftime("%Y%m%d_%H%M")

    # ── 1. 데이터 수집 ──────────────────────────────────
    logger.info("=== [1/4] 데이터 수집 ===")
    kr_stocks = KRDataCollector(config.collector).collect_universe()
    us_stocks = USDataCollector(config.collector).collect_universe()
    all_stocks = kr_stocks + us_stocks
    logger.info(f"KR {len(kr_stocks)}개 / US {len(us_stocks)}개 수집 완료")

    logger.info("=== [1-2/4] 뉴스 수집 ===")
    all_stocks = NewsCollector(config.news).collect(all_stocks)

    # ── 2. 전처리 ───────────────────────────────────────
    logger.info("=== [2/4] 전처리 파이프라인 ===")
    clean_stocks, hype_reports = PreprocessingPipeline(config.preprocessing).run(all_stocks)
    hype_tickers = [r.ticker for r in hype_reports if r.is_hype_suspected]
    if hype_tickers:
        logger.info(f"Hype 제외: {hype_tickers}")

    # ── 3. 분석 ─────────────────────────────────────────
    logger.info("=== [3/4] AnalysisAgent (Llama 감성 분석 포함) ===")
    sentiment_analyzer = LlamaSentimentAnalyzer(config.llm)
    analysis_results = AnalysisAgent(config.analysis, sentiment_analyzer).analyze_all(clean_stocks)

    # ── 4. 리스크 관리 ───────────────────────────────────
    logger.info("=== [4/4] RiskManagementAgent ===")
    risk_result = RiskManagementAgent(config.risk).run(analysis_results, clean_stocks)

    # ── 5. 최종 결정 ─────────────────────────────────────
    save_path = f"report_{ts}.txt"
    executor = DecisionExecutor(report_save_path=save_path)
    execution = executor.execute(analysis_results, risk_result)

    # 리포트 콘솔 출력
    print("\n" + execution.report_text)

    return execution


def run_backtest(report_path: str = "backtest_report.txt"):
    """데이터 수집 후 백테스트만 실행."""
    ts = datetime.now().strftime("%Y%m%d_%H%M")

    logger.info("=== [1/2] 데이터 수집 ===")
    kr_stocks = KRDataCollector(config.collector).collect_universe()
    us_stocks = USDataCollector(config.collector).collect_universe()
    all_stocks = kr_stocks + us_stocks
    logger.info(f"KR {len(kr_stocks)}개 / US {len(us_stocks)}개 수집 완료")

    logger.info("=== [2/2] 백테스트 실행 ===")
    engine = BacktestEngine(config.backtest, config.analysis)
    result = engine.run(all_stocks)

    save_path = f"backtest_{ts}.txt"
    result.save_report(save_path)
    print("\n" + result.report_text)
    return result


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "backtest":
        run_backtest()
    else:
        run()
