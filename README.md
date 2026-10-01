# Experimental TradingAgents Fork

> [!IMPORTANT]
> This repository is an experimental fork of
> [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents),
> based on upstream **TradingAgents v0.5.1**.
>
> Fork repository:
> [https://github.com/ubanov/TradingAgents](https://github.com/ubanov/TradingAgents)
>
> The original project and its authors remain the source of the underlying
> TradingAgents framework. This fork adds a set of experimental changes focused
> on prompt transparency, evidence integrity, debate structure, verification,
> unattended execution, and future evaluation of agent recommendations.

## Changes in this fork

### Prompt architecture

- Agent prompts have been externalized from Python code into text files under
  `tradingagents/prompts/`, making them easier to inspect, modify, compare, and
  version independently from the agent implementation.

- A shared `global_policy.txt` has been added and is automatically applied to
  the relevant LLM agents.

- The shared policy includes common numerical and evidence-integrity rules:
  - do not present unsupported numerical claims as facts;
  - verify arithmetic before relying on a numerical result;
  - independently check numerical claims made by other agents;
  - do not invent probabilities, historical frequencies, expected outcomes,
    or other statistics when they are not supported by supplied data;
  - preserve units and distinguish price distance, ATR, volatility, position
    size, notional exposure, and portfolio risk;
  - prefer evidence, calculations, and explicit reasoning over rhetorical
    argument.

### Research debate architecture

- The Bull and Bear researchers now create their **initial theses
  independently** from the Analyst Team reports.

- The initial Bull thesis is generated without seeing the Bear thesis, and the
  initial Bear thesis is generated without seeing the Bull thesis. This is
  intended to reduce first-mover bias and prevent one side from anchoring the
  other's initial interpretation.

- After the independent phase, Bull and Bear enter explicit **cross-review
  rounds** where they can challenge calculations, evidence, assumptions,
  contradictions, and unsupported conclusions in the opposing thesis.

- Reviews explicitly classify disputed points using states such as
  **ACCEPTED**, **REJECTED**, and **UNRESOLVED**.

- Research depth controls the number of Bull/Bear review rounds:
  - **Shallow:** 1 review round;
  - **Medium:** 2 review rounds;
  - **Deep:** 3 review rounds.

- Research review depth is kept separate from Risk Management discussion depth,
  so increasing research depth does not implicitly increase unrelated Risk
  debate.

### Collaborative research reviews

- Bull and Bear retain distinct bullish and bearish perspectives so the same
  evidence is explored from materially different starting points.

- During cross-review they act as complementary researchers with the shared
  objective of improving forecast accuracy, calibration, evidence quality,
  and robustness, rather than trying to win a debate.

- Accepting a supported correction or lowering conviction after valid
  counterevidence is treated as a successful research outcome, not a loss.
  Genuinely unresolved disagreements remain explicit instead of being forced
  into artificial consensus.

### Research Verifier

- An independent **Research Verifier** has been added between the completed
  Bull/Bear debate and the Research Manager.

- The verifier does not decide whether the bullish or bearish investment thesis
  is preferable. Its role is quality control.

- It checks for issues such as:
  - arithmetic errors;
  - unit or dimensional errors;
  - unsupported claims;
  - source/evidence mismatches;
  - contradictions;
  - conclusions that materially overstate the supplied evidence.

- Verification results distinguish between **PASS**, **WARN**, and **FAIL**.

- Material verification failures can trigger a bounded **repair round** before
  the result is passed to the Research Manager.

- The repair process is deliberately bounded so the system cannot enter an
  indefinite verifier/repair loop.

- Repair reuses the same structured review mechanism as a normal cross-review
  round: when it succeeds, the repaired position updates the canonical
  `bull_thesis`/`bear_thesis` (trade-plan levels, conviction) the same way a
  review would, so the Research Manager, the post-manager integrity check, and
  the Trader all see the repaired levels automatically. A level that a repair
  revises or withdraws is tracked the same way a normal review's is, and can
  never again be treated as active verified provenance. If structured output
  is unavailable, the repair still produces free text for semantic context,
  but the structured trade plan is explicitly left unchanged rather than
  guessed at — this is recorded per side (`APPLIED` / `TEXT_ONLY` / `NOT_RUN`)
  and surfaced to the Research Manager and the Trader so neither treats a
  stale structured value as repair-confirmed.

### Research Manager integrity check

- The Research Verifier checks the Bull/Bear research *before* it reaches the
  Research Manager, but the manager itself is a free-text-capable synthesis
  step: real runs showed it could reintroduce a numeric threshold, sizing
  rule, or price level that was never in the verified evidence (e.g. an
  invented MACD-histogram threshold, volume threshold, allocation percentage,
  or yield trigger).

- The Research Manager's prompt is now explicit that its role is **synthesis
  of the verified research, not creation of a new trading system**: it may
  select between, combine, or summarize existing supported interpretations
  and deterministic metrics, but must not invent new price targets, stops,
  thresholds, probabilities, historical frequencies, sizing/allocation
  percentages, or arbitrary confirmation conditions.

- A lightweight, **deterministic, LLM-free check** runs immediately after the
  Research Manager and before the Trader. It builds a pool of every number
  already traceable to the analyst reports, the verified Bull/Bear trade
  plans, or deterministic calculations, then flags any operational
  threshold/sizing claim in the manager's output that isn't traceable to it,
  a trade-plan level withdrawn during review resurfacing, or conviction
  being described as a forecast probability. No LLM call is added, and no
  automatic correction loop is triggered.

- Result is **PASS** or **WARN** with compact finding categories
  (`NEW_UNSUPPORTED_THRESHOLD`, `NEW_UNSUPPORTED_LEVEL`,
  `UNSUPPORTED_SIZING_RULE`, `CONVICTION_AS_PROBABILITY`,
  `WITHDRAWN_VALUE_REUSED`, among others). On WARN, the offending claims are
  not silently rewritten or dropped (the manager's text could change
  meaning); they are passed to the Trader explicitly marked as unsupported,
  rather than as if they were verified input.

### Constrained review rounds

- Normal Bull/Bear review rounds primarily defend, refute, correct, accept, or
  withdraw claims already present in the initial theses, using only:
  - the supplied analyst reports;
  - either side's initial thesis;
  - the shared objective setup tags;
  - deterministic recalculations from numbers already in that evidence.

- Reviews should not introduce a new market fact, source, price level,
  threshold, or catalyst that cannot be derived from that evidence.

- **NEW_DATA_EXCEPTION**: a narrow, explicit exception for when a new datum is
  genuinely necessary to correct a material factual misunderstanding. A review
  that uses one must mark it explicitly, with what the datum is, why it is
  necessary, and where it came from. The Research Verifier can flag an
  unmarked introduction of new data or an unnecessary/poorly justified
  exception.

### Structured Bull/Bear trade hypotheses

- Each initial Bull and Bear thesis commits to a structured trade hypothesis:
  direction, conviction (see below), an explicit shared analysis horizon,
  entry level or range, take-profit target, and stop-loss/invalidation level,
  alongside supporting evidence, key risks, and explicit data gaps.

- Entry, take-profit, and stop-loss are explicit commitments. Later review
  rounds classify each as **KEEP**, **REVISE**, or **WITHDRAW** rather than
  freely replacing them; a REVISE or WITHDRAW must state a reason grounded in
  already-supplied evidence.

- Bear's direction represents a bearish/reduce-risk thesis, consistent with
  the existing Trader semantics (Buy/Hold/Sell) — it is not forced into a
  literal short trade.

### Conviction semantics

- Conviction is a structured 0–100 score with four 0–25 components (evidence
  quality, internal consistency, robustness to challenge, trade-plan
  coherence). The total is always recomputed deterministically from the
  components in code, so it cannot drift from a model's own arithmetic.

- **Conviction is a self-assessed evidence-strength score, NOT a calibrated
  probability of the market outcome**, and the Research Manager is told not to
  select a thesis, or build a mechanical winner rule, solely because its
  conviction score is higher.

- Conviction is tracked across the debate: an initial value, a value after
  each review round, and a required reason whenever it changes materially.
  Lowering conviction after valid counterevidence is treated as a successful,
  well-calibrated research outcome, not a loss.

### Shared research horizon

- Bull and Bear use the same explicit analysis horizon (a shared config value,
  not independently chosen), so one side cannot silently reason over a
  materially different holding window than the other.

### Objective setup tags

- A small, fixed v1 taxonomy of objective market-state tags (RSI bucket, MACD
  sign, MACD histogram sign, price vs. EMA10/SMA20/SMA50, SMA50-vs-SMA200,
  ATR% bucket, volume-vs-average bucket, trend structure) is computed
  deterministically from market data, once per run, and given identically to
  both Bull and Bear.

- Tags are objective buckets, not interpretations: Bull and Bear may read the
  same tags differently, and that disagreement is intentional. The taxonomy
  deliberately excludes semantic/interpretive tags (e.g. "BULL_FLAG",
  "ACCUMULATION").

### Deterministic trade calculations

- Risk, reward, reward/risk ratio, percentage distances, and ATR-multiple
  distances for each side's trade plan are computed in plain code from the
  committed entry/take-profit/stop-loss/ATR values, never by the LLM.

- An entry given as a range uses its midpoint as the reference price for these
  calculations (a documented default rule); missing entry/target/stop values
  degrade the metrics gracefully instead of erroring.

- The Trader now receives this same deterministic trade plan (entry, take
  profit, stop loss, reward/risk, ATR distance) for both sides directly from
  the research team's verified state, and is instructed to prefer those
  levels over inventing its own from the market report alone.

### Suggested risk unit

- Each side's thesis carries a `SUGGESTED_RISK_UNIT` (`NO_TRADE` / `LOW` /
  `MEDIUM` / `HIGH`), mapped deterministically from its conviction score
  (`<50` → `NO_TRADE`, `50–64` → `LOW`, `65–79` → `MEDIUM`, `80+` → `HIGH`).

