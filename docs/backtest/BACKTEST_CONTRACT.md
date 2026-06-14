# Stage V.1 Backtest Contract Freeze

Baseline：`stage-u6-static-historical-data-fixture / 95508e0`。

Stage V.1 is documentation-only. It freezes the local Backtest input, output,
execution boundary and safety rules. It does not add code, tests, schema,
Alembic migration, DB writes, live feed, quote API, CTP, SimNow, broker,
network integration or execution target enablement.

Backtest must consume resolver-derived identity and standardized historical
market data. It must not guess instrument identity, consume raw source payloads
as facts, connect to live sources or write production trading ledgers.

## Backtest Scope

Backtest is：

- local only。
- deterministic。
- research / observability only。
- a consumer of `InstrumentResolver` and `ResolverConsumerContext`。
- a consumer of `HistoricalBar`, `HistoricalTick` and `HistoricalQuote`。
- allowed to use static historical fixture data。
- allowed to use a future accepted historical source only after separate
  implementation acceptance。

Backtest is not：

- live feed。
- broker execution。
- CTP integration。
- SimNow integration。
- real capital execution。
- production ledger writer。
- source-of-truth for OMS, Trade, Position or Accounting。

## Input Contract

A future `BacktestRequest` must be typed and deterministic.

Required request fields：

- `strategy_name`。
- `symbol`。
- trading-day range。
- `timeframe`。
- `initial_cash`。
- commission model placeholder。
- slippage model placeholder。
- resolver config。
- data source selection：`static_fixture` or future accepted historical source。

Input rules：

- `symbol` and trading-day range are the identity entrypoint。
- `instrument_id`, `trade_instrument_id` and `exchange` must come from
  resolver-derived identity, not request free text。
- resolver status must be `RESOLVED` for every trading day that requires market
  data consumption。
- unresolved resolver status fails closed before strategy evaluation。
- `initial_cash`, commission settings and slippage settings are simulation
  parameters only; they do not imply real account balance or broker state。
- data source selection must not bypass resolver-derived identity。
- raw CSV rows, raw vendor payloads, raw broker payloads and `raw_payload` must
  not be request identity or market-data facts。

## Market Data Rules

Backtest may consume only standardized market data objects：

- `HistoricalBar`。
- `HistoricalTick`。
- `HistoricalQuote`。

Market data rules：

- no lookahead。
- bars and ticks are immutable。
- quote is the latest available snapshot at or before the simulation clock。
- market data is session-aware。
- market data is `trading_day`-bound。
- session boundary semantics must follow the accepted historical market data
  contract。
- continuous/main contract is used for market observation。
- trade contract is used for simulated execution identity。
- roll rules must be deterministic and bound to `trading_day`。
- missing bars fail closed unless a future accepted gap policy explicitly
  allows another deterministic behavior。
- missing ticks or quotes fail closed when the strategy or fill model requires
  them。
- fixture corrections must not silently rewrite prior observations。

Backtest must not consume：

- raw CSV row。
- raw vendor payload。
- raw broker payload。
- filename。
- UI label。
- free-form metadata。
- `raw_payload`。

## Execution Model

Stage V.1 freezes the execution model boundary only.

Backtest execution rules：

- no real broker。
- no live execution。
- no live quote。
- simulated fills only。
- future fill model must be deterministic。
- future fill model must use only standardized historical market data available
  at or before the simulation clock。
- future fill model must not submit through `ExecutionGateway` to a live,
  paper, SIM, broker, CTP or SimNow target。
- future fill model must not write OMS, Trade, Position or Accounting live
  ledgers unless a separate contract freeze explicitly creates a local
  backtest-only persistence boundary。

Backtest may produce simulated orders, events and trades as output views. Those
views are research artifacts only and must remain separate from production OMS,
Trade, Position and Accounting facts.

## Output Contract

A future `BacktestResult` must be typed and deterministic.

Required output fields：

- status。
- metrics summary placeholder。
- simulated orders / events / trades view。
- equity curve。
- diagnostics。
- resolver lineage。
- data source summary。
- gap report。

Output rules：

- status must distinguish completed, blocked, invalid input, resolver failure,
  data gap and error states in a future implementation。
- metrics summary is research output only。
- simulated orders / events / trades must be clearly labeled simulated。
- equity curve is simulated and must not be treated as account truth。
- diagnostics must include resolver status and historical data source summary。
- resolver lineage must include symbol, instrument identity, trade contract,
  exchange, trading days, resolver source, resolver confidence and effective
  window or diagnostics summary。
- data source summary must identify static fixture versus future historical
  source。
- gap report must record missing bars, ticks, quotes or session coverage needed
  by the run。

## Source-of-Truth Boundary

Backtest output is research / observability only.

Backtest output is not：

- OMS truth。
- Trade ledger truth。
- Position truth。
- Accounting truth。
- live execution truth。
- broker report truth。
- real account truth。
- source-of-truth for production replay。

No downstream component may treat Backtest simulated orders, events, trades,
equity curve or metrics as production facts without a separate accepted
promotion / persistence contract.

## Safety Boundary

Backtest must not：

- write production ledger。
- write OMS。
- write Trade。
- write Position。
- write Accounting。
- mutate schema or Alembic migration。
- use raw CSV rows as facts。
- use raw vendor payloads as facts。
- use raw broker payloads as facts。
- use `raw_payload` as identity。
- enable `ExecutionTarget.PAPER`。
- enable `ExecutionTarget.SIM`。
- enable `ExecutionTarget.LIVE`。
- use live quote。
- connect network。
- connect live feed。
- connect CTP。
- connect SimNow。
- connect broker。
- bypass resolver-derived identity。

Any future durable backtest storage, result table, run table, fixture version
table or ledger-like persistence requires a separate contract freeze and
acceptance review.

## Future Implementation

The next allowed implementation stage is：

```text
V.2 Local Backtest Engine Skeleton
```

V.2 may implement a local deterministic Backtest engine skeleton using only：

- `InstrumentResolver`。
- `ResolverConsumerContext`。
- static historical market data fixture。
- standardized `HistoricalBar`, `HistoricalTick` and `HistoricalQuote`。
- in-memory simulated result objects。

Default schema decision：no schema.

V.2 must not add live feed, quote API, CTP, SimNow, broker, network, production
ledger writes or execution target enablement unless a separate accepted freeze
explicitly changes those boundaries.

## Stage V.2 Skeleton Status

Stage V.2 implements the first local deterministic skeleton only.

Implemented boundary：

- typed in-memory `BacktestRequest` / `BacktestResult` models。
- `BacktestStatus` distinguishes `COMPLETED`, `BLOCKED`, `DATA_GAP`,
  `INVALID_INPUT` and `ERROR`。
- request validation requires strategy name, symbol, trading-day range,
  timeframe, positive initial cash, resolver and data provider。
- resolver consumption requires `InstrumentResolution.RESOLVED` and builds
  `ResolverConsumerContext` before market data consumption。
- standardized bars are consumed through
  `StaticHistoricalDataFixtureProvider.get_bars(...)`。
- unresolved identity, ambiguous identity, expired identity or invalid metadata
  fail closed as `BLOCKED`。
- unsupported timeframe fails as `INVALID_INPUT`。
- missing bars fail as `DATA_GAP`。
- current strategy is a deterministic no-op placeholder: no simulated orders,
  no simulated trades and a flat equity curve equal to initial cash。

Stage V.2 result objects remain research / observability only. They do not
write DB, schema, Alembic, OMS, Trade, Position, Accounting or broker state and
must not be promoted to production truth without a separate accepted contract.
