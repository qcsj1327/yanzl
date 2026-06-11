# Stage R.1 Operator Console Contract Freeze

Baseline：`sim-local-mvp-stable-baseline / 5f28114`。

Stage R.1 is documentation-only. It freezes the local Operator Console UX, functions, configuration, safety boundary and forbidden actions before any implementation.

This stage does not add code, schema, Alembic migration, `src` changes, tests, commit or tag.

## Console positioning

The Operator Console is a local Streamlit-first control panel for users who are not comfortable reading code or using CLI commands.

The Console is used for：

- local Paper run control。
- local controlled SIM run control。
- Runtime and Ops status viewing。
- safety control visibility and safe toggles。
- Paper / SIM result inspection。
- read-only diagnostics。

The Console is not：

- a strategy developer。
- a database editor。
- a LIVE console。
- a broker console。
- a CTP console。
- a SimNow console。
- a FastAPI control plane。
- a public-network service。

The Console must run locally only, keep `ExecutionTarget.MOCK` as the only selectable/usable target, and must not expose any path to `ExecutionTarget.PAPER`, `ExecutionTarget.SIM` or `ExecutionTarget.LIVE` enablement.

## Page layout

The initial Console layout is frozen as these pages：

- Dashboard。
- Paper Session。
- SIM Session。
- Safety Controls。
- Configuration。
- Results / History。
- Diagnostics。
- Live Locked Page。

Navigation labels should be plain and operator-facing. The first opened page should be Dashboard.

## Dashboard

Dashboard must answer what state the local system is in before the operator clicks anything.

Dashboard displays：

- Runtime status。
- current rollout mode。
- ExecutionTarget status。
- migration status。
- kill switch status。
- scheduler pause status。
- replay pause status。
- most recent Paper result。
- most recent SIM result。
- `MOCK only / no live` notice。

Dashboard must make these facts visually obvious：

- LIVE is disabled。
- Broker is disabled。
- CTP is disabled。
- SimNow is disabled。
- real capital is disabled。
- `ExecutionTarget.MOCK` is the only allowed target。

Dashboard must not contain run/apply buttons except links or navigation affordances into the Paper and SIM pages.

## Paper Session page

Allowed buttons：

- `Run Paper Dry-run`。
- `Run Paper Apply`。
- `View Paper Result`。

Display requirements：

- dry-run does not write ledgers or mutate business facts。
- apply may write local ledgers only through `PaperLocalSession -> PaperRuntimeJob -> PaperTradingCoordinator`。
- apply requires explicit confirmation before it becomes enabled。
- Paper runs use `ExecutionTarget.MOCK` only。
- ACKED and FILLED report sequence must be visible when produced。
- Trade, Position, Margin, PnL and Settlement completion status must be visible after apply。
- duplicate/no-op and conflict stop results must be visible。

`Run Paper Apply` is a dangerous action. It must default disabled until the UI captures an explicit confirmation that states the run may write local business ledgers through the accepted Paper chain.

Paper page must not expose direct OMS, Trade, Position or Accounting mutation controls.

## SIM Session page

Allowed buttons：

- `Run SIM Dry-run`。
- `Run SIM Apply`。
- `View SIM Result`。

Display requirements：

- SIM is local controlled simulation。
- SIM is not SimNow。
- SIM is not CTP。
- SIM is not Live。
- `ExecutionTarget.SIM` remains disabled。
- target is `ExecutionTarget.MOCK` only。
- dry-run does not write ledgers or mutate business facts。
- apply may write local ledgers only through `SimLocalSession -> SimRuntimeJob -> SimTradingCoordinator`。
- apply requires explicit confirmation before it becomes enabled。
- ACKED and FILLED report sequence must be visible when produced。
- Trade, Position, Margin, PnL and Settlement completion status must be visible after apply。
- duplicate/no-op and conflict stop results must be visible。

`Run SIM Apply` is a dangerous action. It must default disabled until the UI captures an explicit confirmation that states the run may write local business ledgers through the accepted SIM chain.

SIM page must not expose `ExecutionTarget.SIM` selection or any SimNow / CTP / broker option.

## Safety Controls page

Allowed safety toggles：

