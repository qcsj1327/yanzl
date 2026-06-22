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

## Stage V.18 Minimal Position / PnL / Equity Implementation Status

Baseline：`stage-v17-next-bar-open-fill-integration / e3fbee0`。

Stage V.18 implements the minimal Backtest research-only Position, PnL and
Equity chain for the accepted `BuyAndHoldStrategy` + injected
`NextBarOpenFillModel` path. The implementation handles only the single BUY
long trade produced by that flow. It does not implement close, short,
commission, slippage, partial fill, production Position, production PnL,
Accounting, DB writes or live execution.

### Simulated Position

`SimulatedPosition` is a Backtest research object only. It is not the production
Position ledger, broker position, exchange position or accounting position
source-of-truth.

Required fields：

- `symbol`。
- `instrument_id`。
- `trade_instrument_id`。
- `exchange`。
- `trading_day`。
- `side`。
- `quantity`。
- `avg_price`。
- resolver lineage。

Every simulated position must preserve resolver-derived identity from the
`SimulatedTrade` / `SimulatedOrder` path. Backtest must not guess
`instrument_id`, `trade_instrument_id`, `exchange` or `trading_day`.

Stage V.18 creates a `ResearchPosition` only after a research-only
`SimulatedTrade` is generated by `NextBarOpenFillModel`. No-fill runs and no-op
strategy runs produce no research position.

### Realized PnL

Realized PnL may be produced only from closed simulated quantity. Stage V.18 has
no close path, so realized PnL remains zero. It must not be created from
strategy decisions, unfilled simulated orders, unresolved instrument identity or
raw market payloads.

Realized PnL fields：

- `gross_pnl`：price difference multiplied by closed quantity and contract
  multiplier when a multiplier contract exists。
- `commission`：placeholder cost-model amount。
- `slippage`：placeholder cost-model amount。
- `net_pnl`：`gross_pnl - commission - slippage`。

Stage V.18 uses zero commission and zero slippage. Future non-zero costs require
a separate accepted deterministic cost model. Missing cost configuration must
fail closed or use an explicitly documented zero-cost placeholder; it must not
call a broker, exchange, network service or accounting repository.

### Unrealized PnL

Unrealized PnL may be produced only from open simulated position quantity.

Unrealized PnL is mark-to-market：

- long position：`(mark_price - avg_price) * quantity`。
- short position：`(avg_price - mark_price) * quantity`。

Future prices are forbidden. The mark price for a bar may use only data
available at that bar boundary under the accepted market data contract. It must
not use future bars, future ticks, future quotes, final run metrics, final daily
close before it is available, or hindsight equity / PnL summaries.

Stage V.18 marks the BUY long position to each bar close after the trade exists.
The fill bar is the next bar after order creation, and the fill bar close is
allowed for that bar's research equity point.

### Equity Calculation Order

Backtest equity is a research-only curve. For each equity point, calculation
order is frozen as：

1. Start from initial simulated cash.
2. When a BUY research trade is generated, subtract trade notional from cash：
   `cash = cash - fill_price * fill_qty`。
3. Mark the open long position to the current bar close after the trade exists.
4. Calculate market value：
   `market_value = quantity * current_bar.close`。
5. Calculate equity as：

```text
equity = cash + market_value
```

`ResearchPnLPoint` also records realized PnL and unrealized PnL for
observability. In Stage V.18 realized PnL is always zero because there is no
close path. `cash`, `market_value`, `realized_pnl`, `unrealized_pnl` and
`equity` are Backtest research values only. They must not mutate production
account balances, Position state, Trade ledger facts, Accounting facts or broker
state.

### Cost Model

The Stage V.18 Backtest cost model is a deterministic zero-cost placeholder for：

- commission。
- slippage。

Future cost models must be deterministic for the same input trades, resolver
lineage, strategy config and market data. They must not use wall-clock time,
unseeded randomness, network calls, broker state, live account state, DB writes
or raw payload source-of-truth.

### Source-of-Truth Boundary

Backtest Position, PnL and Equity outputs are research / observability objects
only.

They are not：

