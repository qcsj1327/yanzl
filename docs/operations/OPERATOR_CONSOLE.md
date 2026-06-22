# Operator Console V1

Baseline：`phase-l-read-only-market-data-mvp / 52744c4`。

Operator Console V1 是本地只读 / dry-run preview UI。它面向不想直接读代码或跑 CLI 的本地操作者，用中文页面展示 Research、Paper、Portfolio、Market Data、Diagnostics 的链路状态。

它不是实盘交易控制台，不是 Broker / CTP / SimNow 控制台，不是真实账户入口，也不是数据库编辑器。

## 安全边界

Console V1 固定边界：

- 仅展示本地状态和 research-only 结果。
- 仅允许 `MOCK only` dry-run preview。
- 不启用 `ExecutionTarget.PAPER`、`ExecutionTarget.SIM` 或 `ExecutionTarget.LIVE`。
- 不连接 Broker、CTP、SimNow、交易所或任何 live / network 交易服务。
- 不提交真实订单，不读取或操作真实账户。
- 不写数据库，不写 schema，不执行 Alembic migration。
- 不写 OMS / Trade / Position / Accounting / Margin / Settlement。
- 不持久化 console history、result 或 config。

`read_only_adapter_placeholder` 只作为可见但阻断的数据源占位。选择它时 Console 必须显示 `BLOCKED`，不得生成 command，不得访问网络。

## 页面

### Dashboard

展示本地总览：

- Research Platform status。
- Paper Runtime status。
- Portfolio status。
- Market Data source status。
- Current source：`static_fixture` 或 `read_only_adapter_placeholder`。
- Last dry-run summary。
- Safety banner：`MOCK only / research only / no live trading / 不写数据库`。

### Research

展示 backtest / research-only 结果：

- Backtest status。
- strategy。
- symbols。
- orders。
- trades。
- positions。
- realized / unrealized pnl。
- equity curve summary。
- metrics：`total_return`、`max_equity`、`min_equity`。

这些结果只用于研究观测，不是 OMS、Trade、Position、Accounting 或真实账户事实源。

### Portfolio

展示 research portfolio：

- cash。
- equity。
- market value。
- positions table。
- symbol contributions。
- position weights。
- cash weight。
- allocation。

### Paper

展示 Paper research runtime：

- `PaperResearchRuntime` status。
- `PaperSession` lifecycle：run / pause / stop。
- paper orders。
- paper fills。
- paper positions。
- paper portfolio。
- `PaperConsistencyReport`。

页面只提供 dry-run preview 按钮。Paper apply 按钮保持禁用占位，不写本地账本。

### Market Data

展示行情源与 resolver 状态：

- selected data source。
- static fixture status。
- read-only adapter placeholder status。
- resolver source。
- blocked reason。
- supported symbols：`ao`、`rb`、`ag`、`cu`。
- source diagnostics。

数据源选择：

- `static_fixture`：允许本地 preview / dry-run。
- `read_only_adapter_placeholder`：固定 `BLOCKED`，不生成 command，不执行 network。

### Diagnostics

只读展示：

- resolver diagnostics。
- market data diagnostics。
- research diagnostics。
- paper diagnostics。
- safety checks。
- local checks。

Diagnostics 不运行 migration，不修复数据库，不启用 Broker / LIVE，也不启动网络服务。

## 当前实现说明

Console V1 复用现有 operator console 的 session-state dry-run summary，但 session-state 只用于当前 UI 会话展示，不作为持久化 history / result / config。

所有页面采用 wide layout 和紧凑卡片 / 表格，目标是在 1280x720 截图下尽量完整显示主要状态。页面文案以中文为主，避免把内部英文状态长段堆给操作者。
