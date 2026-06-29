# 本地操作台 UX V3：新手上手工作流

基线：`phase-i-akshare-historical-sync` 或当前最新 main。

本地操作台 UX V3 面向不懂代码的本地操作者。它不再只是功能展示型控制台，而是从总览开始引导用户完成：选择品种、检查合约解析、检查 AkShare 映射、同步历史行情、检查数据覆盖、进入本地库回测、查看纸面模拟和 Broker 只读对照。

它不是实盘交易控制台，不是 Broker / CTP / SimNow 控制台，不是真实账户入口，也不是数据库编辑器。

## 安全边界

本地操作台 UX V3 固定边界：

- 仅展示本地状态、数据状态和 research-only 结果。
- 仅允许本地模拟和只读查看。
- 不启用 `ExecutionTarget.PAPER`、`ExecutionTarget.SIM` 或 `ExecutionTarget.LIVE`。
- 不连接 Broker、CTP、SimNow、交易所或任何 live / network 交易服务，除非用户在数据中心明确点击历史行情同步且同步服务已配置。
- 不读取或操作真实账户。
- 不写 schema，不执行 Alembic migration。
- 不写 OMS / Trade / Position / Accounting / Margin / Settlement。
- 不持久化操作台历史、结果或配置。
- 数据库写入只允许历史K线同步路径，不写交易事实。

配置中心只管理本地 UI 会话中的配置视图。它可以展示和临时装配本次运行所需配置，但不能修改业务事实，不能写入 OMS、Trade、Position、Accounting、Margin、Settlement，也不能启用任何非 `MOCK` 执行目标。

`read_only_adapter_placeholder` 只作为可见但阻断的数据源占位。选择它时 Console 必须显示 `BLOCKED`，不得生成 command，不得访问网络。

真实行情阶段之后，控制台中的真实行情数据源名称为 `real_market_data`。默认仍未配置，页面必须显示：

- 已阻断。
- 未配置。
- 不会访问网络。
- 不会连接 Broker、CTP、SimNow。
- 不会生成非模拟命令。

## 新手上手流程

1. 打开控制台。
2. 进入数据中心。
3. 选择品种。
4. 检查配置。
5. 同步历史行情。
6. 检查覆盖和质量。
7. 进入回测。
8. 查看纸面模拟和 Broker 只读对照。

## 页面

### 总览

总览是新手首页，展示完整流程：

- 第一步：选择品种。
- 第二步：检查合约解析。
- 第三步：检查 AkShare 映射。
- 第四步：同步历史行情。
- 第五步：检查数据覆盖。
- 第六步：运行本地库回测。
- 第七步：查看纸面模拟 / Broker Shadow。

每一步都显示状态、下一步建议、阻断原因和用户该怎么处理。

### 配置中心

配置中心用用户能理解的问题组织配置：

- 基本配置回答：我是谁、我要跑哪天、我要看哪些品种、我要用什么数据、我要跑什么模式。
- 研究配置回答：用什么策略、用多少数量、手续费多少、滑点多少、当前是否可回测。
- 行情配置回答：当前是静态样例还是真实数据、真实行情是否已配置、是否会联网、是否已有本地历史数据。
- 券商配置回答：只读、影子对照、禁止登录、禁止下单、禁止撤单。
- 安全锁回答：实盘交易关闭、ExecutionTarget 未启用、数据库只写历史K线，不写交易事实。

配置中心的配置只属于本地操作台会话，不是业务事实源，不落库，不改变交易、仓位、资金或会计状态。

### 数据中心

数据中心是历史行情管理中心，详见 [DATA_CENTER.md](DATA_CENTER.md)。

它展示单品种工作流。用户先选择 AO、RB、AG 或 CU，然后只看到当前品种的 AkShare 品种映射、合约解析状态、主力合约、交易合约、交易所、历史行情覆盖、K线数量、最近同步时间、数据质量和是否可回测。

数据中心按钮只允许：

- 检查配置。
- 同步该品种历史行情。
- 检查覆盖。
- 检查数据质量。
- 查看本地库回测入口。
- 查看纸面模拟结果。
- 查看券商只读对照。

数据中心只负责数据、质量、同步、覆盖和管理。它保持在行情数据链路内，不改变 OMS、Position、Accounting，不启用 `ExecutionTarget`，不触发 Broker 动作，不自动后台同步，不自动联网。

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
- 每个品种的最近行情状态。
- 诊断信息。

数据源选择：

- `static_fixture`：允许本地预览。
- `real_market_data`：未配置时固定 `BLOCKED`，不生成命令，不访问网络；显式配置后只读读取行情，仍不提交订单。

行情数据页面可以显示本地真实行情只读运行时：

- “检查行情运行状态”只调用本地行情运行状态检查。
- “停止本地行情查看”只停止本地行情查看。
- “刷新一次行情状态”只刷新一次行情状态。

这些按钮只控制行情读取状态，不生成命令，不进入预演或写入路径，不触发交易链路。

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

Phase H 之后，行情数据页面可以显示历史行情同步控件：

- 品种。
- 交易日。
- 周期。
- 同步历史行情按钮。
- 本地库覆盖情况。
- 最近入库时间。
- bar 数量。
- 数据源。
- 失败原因。

同步按钮只执行历史行情同步：

```text
真实数据源 -> 标准化 -> 本地库
```

按钮不得生成 typed command，不进入 dry-run / apply，不下单，不登录 Broker，
不连接 CTP / SimNow，不启用任何 `ExecutionTarget`。未注入同步服务、交易日
无效、resolver 失败、AkShare 不可用、空数据、标准化失败或数据库不可用时，
页面必须显示 `BLOCKED` 和中文失败原因。

Backtest / Console 后续展示优先读取本地历史行情库。没有本地数据时，必须显示
已阻断，不得在展示或回测路径里自动联网补数。

Phase I 后，配置中心必须展示 AkShare 显式映射：

- 品种。
- AkShare 符号。
- 交易所。
- 是否启用。
- 映射诊断。

当前启用映射为 `ao -> AO0`、`rb -> RB0`、`ag -> AG0`、`cu -> CU0`。未配置
映射或映射禁用时，同步按钮必须显示 `BLOCKED`，且不得访问网络。

历史行情管理展示：

- 写入条数。
- 更新条数。
- 跳过条数。
- 覆盖开始。
- 覆盖结束。
- bar 数量。
- 最近入库时间。
- 数据源。
- 失败原因。

AkShare 当前定位为开发、验证和补数据。RQData 后续定位为高质量历史数据，
CTP MdApi 后续定位为生产实时行情，CTP TraderApi 最后接入。

### 系统诊断

只读展示：

- resolver diagnostics。
- market data diagnostics。
- AkShare 可用性。
- 配置状态。
- 网络调用是否已发生。
- 最近错误。
- 每个品种状态。
- 研究诊断信息。
- 纸面模拟诊断信息。
- 安全检查。
- 本地检查。

诊断信息不运行迁移，不修复数据库，不启用 Broker 或真实交易，也不启动网络服务。

## 当前实现说明

本地操作台 UX V3 复用现有操作台的会话状态预演摘要，但会话状态只用于当前 UI 会话展示，不作为持久化历史、结果或配置。

所有页面采用宽布局和紧凑卡片 / 表格，目标是在 1280x720 截图下尽量完整显示主要状态。页面文案统一中文，内部 Python 标识符、类名、函数名、枚举名和第三方名称除外。