- Kill Switch。
- Scheduler Pause。
- Replay Pause。

The page must explain whether each toggle blocks new work, scheduler work, replay work, or all apply actions.

Forbidden controls：

- Live Enable。
- Broker Enable。
- CTP Enable。
- SimNow Enable。
- Manual DB edit。
- Force Order。
- Force Trade。
- Force Position。

Safety Controls must not offer an override that bypasses RuntimeJob, LocalSession or application service gates.

## Configuration page

Normal configuration fields：

- `account_id`。
- `trading_day`。
- instrument whitelist。
- max order size。
- max position size。
- max daily loss。
- Paper/SIM mode。
- dry-run/apply intent。

Advanced configuration fields：

- `runtime_id`。
- `config_hash`。
- migration revision。
- capital control details。

Initial configuration sources are limited to：

- typed config object。
- local TOML/YAML file。
- environment variables。
- UI session state。

Stage R.1 does not add durable configuration storage. Persisted Console configuration, durable approvals, durable audit/session tables, multi-user auth or UI profile storage require a separate contract freeze.

Configuration UI must not allow selecting or enabling `ExecutionTarget.PAPER`, `ExecutionTarget.SIM`, `ExecutionTarget.LIVE`, live broker, CTP or SimNow.

## Results / History page

Results / History displays local observability and accepted ledger inspection results. It is not a business source-of-truth.

Required display fields：

- session status。
- job status。
- run status。
- raw reports。
- normalized reports。
- OMS status。
- trade status。
- position status。
- margin status。
- PnL status。
- settlement status。
- duplicate flag。
- DB delta。
- target list。

The page should make it easy to see：

- whether dry-run wrote zero rows。
- whether apply wrote the expected local rows。
- whether the final target list is `MOCK` only。
- whether duplicate rerun produced zero DB delta。
- where a conflict/error stopped downstream processing。

Results / History must not provide edit, repair, force, retry-as-new-order or manual ledger mutation controls.

## Diagnostics page

Diagnostics is read-only.

Required display fields：

- pytest result。
- ruff result。
- mypy result。
- alembic current。
- git commit。
- git tag。
- worktree clean status。
- DB health。
- Redis health if configured。
- last error。

Diagnostics may run or display read-only checks only. It must not run schema migrations, mutate DB state, repair ledgers, enable broker, enable LIVE or start network services.

## Live Locked Page

Live Locked Page must clearly display：

- LIVE disabled。
- CTP disabled。
- SimNow disabled。
- Broker disabled。
- Real capital disabled。

The page must not provide enable buttons, unlock buttons, credential inputs, broker target selectors, CTP selectors or SimNow selectors.

Any future live, CTP, SimNow, broker or real capital enablement requires a separate contract freeze, implementation stage and acceptance review. Stage R.1 provides no hidden enable path.

## Operation safety

Dangerous actions must：

- require second confirmation。
- show impact explanation。
- default disabled。
- distinguish dry-run from apply。
- state whether the action writes database rows。
- state `MOCK only`。
- state the exact accepted chain used for mutation。

Dry-run semantics：

- Paper dry-run must not write business ledgers。
- SIM dry-run must not write business ledgers。
- dry-run results are observability only。

Apply semantics：

- Paper apply may write local ledgers only through `PaperLocalSession -> PaperRuntimeJob -> PaperTradingCoordinator` after all gates pass。
- SIM apply may write local ledgers only through `SimLocalSession -> SimRuntimeJob -> SimTradingCoordinator` after all gates pass。
- apply must preserve duplicate/no-op and conflict-stop behavior。
- apply must not use broker, CTP, SimNow, LIVE or non-`MOCK` targets。

## Architecture boundary

Console may call only：

- `PaperLocalSession`。
- `SimLocalSession`。
- Runtime / Ops health surfaces。
- read-only diagnostics。

Console must not：

- directly call OMS repository mutation。
- directly call Trade repository mutation。
- directly call Position repository mutation。
- directly call Accounting repository mutation。
- directly call `PaperTradingCoordinator` or `SimTradingCoordinator` by bypassing LocalSession / RuntimeJob。
- directly call `PaperRuntimeJob` or `SimRuntimeJob` in a way that bypasses LocalSession confirmation semantics。
- call execution harnesses directly。
- construct commands from raw payloads。
- use broker callbacks as commands。
- write ledgers directly。
- connect to broker, CTP, SimNow, live account or broker network。
- modify schema or run Alembic migrations。
- expose FastAPI, public network or remote control endpoints。

