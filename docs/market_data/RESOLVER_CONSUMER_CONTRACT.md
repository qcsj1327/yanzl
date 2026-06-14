# Stage U.4.1 Backtest / Paper / SIM Resolver Consumer Contract Freeze

Baseline：`stage-u31-static-registry-metadata-coverage / e76811a`。

Stage U.4.1 is documentation-only. It freezes how local resolver consumers use
`InstrumentResolution`. It does not add code, tests, schema, Alembic migration,
DB writes, live feed, CTP, SimNow, broker, network integration or non-`MOCK`
execution targets.

## Stage U.4.3 In-Memory Resolver Consumer Context

Baseline：`stage-u41-resolver-consumer-contract-freeze / 4816877`。

Stage U.4.3 implements the first local in-memory resolver consumer context. It
does not persist resolver snapshots and does not add schema, Alembic migration,
DB writes, live feed, quote API, CTP, SimNow, broker, network integration or
non-`MOCK` execution targets.

The typed context is code-local only：

- `ResolvedInstrumentIdentity` carries `symbol`, `instrument_id`,
  `trade_instrument_id`, `exchange` and `trading_day`。
- `ResolverLineage` carries resolver source, confidence, effective window,
  diagnostics summary and optional static metadata summary。
- `ResolverConsumerContext` combines identity and lineage。

`ResolverConsumerContext` may be built only from
`InstrumentResolution.status == RESOLVED`. `NOT_FOUND`, `INVALID_INPUT`,
`EXPIRED`, `AMBIGUOUS` and `METADATA_INVALID` fail closed and do not produce a
consumer context.

Console dry-run assembly must build both the typed command preview and the
resolver consumer context from the same resolver result. Paper and SIM console
dry-run wiring must require the context and block if it is missing or if command
identity does not match resolver identity.

PaperLocalSession and SimLocalSession expose a `resolver_required` migration
gate for local dry-run wiring. When the gate is enabled, direct typed commands
without resolver context are blocked, and command/context identity mismatch is
blocked. Non-console migration paths may keep the gate disabled until they are
ported to resolver-derived identity, but they must not claim U.4.1 compliance
until the gate is enabled.

The context must not be copied into `raw_payload` as a fact source. Durable
resolver lineage still requires a separate `Resolver Snapshot Persistence
Contract Freeze`.

## Consumer Scope

This contract applies to local deterministic consumers only：

- Backtest。
- Paper。
- SIM。
- Operator Console dry-run。

It does not apply to and does not enable：

- LIVE。
- CTP。
- SimNow。
- broker execution。
- real capital。

Any future live, CTP, SimNow, broker or real capital identity path requires a
separate contract freeze and acceptance review.

## Required Identity Input

Resolver consumers must enter instrument identity through：

- `symbol`。
- `trading_day`。
- `mode`。

Consumers must not ask operators, fixtures or strategy code to input, infer or
guess：

- `instrument_id`。
- `trade_instrument_id`。
- `exchange`。

Those fields must come from a resolver-derived `InstrumentResolution`.

## Required Resolver Result

Every consumer must obtain an `InstrumentResolution` before it generates a
command, order, report or trade candidate. The only status that permits
downstream generation is：

- `RESOLVED`。

These statuses must fail closed：

- `NOT_FOUND`。
- `INVALID_INPUT`。
- `EXPIRED`。
- `AMBIGUOUS`。
- `METADATA_INVALID`。

Fail closed means no command, order, report, trade, position or accounting fact
may be generated from that unresolved identity.

## Identity Lineage

Downstream objects that are allowed by a future implementation stage must carry
resolver-derived identity lineage sufficient to explain how identity was chosen：

- `symbol`。
- `instrument_id`。
- `trade_instrument_id`。
- `exchange`。
- `trading_day`。
- `resolver_source`。
- `resolver_confidence`。
- `resolver_effective_from`。
- `resolver_effective_to`。
- `resolver_diagnostics_ref` or resolver diagnostics summary。

Stage U.4.1 freezes the lineage requirement only. It does not add fields to
domain models, ORM models, repositories, commands, reports or database tables.

