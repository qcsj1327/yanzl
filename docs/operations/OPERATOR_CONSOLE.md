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

## Stage R.5.1 blocked result UX polish facts

Baseline：`stage-r5-console-real-dry-run-wiring / 48a1978`。

Stage R.5.1 changes display wording only. It does not change dry-run provider
semantics or safety decisions：

- English blocked reasons are mapped to user-facing Chinese in `labels.py`。
- Paper/SIM pages render a blocked dry-run card when the latest dry-run status
  is `BLOCKED`。
- Results / History renders the same blocked dry-run card for blocked latest
  results。
- The blocked card explains why the operation was blocked, whether it was safe,
  and what the operator should do next。
- The blocked card states that no database write happened, no real exchange was
  connected, the target remains local MOCK, and real capital was not used。
- Configuration now includes a `预演所需配置` section with account ID, trading
  day, instrument whitelist, max order size, max position size, max daily loss,
  typed command provider and job factory readiness。

Stage R.5.1 preserves these boundaries：

- no dry-run safety semantic change。
- no Paper/SIM apply execution。
- no DB or ledger writes。
- no broker / CTP / SimNow / LIVE / network integration。
- no FastAPI control plane。
- no `ExecutionTarget.PAPER` / `SIM` / `LIVE` enablement。
- no schema or Alembic migration。
- no new dependency。

## Stage T.1 Local Operator Workflow Hardening Contract Freeze

Baseline：`stage-r51-console-blocked-result-ux / b7c6035`。

Stage T.1 is documentation-only. It freezes the next local Operator Console
hardening scope for non-code / non-CLI operators. The goal is to let operators
assemble the configuration needed for Paper/SIM dry-run, preview typed dry-run
commands/config, inspect in-session result history, view known soak evidence and
read read-only diagnostics from the UI.

Stage T.1 does not add code, schema, Alembic migration, `src` changes, tests,
commit or tag.

### Stage T.1 allowed future implementation

Future implementation may add：

- Console dry-run configuration assembly。
- typed command fixture preview。
- account, trading day, instrument whitelist and capital controls UI。
- Paper/SIM dry-run providers constructed from typed UI configuration。
- Results history kept in memory / session state only。
- read-only soak evidence display for known Paper/SIM baselines。
- read-only diagnostics。

Future implementation must not add：

- Paper/SIM apply from this workflow。
- DB writes, ledger writes or repository mutation。
- durable result/history/config tables。
- `ExecutionTarget.PAPER`, `ExecutionTarget.SIM` or `ExecutionTarget.LIVE`
  enablement。
- SimNow, CTP, broker, live account or network integration。
- schema or Alembic migration。
- Console result/history source-of-truth semantics。
- Live/Broker/CTP/SimNow enable buttons。
- Force Order, Force Trade, Force Position or Force Accounting buttons。

### Console Config Workflow

The Configuration page may collect these operator-facing fields：

- `account_id`。
- `trading_day`。
- `instrument_id`。
- `trade_instrument_id`。
- `symbol`。
- `exchange`。
- `quantity`。
- `price`。
- `max_order_size`。
- `max_position_size`。
- `max_daily_loss`。
- allowed instruments。

The UI may use these fields only to build typed dry-run command/config previews.
It must not write DB rows, ledgers, repositories, durable config, approvals or
audit/session tables.

Configuration preview must keep `instrument_id`, `trade_instrument_id`,
`symbol` and `exchange` explicit. It must not hide missing trading identity in
`raw_payload`, `metadata`, free-form JSON or display-only text.

Missing or invalid configuration must produce a `BLOCKED` dry-run result with
Chinese guidance that explains why it is blocked, whether it is safe and what
the operator should do next.

### Dry-run Provider Assembly

Paper/SIM dry-run providers may be constructed only from typed UI config. The
assembly contract is：

- `dry_run=True`。
- `apply_confirmed=False`。
- `apply_requested=False`。
- target is `MOCK` only。
- provider input comes from typed UI config, not raw payload strings。
- missing config blocks before session execution。
- invalid config blocks before session execution。
- non-`MOCK` target is impossible; if observed, result is `BLOCKED`。
- nonzero DB delta is `BLOCKED`。

The Console may continue to keep `dry_run_wiring.py` as the only module that
imports `PaperLocalSession` and `SimLocalSession`. UI pages, labels, view models
and result history must not import LocalSession internals directly.

Every dry-run result must display：

- 是否写库。
- target。
- reason。
- next step。

### Result History