- **This is a research-level signal only. It is NOT a portfolio percentage,
  leverage, or position size** — actual position sizing remains the
  Trader/Portfolio Manager's job and is not implemented by this value.

### Non-interactive and batch CLI execution

- Added non-interactive CLI execution so TradingAgents can be run from scripts
  without answering interactive questions.

- Added batch execution for analysing multiple tickers sequentially using a
  shared configuration and fixed analysis date.

- Batch execution isolates ticker failures so one failed analysis does not
  prevent the remaining tickers from being processed.

- Batch runs can generate:
  - the complete report for each ticker;
  - structured per-ticker result data;
  - an aggregate Markdown summary;
  - an aggregate machine-readable summary.

- Aggregate summaries are generated deterministically from completed run
  results rather than by making an additional LLM call.

- `tradingagents batch` only requires `--tickers` (or `--tickers-file`); every
  other option now has a default, resolved in this order — an explicit flag,
  then an environment variable, then a hardcoded fallback:
  - `--date`: today's date (`YYYY-MM-DD`), fixed once when the command
    starts, so a run that crosses midnight keeps using the day it started on;
  - `--output-dir`: `.\test\<date>`;
  - `--language`: `TRADINGAGENTS_OUTPUT_LANGUAGE`, else `English`;
  - `--depth`: `TRADINGAGENTS_DEPTH`, else `medium`;
  - `--analysts`: `TRADINGAGENTS_ANALYSTS`, else all four
    (`market,social,news,fundamentals`).

  Example — analyze three tickers with every other setting defaulted:
  ```bash
  tradingagents batch --tickers NVDA,SPY,BTC-USD
  ```

