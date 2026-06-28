# Phase P Broker Adapter Shadow Mode

## 范围

Phase P 只交付 Broker ReadOnly Adapter 与 Shadow Compare。该阶段不启用
`ExecutionTarget.PAPER` / `ExecutionTarget.SIM` / `ExecutionTarget.LIVE`，不新增真实下单、
撤单、自动登录、自动重试或任何资金修改能力。

## 组件

- `BrokerAccountSnapshot`：只读账户快照。
- `BrokerPositionSnapshot`：只读持仓快照。
- `BrokerOrderSnapshot`：只读订单快照。
- `BrokerTradeSnapshot`：只读成交快照。
- `BrokerReadOnlyAdapter`：只读取快照源，并把网络、Broker 错误、登录失败、账户不存在
  统一折叠为 `BLOCKED`。
- `DifferenceReport`：Shadow Compare 输出，链路为 Research -> Paper -> Broker Snapshot
  -> Compare。
- Operator Console Broker 页面：展示账户、持仓、订单、成交、Shadow Compare 与
  Difference Report。
- Broker Diagnostics：展示只读适配器、快照、比较、安全边界状态。

## 安全边界

- Read Only：Broker 快照只用于诊断和差异比对。
- Fail Closed：网络错误、Broker 错误、登录失败、账户不存在、缺少配置都会返回
  `BLOCKED`。
- 不自动重试。
- 不自动登录。
- 不提供报单接口。
- 不提供撤单接口。
- 不写数据库。
- 不修改 OMS 状态。
- 不修改 Position Ledger。
- 不修改 Accounting。
- 不修改 Settlement。

## 架构影响

Broker ReadOnly Adapter 位于 broker_adapter 边界内，不导入 OMS、Position、Accounting、
Settlement 或数据库模块。Shadow Compare 位于独立 `shadow` 模块，只消费 Paper research
输出和 Broker snapshot，输出差异报告，不反向写入任何业务事实源。

Operator Console 仅新增展示页和诊断区，不改变 Paper/SIM/LIVE enablement 策略。当前目标仍为
`MOCK only`。
