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

## Stage V.3 Strategy Interface Contract Freeze

Baseline：`stage-v2-local-backtest-engine-skeleton / cfe55be`。

Stage V.3 is documentation-only. The detailed contract is
`docs/strategy/STRATEGY_INTERFACE_CONTRACT.md`.

The Backtest engine must remain a coordinator, not a place where strategy logic
grows directly. Future Backtest strategy integration must call a typed strategy
interface for each bar：

1. resolve `symbol + trading_day`。
2. build `ResolverConsumerContext`。
3. consume standardized bars without lookahead。
4. build `StrategyContext` with `current_bar` and historical bars up to the
   current bar only。
5. receive a `StrategyDecision` / `StrategySignal`。
6. later, in a separate accepted stage, convert that decision into simulated
   order / fill output。

Strategy output is not an order, trade, position or ledger fact. Backtest
results remain research / observability only and must not become OMS, Trade,
Position, Accounting, broker, live execution or real account truth.

Stage V.3 does not implement strategy runtime, reference strategies, simulated
fill conversion, metrics, optimization, persistence, schema or execution target
enablement. The next recommended implementation stages are `V.4 Strategy
Runtime Skeleton`, `V.5 Reference No-op Strategy via strategy interface` and
`V.6 Buy-and-hold or MA Crossover reference strategy`.

## Stage V.5 Backtest Strategy Runtime Integration

Baseline：`stage-v4-strategy-runtime-skeleton / f23b5fb`。

Stage V.5 wires `LocalBacktestEngine` to the local Strategy Runtime skeleton.
For each consumed standardized bar, Backtest builds a `StrategyContext` with the
current bar, historical bars up to the current bar only, resolver lineage, data
source summary, read-only portfolio snapshot placeholder and strategy config
placeholder. It then calls `StrategyRuntime` and records the runtime result and
decision in `BacktestResult`.

Current V.5 strategy behavior remains no-op only. `NoOpStrategy` returns
`HOLD`; Backtest still produces zero simulated orders, zero simulated trades and
a flat equity curve equal to initial cash.

If strategy runtime returns `BLOCKED`, Backtest fails closed as blocked. If
strategy runtime returns `ERROR` or any non-completed status, Backtest returns
`ERROR` and does not continue as completed.

Stage V.5 does not implement real trading strategy logic, simulated order
conversion, fill model, metrics, optimization, persistence, schema, Alembic
migration, DB writes, OMS / Trade / Position / Accounting mutation, broker,
CTP, SimNow, live feed, network integration or execution target enablement.

## Stage V.6 Reference Strategy Contract Impact

Baseline：`stage-v5-backtest-strategy-runtime-integration / 5444200`。

Stage V.6 is documentation-only. The detailed reference strategy contract is
`docs/strategy/STRATEGY_INTERFACE_CONTRACT.md`.

Backtest remains a strategy-decision consumer only. Reference strategies may
produce `StrategyDecision` values, but they must not create orders, trades,
positions, accounting facts or broker commands directly.

The frozen reference strategy roadmap is：

- Tier 0：`NoOpStrategy`。
- Tier 1：`BuyAndHoldStrategy`，future V.7 implementation。
- Tier 2：`MovingAverageCrossStrategy`，future V.8 implementation。
- V.9：simulated order model after strategy decisions are available。

All Backtest strategy integration must preserve resolver-derived identity,
no-lookahead bar slicing, deterministic replay, no side effects and
research-only result semantics. Simulated order conversion remains a future
separate boundary.

## Stage V.8 Backtest BuyAndHold Decision Integration

Baseline：`stage-v7-buy-and-hold-reference-strategy / a7c842e`。

Stage V.8 verifies `LocalBacktestEngine` can run with injected
`BuyAndHoldStrategy`. The first consumed bar records a `BUY` strategy decision;
later consumed bars record `HOLD` decisions.

This stage remains decision-only. Backtest records `StrategyDecision` values as
research output and does not convert them into simulated orders, simulated
trades, positions, accounting facts, broker commands or source-of-truth records.
The equity curve remains flat until a separate simulated order / fill model is
accepted.

## Stage V.9 Simulated Order Model Contract Freeze

Baseline：`stage-v8-backtest-buy-hold-decision-flow / 8a92e00`。

Stage V.9 is documentation-only. It freezes the research-only simulated order
and simulated trade model contract for future Backtest stages.

### Decision to Order Boundary

`StrategyDecision` is not an order.