### Structured-output consistency in Risk Management

- The three Risk Management debators (Aggressive, Conservative, Neutral) now
  follow the same structured-output-with-free-text-fallback pattern already
  used by the Trader, Research Manager, and Portfolio Manager, instead of
  being the only free-text-only debate participants.

- Each turn still produces the same free-form conversational argument, but
  now carries an explicit `risk_level` (`LOW`/`MEDIUM`/`HIGH`) alongside it:
  that debator's own read of how risky the Trader's current plan is, not a
  label for their assigned archetype. The latest reading from each analyst is
  shown to the Portfolio Manager and in the saved report.

### Bug fixes

This fork also carries a set of correctness fixes found during an internal
audit, applied on top of upstream behavior:

- A decision whose holding window opened at a zero price (bad vendor tick, a
  halted/delisted name) no longer silently divides to `inf`/`nan`; the memory
  log now leaves it pending instead of storing a corrupted return that would
  have poisoned any later average (e.g. a backtest's mean alpha for that
  rating bucket).
- The Yahoo OHLCV cache is now written atomically (temp file + rename), so two
  graphs running concurrently in the same process can no longer read a
  partially-written cache file for the same symbol.
- `temperature` is no longer forwarded to OpenAI/Azure reasoning-tier models
  (o-series, GPT-5+) when explicitly configured — those models reject a
  non-default value, the same failure mode already handled for
  `reasoning_effort`.
- FRED rate limits and outages (HTTP 429/5xx) are now classified the same way
  every other vendor's are, so the router's existing graceful-degradation path
  applies instead of surfacing a generic HTTP error.
- A single invalid ticker in a batch run (and the aggregate summary generated
  afterward) can no longer abort the rest of the batch; the failure is now
  isolated and reported per-ticker like any other.
- Minor: an Azure OpenAI client was mislabeled as `azureopenai` instead of
  `azure` in warnings; a non-Typer `exit()` call in the interactive ticker
  prompt was replaced with the same clean-exit path used everywhere else in
  the CLI.
- The Sentiment Analyst's `overall_score = 0` (maximally bearish) was
  incorrectly treated as a missing value and silently overwritten with the
  band's midpoint; a genuine zero now survives unchanged, and a
  deterministically inferred score is explicitly marked `INFERRED_FROM_BAND`
  rather than presented as the model's own judgment (`score_source`).