Initial result history is limited to in-memory / UI session-state history.

Result history is observability only：

- no schema。
- no durable table。
- no repository。
- no ledger。
- no source-of-truth status。
- no business fact reconstruction from history。

History may show dry-run status, DB delta, target, reason, next step, duplicate
or conflict flags and timestamps for operator readability. It must not provide
edit, repair, retry-as-new-order, force, replay-apply or manual ledger mutation
controls.

### Soak Evidence Display

Soak evidence display may show known accepted Paper/SIM baseline evidence as
read-only UI content.

It must not：

- execute commands from the UI。
- run pytest, ruff, mypy, Alembic, shell scripts or local session commands。
- mutate DB, ledgers, repositories or schema。
- promote evidence into business facts。
- infer new acceptance from stale evidence。

Displayed evidence must be labeled as evidence display only. Current acceptance
for a later stage still requires a separate validation run and acceptance review.

### Diagnostics

Diagnostics remain read-only. Stage T.1 may keep the current placeholder
diagnostics or add a safe injected diagnostics provider that only reads supplied
status values.

Running shell commands from the UI requires a separate contract freeze and
acceptance review. Stage T.1 does not approve command execution from the
Console.

Diagnostics must not run migrations, repair ledgers, write DB rows, enable live
targets, start network services or inspect broker/CTP/SimNow sessions.

### Safety UX

Apply remains disabled for this workflow.

The Live Locked Page remains visible and locked. It must not provide enable
buttons, unlock buttons, credential inputs, broker target selectors, CTP
selectors, SimNow selectors or live mode selectors.

Forbidden actions must remain impossible：

- Paper apply。
- SIM apply。
- Live Enable。
- Broker Enable。
- CTP Enable。
- SimNow Enable。
- Manual DB edit。
- Force Order。
- Force Trade。
- Force Position。
- Force Accounting。
- `ExecutionTarget.PAPER` enablement。
- `ExecutionTarget.SIM` enablement。
- `ExecutionTarget.LIVE` enablement。

### Stage T.1 future test matrix

Future implementation tests should cover：

- valid config builds a `MOCK` dry-run provider。
- invalid config is blocked。
- non-`MOCK` target is impossible。
- dry-run does not write DB。
- apply remains disabled。
- result history is in-memory / session-state only。
- forbidden buttons do not exist。
- no DB, repository, broker, live, CTP, SimNow or network imports outside
  accepted dry-run wiring。
- no schema changes。

Stage T.1 validation：

```bash
git diff --check
```

## Stage T.2 Console Dry-run Config Assembly Implementation Facts

Baseline：`stage-t1-console-workflow-hardening-freeze / 88c937c`。

Stage T.2 implements local Operator Console dry-run configuration assembly for
Paper/SIM dry-run preview and provider construction.

Implemented files：

- `src/futures_mvp/modules/operator_console/config_assembly.py`。
- `src/futures_mvp/modules/operator_console/view_models.py`。
- `src/futures_mvp/modules/operator_console/app.py`。
- `src/futures_mvp/modules/operator_console/dry_run_wiring.py`。
- `src/futures_mvp/modules/operator_console/labels.py`。
- `tests/unit/operator_console/*`。

Stage T.2 UI config fields：

- `account_id`。
- `trading_day`。
- `instrument_id`。
- `trade_instrument_id`。
- `symbol`。
- `exchange`。
- `quantity`。
- `price`。
- `max_order_size`。
- `max_position_size`。
- `max_daily_loss`。
- allowed instruments。

Stage T.2 validation：

- missing `account_id` blocks。
- missing `trading_day` blocks。
- missing `instrument_id` / `trade_instrument_id` blocks。
- `quantity <= 0` blocks。
- `price <= 0` blocks。
- allowed instruments mismatch blocks。
- target remains `MOCK only`。
- `apply_requested` remains false。

Stage T.2 typed command preview displays：

- account。
- trading day。
- instrument identity。
- `BUY / OPEN` as read-only direction / offset。
- quantity。
- price。
- target：仅本地模拟，不连接真实交易所。
- dry-run：是。
- 写库：否。

Stage T.2 provider assembly：

- UI config is assembled into a typed preview `ExecutionCommand` with
  `ExecutionTarget.MOCK` only。
- Paper/SIM config provider constructors use typed UI config and keep
  `dry_run=True`, `apply_confirmed=False`, `apply_requested=False`。
- If `job_factory` or other accepted LocalSession dependencies are missing, the
  provider returns `BLOCKED` instead of fail-open。