- production position。
- accounting fact。
- broker truth。
- exchange truth。
- OMS truth。
- Trade ledger truth。
- source-of-truth for replay, reconciliation, settlement or live capital。

No downstream component may promote Backtest Position, PnL or Equity outputs
into production truth without a separate accepted persistence, promotion and
reconciliation contract.

### Resolver Lineage

Every future Backtest Position, PnL and Equity calculation must retain resolver
lineage, including：

- `symbol`。
- `instrument_id`。
- `trade_instrument_id`。
- `exchange`。
- `trading_day`。
- resolver source。
- resolver confidence。
- resolver diagnostics / lineage summary。

Unresolved or metadata-invalid identity remains a blocked Backtest state and
must not enter simulated Position, PnL or Equity calculation.

### Safety Boundary

Stage V.18 and future Backtest Position / PnL / Equity stages must not：

- write DB。
- write OMS。
- write Trade ledger。
- write production Position。
- write Accounting。
- call broker。
- call CTP。
- call SimNow。
- call live feed。
- call network。
- enable `ExecutionTarget.PAPER`。
- enable `ExecutionTarget.SIM`。
- enable `ExecutionTarget.LIVE`。
- change schema or Alembic。

### Future Stages

V.19 Position Model Hardening

V.20 PnL Model Hardening

V.21 Equity Curve Integration Hardening

## Stage W.1 组合研究层契约冻结

基线：`stage-v19-local-research-backtest-mvp-baseline / b410f68`。

Stage W.1 只改文档。详细契约见
`docs/backtest/PORTFOLIO_RESEARCH_CONTRACT.md`。

W.1 将 `ResearchPortfolio` 冻结为 Backtest 研究专用组合视图，为未来多品种、多持仓、多策略工作定义边界。未来 `ResearchPortfolio` 必须携带 `portfolio_id`、`strategy_name`、`run_id`、`initial_cash`、`cash`、`total_market_value`、`total_equity`、`positions`、`pnl_points` 和 `diagnostics`。

portfolio 使用单一资金池。每笔 accepted research trade 都从 cash 扣减 notional；cash 不得为负；leverage / margin 仍是未冻结能力。Portfolio equity 计算规则为：

```text
total_equity = cash + sum(position market value)
```

per-symbol contribution 必须可观测。每个 position 必须保留其 `symbol`、`instrument_id`、`trade_instrument_id`、exchange 和 trading-day context 的 resolver lineage。

Stage W.1 仍为 long-only。close、short、partial fill、commission、slippage、leverage、margin 和 multi-currency 在单独 contract 被接受前继续 fail closed。

`ResearchPortfolio` 不是生产组合、会计账本、broker account 或 live position truth。W.1 不得 write DB、OMS、Trade、Position 或 Accounting；不得 mutate schema / Alembic；不得 connect broker / CTP / SimNow / live feed / network；不得 enable `ExecutionTarget.PAPER`、`ExecutionTarget.SIM` 或 `ExecutionTarget.LIVE`。

后续组合研究层阶段为 `W.2 ResearchPortfolio skeleton`、`W.3 multi-symbol fixture backtest`、`W.4 portfolio equity aggregation`、`C.1 close/exit research contract freeze`、`C.2 Exit Skeleton`、`C.3 Realized PnL Skeleton` 和 `C.4 Cash Return Integration`。

## Stage C.1 Close / Exit 研究契约冻结

基线：`stage-w3-backtest-research-portfolio-integration / d69a7cd`
以及 `stage-v19-local-research-backtest-mvp-baseline`。

Stage C.1 只改文档。详细契约见
`docs/backtest/PORTFOLIO_RESEARCH_CONTRACT.md`。

Research position lifecycle 冻结为：

```text
FLAT -> OPEN_LONG -> LONG -> CLOSE -> FLAT
```

当前只冻结 `LONG -> CLOSE`。`SHORT`、sell short、short cover、
position reversal 和 cross-position close 仍未支持。

未来 `StrategyDecision.CLOSE` 只表示退出已有 `LONG` research position，
不是 `SELL SHORT`。未来 exit order flow 必须为：

```text
StrategyDecision(CLOSE)
-> DecisionTranslator
-> Exit SimulatedOrder
```

