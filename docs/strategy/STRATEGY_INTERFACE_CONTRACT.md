# Stage V.3 Strategy Interface Contract Freeze

Baseline：`stage-v2-local-backtest-engine-skeleton / cfe55be`。

Stage V.3 is documentation-only. It freezes the local strategy interface
contract before strategy runtime implementation. It does not add code, tests,
schema, Alembic migration, DB writes, live feed, quote API, CTP, SimNow,
broker, network integration or execution target enablement.

The purpose of this stage is to keep strategy logic out of `BacktestEngine`.
Backtest, future Paper and future SIM may call strategy through a typed
interface. Strategy may produce decisions only. Strategy must not execute
trades, write ledgers, bypass resolver identity or look ahead.

## Strategy Scope

Strategy interface is allowed for：

- Backtest。
- future Paper。
- future SIM。

Strategy interface is not allowed for：

- LIVE。
- broker execution。
- CTP integration。
- SimNow integration。
- real capital execution。

Any future LIVE, broker, CTP, SimNow or real capital strategy enablement
requires a separate contract freeze, implementation stage and acceptance
review.

## Strategy Input Contract

A future `StrategyContext` must be typed and deterministic.

Required fields：

- `strategy_name`。
- `symbol`。
- `instrument_id`。
- `trade_instrument_id`。
- `exchange`。
- `trading_day`。
- `timeframe`。
- `current_bar`。
- `historical_bars` up to and including `current_bar` only。
- resolver lineage。
- data source summary。
- portfolio snapshot placeholder。
- `config`。

Input identity rules：

- `symbol`, `instrument_id`, `trade_instrument_id`, `exchange` and
  `trading_day` must come from resolver-derived identity。
- Strategy must not infer, guess or override `instrument_id`,
  `trade_instrument_id` or `exchange`。
- unresolved, ambiguous, expired, invalid input or `METADATA_INVALID` resolver
  result means Strategy is not called。
- resolver lineage must be present in the context so downstream research output
  can explain which identity snapshot was used。

Forbidden inputs：

- future bars。
- future ticks。
- future quotes。
- future session data。
- future trading-day data。
- raw CSV rows。
- raw vendor payload。
- raw broker payload。
- `raw_payload` identity。
- direct DB session。
- repository。
- UnitOfWork。
- OMS mutable service。
- Trade ledger mutable service。
- Position mutable service。
- Accounting mutable service。
- broker adapter or broker query result。
- network client。

`portfolio snapshot placeholder` is read-only simulation context. It is not a
live account, broker account, Trade ledger, Position source-of-truth or
Accounting source-of-truth.

## Strategy Output Contract

A future `StrategyDecision` / `StrategySignal` must be typed and deterministic.

Required fields：

- `decision`：`BUY` / `SELL` / `CLOSE` / `HOLD`, or an explicitly accepted
  mapping to existing domain strategy decision types。
- `side`。
- `confidence`。
- `reason`。
- `expected_price`。
- `stop_loss` optional。
- `take_profit` optional。
- `tags`。
- `diagnostics`。

Output rules：

- Strategy output is a decision or signal only。
- Strategy output is not an order。
- Strategy output is not an execution command。
- Strategy output is not a fill。
- Strategy output is not a trade。
- Strategy output is not a position。
- Strategy output is not an accounting ledger fact。
- Strategy output is not broker state。
- Strategy output is not source-of-truth for OMS, Trade, Position,
  Accounting, broker, live execution or real account state。

Future conversion from `StrategyDecision` to simulated order / fill belongs to
a later Backtest implementation stage. Future conversion from strategy decision
to Paper / SIM workflow must go through accepted application-layer gates and
must not bypass Risk, OMS, Execution Gateway, report normalization, Trade,
Position or Accounting contracts.

## No-Lookahead Rule

Strategy may see only：

- `current_bar`。
- previous bars in the same context。
- current `as_of` quote if explicitly provided by a future accepted contract。
- current `as_of` tick if explicitly provided by a future accepted contract。
- read-only portfolio snapshot placeholder assembled at or before the
  simulation clock。

Strategy must not see：

- any bar after `current_bar`。
- any tick after the current simulation clock。
- any quote after the current simulation clock。
- future session data。
- future trading-day data。
- final daily close before it is available to the simulation clock。
- future roll decision。
- full-day aggregate that was not available at the current bar。

Backtest integration must build `historical_bars` by slicing the standardized
bar stream up to the current bar. It must not pass the complete run data set to
Strategy.