- Invalid config returns `BLOCKED` with Chinese operator-facing reason and
  missing-field detail。
- non-`MOCK` target cannot be generated from UI config。

Stage T.2 result history：

- dry-run action results are appended to in-memory / Streamlit session-state
  history only。
- history keeps only the recent entries for display。
- history is observability only and not source-of-truth。
- no DB, repository, ledger or durable table is used。

Stage T.2 preserves these boundaries：

- no Paper/SIM apply execution。
- apply buttons remain disabled。
- no DB or ledger writes。
- no repository mutation。
- no broker / CTP / SimNow / LIVE / network integration。
- no FastAPI control plane。
- no `ExecutionTarget.PAPER` / `SIM` / `LIVE` enablement。
- no schema or Alembic migration。
- no new dependency。

Stage T.2 validation：

```bash
uv run pytest tests/unit/operator_console
uv run pytest
uv run ruff check .
uv run mypy src
git diff --check
```

## Stage T.3 Console Local Dry-run Fixture Wiring Facts

Baseline：`stage-t2-console-dry-run-config-assembly-layout-fix / 45e470d`。

Stage T.3 wires valid UI configuration to local Paper/SIM dry-run fixture
execution. It keeps the accepted LocalSession boundary and still does not
enable apply, DB writes, broker/live/network targets or durable history.

Implemented behavior：

- Configuration page still builds a typed `ExecutionCommand` from UI fields。
- The command always uses `ExecutionTarget.MOCK` and is displayed as
  `MOCK only` / `仅本地模拟，不连接真实交易所`。
- `create_paper_config_dry_run_provider(...)` now supplies a console-local
  dry-run fixture job factory by default when config is valid。
- `create_sim_config_dry_run_provider(...)` now supplies a console-local dry-run
  fixture job factory by default when config is valid。
- The fixture factories return local `DRY_RUN` job results with processed
  command count and no coordinator/repository execution。
- `PaperLocalSession.run()` and `SimLocalSession.run()` map those fixture jobs to
  `DRY_RUN_COMPLETED` session results。
- Console results keep `DB delta = 0` and target `MOCK only`。
- Results history remains in-memory / Streamlit session-state only。

Paper dry-run result fields：

- session status：`DRY_RUN_COMPLETED`。
- job status：`DRY_RUN`。
- run status：`DRY_RUN_COMPLETED`。
- database write delta：`0`。
- target：`MOCK only`。

SIM dry-run result fields：

- session status：`DRY_RUN_COMPLETED`。
- job status：`DRY_RUN`。
- run status：`DRY_RUN_COMPLETED`。
- database write delta：`0`。
- target：`MOCK only`。

Stage T.3 safety boundaries：

- invalid UI config still returns `BLOCKED` before session execution。
- lower-level wiring without a job factory still returns `BLOCKED`。
- non-`MOCK` command targets remain impossible from UI config and are blocked if
  injected in tests。
- action handling converts any nonzero DB delta into `BLOCKED`。
- apply buttons remain disabled。
- no Paper/SIM apply path is wired。
- no DB, ledger, repository, coordinator or harness call is made from the
  Console。
- no broker, CTP, SimNow, LIVE or network integration is added。
- no `ExecutionTarget.PAPER`, `ExecutionTarget.SIM` or `ExecutionTarget.LIVE`
  enablement is added。
- no schema or Alembic migration is added。
- no dependency is added。

Stage T.3 validation：

```bash
uv run pytest tests/unit/operator_console
uv run pytest
uv run ruff check .
uv run mypy src
git diff --check
```

## Stage U.1 Instrument Resolver / Market Data Contract Freeze Impact

Baseline：`stage-t4-console-preview-stable / fa234eb`。

Stage U.1 is documentation-only for Operator Console. Current Console config
fields `symbol`、`instrument_id` and `trade_instrument_id` remain temporary local
dry-run fixture inputs. They are not sufficient for domestic futures backtest,
Paper, SIM or future Live workflows.

Future Console workflow should not ask ordinary users to guess
`instrument_id` or `trade_instrument_id`. The UI should ask for：

- `symbol`。
- `trading_day`。
- mode：Paper / SIM。

Then it should show an Instrument Resolver preview：

- `symbol`。
- `instrument_id`。
- `trade_instrument_id`。
- `exchange`。
- `contract_role`。
- `source`。
- `confidence`。
- `effective_from / effective_to`。
- diagnostics。

Console impact boundary：

- main / continuous contract is for market data, backtest and strategy
  observation only。