Future Backtest simulation must convert decisions through a dedicated
`DecisionTranslator` before any `SimulatedOrder` is created：

```text
StrategyDecision -> DecisionTranslator -> SimulatedOrder
```

Strategies must not create `SimulatedOrder` objects directly. Strategies may
only produce deterministic decisions from `StrategyContext`.

### SimulatedOrder Contract

`SimulatedOrder` is an in-memory Backtest research object only.

Required fields：

- `order_id`。
- `strategy_name`。
- `symbol`。
- `instrument_id`。
- `trade_instrument_id`。
- `exchange`。
- `trading_day`。
- `side`。
- `quantity`。
- `expected_price`。
- `order_type`。
- `created_bar_ts`。
- resolver lineage。
- diagnostics。

Allowed statuses：

- `CREATED`。
- `REJECTED`。
- `FILLED`。
- `CANCELLED`。

`SimulatedOrder` is not：

- an OMS order。
- a broker order。
- an exchange order。
- a production order source-of-truth。

### SimulatedTrade Contract

`SimulatedTrade` is an in-memory Backtest research object only.

Required fields：

- `trade_id`。
- `order_id`。
- `fill_price`。
- `fill_qty`。
- `fill_bar_ts`。
- resolver lineage。
- diagnostics。

`SimulatedTrade` is not：

- a Trade ledger entry。
- an Accounting fact。
- a production trade source-of-truth。

### Fill Model Boundary

Stage V.9 does not implement a fill model.

Future fill models may include：

- next bar open。
- next bar close。
- midpoint。
- custom deterministic fill。

Every future fill model must be deterministic for the same strategy decision,
resolver context, standardized bars and configuration. Fill modeling must not
consume future data outside the accepted fill rule.

### Resolver Lineage Requirement

Simulated orders and trades must inherit resolver-derived identity. They must
not guess contracts.

Required lineage fields：

- `symbol`。
- `instrument_id`。
- `trade_instrument_id`。
- `exchange`。
- `trading_day`。
- `resolver_source`。
- `resolver_confidence`。

If resolver identity is unresolved or metadata-invalid, Backtest must fail
closed before strategy evaluation, decision translation, simulated order
creation or simulated trade creation.

### V.9 Safety Boundary

Simulated order and trade modeling must not：

- write DB。
- write OMS。
- write Trade ledger。
- write Position。
- write Accounting。
- connect broker。
- connect network。
- connect live execution。
- enable `ExecutionTarget.PAPER`。
- enable `ExecutionTarget.SIM`。
- enable `ExecutionTarget.LIVE`。

Backtest simulated orders and simulated trades remain research / observability
only and must not be promoted to production facts without a separate accepted
contract.

### Future Stages

Next Backtest simulation stages：

```text
V.10 DecisionTranslator Skeleton
V.11 Simulated Fill Model Skeleton
V.12 Backtest Equity / PnL Contract
```

## Stage V.10 DecisionTranslator Skeleton Status

Baseline：`stage-v9-simulated-order-model-contract-freeze / 8529f9b`。

Stage V.10 implements the research-only `DecisionTranslator` skeleton. It is a
standalone Backtest simulation component and does not change
`LocalBacktestEngine` equity, fill or persistence behavior.

Translation rules：

- `BUY` => `SimulatedOrder(status=CREATED)`。
- `HOLD` => `DecisionTranslationStatus.SKIPPED` and no order。
- `SELL` => `DecisionTranslationStatus.REJECTED` until a fill and position
  model exists。
- `CLOSE` => `DecisionTranslationStatus.REJECTED` until a fill and position
  model exists。
- missing resolver lineage => `DecisionTranslationStatus.BLOCKED`。
- missing current bar => `DecisionTranslationStatus.BLOCKED`。
- missing `BUY.expected_price` uses `current_bar.close` deterministically。
- quantity is the fixed research placeholder `1` unless a later accepted stage
  defines strategy sizing。
- order type is the fixed research placeholder `MARKET` unless a later accepted
  stage defines order-type modeling。

The generated `order_id` is deterministic from：

- `strategy_name`。
- current bar timestamp。
- decision type。
- `symbol`。
- `instrument_id`。
- `trade_instrument_id`。
- `exchange`。
- `trading_day`。

`DecisionTranslator` carries resolver lineage into `SimulatedOrder`：

- `symbol`。
- `instrument_id`。
- `trade_instrument_id`。
- `exchange`。
- `trading_day`。
- `resolver_source`。
- `resolver_confidence`。