## Resolver Identity Rule

Strategy is an identity consumer, not an identity resolver.

Strategy must use：

- resolver-derived `symbol`。
- resolver-derived `instrument_id` for market observation identity。
- resolver-derived `trade_instrument_id` for simulated execution identity。
- resolver-derived `exchange`。
- resolver-derived `trading_day`。
- resolver lineage summary。

Strategy must not：

- parse contract codes from raw payloads。
- infer trade contracts from filename, UI label, broker raw field or metadata。
- switch instruments without a resolver-derived context。
- continue when resolver status is not `RESOLVED`。
- continue when resolver metadata is invalid。

Resolver output remains identity input only. It does not decide strategy
direction, price, quantity, stop loss, take profit or risk acceptance.

## Side-Effect Boundary

Strategy must not：

- write DB。
- write OMS。
- write Trade ledger。
- write Position。
- write Accounting。
- write production ledger。
- call broker。
- call CTP。
- call SimNow。
- call live feed。
- call quote API。
- call network。
- enable or dispatch any execution target。
- enable `ExecutionTarget.PAPER`。
- enable `ExecutionTarget.SIM`。
- enable `ExecutionTarget.LIVE`。
- mutate market data。
- mutate resolver context。
- mutate `StrategyContext`。
- mutate portfolio snapshot placeholder。
- run schema or Alembic migration。

Strategy code must be pure decision logic over typed context and config. Any
persistence of strategy candidates, decisions, lifecycle events or metrics
requires a separate accepted implementation contract and must remain clearly
separate from production OMS, Trade, Position and Accounting facts.

## Determinism

For the same：

- strategy implementation。
- strategy config。
- resolver context。
- historical bars visible to the current bar。
- trading day。
- timeframe。
- portfolio snapshot placeholder。

Strategy must return the same decision.

Forbidden nondeterminism：

- wall-clock `now`。
- random values without seeded config。
- network calls。
- file-system side effects。
- DB reads or writes。
- repository reads or writes。
- broker queries。
- live quote reads。
- mutable global state that changes decisions between equivalent inputs。

If a future strategy requires randomness for research, the seed must be part of
typed config and the output must remain replayable.

## Backtest Integration Contract

Future `BacktestEngine` integration must call Strategy through the frozen
interface：

1. Resolve `symbol + trading_day`。
2. Build `ResolverConsumerContext`。
3. Load standardized historical bars without lookahead。
4. For each bar, build `StrategyContext` with `current_bar` and
   `historical_bars` up to the current bar only。
5. Call Strategy and receive `StrategyDecision` / `StrategySignal`。
6. Preserve decision diagnostics in Backtest research output。
7. In a later stage, convert decisions into simulated orders / fills through a
   deterministic simulation boundary。

Stage V.3 freezes this contract only. It does not implement strategy runtime,
reference strategies, simulated order conversion, fill model, metrics,
optimization, persistence or UI.

## Paper / SIM Integration Contract

Future Paper and future SIM strategy use must remain local and gate-controlled.

Paper / SIM Strategy integration must：

- consume resolver-derived identity。
- consume standardized market data or accepted typed feature context。
- use the same no-lookahead rule。
- output decisions only。
- route decisions through accepted workflow gates before any local apply。
- keep `ExecutionTarget.MOCK` as the only accepted execution target until a
  separate target enablement contract changes it。

Paper / SIM Strategy integration must not：

- dispatch directly to broker。
- bypass Risk / OMS / Execution Gateway contracts。
- bypass local session / runtime job safety gates。
- write business ledgers from strategy code。
- imply `ExecutionTarget.PAPER` or `ExecutionTarget.SIM` enablement。

## Source-of-Truth Boundary

Strategy output is research / workflow input only.

Strategy output is not：

- OMS truth。
- Trade ledger truth。
- Position truth。
- Accounting truth。
- live execution truth。
- broker report truth。
- real account truth。
- market-data truth。
- resolver truth。

No downstream component may treat `StrategyDecision`, `StrategySignal`,
strategy diagnostics or strategy metrics as production facts without a separate
accepted promotion / persistence contract.

## Safety Boundary

Stage V.3 must not：

- implement strategy code。
- change `BacktestEngine`。
- change tests。
- change `src`。
- write schema。
- write Alembic migration。
- add dependency。
- write DB。
- write OMS / Trade / Position / Accounting。
- enable live execution。
- enable real capital。
- enable Paper apply。
- enable SIM apply。
- enable `ExecutionTarget.PAPER`。
- enable `ExecutionTarget.SIM`。
- enable `ExecutionTarget.LIVE`。
- use raw payload as source-of-truth。