- A run that fails after the risk discussion completes (observed as an
  uncaught `KeyError` building the Portfolio Manager prompt) no longer loses
  the hours of completed work ahead of it: every agent prompt now renders
  safely against missing placeholders instead of raising, and a failure
  partway through the graph is caught, tagged with the furthest pipeline
  stage reached (`failure_stage`), and saved as `partial_report.md` /
  `result.json` with everything completed so far (analyst reports, Bull/Bear
  research, verification, repair, the Research Manager's plan, the Trader's
  plan, and the risk discussion) — clearly banner-marked as an incomplete run,
  never presented as a final recommendation. A batch run's summary links a
  failed ticker's partial report the same way it links a successful one's.
- Rating/action parsing (Trader, Research Manager, Portfolio Manager) now
  recognizes a bolded standalone heading (`**Hold**`, `**Overweight**`) and
  `Rating:`/`Recommendation:` labels alike, instead of only one exact
  `**Label**: Value` shape; an output that still can't be parsed keeps its raw
  text and is marked `unparsed` rather than guessed at.

## Planned experiments

The following ideas are planned or under evaluation and should not be
considered part of the implemented architecture until they are completed.

### Position sizing

- Convert the research-level `SUGGESTED_RISK_UNIT` (implemented) and trade
  quality into an actual position size, using deterministic code over entry,
  stop, volatility (ATR), and portfolio-risk constraints (e.g. max risk per
  trade, portfolio equity).

- Position sizing should not directly equate an LLM conviction score with a
  portfolio percentage — conviction only selects the bounded risk unit; sizing
  math is separate and deterministic.

### Historical recommendation tracking

- Persist structured recommendations from:
  - Bull;
  - Bear;
  - Research Manager;
  - final Portfolio Manager.

- Record their initial thesis, final thesis, conviction, trade levels, and key
  reasoning in a structured history.

- Update completed recommendations later using realised market prices.

- Possible outcomes include:
  - entry not triggered;
  - take profit reached;
  - stop loss reached;
  - expired at the defined horizon.

- Additional statistics may include maximum favourable excursion, maximum
  adverse excursion, realised return, and time to outcome.

### Historical feedback

- Build deterministic historical-performance summaries for future analyses.

- The initial Bull and Bear researchers may receive relevant historical
  performance context, while normal review agents should not receive this
  additional information.

- Historical summaries may include:
  - overall results;
  - results by conviction range;
  - results for similar technical conditions;
  - recurring failure patterns;
  - recurring strengths.

- The objective is to allow agents to recognise patterns such as:
  "this type of setup has historically been weak for my thesis"
  without treating past results as a guarantee of future performance.

- Historical context should be derived as far as possible from objective,
  structured market variables rather than free-form LLM narratives, to reduce
  feedback loops and confirmation bias.

---


<p align="center">
  <img src="assets/TauricResearch.png" style="width: 60%; height: auto;">
</p>

<div align="center" style="line-height: 1;">
  <a href="https://arxiv.org/abs/2412.20138" target="_blank"><img alt="arXiv" src="https://img.shields.io/badge/arXiv-2412.20138-B31B1B?logo=arxiv"/></a>
  <a href="https://discord.com/invite/hk9PGKShPK" target="_blank"><img alt="Discord" src="https://img.shields.io/badge/Discord-TradingResearch-7289da?logo=discord&logoColor=white&color=7289da"/></a>
  <a href="https://x.com/TauricResearch" target="_blank"><img alt="X Follow" src="https://img.shields.io/badge/X-TauricResearch-white?logo=x&logoColor=white"/></a>
  <a href="https://github.com/TauricResearch/" target="_blank"><img alt="Community" src="https://img.shields.io/badge/GitHub_Community-TauricResearch-14C290?logo=discourse"/></a>
</div>
<br>
<div align="center">
  <a href="https://github.com/TauricResearch" target="_blank"><img alt="TradingAgents #1 Repository of the Day" src="https://trendshift.io/api/badge/repositories/16192" width="250" height="55"/></a>
</div>
<br>
<div align="center">
  <!-- Keep these links. Translations will automatically update with the README. -->
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=de">Deutsch</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=es">Español</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=fr">français</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=ja">日本語</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=ko">한국어</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=pt">Português</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=ru">Русский</a> | 
  <a href="https://www.readme-i18n.com/TauricResearch/TradingAgents?lang=zh">中文</a>
</div>

---

# TradingAgents: Multi-Agents LLM Financial Trading Framework

## News

<!-- news:start -->
- [2026-09] **TradingAgents v0.5.1** released with a package layout organised by what each module holds (import paths moved), optional Jev screening of social posts, GPT-6 Sol and Luna as the default models, and fixes to run isolation and SEC EDGAR statements.
- [2026-09] **TradingAgents v0.5.0** released with point-in-time integrity across every dated path, SEC EDGAR fundamentals served as filed, backtesting over a ticker and date grid, portfolio-aware runs, and current model lineups across every provider.
- [2026-08] **TradingAgents v0.4.0** released with look-ahead / point-in-time fixes across FRED macro, social sentiment, and the decision-log memory; clearer decision signals; working CLI checkpoint resume; Trader price grounding; and the GPT-5.6 and GLM-5.3 models.