Stage V.10 does not generate `SimulatedTrade`, does not implement a fill model,
does not update equity / PnL, does not write DB, does not write OMS / Trade /
Position / Accounting, does not connect broker / CTP / SimNow / live feed /
network and does not enable `ExecutionTarget.PAPER`, `ExecutionTarget.SIM` or
`ExecutionTarget.LIVE`.

`SimulatedOrder` remains a Backtest research / observability object only. It is
not an OMS order, broker order, exchange order, ledger fact or production
source-of-truth.

## Stage V.11 Backtest DecisionTranslator Integration Status

Baseline：`stage-v10-decision-translator-skeleton / ba39719`。

Stage V.11 wires `DecisionTranslator` into `LocalBacktestEngine` after each
successful strategy runtime decision：

```text
StrategyDecision -> DecisionTranslator -> DecisionTranslationResult
```

Backtest records `decision_translation_results` in `BacktestResult`.

Integrated behavior：

- `BUY` translation `CREATED` appends one research-only `SimulatedOrder` to
  `BacktestResult.simulated_orders`。
- `HOLD` translation `SKIPPED` records the translation result and appends no
  order。
- `SELL` / `CLOSE` translation `REJECTED` records the translation result and
  appends no order or trade。
- `DecisionTranslationStatus.BLOCKED` returns `BacktestStatus.BLOCKED`。
- `DecisionTranslationStatus.ERROR` returns `BacktestStatus.ERROR`。
- translator-generated simulated trades are rejected as a Backtest error until
  a separate fill model stage exists。

Current strategy effects：

- `NoOpStrategy` still produces zero simulated orders。
- `BuyAndHoldStrategy` produces one `CREATED` simulated order on the first
  consumed bar and no additional orders for later `HOLD` decisions。
- `simulated_trades` remains empty。
- equity and cash curves remain flat because no fill / PnL model exists。

Stage V.11 does not implement fill modeling, does not generate
`SimulatedTrade`, does not write DB, does not write OMS / Trade / Position /
Accounting, does not connect broker / live / network and does not enable any
execution target.

## Stage V.12 Fill Model Contract Freeze

Baseline：`stage-v11-backtest-decision-translator-integration / 4c5873d`。

Stage V.12 is documentation-only. It freezes the Backtest simulated fill model
contract before any fill implementation, trade generation or equity / PnL
calculation is added.

### Fill Model Scope

The simulated fill model applies only to：

- Backtest。

The simulated fill model does not apply to：

- Paper。
- SIM。
- LIVE。
- broker。
- exchange。

Backtest fills are local research artifacts only. They do not imply executable
intent, broker acceptance, exchange matching, real capital movement or any
production trading fact.

### Fill Inputs

Allowed fill inputs：

- `SimulatedOrder`。
- standardized `HistoricalBar`。
- resolver lineage inherited from the order and current Backtest run。

Forbidden fill inputs：

- raw CSV rows。
- raw vendor payload。
- raw broker payload。
- `raw_payload` identity。
- broker order state。
- exchange order state。
- live quote / live feed state。

Fill logic must consume standardized market data only. It must not use raw
payloads as source-of-truth for price, instrument identity or order state.

### Fill Status

Allowed simulated fill statuses：

- `CREATED`。
- `FILLED`。
- `REJECTED`。
- `CANCELLED`。

`CREATED` means a research-only simulated order exists and is eligible for a
future fill decision. `FILLED`, `REJECTED` and `CANCELLED` are simulated
Backtest outcomes only; none are OMS, broker, exchange, Trade ledger,
Position or Accounting truth.

### Fill Policy Tiers

Frozen policy tiers：

- Tier 0：No Fill。
- Tier 1：Next Bar Open Fill。
- Tier 2：Next Bar Close Fill。
- Tier 3：Midpoint Fill。
- Tier 4：Advanced deterministic model。

Stage V.12 freezes these tiers only. It does not implement any tier.

Any future enabled fill policy must be explicit in request/config, deterministic
for the same order, resolver lineage, bars and policy config, and testable
without network, broker, DB or wall-clock state.

### No-Lookahead Rule

Fill decisions may use only：

- the `SimulatedOrder`。
- resolver lineage。
- the next available standardized `HistoricalBar` accepted by the selected fill
  policy。

Fill decisions must not use：

- future run summary。
- future session data beyond the selected next bar。
- future trading day data unless a later accepted contract explicitly defines
  cross-day next-bar behavior。
- final daily close before it is available。
- performance metrics, equity curve, PnL summary or hindsight state。