## Future Implementation

Next recommended stages：

```text
V.4 Strategy Runtime Skeleton
V.5 Reference No-op Strategy via strategy interface
V.6 Buy-and-hold or MA Crossover reference strategy
```

Later, separate contract freezes should cover：

- strategy metrics。
- strategy optimization。
- durable strategy run/result storage。
- strategy lifecycle persistence for Backtest。
- Paper strategy wiring。
- SIM strategy wiring。
- feature-based strategy context。
- live strategy preflight and enablement。

No future stage may combine strategy interface implementation with live broker,
CTP, SimNow, real capital, target enablement or schema persistence unless a
separate accepted contract explicitly opens that scope.

## Stage V.4 Runtime Skeleton Status

Stage V.4 implements the first local Strategy Runtime skeleton only.

Implemented boundary：

- typed in-memory `StrategyContext`, `StrategyDecision` and
  `StrategyRuntimeResult` models。
- `StrategyRuntimeStatus` distinguishes `COMPLETED`, `BLOCKED`,
  `INVALID_INPUT` and `ERROR`。
- `StrategyEvaluator` interface exposes `evaluate(context) ->
  StrategyDecision`。
- `NoOpStrategy` returns deterministic `HOLD` and performs no side effects。
- `StrategyRuntime` validates required context, calls strategy `evaluate(...)`
  and returns an in-memory result。
- `StrategyContext` is deeply immutable at construction time. Mutable mapping,
  list, tuple and set inputs are recursively frozen before strategy evaluation。
- `StrategyRuntime` passes a defensive frozen context copy into
  `strategy.evaluate(...)`。
- missing resolver lineage, missing current bar, missing historical bars,
  missing symbol or missing trading day blocks before strategy evaluation。
- historical bars must contain the current bar and must not contain bars after
  the current bar。

Strategies must treat every `StrategyContext` field as read-only. They must not
mutate `config`, `data_source_summary`, `portfolio_snapshot`,
`historical_bars`, resolver lineage or market data objects.

Stage V.4 does not implement real trading strategy logic, strategy persistence,
BacktestEngine integration, simulated order conversion, fill model, metrics,
optimization, schema, Alembic migration, DB writes, broker, CTP, SimNow, live
feed, network integration or execution target enablement.

## Stage V.5 Backtest Integration Status

Stage V.5 integrates the Strategy Runtime skeleton into `LocalBacktestEngine`
only. Backtest constructs one immutable `StrategyContext` per consumed bar and
passes it to `StrategyRuntime`.

No-lookahead remains mandatory：the context for bar `N` contains only bars
`0..N`, with `current_bar` equal to the last bar in that slice. Future bars are
not passed to strategy evaluation.

V.5 records strategy runtime results and decisions as Backtest research output.
Those decisions remain signals / decisions only. They are not orders, trades,
positions, accounting facts, broker state or live execution truth.

V.5 default behavior remains `NoOpStrategy` / `HOLD`; it creates no simulated
orders or trades and does not change the flat equity behavior.

## Stage V.6 Reference Strategy Contract Freeze

Baseline：`stage-v5-backtest-strategy-runtime-integration / 5444200`。

Stage V.6 is documentation-only. It freezes reference strategy tiers,
responsibilities and validation rules. It does not add code, tests, schema,
Alembic migration, DB writes, live feed, broker, CTP, SimNow, network
integration, execution target enablement or Backtest order generation.

### Strategy Tiers

Reference strategy tiers are：

- Tier 0：`NoOpStrategy`。
- Tier 1：`BuyAndHoldStrategy`。
- Tier 2：`MovingAverageCrossStrategy`。
- Tier 3：future advanced strategies。

Tier 0 is the current accepted runtime default. Tier 1 and Tier 2 require
separate implementation stages and acceptance reviews. Tier 3 is future scope
only and must not be treated as enabled by this contract.

### Reference Strategy Rules

All reference strategies must be：

- deterministic。
- no-lookahead。
- side-effect free。
- resolver-lineage aware。
- replayable from typed `StrategyContext` and config。

All reference strategies must not：

- write DB。
- write ledgers。
- call network。
- call broker。
- call CTP。
- call SimNow。
- call live feed or quote API。
- use randomness unless the seed is part of typed config。
- read future bars, future ticks, future quotes, future sessions or future
  trading days。
