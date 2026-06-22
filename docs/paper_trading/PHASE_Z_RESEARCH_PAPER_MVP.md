# Phase Z Research Paper Trading MVP

Baseline:

- Phase Y implementation outputs from the local Research Platform.
- Phase Y was not promoted to a stable accepted baseline in this workspace
  until its acceptance review findings are resolved.

Phase Z adds a local, in-memory Paper MVP that consumes `BacktestResult`
research outputs and maps them into paper diagnostics. The MVP supports the
AO/RB/AG/CU multi-symbol research path without creating any paper source of
truth.

The accepted Phase Z package surface is the Research Paper MVP exported from
`futures_mvp.modules.paper_trading`. The root package intentionally exports
only research-paper objects such as `PaperResearchRuntime`,
`PaperResearchSession`, `PaperPortfolio`, `PaperPosition`, `PaperPnL`,
`PaperOrder`, `PaperFill`, `PaperReport` and `PaperConsistencyReport`.

Legacy paper files such as `harness.py`, `coordinator.py`, `job.py`,
`session.py` and `reports.py` remain in the tree for historical tests and
internal compatibility. They are not part of the accepted Phase Z MVP surface
and must be imported only through their concrete legacy modules.
Any root-package compatibility hook for existing runtime imports is internal
only, is not listed in `__all__`, and must not be treated as accepted Phase Z
API.

## Flow

```text
Research Backtest Strategy
-> Decision
-> SimulatedOrder
-> Mock SimulatedTrade
-> ResearchPosition
-> PaperPosition
-> PaperPnL
-> PaperPortfolio
-> PaperConsistencyReport
-> PaperReport
```

## Objects

- `PaperOrder` mirrors research simulated orders.
- `PaperFill` mirrors research simulated trades, including Research Platform
  commission and slippage values, and remains a mock fill.
- `PaperPosition` maps from `ResearchPosition` and includes a
  `resolver_lineage_summary` plus `resolver_diagnostics` for resolver-derived
  identity traceability.
- `PaperPnL` maps from `ResearchPnLPoint`.
- `PaperPortfolio` contains cash, paper positions, PnL points, equal allocation
  diagnostics and equity.
- `PaperConsistencyReport` compares paper cash, equity, orders, fills and
  positions against the Research Platform output produced by the same input.
- `PaperReport` exposes equity, positions, orders and fills.
- `PaperResearchSession` supports `run`, `pause` and `stop`.

## Portfolio Aggregation

The paper portfolio is derived from `ResearchPortfolio`:

```text
paper_equity = research_portfolio.total_equity
paper_cash = research_portfolio.cash
paper_positions = research_positions
paper_allocation_per_symbol = research_portfolio.initial_cash / position_count
```

The MVP keeps allocation deterministic and equal-weight for AO/RB/AG/CU. It
does not rebalance dynamically and does not allow negative cash to be created by
paper code; negative-cash validation remains in the Research Platform input
path.

## Research Reuse

Commission, slippage and sizing are not recalculated in paper trading. Paper
fills and positions reuse the Research Platform outputs:

- `FixedCommissionModel` values flow through `SimulatedTrade.commission`.
- `FixedSlippageModel` values flow through `SimulatedTrade.slippage`.
- `FixedQuantitySizing` and `FixedCashSizing` determine paper order and fill
  quantities through the research simulated order/trade.

## Operator Console

`paper_runtime_console_view` converts a `PaperRuntimeResult` into display rows
for orders, fills, positions, equity, portfolio, allocation and consistency.
It is a view-model adapter only; it does not run a job, persist data, enable a
target or connect to a broker.

The console view consumes the Research Paper MVP result shape. It is not a
gateway into legacy harness or coordinator behavior.

## Safety

This Phase Z MVP is MOCK only. It does not enable
`ExecutionTarget.PAPER`, `ExecutionTarget.SIM` or `ExecutionTarget.LIVE`.

It does not write schema, Alembic, DB, OMS, Trade ledger, Position ledger,
Accounting ledger, Margin, Settlement or broker state. It does not connect
broker, CTP, SimNow, live feed or network services. It does not represent real
capital.

All Phase Z outputs are research-only diagnostics. They are not production
source-of-truth for orders, fills, trades, positions, PnL, portfolio, cash,
account balances or broker/exchange state.

The accepted root package surface must not import or expose broker adapter,
OMS, Trade ledger, Position ledger, Accounting, Margin, Settlement, CTP,
SimNow, live network, or non-MOCK execution target enablement.
