# 本地操作台 V2：配置中心

基线：`phase-p-broker-readonly-platform-v1 / 272ce01`。

本地操作台 V2 是平台配置中心。它面向不想直接读代码或跑命令行的本地操作者，用中文页面统一展示总览、配置中心、研究、组合、纸面运行、券商只读、行情数据和系统诊断。

它不是实盘交易控制台，不是 Broker / CTP / SimNow 控制台，不是真实账户入口，也不是数据库编辑器。

## 安全边界

本地操作台 V2 固定边界：

- 仅展示本地状态和 research-only 结果。
- 仅允许 `MOCK only` dry-run preview。
- 不启用 `ExecutionTarget.PAPER`、`ExecutionTarget.SIM` 或 `ExecutionTarget.LIVE`。
- 不连接 Broker、CTP、SimNow、交易所或任何 live / network 交易服务。
- 不提交真实订单，不读取或操作真实账户。
- 不写数据库，不写 schema，不执行 Alembic migration。
- 不写 OMS / Trade / Position / Accounting / Margin / Settlement。
- 不持久化操作台历史、结果或配置。

配置中心只管理本地 UI 会话中的配置视图。它可以展示和临时装配本次运行所需配置，但不能修改业务事实，不能写入 OMS、Trade、Position、Accounting、Margin、Settlement，也不能启用任何非 `MOCK` 执行目标。

`read_only_adapter_placeholder` 只作为可见但阻断的数据源占位。选择它时 Console 必须显示 `BLOCKED`，不得生成 command，不得访问网络。

真实行情阶段之后，控制台中的真实行情数据源名称为 `real_market_data`。默认仍未配置，页面必须显示：

- 已阻断。
- 未配置。
- 不会访问网络。
- 不会连接 Broker、CTP、SimNow。
- 不会生成非模拟命令。

## 页面

### 总览

展示本地总览：

- 研究平台状态。
- 纸面运行时状态。
- 组合状态。
- 行情数据源状态。
- 当前来源：`static_fixture` 或 `read_only_adapter_placeholder`。
- 最近预演摘要。
- 安全边界：仅本地模拟、仅研究展示、不启用实盘、不写数据库。

### 配置中心

配置中心是 V2 的新增入口，统一展示：

- 基本配置：账户、交易日、数据源、运行模式、交易品种、时间周期。
- 研究配置：策略、仓位模式、固定数量、固定资金、手续费、滑点、资金分配。
- 纸面配置：纸面运行时、状态、运行、暂停、停止；未启动时显示“未启动”。
- 券商配置：Broker、只读、Shadow、禁用；不得出现登录、提交、撤销按钮。
- 行情配置：静态样例、只读行情数据；只读行情未配置时必须显示“未配置、不会联网、不会读取真实行情”。
- 安全锁：实盘交易关闭、Paper 启用、Broker 只读、ExecutionTarget 未启用。
- 本次运行配置：账户、数据源、策略、交易品种、手续费、滑点、运行模式。
- 配置检查：数据源、策略、解析器、券商、运行时、诊断。

配置中心的配置只属于本地操作台会话，不是业务事实源，不落库，不改变交易、仓位、资金或会计状态。

### 研究

展示 backtest / research-only 结果：

- 回测状态。
- 策略。
- 品种。
- 订单。
- 成交。
- 持仓。
- 已实现 / 未实现 PnL。
- 权益曲线摘要。
- 指标：`total_return`、`max_equity`、`min_equity`。

这些结果只用于研究观测，不是 OMS、Trade、Position、Accounting 或真实账户事实源。

### 组合

展示 research portfolio：

- cash。
- equity。
- market value。
- positions table。
- symbol contributions。
- position weights。
- cash weight。
- allocation。

### 纸面运行

展示 Paper research runtime：

- `PaperResearchRuntime` status。
- `PaperSession` lifecycle：run / pause / stop。
- paper orders。
- paper fills。
- paper positions。
- paper portfolio。
- `PaperConsistencyReport`。

页面只提供预演按钮。Paper 写入按钮保持禁用占位，不写本地账本。

### 行情数据

展示行情源与 resolver 状态：

- 数据源。
- 运行状态。
- 是否已启动。
- 是否已配置。
- 连接状态。
- 配置状态。
- 当前数据源。
- 最近行情。
- 最近 K 线。
- 更新时间。
- 解析器来源。
- 阻断原因。
- 支持品种：`ao`、`rb`、`ag`、`cu`。
- 每个 symbol 的最近行情状态。
- 诊断信息。

数据源选择：

- `static_fixture`：允许本地 preview / dry-run。
- `real_market_data`：未配置时固定 `BLOCKED`，不生成命令，不访问网络；显式配置后只读读取行情，仍不提交订单。

行情数据页面可以显示本地真实行情只读运行时：

- 启动按钮只调用本地 `MarketDataRuntime.start()`。
- 停止按钮只调用本地 `MarketDataRuntime.stop()`。
- 单次刷新按钮只调用本地 `MarketDataRuntime.poll_once(symbols)`。

这些按钮只控制行情读取运行时，不生成 typed command，不进入 dry-run /
apply 路径，不触发交易链路。

默认页面仍是安全关闭状态：

- 未启动。
- 未配置。
- 不会联网。
- 不会调用 AkShare。

只有运行时显式配置 `enabled=True` 且用户触发启动或单次刷新后，才允许读取
AkShare。读取结果只保存在内存快照中，用于页面展示：

- 最近报价。
- 最近 K 线摘要。
- 最近更新时间。
- 数据源。
- 错误诊断。
- 每个 symbol 状态。

Phase N 的 `real_market_data` 是真实行情只读运行时，不是 Broker，不是
CTP，不是 SimNow，不是实盘，不下单，不写数据库，不启用
`ExecutionTarget.PAPER` / `ExecutionTarget.SIM` / `ExecutionTarget.LIVE`。

### 系统诊断

只读展示：

- resolver diagnostics。
- market data diagnostics。
- AkShare 可用性。
- 配置状态。
- 网络调用是否已发生。
- 最近错误。
- 每个 symbol 状态。
- research diagnostics。
- paper diagnostics。
- safety checks。
- local checks。

Diagnostics 不运行 migration，不修复数据库，不启用 Broker / LIVE，也不启动网络服务。

## 当前实现说明

本地操作台 V2 复用现有操作台的会话状态预演摘要，但会话状态只用于当前 UI 会话展示，不作为持久化历史、结果或配置。

所有页面采用宽布局和紧凑卡片 / 表格，目标是在 1280x720 截图下尽量完整显示主要状态。页面文案统一中文，内部 Python 标识符、类名、函数名、枚举名和第三方名称除外。