- infer instrument identity outside resolver-derived context。

### BuyAndHold Contract

`BuyAndHoldStrategy` is Tier 1.

Expected behavior：

- first eligible bar returns `BUY`。
- every later bar returns `HOLD`。

Eligibility must be based only on current and prior context available at the
current bar. The strategy must not inspect future bars to decide whether the
first eligible bar exists.

`BuyAndHoldStrategy` must not：

- automatically add to the position after the first eligible buy。
- automatically close the position。
- create orders directly。
- create trades directly。
- mutate portfolio snapshot placeholder。
- treat its decision as position or accounting truth。

Future simulated order conversion belongs to a separate stage after the strategy
decision is produced.

### Moving Average Contract

`MovingAverageCrossStrategy` is Tier 2.

Required config：

- `fast_window`。
- `slow_window`。

Window rules：

- `fast_window` and `slow_window` must be positive integers。
- `fast_window` must be less than `slow_window` unless a future accepted
  contract explicitly permits another relation。
- moving averages may use only `historical_bars` available in the
  `StrategyContext`。
- moving averages must not use future bars, future ticks, future quotes, future
  sessions, future trading days or final close values before they are available。
- insufficient history must produce a deterministic non-trading decision such
  as `HOLD` or a typed blocked / invalid result defined by the implementation
  stage。

`MovingAverageCrossStrategy` output remains a `StrategyDecision` only. It must
not create orders, trades, positions, accounting facts or broker commands.

### Strategy Validation

Every reference strategy implementation must pass：

- deterministic replay。
- same input => same output。
- resolver lineage present。
- no side effects。
- no mutation of `StrategyContext` or nested context structures。
- no future bars in decision input。
- no DB, repository, UnitOfWork, broker, CTP, SimNow, live feed or network
  imports。
- no execution target enablement。

Validation tests must include at least：

- repeated evaluation with identical context and config。
- no-lookahead context inspection。
- missing resolver lineage blocked before strategy evaluation or rejected by
  runtime。
- strategy output is decision only。
- no simulated order or trade is created by the strategy itself。

### Backtest Integration Rule

`LocalBacktestEngine` consumes `StrategyDecision` only.

Backtest may record strategy decisions and runtime results as research output,
but strategy code must not create orders directly. Conversion from
`StrategyDecision` to simulated order / simulated fill is a separate future
simulation boundary.

Backtest integration must continue to：

- resolve identity before strategy evaluation。
- pass only current and historical bars up to the current bar。
- stop on strategy runtime `BLOCKED` / `ERROR`。
- keep strategy decisions separate from OMS, Trade, Position and Accounting
  facts。

### Future Implementation Roadmap

Next strategy stages：

```text
V.7 BuyAndHold implementation
V.8 MovingAverage implementation
V.9 Simulated Order Model
```

V.7 may implement Tier 1 decision generation only. V.8 may implement Tier 2
decision generation only. V.9 may freeze and implement simulated order modeling
after decisions exist. None of these stages may enable live execution or write
production business facts without a separate accepted contract.

### V.6 Safety Boundary

Reference strategy work must not：

- enable live execution。
- enable `ExecutionTarget.PAPER`。
- enable `ExecutionTarget.SIM`。
- enable `ExecutionTarget.LIVE`。
- mutate OMS。
- mutate Trade。
- mutate Position。
- mutate Accounting。
- write DB or ledgers。
- connect broker。
- connect CTP。
- connect SimNow。
- connect live feed, quote API or network。
- treat `StrategyDecision` as source-of-truth for any production fact。

## Stage V.7 BuyAndHold Implementation Status

Baseline：`stage-v6-reference-strategy-contract-freeze / f14beed`。

Stage V.7 implements Tier 1 `BuyAndHoldStrategy` as local strategy decision
logic only.

Implemented behavior：

- `len(context.historical_bars) == 1` returns `BUY` with side `BUY`。
- `len(context.historical_bars) > 1` returns `HOLD` with side `NONE`。
- `BUY` reason is `first eligible bar buy`。
- `HOLD` reason is `already entered hold`。
- `BUY.expected_price` uses `current_bar.close`。
- `HOLD.expected_price` is `None`。

`BuyAndHoldStrategy` is deterministic and has no internal mutable state. It
uses only `context.current_bar` and `context.historical_bars`; it does not read
future bars, mutate `StrategyContext`, create orders, create trades, create
positions, write accounting facts, write DB, call broker / CTP / SimNow / live
feed / network, or enable execution targets.