Console result objects are observability only and never replace DB business ledgers as source-of-truth.

## Implementation recommendation

Future implementation package：

- `src/futures_mvp/modules/operator_console/app.py`。
- `src/futures_mvp/modules/operator_console/view_models.py`。
- `src/futures_mvp/modules/operator_console/actions.py`。
- `src/futures_mvp/modules/operator_console/diagnostics.py`。
- `src/futures_mvp/modules/operator_console/safety.py`。

Recommended responsibilities：

- `app.py` owns Streamlit layout/navigation only。
- `view_models.py` converts typed session/job/run/health results into display-only view models。
- `actions.py` calls only `PaperLocalSession` and `SimLocalSession` entrypoints。
- `diagnostics.py` gathers read-only diagnostics。
- `safety.py` renders and validates allowed safety controls without adding forbidden enable paths。

Future tests should cover：

- Console actions do not bypass `PaperLocalSession` or `SimLocalSession`。
- forbidden actions do not exist。
- live buttons do not exist。
- Paper apply requires confirmation。
- SIM apply requires confirmation。
- non-`MOCK` target cannot be selected。
- diagnostics are read-only。
- configuration cannot enable broker, CTP, SimNow, LIVE or non-`MOCK` targets。

## Validation

Stage R.1 validation is documentation-only：

```bash
git diff --check
```

No pytest, ruff, mypy, schema migration or app run is required for this contract freeze unless later implementation changes code.

## Stage R.2 skeleton implementation facts

Baseline：`stage-r1-operator-console-contract-freeze / bb1d063`。

Stage R.2 implements the first local Operator Console skeleton only：

- package：`src/futures_mvp/modules/operator_console/`。
- pages：Dashboard、Paper Session、SIM Session、Safety Controls、Configuration、Results / History、Diagnostics and Live Locked Page。
- Chinese UI text is centralized in `labels.py`。
- `view_models.py` provides display-only frozen view models and `default_console_view_model()`。
- `actions.py` contains disabled/placeholder actions only；Paper/SIM apply does not call real sessions。
- `diagnostics.py` is read-only placeholder display data；it does not run commands。
- `safety.py` is display-only placeholder safety data；it does not mutate safety state。
- `app.py` is Streamlit-compatible through a small UI protocol and lazy Streamlit import；Stage R.2 adds no Streamlit dependency。

Stage R.2 preserves these boundaries：

- no Paper/SIM apply execution。
- no DB writes。
- no broker / CTP / SimNow / LIVE / network integration。
- no FastAPI control plane。
- no `ExecutionTarget.PAPER` / `SIM` / `LIVE` enablement。
- no schema or Alembic migration。

## Stage R.3 UI polish and read-only diagnostics facts

Baseline：`stage-r2-operator-console-skeleton / e1b3f73`。

Stage R.3 keeps the Operator Console as a local UI skeleton and improves display polish：

- residual UI field names such as Operator Console, Runtime, rollout mode, mode, target, health, latest result, diagnostics and history are centralized in `labels.py` with Chinese display labels。
- diagnostics display labels and values are centralized in `labels.py`。
- `diagnostics.py` returns read-only unknown/not-run or unknown/not-checked placeholder values for pytest, ruff, mypy, Alembic, git, worktree, DB health, Redis health and last error。
- diagnostics provider does not execute shell commands or inspect external services。
- Paper/SIM apply remains disabled/placeholder。
- forbidden actions remain display-only text and have no enable/unlock buttons。

Stage R.3 preserves these boundaries：

- no PaperLocalSession / SimLocalSession wiring。
- no Paper/SIM apply execution。
- no DB or ledger writes。
- no Streamlit dependency addition。
- no FastAPI / broker / CTP / SimNow / LIVE / network integration。
- no `ExecutionTarget.PAPER` / `SIM` / `LIVE` enablement。
- no schema or Alembic migration。

## Stage R.3.1 UX redesign facts