For next-bar policies, the fill candidate is the next available bar after
`SimulatedOrder.created_bar_ts` for the same resolver-derived instrument
identity unless a later accepted contract defines a different deterministic
ordering rule.

### Resolver Lineage Requirement

Every simulated fill and future `SimulatedTrade` must inherit resolver-derived
identity from the `SimulatedOrder` and Backtest resolver context：

- `symbol`。
- `instrument_id`。
- `trade_instrument_id`。
- `exchange`。
- `trading_day`。
- resolver lineage。

Fill logic must not guess contracts or override resolver identity. If resolver
lineage is missing, inconsistent or metadata-invalid, fill simulation must fail
closed before producing a simulated trade.

### Research Only

`SimulatedTrade` is a Backtest research / observability object only.

`SimulatedTrade` is not：

- Trade ledger。
- Accounting fact。
- OMS truth。
- broker execution。
- exchange match。
- position truth。
- real account truth。

No downstream component may treat a simulated fill or `SimulatedTrade` as
production source-of-truth without a separate accepted persistence and promotion
contract.

### Gap Policy

Missing next bar must be handled deterministically.

The allowed future gap policies are：

- return `BacktestStatus.DATA_GAP` and do not produce a simulated trade。
- deterministically reject the simulated fill and do not produce a simulated
  trade。

The selected policy must be frozen by the implementation stage that enables a
fill model. Stage V.12 does not choose or implement either behavior.

### V.12 Safety Boundary

Fill model work must not：

- write DB。
- write OMS。
- write Trade ledger。
- write Position。
- write Accounting。
- connect broker。
- connect live feed。
- connect network。
- enable `ExecutionTarget.PAPER`。
- enable `ExecutionTarget.SIM`。
- enable `ExecutionTarget.LIVE`。
- mutate schema。
- add Alembic migration。

### Future Stages

Next Backtest fill / trade / equity stages：

```text
V.13 Fill Model Skeleton
V.14 Backtest Trade Generation
V.15 Equity / PnL Contract
```

## Stage V.13 No-Fill Model Skeleton Status

Baseline：`stage-v12-fill-model-contract-freeze / 4fa21d5`。

Stage V.13 implements Tier 0 `NoFillModel` only. It is a research-only Backtest
fill model skeleton and does not implement next-bar-open, next-bar-close,
midpoint or advanced fill behavior.

Implemented behavior：

- input is a `SimulatedOrder`。
- output is `FillModelResult(status=NO_FILL)`。
- `simulated_trade` is always `None`。
- deterministic reason is `no fill model selected`。
- the input order is not mutated。
- no historical bars are accepted by the model, so it cannot read future bars。

Implemented statuses for future fill model work：

- `NO_FILL`。
- `FILLED`。
- `REJECTED`。
- `DATA_GAP`。
- `BLOCKED`。
- `ERROR`。

`NoFillModel` is not wired into production execution, broker, live feed,
network, OMS, Trade ledger, Position or Accounting. It does not generate
`SimulatedTrade`, does not update equity / cash / PnL and does not persist any
state.

`SimulatedOrder` and `FillModelResult` remain Backtest research /
observability-only objects and must not be treated as OMS, broker, exchange,
Trade ledger or Accounting truth.

## Stage V.14 Backtest NoFillModel Integration Status

Baseline：`stage-v13-no-fill-model-skeleton / a7e96db`。

Stage V.14 wires Tier 0 `NoFillModel` into `LocalBacktestEngine` after each
created simulated order：

```text
StrategyDecision
-> DecisionTranslator
-> SimulatedOrder(CREATED)
-> NoFillModel.fill(order)
-> FillModelResult(NO_FILL)
```

Backtest records `fill_model_results` in `BacktestResult`.

Integrated behavior：

- `NoOpStrategy` produces zero simulated orders, zero fill model results and
  zero simulated trades。
- `BuyAndHoldStrategy` produces one `CREATED` simulated order and one
  `FillModelResult(status=NO_FILL)`。
- `NoFillModel` never produces `SimulatedTrade`。
- `simulated_trades` remains empty in successful V.14 paths。
- equity and cash curves remain flat because there is still no fill / PnL
  model。

Failure behavior：

- `FillModelStatus.BLOCKED` returns `BacktestStatus.BLOCKED`。
- `FillModelStatus.ERROR` returns `BacktestStatus.ERROR`。
- any fill model result that contains a `SimulatedTrade` fails closed as
  `BacktestStatus.ERROR` until a separate trade generation stage exists。