- main / continuous contract must not be used directly for orders。
- `trade_instrument_id` must be traceable to resolver output。
- same `symbol + trading_day` must resolve consistently for backtest, Paper,
  SIM and future Live。
- Console resolver preview is observability / configuration preview only and
  must not become a business fact source-of-truth。

Stage U.1 does not implement resolver preview. It does not add code, schema,
tests, CTP, SimNow, broker, live feed, network calls or non-`MOCK` execution
targets.

## Stage U.2 Static Instrument Resolver Console Integration

Baseline：`stage-u1-instrument-resolver-contract-freeze / 81bcaf1`。

Stage U.2 adds local static resolver integration to the Operator Console.
Normal configuration now asks for：

- `symbol`。
- `trading_day`。
- account / quantity / price / local safety limits。

The Console displays resolver preview values：

- 行情合约 `instrument_id`。
- 交易合约 `trade_instrument_id`。
- 交易所 `exchange`。
- 来源 `source`。
- 置信度 `confidence`。
- 生效区间 `effective_from / effective_to`。

Dry-run config assembly fills `instrument_id`, `trade_instrument_id` and
`exchange` from resolver output. Advanced fields still show those values for
review, but are labeled `由 resolver 生成，不建议手填`。In the normal path, manual
`instrument_id` / `trade_instrument_id` cannot bypass an unresolved resolver.

Blocked resolver states remain fail-closed：

- unknown symbol blocks as `resolver 未找到匹配合约，已阻断`。
- ambiguous fixture blocks as `resolver 结果不唯一，已阻断`。
- expired window blocks as `resolver 合约不覆盖当前交易日，已阻断`。
- invalid input blocks as `resolver 输入无效，已阻断`。

Safety boundary：

- resolver preview writes no DB rows。
- resolver result is not a trading signal。
- resolver does not decide quantity, price, direction or offset。
- Console target remains `MOCK only`。
- no CTP, SimNow, broker, live feed, network call, schema change or Alembic
  migration is added。

## Stage U.2.1 Console Resolver UI Polish

Baseline：`stage-u2-static-instrument-registry-resolver / 9996a7d`。

Stage U.2.1 changes Console UI copy and layout only. It does not change
resolver safety semantics.

Configuration normal path now keeps editable inputs limited to：

- `symbol`。
- `trading_day`。
- quantity / price。
- max order size / max position size / max daily loss。
- resolver recommended allowed instruments。

`instrument_id`, `trade_instrument_id` and `exchange` are no longer editable
normal-form fields. They are shown as resolver-generated, read-only preview
values：

- 行情合约：由 resolver 生成。
- 交易合约：由 resolver 生成。
- 交易所：由 resolver 生成。
- 来源：`static fixture only, not live market source`。
- 生效区间。
- 置信度。

The UI states that the mapping is local static contract mapping only, is not a
real market data source, and does not connect to an exchange. Unresolved
resolver status still blocks dry-run. Manual instrument fields cannot bypass
resolver output in the normal path.

Safety boundary remains unchanged：

- no resolver safety semantic change。
- no DB write。
- no schema or Alembic migration。
- no CTP, SimNow, broker, live feed or network integration。
- no `ExecutionTarget.PAPER`, `ExecutionTarget.SIM` or
  `ExecutionTarget.LIVE` enablement。

## Stage U.3.1 Resolver Whitelist UX

Baseline：`stage-u21-console-resolver-ui-polish / 9912b24`。

Stage U.3.1 improves the local Console whitelist experience without changing
resolver safety semantics.

Configuration normal path still asks for `symbol + trading_day`; the editable
whitelist field now defaults to the resolver trade contract. Operators no
longer need to copy `ao2609` or another trade contract manually for the happy
path.

Resolver preview displays：

- `当前白名单：<trade_instrument_id>（由 resolver 推荐）`。
- the static fixture source warning。
- resolver-generated market contract, trade contract and exchange。

If the whitelist is cleared or does not contain the resolver
`trade_instrument_id`, dry-run config assembly remains `BLOCKED` with Chinese
operator-facing guidance.

If selected main or trade contract metadata is missing or invalid, resolver
status is `METADATA_INVALID` and Console dry-run remains `BLOCKED`.

Safety boundary remains unchanged：

- no DB write。
- no schema or Alembic migration。
- no live feed, quote API, CTP, SimNow, broker or network integration。
- no `ExecutionTarget.PAPER`, `ExecutionTarget.SIM` or
  `ExecutionTarget.LIVE` enablement。