Exit fill 冻结为 Next Bar Open Exit Fill：bar N 创建 close order，
bar N+1 open 成交；same bar exit fill 禁止。

long-only realized PnL 公式冻结为：

```text
realized_pnl = (exit_price - entry_price) * quantity
```

cash flow 冻结为 `entry: cash -= entry_notional` 和
`exit: cash += exit_notional`。Exit order、exit trade 和 realized PnL
均为 Backtest research-only output，不是 OMS truth、Trade ledger、
Accounting fact 或 Broker truth。

close without position、wrong symbol、wrong resolver lineage、negative 或
zero quantity、cross-position close、same bar exit fill 都必须 fail closed。

后续阶段为 `C.2 Exit Skeleton`、`C.3 Realized PnL Skeleton` 和
`C.4 Cash Return Integration`。

## Stage C.2 Exit Skeleton Status

基线：`stage-c1-close-exit-research-contract-freeze / 6826086`。

Stage C.2 implements the research-only CLOSE skeleton. It adds
`ExitReferenceStrategy` for tests and allows `DecisionTranslator` to convert
`StrategyDecision.CLOSE` into `SimulatedOrder(intent=EXIT, side=CLOSE,
status=CREATED)`.

`BUY` remains `SimulatedOrder(intent=ENTRY, side=BUY, status=CREATED)`.
`SELL` remains rejected by the long-only research skeleton.

C.2 does not implement exit fill, exit trade, realized PnL or cash return.
Translator output must contain no `SimulatedTrade`; default Backtest execution
keeps exit orders at `NO_FILL`, with no equity, cash, research position or PnL
mutation.

## Stage C.3 Exit Fill Skeleton Status

基线：`stage-c2-exit-order-skeleton / b130d8e`。

Stage C.3 extends `NextBarOpenFillModel` so `SimulatedOrder(intent=EXIT,
side=CLOSE, status=CREATED)` can generate a research-only EXIT
`SimulatedTrade`. Existing ENTRY order fill behavior remains unchanged.

EXIT fill uses the first same-identity bar after `created_bar_ts`, sets
`fill_price` to `next_bar.open`, and sets `fill_qty` to `order.quantity`.
Same-bar fill is forbidden; no next bar and identity mismatch return no trade.

ENTRY and EXIT trade diagnostics must be distinct and research-only. C.3 does
not implement realized PnL, cash return, position close, equity update, schema,
DB writes, broker/live/network integration or execution target enablement.

## Stage C.4 Realized PnL + Cash Return Skeleton Status

基线：`stage-c3-exit-fill-skeleton / 81b6f00`。

Stage C.4 implements the research-only long close accounting skeleton described
in `docs/backtest/PORTFOLIO_RESEARCH_CONTRACT.md`.

Supported lifecycle is deliberately narrow:

```text
one ENTRY trade -> one matching EXIT trade -> FLAT
```

Matching requires the same `symbol`, `instrument_id`, `trade_instrument_id`,
exchange, `trading_day`, resolver lineage and quantity. Duplicate entry,
duplicate exit, mismatched identity, mismatched quantity and exit-before-entry
fail closed.

Long-only realized PnL and research cash flow are:

```text
realized_pnl = (exit_price - entry_price) * quantity
entry: cash -= entry_price * quantity
exit:  cash += exit_price * quantity
```

After close, the final research position is `FLAT` with quantity `0` and market
value `0`; final unrealized PnL is `0`; final equity equals final cash.

`ExitReferenceStrategy + NextBarOpenFillModel` is accepted for the C.4 reference
path: bar 1 BUY, bar 2 CLOSE decision, close fills at bar 3 open, producing one
ENTRY trade and one EXIT trade.

All C.4 outputs remain Backtest research / observability artifacts only.
Realized PnL is not Accounting truth and cash return is not account balance,
broker balance, settlement, margin or ledger truth. C.4 does not write schema,
Alembic, DB, OMS, Trade, Position or Accounting state; does not connect broker,
CTP, SimNow, live feed or network; and does not enable PAPER, SIM or LIVE
execution targets.

## Phase X Multi-Symbol Research Backtest Status