- any enabled fill-like status other than `NO_FILL` fails closed before trade
  generation。

Stage V.14 does not implement next-bar-open fill, next-bar-close fill, midpoint
fill, advanced fill, `SimulatedTrade` generation, equity / cash / PnL updates,
DB writes, OMS / Trade / Position / Accounting mutation, broker / live /
network integration or execution target enablement.

## Stage V.15 Next-Bar-Open Fill Contract Freeze

Baseline：`stage-v141-fill-status-fail-closed-tests / ded48fa`。

Stage V.15 is documentation-only. It freezes the Backtest research-only
Next-Bar-Open fill model contract. It defines fill eligibility, timing, price,
quantity, output and fail-closed behavior before any成交 implementation.

### Scope

Next-Bar-Open Fill applies only to：

- Backtest research / observability。

Next-Bar-Open Fill does not apply to：

- Paper。
- SIM。
- LIVE。
- broker。
- exchange。

It is not an execution model for real capital, broker routing, exchange
matching or production order state.

### Inputs

Allowed inputs：

- `SimulatedOrder(status=CREATED)`。
- standardized `HistoricalBar` series。
- resolver lineage。
- explicit fill policy config。

Forbidden inputs：

- raw CSV rows。
- raw vendor payload。
- raw broker payload。
- live quote。
- live feed。
- `raw_payload` identity。
- broker order state。
- exchange order state。

Fill logic must use standardized market data and resolver-derived identity
only. Raw payloads must not become source-of-truth for instrument identity,
price, fill status or trade facts.

### Eligibility

A simulated order is eligible for Next-Bar-Open Fill only when all conditions
are true：

- `order.status == CREATED`。
- order side is supported by the accepted implementation stage。
- `order.quantity > 0`。
- resolver lineage is present。
- a next available standardized bar exists。
- the next bar resolver identity matches the order resolver identity。

If any condition fails, the model must fail closed before producing a
`SimulatedTrade`.

### Fill Timing

The fill candidate is the first standardized bar after
`order.created_bar_ts` for the same resolver-derived identity.

Rules：

- same-bar fill is forbidden。
- future run summary is forbidden。
- future session data beyond the selected next bar is forbidden。
- future trading day data is forbidden unless a later accepted contract
  explicitly defines cross-day next-bar behavior。
- bars from a different resolver identity are forbidden。

The selected next bar must be determined by bar timestamp ordering and
resolver identity, not by hindsight PnL, final run metrics or future session
knowledge.

### Fill Price

For eligible fills：

- `fill_price = next_bar.open`。
- `next_bar.open` must be greater than `0`。

Default invalid-open behavior：

- `FillModelStatus.DATA_GAP`。
- no `SimulatedTrade`。
- deterministic diagnostics。

Invalid open must not be silently replaced by close, midpoint, last price,
vendor payload or any future value.

### Fill Quantity

For eligible fills：

- `fill_qty = order.quantity`。

Partial fill is forbidden. Overfill is forbidden. Quantity must not be derived
from account state, broker state, liquidity simulation or future volume unless
a later accepted deterministic model explicitly freezes those rules.

### Output

An eligible fill may generate one research-only `SimulatedTrade` with：

- deterministic `trade_id`。
- `order_id`。
- `fill_price`。
- `fill_qty`。
- `fill_bar_ts`。
- resolver lineage。
- diagnostics。

`trade_id` must be deterministic for the same order id, resolver identity,
fill bar timestamp, fill price, fill quantity and policy config.

### Gap Policy

If no next available bar exists：

- `FillModelStatus.DATA_GAP`。
- no `SimulatedTrade`。
- deterministic diagnostics。

Backtest handling after `DATA_GAP` is deferred to the V.16 implementation, but
the contract requires fail-closed behavior. `DATA_GAP` must not be converted
into a synthetic fill or hidden successful result.

### Source-of-Truth Boundary

`SimulatedTrade` is not：

- Trade ledger。
- Accounting fact。
- OMS truth。
- broker execution。
- exchange execution。
- position truth。
- real account truth。

No downstream component may use a Next-Bar-Open `SimulatedTrade` as production
source-of-truth without a separate accepted persistence and promotion contract.

### Safety Boundary

Next-Bar-Open Fill work must not：

- write DB。
- write OMS。
- write Trade ledger。
- write Position。
- write Accounting。
- connect broker。
- connect live feed。
- connect network。
- enable `ExecutionTarget.PAPER`。
- enable `ExecutionTarget.SIM`。
- enable `ExecutionTarget.LIVE`。
- mutate schema。
- add Alembic migration。

