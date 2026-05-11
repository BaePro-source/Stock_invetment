# Stock Investment Agent

A multi-agent system for long-term equity investment analysis covering Korean (KRX) and US (NYSE/NASDAQ) markets. The system automates the full research pipeline — from data collection and noise filtering through fundamental/technical/sentiment scoring to portfolio allocation and risk management — and produces a structured investment report.

---

## Table of Contents

- [Architecture](#architecture)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Scoring Methodology](#scoring-methodology)
- [Risk Management](#risk-management)
- [Sample Output](#sample-output)

---

## Architecture

The system is organized as a sequential multi-agent pipeline:

```
DataCollectionAgent
    ├── KRDataCollector   (pykrx + OpenDartReader)
    ├── USDataCollector   (yfinance)
    └── NewsCollector     (Naver Search API / yfinance news)
         │
         ▼
PreprocessingPipeline
    ├── NoiseRemoval      (IQR-based outlier filtering)
    └── HypeFilter        (momentum + sentiment consistency check)
         │
         ▼
AnalysisAgent
    ├── FundamentalAnalyzer   (ROE, debt ratio, MOAT proxy, Bio cash runway)
    ├── TechnicalAnalyzer     (SMA-20/60, RSI-14, momentum, golden/dead cross)
    └── LlamaSentimentAnalyzer (Ollama llama3.1:8b, local inference)
         │
         ▼
RiskManagementAgent
    ├── PortfolioAllocator    (score²-proportional weighting)
    ├── StopLossMonitor       (fixed -15% + trailing -20%)
    └── RiskMetricsCalculator (MDD, annualized volatility, Sharpe ratio)
         │
         ▼
DecisionExecutor
    └── RecommendationEngine  (BUY / HOLD / SELL / WATCH / PASS)
         │
         ▼
    Investment Report (report_<timestamp>.txt)
```

---

## Features

- **Dual-market coverage** — Korean KOSPI/KOSDAQ and US NYSE/NASDAQ stocks in a single run
- **Sector focus** — Technology and Biotechnology with sector-specific screening rules
- **Double preprocessing** — IQR noise removal followed by hype detection to filter momentum-driven distortions
- **Three-factor scoring** — Fundamental (50%), Technical (30%), Sentiment (20%)
- **Local LLM sentiment analysis** — Runs entirely offline via Ollama; no API costs or rate limits
- **Bio-specific analysis** — Cash burn rate and runway estimation (minimum 18-month threshold)
- **MOAT proxy** — Revenue growth consistency and operating margin stability over 5 years
- **Portfolio construction** — Score²-proportional allocation with per-position (15%) and per-sector (40%) caps
- **Automated stop-loss** — Fixed stop at −15% from entry; trailing stop at −20% from peak
- **Rebalancing signals** — Triggers when actual weight deviates more than 5 percentage points from target

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.9+ | Tested on 3.14 |
| Ollama | latest | [ollama.com](https://ollama.com) — for local LLM inference |
| llama3.1:8b model | — | `ollama pull llama3.1:8b` |
| DART API key | — | [opendart.fss.or.kr](https://opendart.fss.or.kr) — Korean financial disclosures |
| Naver Search API | — | [developers.naver.com](https://developers.naver.com) — Korean news |

---

## Installation

**1. Clone the repository**

```bash
git clone <repository-url>
cd stock_investment
```

**2. Create and activate a virtual environment**

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

**3. Install dependencies**

```bash
pip install -r requirements.txt
```

**4. Pull the Ollama model**

```bash
ollama pull llama3.1:8b
```

---

## Configuration

Create a `.env` file in the project root with the following keys:

```env
DART_API_KEY=<your_dart_api_key>
NAVER_CLIENT_ID=<your_naver_client_id>
NAVER_CLIENT_SECRET=<your_naver_client_secret>
```

> **Note:** Do not include spaces or tab characters around the `=` sign.

### Key configuration parameters (`config/settings.py`)

| Parameter | Default | Description |
|---|---|---|
| `total_capital` | 10,000,000 KRW | Simulated portfolio size |
| `max_position_pct` | 15% | Maximum weight per single position |
| `max_sector_pct` | 40% | Maximum weight per sector |
| `stop_loss_pct` | 15% | Fixed stop-loss from entry price |
| `trailing_stop_pct` | 20% | Trailing stop from peak price |
| `min_roe` | 10% | Minimum ROE for fundamental screening |
| `max_debt_ratio` | 200% | Maximum debt-to-equity ratio |
| `min_cash_runway_months` | 18 | Minimum cash runway for Bio stocks |
| `financial_years` | 5 | Years of historical financials used |
| `llm.model` | llama3.1:8b | Ollama model for sentiment scoring |

---

## Usage

```bash
python main.py
```

The pipeline runs all five stages automatically and writes two outputs:
- **Console** — full report printed to stdout
- **File** — `report_<YYYYMMDD_HHMM>.txt` saved in the project root

To run with a custom report path:

```python
from main import run
run(report_path="my_report.txt")
```

---

## Project Structure

```
stock_investment/
│
├── main.py                          # Entry point
├── requirements.txt
├── .env                             # API keys (not committed)
│
├── config/
│   └── settings.py                  # All configuration dataclasses
│
├── models/
│   └── stock.py                     # Stock, PriceBar, FinancialStatement, NewsItem
│
├── preprocessing/
│   ├── pipeline.py                  # PreprocessingPipeline orchestrator
│   ├── noise_removal.py             # IQR-based outlier removal
│   └── hype_filter.py               # Momentum + sentiment hype detection
│
└── agents/
    ├── data_collection/
    │   ├── kr_collector.py          # KRX OHLCV via pykrx + financials via DART
    │   ├── us_collector.py          # US OHLCV + financials via yfinance
    │   └── news_collector.py        # Naver API (KR) + yfinance news (US)
    │
    ├── analysis/
    │   ├── analysis_agent.py        # Orchestrates all analyzers, computes total score
    │   ├── fundamental.py           # ROE, debt ratio, MOAT, Bio metrics
    │   ├── technical.py             # SMA, RSI, momentum, crossover signals
    │   └── sentiment.py             # LlamaSentimentAnalyzer (Ollama)
    │
    ├── risk_management/
    │   ├── risk_agent.py            # RiskManagementAgent orchestrator
    │   ├── portfolio.py             # Score²-proportional allocation
    │   ├── stop_loss.py             # Fixed + trailing stop-loss logic
    │   └── risk_metrics.py          # MDD, volatility, Sharpe ratio
    │
    └── decision_executor/
        ├── decision_executor.py     # DecisionExecutor entry point
        ├── recommendation.py        # RecommendationEngine (BUY/HOLD/SELL/WATCH/PASS)
        └── report.py                # Report formatter
```

---

## Scoring Methodology

Each stock receives a composite score out of 100:

| Component | Weight | Key Signals |
|---|---|---|
| **Fundamental** | 50% | ROE, debt ratio, current ratio, revenue growth consistency (MOAT), operating margin stability, Bio cash runway |
| **Technical** | 30% | SMA-20/60 trend, RSI-14 momentum, 1M/3M/6M price momentum, golden/dead cross |
| **Sentiment** | 20% | LLM-scored news articles (−1.0 to +1.0 scale), averaged per stock |

**Decision thresholds:**

| Score | Decision |
|---|---|
| ≥ 60 + portfolio capacity | **BUY** |
| ≥ 60, no portfolio capacity | **WATCH** |
| 40 – 59 | **WATCH** |
| < 40 | **PASS** |
| Trailing/fixed stop triggered | **SELL** (overrides score) |
| Failed fundamental screening | **PASS** (overrides score) |

If no sentiment data is available, the 20% sentiment weight is redistributed proportionally to Fundamental and Technical.

---

## Risk Management

**Portfolio allocation** uses score²-proportional weighting so that high-conviction names receive meaningfully larger allocations than borderline picks.

**Stop-loss rules** (applied before scoring):
- *Fixed stop*: position is flagged SELL if current price is more than 15% below entry price
- *Trailing stop*: position is flagged SELL if current price is more than 20% below its rolling peak

**Rebalancing** is triggered when any position's actual weight deviates by more than 5 percentage points from its target, generating a rebalancing action item in the report.

**Risk metrics** reported per position:
- Maximum Drawdown (MDD) over 252 trading days
- Annualized volatility (60-day window)
- Sharpe ratio (252-day window, 0% risk-free rate)

---

## Sample Output

```
============================================================
  Stock Investment Agent Report
  Generated: 2026-05-12 01:00
============================================================

[ Investment Decisions ]

  [BUY]  (8 stocks)
    GOOGL      Alphabet Inc.   score  84.3   $395   alloc 10.2%
      └ Composite score 84.3 (threshold 60.0)
      └ Revenue growth consistency 100%
    NVDA       NVIDIA Corp.    score  83.5   $208   alloc 10.1%
      └ Composite score 83.5 (threshold 60.0)
      └ Revenue growth consistency 100%
    ...

  [SELL]  (7 stocks)
    MSFT       Microsoft Corp  score  75.3   $411   alloc  8.2%
      └ Trailing stop triggered (peak drawdown -23.9%)
    ...

[ Portfolio Allocation ]
  Total Capital:  10,000,000 KRW
  Invested: 100.0%   Cash: 0.0%

[ Risk Metrics ]
  Ticker       MDD     Ann.Vol   Sharpe
  GOOGL      -13.1%    34.4%     3.26
  NVDA       -15.5%    38.9%     2.20
  ...

[ Action Items ]
   1. [Trailing Stop] MSFT — current 411 / peak drawdown -23.9%
   2. [Rebalance-Buy] 000660 — current 0.0% → target 8.2%
   ...
============================================================
```

---

## Dependencies

```
pykrx>=1.0.47          # Korean stock OHLCV (KRX)
opendartreader>=0.3.0  # Korean financial statements (DART)
yfinance>=0.2.36       # US stock data and news
pandas>=2.0.0
numpy>=1.26.0
ollama>=0.3.0          # Local LLM inference (Ollama)
requests>=2.31.0
beautifulsoup4>=4.12.0
python-dotenv>=1.0.0
```

---

## License

This project is for personal research and educational purposes. Not financial advice.
"# Stock_invetment" 