Baseline：`stage-r3-console-streamlit-preview / 550440b`。

Stage R.3.1 keeps the console local and action-free while improving visual hierarchy for non-code / non-CLI users：

- Dashboard is redesigned into four cards：system status, safety locks, next recommended steps and latest result。
- Paper page is redesigned as a guided flow：what it is, operation flow and current disabled/placeholder buttons。
- SIM page is redesigned as a guided flow with a clear Paper-vs-SIM distinction。
- Safety page explains Kill Switch, Scheduler Pause and Replay Pause, then shows locked forbidden actions prominently。
- Results / History defaults to not-run language instead of a list of disabled statuses。
- Live Locked page starts with `🔒 当前不是实盘环境` and explains no exchange, CTP, SimNow, real capital or LIVE enable button exists。
- Labels use more natural Chinese, including `仅本地模拟，不连接真实交易所` for MOCK-only display。

Stage R.3.1 preserves these boundaries：

- no PaperLocalSession / SimLocalSession wiring。
- no Paper/SIM apply execution。
- no DB or ledger writes。
- no new dependency。
- no FastAPI / broker / CTP / SimNow / LIVE / network integration。
- no `ExecutionTarget.PAPER` / `SIM` / `LIVE` enablement。
- no schema or Alembic migration。

## Stage R.4 dry-run action implementation facts

Baseline：`stage-r31-console-ux-redesign / 56ebcf4`。

Stage R.4 allows the local Operator Console skeleton to trigger Paper/SIM
dry-run through injected callables only：

- `actions.py` defines a dry-run action interface with injected Paper and SIM
  provider callables。
- no provider returns `BLOCKED` and does not execute any session logic。
- Paper dry-run invokes only the injected Paper provider。
- SIM dry-run invokes only the injected SIM provider。
- dry-run action results are display data：session status, job status, run
  status, DB delta and target。
- UI stores the latest dry-run result in the view model for display during the
  current render path。
- Paper/SIM pages show the latest dry-run result after a dry-run click。
- Results / History can show the latest dry-run summary：session status, job
  status, run status, `DB delta = 0` and `MOCK only` target。
- Chinese labels for dry-run result fields remain centralized in `labels.py`。

Stage R.4 preserves these boundaries：

- no Paper/SIM apply execution。
- apply buttons remain disabled/placeholder。
- no DB or ledger writes。
- no PaperLocalSession / SimLocalSession import or direct wiring。
- no broker / CTP / SimNow / LIVE / network integration。
- no FastAPI control plane。
- no `ExecutionTarget.PAPER` / `SIM` / `LIVE` enablement。
- no schema or Alembic migration。

## Stage R.5 real LocalSession dry-run wiring facts

Baseline：`stage-r4-console-dry-run-actions / f368736`。

Stage R.5 wires the console dry-run buttons to the accepted local session
entrypoints, but only for dry-run：

- `dry_run_wiring.py` is the only Operator Console module allowed to import
  `PaperLocalSession` and `SimLocalSession`。
- Paper dry-run provider creates a callable that runs `PaperLocalSession.run()`
  only when complete Paper session config, job factory and command source are
  injected。
- SIM dry-run provider creates a callable that runs `SimLocalSession.run()`
  only when complete SIM session config, job factory and command source are
  injected。
- Default Streamlit startup creates both provider callables, but without local
  fixture/config they fail closed as `BLOCKED`。
- Providers require `dry_run=True`, `apply_confirmed=False`, no
  `apply_requested`, and `MOCK only` target。
- Providers map LocalSession result into console display fields：session
  status, job status, run status, `DB delta = 0`, target and reason。
- Action layer rejects provider output with non-`MOCK` target or non-zero DB
  delta and displays it as `BLOCKED` instead of success。

Stage R.5 preserves these boundaries：

- no Paper/SIM apply execution。
- apply buttons remain disabled/placeholder。
- no DB or ledger writes。
- no direct coordinator, harness or repository call from the console。
- no broker / CTP / SimNow / LIVE / network integration。
- no FastAPI control plane。
- no `ExecutionTarget.PAPER` / `SIM` / `LIVE` enablement。
- no schema or Alembic migration。
- no new dependency。