### Future Implementation

Next stages：

```text
V.16 Next-Bar-Open Fill Model Skeleton
V.17 Backtest trade generation integration
V.18 Backtest Equity/PnL Contract
```

## Stage V.16 Next-Bar-Open Fill Model Skeleton Status

Baseline：`stage-v15-next-bar-open-fill-contract-freeze / dd8f174`。

Stage V.16 implements `NextBarOpenFillModel` as an independent Backtest
research-only fill model skeleton. It is not wired into `LocalBacktestEngine`.

Implemented behavior：

- input is `SimulatedOrder` plus a standardized `HistoricalBar` tuple。
- only `SimulatedOrder(status=CREATED)` is eligible。
- only `BUY` side is supported。
- `order.quantity` must be greater than `0`。
- same-bar fill is forbidden。
- bars with mismatched resolver identity are skipped and must not fill。
- the fill candidate is the first bar after `order.created_bar_ts` with the
  same `symbol`, `instrument_id`, `trade_instrument_id`, `exchange` and
  `trading_day`。
- `fill_price = next_bar.open`。
- `fill_qty = order.quantity`。
- `next_bar.open <= 0` returns `FillModelStatus.DATA_GAP` and no trade。
- missing next bar returns `FillModelStatus.DATA_GAP` and no trade。
- non-created orders return `FillModelStatus.BLOCKED`。
- unsupported side returns `FillModelStatus.REJECTED`。

Generated `SimulatedTrade` fields include：

- deterministic `trade_id`。
- `order_id`。
- `fill_price`。
- `fill_qty`。
- `fill_bar_ts`。
- `symbol`。
- `instrument_id`。
- `trade_instrument_id`。
- `exchange`。
- `trading_day`。
- `resolver_source`。
- `resolver_confidence`。
- resolver lineage。
- diagnostics。

`trade_id` is deterministic from order id, fill bar timestamp, fill price, fill
quantity and resolver identity.

Stage V.16 does not integrate the fill model into BacktestEngine, does not
update equity / cash / PnL, does not write DB, does not write OMS / Trade /
Position / Accounting, does not connect broker / CTP / SimNow / live feed /
network and does not enable `ExecutionTarget.PAPER`, `ExecutionTarget.SIM` or
`ExecutionTarget.LIVE`.

## Stage V.17 Backtest NextBarOpenFillModel Integration Status

Baseline：`stage-v161-next-bar-open-fill-fail-closed-tests / b7b5633`。

Stage V.17 allows `LocalBacktestEngine` to run with injected
`NextBarOpenFillModel`. The default fill model remains `NoFillModel` so existing
no-fill Backtest behavior stays stable unless a caller explicitly injects a
different fill model.

Integrated flow：

```text
StrategyDecision
-> DecisionTranslator
-> SimulatedOrder(CREATED)
-> fill_model.fill(order, bars)
-> FillModelResult
```

When `NextBarOpenFillModel` is injected and returns
`FillModelResult(status=FILLED, simulated_trade=...)`, Backtest appends the
research-only `SimulatedTrade` to `BacktestResult.simulated_trades`.

Status handling：

- `NO_FILL` keeps `simulated_trades` unchanged。
- `FILLED` requires a `SimulatedTrade`; missing trade returns
  `BacktestStatus.ERROR`。
- `DATA_GAP` returns `BacktestStatus.DATA_GAP` and does not synthesize a trade。
- `BLOCKED` returns `BacktestStatus.BLOCKED`。
- `ERROR` returns `BacktestStatus.ERROR`。
- `REJECTED` fails closed as `BacktestStatus.ERROR` until a later accepted
  contract defines rejected-fill handling。
- any non-`FILLED` status carrying a `SimulatedTrade` fails closed as
  `BacktestStatus.ERROR`。

`BuyAndHoldStrategy` with injected `NextBarOpenFillModel` produces one
`CREATED` simulated order and one research-only `SimulatedTrade` at the second
bar open. The first bar cannot fill on itself.

Stage V.17 still does not update equity / cash / PnL, does not create Position
or Accounting facts, does not write DB, does not write OMS / Trade / Position /
Accounting, does not connect broker / CTP / SimNow / live feed / network and
does not enable `ExecutionTarget.PAPER`, `ExecutionTarget.SIM` or
`ExecutionTarget.LIVE`.
