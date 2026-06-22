# Stage U.5 Historical Market Data Contract Freeze

Baseline：`stage-u43-resolver-consumer-context-local-wiring / 0ad8c5e`。

Stage U.5 is documentation-only. It freezes the local historical market data
contract for Backtest, Paper and SIM. It does not add code, tests, schema,
Alembic migration, DB writes, live feed, quote API, CTP, SimNow, broker,
network integration or non-`MOCK` execution targets.

This contract depends on resolver-derived identity from
`docs/market_data/RESOLVER_CONSUMER_CONTRACT.md`. Historical market data
records must carry the resolved identity explicitly; raw vendor rows, CSV rows,
broker payloads and filenames must not become identity or market-data facts.

## Consumer Scope

This contract applies to local deterministic consumers only：

- Backtest。
- Paper。
- SIM。

It does not apply to and does not enable：

- live feed。
- quote API。
- CTP。
- SimNow。
- broker execution。
- network data source。
- real capital。

Any live, CTP, SimNow, broker, network or real-capital market-data path requires
a separate contract freeze and acceptance review.

## Bar Contract

A standardized historical bar is an immutable market observation for one
resolved instrument identity, one session and one timeframe.

Required fields：

- `symbol`。
- `instrument_id`。
- `trade_instrument_id`。
- `exchange`。
- `trading_day`。
- `session_id`。
- `timeframe`。
- `bar_ts`。
- `open`。
- `high`。
- `low`。
- `close`。
- `volume`。
- `turnover`。
- `open_interest`。

Bar rules：

- immutable once accepted into a fixture or historical data set。
- no lookahead：a consumer at time `bar_ts` may not read future bars, future
  ticks, future quote snapshots or future roll decisions。
- no rewrite：a correction must be modeled as a new accepted fixture/source
  version in a future contract, not as silent mutation of an existing bar。
- OHLC values must represent the same timeframe and session boundary。
- `high` must not be lower than `open`, `low` or `close`。
- `low` must not be higher than `open`, `high` or `close`。
- `volume`, `turnover` and `open_interest` must be non-negative。
- `raw_payload` is diagnostic-only if present in a future implementation and
  must not participate in canonical equality or identity。

## Tick Contract

A standardized historical tick is an immutable market observation at one event
timestamp for one resolved instrument identity.

Required tick fields：

- `ts`。
- `last_price`。
- `volume`。
- `turnover`。
- `open_interest`。
- bid / ask ladder。

The bid / ask ladder must be typed and ordered by level. A future
implementation may choose the exact maximum depth, but each populated level must
carry：

- bid price。
- bid volume。
- ask price。
- ask volume。
- level number。

Tick rules：

- immutable once accepted into a fixture or historical data set。
- no lookahead：a consumer may only read ticks with `ts` at or before the
  current simulation clock。
- `last_price`, ladder prices, `volume`, `turnover` and `open_interest` must be
  typed numeric values, not raw strings。
- `volume`, ladder volumes, `turnover` and `open_interest` must be
  non-negative。
- raw CSV rows, raw vendor payloads and raw broker payloads are not
  standardized ticks。

## Quote Contract

A quote is the latest standardized market snapshot available to a consumer at a
specific local simulation time.

A quote may be derived from standardized ticks, bars or a fixture snapshot, but
the resulting object must carry：

- resolver-derived identity。
- snapshot timestamp。
- latest last price if available。
- latest volume / turnover / open interest if available。
- latest bid / ask ladder if available。
- source reference or source summary。

Quote rules：

- latest means latest available without lookahead。
- quote is a local market snapshot, not a live feed subscription。
- quote does not own order, trade, position, accounting, signal, direction,
  order price or order quantity truth。

## Trading Session Contract

Historical market data must be assigned to a deterministic trading session.

Frozen session categories：

- day session。
- night session。

`session_id` identifies the deterministic session bucket for a trading day. A
future implementation may define exchange-specific labels, but it must preserve
the day/night distinction and document the session calendar source.

Session boundary semantics：

- `trading_day` is the business trading day used by resolver-derived identity
  and downstream consumers。
- `bar_ts` / tick `ts` is the observation timestamp。
- night-session observations may belong to the next business `trading_day`
  according to the accepted local calendar fixture。
- a bar must not cross a session boundary unless its `timeframe` explicitly
  represents a full-session aggregate。
- roll decisions must be bound to `trading_day`, not wall-clock ingestion time。
- a consumer must not infer session boundaries from filenames, UI labels or raw
  source text。

## Continuous Contract

Historical market data may expose both a continuous/main observation identity
and a trade-contract execution identity.

Definitions：

- main contract：the resolver-derived `instrument_id` used for market
  observation, for example a continuous or main-contract fixture。
- trade contract：the resolver-derived `trade_instrument_id` used for simulated
  order identity。
- roll rule：the deterministic rule that selects the effective main/trade pair
  for a `symbol + trading_day`。

Continuous contract rules：

- roll rule must be `trading_day`-bound and deterministic。
- Backtest must not dynamically guess or rewrite `trade_instrument_id` during a
  run。
- Paper and SIM local dry-run/session paths must use resolver-derived identity
  and must fail closed if identity is unresolved。
- continuous/main data is market observation input only; it does not authorize
  order generation by itself。

## Consumer Contract

Backtest, Paper and SIM consumers may consume only standardized historical data
objects：

- standardized bar。
- standardized tick。
- standardized quote。

Consumers must not consume these as market-data facts：