## Backtest Consumer Contract

Backtest must consume a resolver snapshot for each `symbol + trading_day + mode`
identity decision.

Backtest must not dynamically guess `trade_instrument_id` during a run. A roll
rule must be `trading_day`-bound and deterministic. Backtest may use the
continuous/main contract as the market observation identity, but any simulated
order identity must use the resolver-derived trade contract.

Backtest unresolved behavior：

- `NOT_FOUND` blocks the scenario or bar window that requires the identity。
- `INVALID_INPUT` blocks before scenario construction。
- `EXPIRED` blocks the affected trading day。
- `AMBIGUOUS` blocks until fixture/source precedence is made deterministic。
- `METADATA_INVALID` blocks until static metadata is repaired。

Backtest must not treat `raw_payload`, filename, UI label, market-data original
string or free text as an identity source-of-truth.

## Paper Consumer Contract

Paper dry-run and local Paper session paths must use resolver result identity.
They must not accept manual `instrument_id`, manual `trade_instrument_id` or
manual `exchange` as a fallback when resolver status is not `RESOLVED`.

Paper unresolved behavior：

- unresolved resolver status is `BLOCKED`。
- `METADATA_INVALID` is `BLOCKED`。
- target remains `ExecutionTarget.MOCK` only。

Stage U.4.1 does not enable `ExecutionTarget.PAPER` and does not add a Paper
live broker path.

## SIM Consumer Contract

Local SIM dry-run and local SIM session paths must use resolver result identity.
They must not accept manual `instrument_id`, manual `trade_instrument_id` or
manual `exchange` as a fallback when resolver status is not `RESOLVED`.

SIM unresolved behavior：

- unresolved resolver status is `BLOCKED`。
- `METADATA_INVALID` is `BLOCKED`。
- target remains `ExecutionTarget.MOCK` only。

Stage U.4.1 does not enable `ExecutionTarget.SIM` and does not add SimNow, CTP,
broker or network integration.

## Operator Console Consumer Contract

Console remains a resolver consumer for local dry-run configuration.

Console normal path：

- operator selects or enters `symbol`。
- operator enters `trading_day`。
- UI shows resolver preview。
- allowed instruments default to resolver `trade_instrument_id`。
- manual instrument fields are review-only and cannot bypass resolver status。

Console unresolved behavior：

- unresolved resolver status blocks dry-run。
- `METADATA_INVALID` blocks dry-run。
- clearing the whitelist blocks dry-run。
- whitelist mismatch blocks dry-run。
- target remains `MOCK only`。

## Source-of-Truth Boundary

Resolver result is an identity input. It is not a business fact source-of-truth.

Resolver does not own：

- order truth。
- trade truth。
- position truth。
- accounting truth。
- signal truth。
- price truth。
- quantity truth。
- direction truth。

The resolver must not produce trading signal, side, offset, order price, order
quantity, order type or risk approval.

## Forbidden Fallbacks

Consumers must not fall back to：

- `raw_payload` as identity source。
- UI label as identity source。
- filename as identity source。
- broker raw field as identity source。
- market data raw string as identity source。
- manual `instrument_id` / `trade_instrument_id` / `exchange` when resolver is
  unresolved。
- live data source without a separate accepted freeze。

Consumers must not hide missing resolver identity in metadata, free-form JSON,
display-only text or diagnostic payload.

## Future Schema Decision

Default decision：no schema.

If a future stage needs durable resolver snapshots, it must first open：

```text
Resolver Snapshot Persistence Contract Freeze
```

That future freeze must define snapshot identity, schema, idempotency, lineage,
retention, replay behavior, migration, and the distinction between resolver
identity input and downstream business facts.

## Safety Boundary

Stage U.4.1 forbids：

- schema or Alembic migration。
- DB or ledger writes。
- live feed or quote API integration。
- CTP integration。
- SimNow integration。
- broker execution。
- network calls。
- `ExecutionTarget.PAPER`, `ExecutionTarget.SIM` or `ExecutionTarget.LIVE`
  enablement。
- using static fixture metadata as live trading truth。