Full release notes are in [CHANGELOG.md](CHANGELOG.md).

<details>
<summary>Earlier news</summary>

- [2026-07] **TradingAgents v0.3.1** released with correctness and stability fixes: Alpha Vantage look-ahead filtering, graph-router crash-safety, graph-shape-aware checkpoint resume, working crypto sentiment sources, a configurable LLM retry budget, Bedrock API-key auth, and Claude Sonnet 5 / Fable 5 support.
- [2026-06] **TradingAgents v0.3.0** released with a verified data-access contract, an expanded provider registry (NVIDIA, Kimi, Groq, Mistral, Bedrock, and any OpenAI-compatible endpoint), FRED and Polymarket data vendors, a current-generation model catalog, and a CI gate.
- [2026-05] **TradingAgents v0.2.5** released with the grounded Sentiment Analyst, GPT-5.5 etc. model coverage, Qwen/GLM/MiniMax dual-region support, `TRADINGAGENTS_*` env-var configurability with API-key auto-detection, remote Ollama support, non-US alpha benchmarks, and ticker path-traversal hardening.
- [2026-04] **TradingAgents v0.2.4** released with structured-output agents (Research Manager, Trader, Portfolio Manager), LangGraph checkpoint resume, persistent decision log, DeepSeek/Qwen/GLM/Azure provider support, Docker, and a Windows UTF-8 encoding fix.
- [2026-03] **TradingAgents v0.2.3** released with multi-language support, GPT-5.4 family models, unified model catalog, backtesting date fidelity, and proxy support.
- [2026-03] **TradingAgents v0.2.2** released with GPT-5.4/Gemini 3.1/Claude 4.6 model coverage, five-tier rating scale, OpenAI Responses API, Anthropic effort control, and cross-platform stability.
- [2026-02] **TradingAgents v0.2.0** released with multi-provider LLM support (GPT-5.x, Gemini 3.x, Claude 4.x, Grok 4.x) and improved system architecture.
- [2026-01] **Trading-R1** [Technical Report](https://arxiv.org/abs/2509.11420) released, with [Terminal](https://github.com/TauricResearch/Trading-R1) expected to land soon.

</details>
<!-- news:end -->

<div align="center">

🚀 [TradingAgents](#tradingagents-framework) | ⚡ [Installation & CLI](#installation-and-cli) | 🎬 [Demo](https://www.youtube.com/watch?v=90gr5lwjIho) | 📦 [Package Usage](#tradingagents-package) | 🤝 [Contributing](#contributing) | 📄 [Citation](#citation)

</div>

> 🎉 **TradingAgents** officially released! We have received numerous inquiries about the work, and we would like to express our thanks for the enthusiasm in our community.
>
> So we decided to fully open-source the framework. Looking forward to building impactful projects with you!

## TradingAgents Framework

TradingAgents is a multi-agent trading framework that mirrors the dynamics of real-world trading firms. By deploying specialized LLM-powered agents: from fundamental analysts, sentiment experts, and technical analysts, to trader, risk management team, the platform collaboratively evaluates market conditions and informs trading decisions. Moreover, these agents engage in dynamic discussions to pinpoint the optimal strategy.

<p align="center">
  <img src="assets/schema.png" style="width: 100%; height: auto;">
</p>

> TradingAgents framework is designed for research purposes. Trading performance may vary based on many factors, including the chosen backbone language models, model temperature, trading periods, the quality of data, and other non-deterministic factors. [It is not intended as financial, investment, or trading advice.](https://tauric.ai/disclaimer/)

Our framework decomposes complex trading tasks into specialized roles.

### Analyst Team
- Fundamentals Analyst: Evaluates company financials and performance metrics, identifying intrinsic values and potential red flags.
- Sentiment Analyst: Aggregates news headlines, StockTwits, and Reddit chatter into a single sentiment read to gauge short-term market mood.
- News Analyst: Monitors global news and macroeconomic indicators, interpreting the impact of events on market conditions.
- Technical Analyst: Utilizes technical indicators (like MACD and RSI) to detect trading patterns and forecast price movements.

<p align="center">
  <img src="assets/analyst.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

### Researcher Team
- Comprises both bullish and bearish researchers who critically assess the insights provided by the Analyst Team. Through structured debates, they balance potential gains against inherent risks.

<p align="center">
  <img src="assets/researcher.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### Trader Agent
- Composes reports from the analysts and researchers to make informed trading decisions, determining the timing and magnitude of trades.

<p align="center">
  <img src="assets/trader.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

### Risk Management and Portfolio Manager
- Continuously evaluates portfolio risk by assessing market volatility, liquidity, and other risk factors. The risk management team evaluates and adjusts trading strategies, providing assessment reports to the Portfolio Manager for final decision.
- The Portfolio Manager approves/rejects the transaction proposal. If approved, the order will be sent to the simulated exchange and executed.

<p align="center">
  <img src="assets/risk.png" width="70%" style="display: inline-block; margin: 0 2%;">
</p>

## Installation and CLI

### Installation

Clone TradingAgents:
```bash
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
```

Create a virtual environment in any of your favorite environment managers:
```bash
conda create -n tradingagents python=3.12
conda activate tradingagents
```

Or with [uv](https://docs.astral.sh/uv/):
```bash
uv venv --python 3.12
source .venv/bin/activate
```

Install the package and its dependencies (`uv pip install .` with uv):
```bash
pip install .
```

### Docker

Alternatively, run with Docker:
```bash
cp .env.example .env  # add your API keys
docker compose run --rm tradingagents
```

After updating the repository, rebuild the image with `docker compose build`.

For local models with Ollama:
```bash
docker compose --profile ollama run --rm tradingagents-ollama
```

### Required APIs

TradingAgents supports multiple LLM providers. Set the API key for your chosen provider:

```bash
export OPENAI_API_KEY=...          # OpenAI (GPT)
export GOOGLE_API_KEY=...          # Google (Gemini)
export ANTHROPIC_API_KEY=...       # Anthropic (Claude)
export XAI_API_KEY=...             # xAI (Grok)
export DEEPSEEK_API_KEY=...        # DeepSeek
export DASHSCOPE_API_KEY=...       # Qwen — International (dashscope-intl.aliyuncs.com)
export DASHSCOPE_CN_API_KEY=...    # Qwen — China (dashscope.aliyuncs.com)
export ZHIPU_API_KEY=...           # GLM via Z.AI (international)
export ZHIPU_CN_API_KEY=...        # GLM via BigModel (China, open.bigmodel.cn)
export MINIMAX_API_KEY=...         # MiniMax — Global (api.minimax.io)
export MINIMAX_CN_API_KEY=...      # MiniMax — China (api.minimaxi.com)
export OPENROUTER_API_KEY=...      # OpenRouter
export MISTRAL_API_KEY=...         # Mistral
export MOONSHOT_API_KEY=...        # Kimi (Moonshot)
export GROQ_API_KEY=...            # Groq
export NVIDIA_API_KEY=...          # NVIDIA NIM
export FRED_API_KEY=...            # FRED macro data (free, optional)
export ALPHA_VANTAGE_API_KEY=...   # Alpha Vantage
export TYPESAFE_API_KEY=...        # Jev social-post screening (optional)
```

For Azure OpenAI, copy `.env.enterprise.example` to `.env.enterprise` and fill in your credentials.

For AWS Bedrock, install the extra with `pip install ".[bedrock]"`, set `llm_provider: "bedrock"`, configure AWS credentials (environment variables, `~/.aws/credentials`, or an IAM role) and `AWS_DEFAULT_REGION`, and use a Bedrock model ID, e.g. `us.anthropic.claude-opus-4-8-v1:0`.

For local models, configure Ollama with `llm_provider: "ollama"`. The default endpoint is `http://localhost:11434/v1`; set `OLLAMA_BASE_URL` to point at a remote `ollama-serve`. Pull models with `ollama pull <name>`, and pick "Custom model ID" in the CLI for any model not listed by default.

For any other OpenAI-compatible server (vLLM, LM Studio, llama.cpp, or a custom relay), use `llm_provider: "openai_compatible"` and set the endpoint via `backend_url` (or `TRADINGAGENTS_LLM_BACKEND_URL`), e.g. `http://localhost:8000/v1` for vLLM or `http://localhost:1234/v1` for LM Studio. The model is whatever your server serves. No key is needed for local servers; set `OPENAI_COMPATIBLE_API_KEY` when the endpoint requires one.

With `TYPESAFE_API_KEY` set, the Sentiment Analyst screens StockTwits and Reddit posts with TypeSafe's Jev before reading them. Posts that are not about the company are dropped, and each source opens with a count of the remaining posts by stance: bullish, bearish, neutral, or unclear. Without the key, posts pass through unscreened. `jev-latest` moves with new releases; set `TYPESAFE_DEFAULT_MODEL` to a versioned ID such as `jev-1.13.0` to hold it fixed across runs.

Alternatively, copy `.env.example` to `.env` and fill in your keys:
```bash
cp .env.example .env
```

### CLI Usage

Launch the interactive CLI:
```bash
tradingagents          # installed command
python -m cli.main     # alternative: run directly from source
```
You will see a screen where you can select your desired tickers, analysis date, LLM provider, research depth, and more. Your previous run's answers come back as the defaults, so pressing Enter accepts them. The `TRADINGAGENTS_*` variables in `.env` still skip their step entirely.

### Markets and tickers

TradingAgents works with any market Yahoo Finance covers, using the exchange-suffixed ticker. Company identity and the alpha benchmark resolve automatically per market.

- US: `AAPL`, `SPY`
- Hong Kong: `0700.HK` · Tokyo: `7203.T` · London: `AZN.L`
- India: `RELIANCE.NS`, `.BO` · Canada: `.TO` · Australia: `.AX`
- China A-shares: Shanghai `.SS`, Shenzhen `.SZ` (e.g. `600519.SS` for Kweichow Moutai)
- Crypto: `BTC-USD`, `ETH-USD`

<p align="center">
  <img src="assets/cli/cli_init.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

An interface will appear showing results as they load, letting you track the agent's progress as it runs.

<p align="center">
  <img src="assets/cli/cli_news.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

<p align="center">
  <img src="assets/cli/cli_transaction.png" width="100%" style="display: inline-block; margin: 0 2%;">
</p>

## TradingAgents Package

### Implementation Details

We built TradingAgents with LangGraph to ensure flexibility and modularity. The framework supports multiple LLM providers: OpenAI, Google, Anthropic, xAI, DeepSeek, Qwen (Alibaba DashScope, international and China endpoints), GLM (Zhipu), MiniMax (global + China), OpenRouter, Ollama for local models, and Azure OpenAI for enterprise.

Agent prompts are stored under `tradingagents/prompts/`. The shared `global_policy.txt` contains minimal instructions applied to all trading agents. `global_policy.example.hardmode.txt` is a stricter reference policy for local experimentation and is not enabled by default.

### Python Usage

To use TradingAgents inside your code, you can import the `tradingagents` module and initialize a `TradingAgentsGraph()` object. The `.propagate()` function will return a decision. You can run `main.py`, here's also a quick example:

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())

# forward propagate
_, decision = ta.propagate("NVDA", "2026-09-01")
print(decision)
```

You can also adjust the default configuration to set your own choice of LLMs, debate rounds, etc.

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"        # e.g. openai, google, anthropic, deepseek, groq, ollama; openai_compatible covers any OpenAI-compatible endpoint (vLLM, LM Studio, llama.cpp, ...)
config["deep_think_llm"] = "gpt-6-sol"    # Model for complex reasoning
config["quick_think_llm"] = "gpt-6-luna"   # Model for quick tasks
config["max_debate_rounds"] = 2

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2026-09-01")
print(decision)
```

See `tradingagents/default_config.py` for all configuration options.

### Fundamentals as filed

US company statements can come from SEC EDGAR, which records the date every figure was filed. A run dated in the past then reads the statements exactly as they stood that day: a fiscal year that has ended but has not been filed yet is not served, and a figure restated later still reads as first reported. Apple's 2008 total assets were filed as $39.6B and restated to $36.2B in 2010, so a run dated in between reads $39.6B.

EDGAR needs no account or API key. Add the vendor to the chain:

```python
config["data_vendors"]["fundamental_data"] = "sec_edgar,yfinance"
```

SEC asks callers to identify themselves and refuses requests that carry no contact address, so a default one is sent. Set your own so SEC can reach you rather than the project:

```bash
SEC_EDGAR_USER_AGENT="Your Name your@email.com"
```

It covers companies that file with the SEC, including foreign companies listed in the US. Anything else, such as Hong Kong or A-share listings, falls through to the next vendor in the chain. EDGAR's machine-readable filings begin in 2009, and a fourth quarter is reported as unavailable rather than derived, because filers publish it only inside the annual figure.

### Current holdings

By default the agents do not know what you hold, so their guidance is written for a reader who applies it to their own position. Pass a portfolio to have the trader, the risk analysts and the portfolio manager work against your actual book.

```python
from tradingagents.portfolio import PortfolioContext

portfolio = PortfolioContext.model_validate({
    "cash": 25000.0,
    "currency": "USD",
    "positions": [{"ticker": "NVDA", "quantity": 120, "average_price": 150.0}],
})
_, decision = ta.propagate("NVDA", "2026-09-01", portfolio=portfolio)
```

The CLI takes the same content as a JSON file: `tradingagents --portfolio my_book.json`.

An empty `positions` list means a flat book, which is different from passing nothing. A run without a portfolio is never treated as flat.

## Persistence and Recovery

TradingAgents persists two kinds of state across runs.

### Decision log

The decision log is always on. Each completed run appends its decision to `~/.tradingagents/memory/trading_memory.md`. On the next run for the same ticker, TradingAgents fetches the realised return (raw, and alpha against the instrument's regional benchmark), generates a one-paragraph reflection, and injects the most recent same-ticker decisions plus recent cross-ticker lessons into the Portfolio Manager prompt, so each analysis carries forward what worked and what didn't.

Override the path with `TRADINGAGENTS_MEMORY_LOG_PATH`.

### Checkpoint resume

Checkpoint resume is opt-in via `--checkpoint`. When enabled, LangGraph saves state after each node so a crashed or interrupted run resumes from the last successful step instead of starting over. The run view says whether it resumed a saved run or started fresh. Checkpoints are cleared automatically on successful completion.

Per-ticker SQLite databases live at `~/.tradingagents/cache/checkpoints/<TICKER>.db` (override the base with `TRADINGAGENTS_CACHE_DIR`). Use `--clear-checkpoints` to reset all of them before a run.

```bash
tradingagents --checkpoint           # enable for this run
tradingagents --clear-checkpoints    # reset before running
```

```python
config = DEFAULT_CONFIG.copy()
config["checkpoint_enabled"] = True
ta = TradingAgentsGraph(config=config)
_, decision = ta.propagate("NVDA", "2026-09-01")
```

## Evaluating decisions over time

One run gives one decision, which cannot tell you whether the system decides well. `run_backtest` runs the same pipeline over a grid of tickers and dates, writes to a decision log of its own, and scores the decisions whose holding window has since traded.

```python
from tradingagents.backtest import iter_grid, run_backtest, summarize

dates = iter_grid("2026-06-01", "2026-08-01", every_n_days=7)
result = run_backtest(["NVDA", "AAPL"], dates, config, selected_analysts=["market", "news"])
print(summarize(result).render())
```

From the CLI:

```bash
tradingagents backtest NVDA,AAPL --start 2026-06-01 --end 2026-08-01 --every 7
```

Each cell is scored on realized alpha against the instrument's regional benchmark, grouped by rating. Your own decision log is never written to, and re-running the same grid with `run_id=result.run_id` skips the cells that already ran, so an interrupted sweep continues where it stopped.

## Reproducibility

TradingAgents is LLM-driven, so two runs of the same ticker and date can differ. This is expected for a research tool built on language models, not a defect. The variation comes from a few distinct sources, and it helps to separate them.

Language model sampling is non-deterministic. Even at a fixed temperature, providers do not guarantee byte-identical output across calls, and reasoning models (the default GPT-6 family, and any thinking-mode model) vary the most because their internal reasoning is itself sampled.

Live data moves. News, StockTwits, and Reddit return different content as time passes, so a run today sees different inputs than a run last week even for the same historical trade date. Pin the analysis date to hold the price and indicator window fixed, but the social and news sources still reflect "now".

To reduce variation you can lower the sampling temperature. Set `temperature` in your config (or `TRADINGAGENTS_TEMPERATURE` in `.env`); lower values make models that honor it more repeatable. The current curated models are reasoning-first and largely ignore temperature, so for tighter reproducibility name a non-reasoning model in your config, or in `TRADINGAGENTS_DEEP_THINK_LLM` and `TRADINGAGENTS_QUICK_THINK_LLM`. Any model ID your provider serves is accepted, whether or not the picker lists it.

```python
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"
config["temperature"] = 0.0
# Reasoning models ignore temperature. For tighter reproducibility, name a
# non-reasoning model in deep_think_llm / quick_think_llm.
```

What does not vary anymore: the analyzed company identity is resolved deterministically from the ticker before any agent runs, and the market analyst grounds exact price and indicator claims in a verified data snapshot. Earlier reports of "different companies" or fabricated price levels across runs are addressed by these two mechanisms.

Backtest results are not guaranteed to match any published figure. Returns depend on the model, the temperature, the date range, data quality, and the sampling above. Treat the framework as a research scaffold for studying multi-agent analysis, not as a strategy with a fixed, replicable return.

## Contributing

Contributions are welcome: bug fixes, documentation, and feature ideas; past contributions are credited per release in [`CHANGELOG.md`](CHANGELOG.md).

## Citation

Please reference our work if you find *TradingAgents* provides you with some help :)

```
@misc{xiao2025tradingagentsmultiagentsllmfinancial,
      title={TradingAgents: Multi-Agents LLM Financial Trading Framework}, 
      author={Yijia Xiao and Edward Sun and Di Luo and Wei Wang},
      year={2025},
      eprint={2412.20138},
      archivePrefix={arXiv},
      primaryClass={q-fin.TR},
      url={https://arxiv.org/abs/2412.20138}, 
}
```