- raw CSV row。
- raw vendor payload。
- raw broker payload。
- filename。
- UI label。
- free-form metadata。
- `raw_payload`。

Consumer fail-closed rules：

- unresolved resolver identity blocks consumption for that identity。
- invalid or missing resolver metadata blocks consumption for that identity。
- missing required bar/tick/quote fields block the affected observation。
- invalid session assignment blocks the affected observation。
- lookahead access blocks the run or scenario。

Market data consumers must not write OMS, Trade, Position or Accounting facts.
They may provide typed market observations to strategy, risk, backtest, Paper or
SIM orchestration only through accepted future implementation boundaries.

## Source Priority

Future historical market data source priority is frozen as：

1. local fixture。
2. historical data source。
3. read-only adapter。

The priority order is a future-facing contract only. Stage U.5 does not
implement any data source, adapter, network access or persistence.

Source rules：

- local fixture means deterministic repository-local or test-local fixture data。
- historical data source means an accepted local source defined by a future
  contract。
- read-only adapter means a future adapter that may read but must not mutate
  OMS, Trade, Position, Accounting or schema。
- no source may bypass resolver-derived identity。
- no source may use raw payload as canonical market fact or identity。

## Safety Boundary

Historical market data sources must not write：

- OMS。
- Trade。
- Position。
- Accounting。
- ledger tables。
- schema or Alembic migration。

Historical market data sources must not：

- generate trading signals。
- decide order direction。
- decide order price。
- decide order quantity。
- submit orders。
- enable `ExecutionTarget.PAPER`。
- enable `ExecutionTarget.SIM`。
- enable `ExecutionTarget.LIVE`。
- connect to live feed, quote API, CTP, SimNow, broker or network source in
  Stage U.5。

## Schema Decision

Default decision：no schema.

## Phase L Read-Only Market Data Adapter Framework

Baseline：`phase-rp-v1 / 76ec4cf`。

Phase L implements a read-only market data adapter framework. It is the first
code path that lets the system name a source beyond static fixtures, but the
default source remains `static_fixture`.

Frozen source priority：

1. `static_fixture`：the current deterministic static fixture path。
2. `local_historical_cache_placeholder`：reserved for a future local file /
   historical cache source。
3. `read_only_adapter_placeholder`：reserved for a future read-only adapter。

The Phase L adapter protocol is read-only：

- `list_symbols()`。
- `list_contracts(symbol, trading_day)`。
- `get_main_contract(symbol, trading_day)`。
- `get_trade_contract(symbol, trading_day)`。
- `get_bars(identity, timeframe, start, end, as_of)`。
- `get_latest_quote(identity, as_of)`。

`StaticHistoricalDataFixtureProvider` adapts this protocol while preserving the
existing static fixture behavior. `ReadOnlyMarketDataAdapter` is a disabled
placeholder and returns `BLOCKED` / not configured diagnostics for data reads.

Phase L explicitly does not add：

- broker integration。
- CTP or SimNow integration。
- live trading。
- live order or live account capability。
- real capital access。
- DB persistence。
- schema or Alembic migration。
- default network enablement。
- `ExecutionTarget.PAPER`, `ExecutionTarget.SIM` or `ExecutionTarget.LIVE`
  enablement。

Future providers such as Tushare, Akshare, RQData or CTP market data may only
be attached behind this read-only boundary in a later accepted stage. Adapter
raw payloads remain diagnostic-only and must not become identity truth.

Stage U.5 does not add or require a new historical data table, resolver snapshot
table, fixture table, audit table or Alembic migration.

If a future stage needs durable historical market-data storage, it must first
open a separate contract freeze that defines：

- canonical identity。
- idempotency。
- source versioning。
- correction policy。
- replay behavior。
- session calendar lineage。
- resolver lineage。
- schema and migration plan。

## Future Stage

The next allowed implementation stage is：

```text
U.6 Static Historical Data Fixture
```

U.6 may implement a deterministic local fixture that emits standardized
bar/tick/quote objects under this contract. U.6 must still avoid live feed,
quote API, CTP, SimNow, broker, network, schema changes, DB writes and
non-`MOCK` target enablement unless a separate accepted freeze explicitly
changes those boundaries.

## Stage U.6 Static Historical Data Fixture

Baseline：`stage-u5-historical-market-data-contract`。

Stage U.6 implements the first deterministic local historical market data
fixture. It is static fixture data only and is not a live market source, quote
API, vendor adapter, CTP, SimNow, broker or network integration.

Implemented local fixture scope：

- supported symbols：`ao`, `rb`, `ag`, `cu`。
- supported trading-day window：2026 resolver fixture window。
- supported bar timeframes：`1m`, `5m`, `15m`, `1h`, `1d`。
- deterministic tick stream。
- latest quote snapshot derived from the latest available fixture tick。
- no-lookahead filtering through the query `as_of` timestamp。

The fixture provider interface is：

- `get_bars(...)`。
- `get_ticks(...)`。
- `get_latest_quote(...)`。

The provider returns typed fixture result objects. Unsupported symbol resolves
to `NOT_FOUND`; unsupported timeframe resolves to `INVALID_INPUT`. The fixture
does not write DB rows and does not mutate OMS, Trade, Position, Accounting,
ledger or schema state.

U.6 keeps the same safety boundary：

- no live feed。
- no quote API。
- no CTP。
- no SimNow。
- no broker。
- no network。
- no schema or Alembic migration。
- no DB or ledger writes。
- no `ExecutionTarget.PAPER`, `ExecutionTarget.SIM` or
  `ExecutionTarget.LIVE` enablement。