基线：`stage-c4-realized-pnl-cash-return / 0a11b38`。

Phase X implements the research-only multi-symbol MVP. `BacktestRequest`
continues to support single-symbol `symbol` requests and adds `symbols` for
deterministic multi-symbol fixture runs, for example:

```text
symbols = ["ao", "rb", "ag", "cu"]
```

For each symbol, `LocalBacktestEngine` executes the same local research chain:

```text
resolver
-> historical fixture
-> strategy
-> decision
-> simulated order
-> fill model
-> research position
-> research pnl
```

Supported Phase X allocation is fixed cash allocation only:

```text
allocation_per_symbol = initial_cash / len(symbols)
```

The allocation is exposed to strategy context as research-only portfolio
snapshot data. It does not implement dynamic sizing, leverage, margin or risk
sizing, and it does not create account or broker truth.

`BuyAndHoldStrategy + NextBarOpenFillModel` can create simultaneous long
research positions for multiple symbols. Research accounting groups trades by
resolver identity, validates each symbol fail-closed, aggregates multiple
`ResearchPosition` objects, multiple `ResearchPnLPoint` objects and a single
`ResearchPortfolio`.

Portfolio equity remains:

```text
portfolio_equity = cash + sum(position market value)
```

If any requested symbol fails resolver resolution, including `NOT_FOUND` or
`METADATA_INVALID`, the whole backtest returns `BLOCKED` before market data
consumption for that symbol. Resolver failure must not produce orders, trades,
research positions, PnL points or portfolio output.

All Phase X outputs remain Backtest research / observability artifacts only.
Phase X does not write schema, Alembic, DB, OMS, Trade, production Position,
Accounting, Margin, Settlement or broker state; does not connect broker, CTP,
SimNow, live feed or network; and does not enable PAPER, SIM or LIVE execution
targets.

## Phase Y Research Realism + Portfolio Analytics Status

基线：`stage-w3-backtest-research-portfolio-integration` +
`stage-c4-realized-pnl-cash-return`。

Phase Y implements the first research realism layer for the local Backtest
research platform. It remains in-memory and research-only.

`ResearchPortfolio` now carries deterministic analytics:

- `portfolio_equity_curve`
- `symbol_contributions`
- `position_weights`
- `cash_weight`
- `metrics`

Each symbol contribution contains:

```text
symbol
market_value
equity_contribution
pnl_contribution
```

Portfolio metrics are deterministic:

```text
total_return = (total_equity - initial_cash) / initial_cash
max_equity = max(portfolio_equity_curve.equity)
min_equity = min(portfolio_equity_curve.equity)
```

Phase Y adds `FixedCommissionModel`:

```text
commission = fill_price * fill_qty * commission_rate
default commission_rate = 0.0001
```

ENTRY commission is deducted from research cash on entry. EXIT commission is
deducted from research cash on exit. Long-only realized PnL after close is:

```text
realized_pnl = (exit_price - entry_price) * quantity
               - entry_commission
               - exit_commission
```

Phase Y adds `FixedSlippageModel`:

```text
default ticks = 1
default tick_size = 1
ENTRY fill price = next_bar.open + slippage
EXIT fill price  = next_bar.open - slippage
```

The model is long-only. Negative slippage ticks and non-positive tick size
fail closed.

Phase Y adds sizing modes on `BacktestRequest`:

```text
quantity_mode = fixed_quantity | fixed_cash
fixed_quantity default = 1
allocation_mode = equal_weight | fixed_cash
allocation_per_symbol default = initial_cash / len(symbols)
```

`fixed_quantity` preserves the earlier default quantity behavior.
`fixed_cash` computes quantity from the active per-symbol allocation and the
decision expected price. Negative quantity, unknown sizing mode, unknown
allocation mode, non-positive allocation and negative research cash all fail
closed.

Cash remains a single research cash pool. The pool must never become negative.
Portfolio equity remains:

```text
portfolio_equity = cash + sum(position market value)
```

Phase Y does not implement short, margin, leverage, production persistence,
schema, Alembic, DB writes, OMS / Trade / Position / Accounting mutation,
broker, live feed, network or execution target enablement.
