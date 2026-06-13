# 文档总入口

本文档目录按系统职能分层维护。新增文档必须进入对应职能目录，除本入口外，不得随意在 `docs/` 根目录新增文件。

## 目录索引

- `architecture/PROJECT_STRUCTURE.md`：项目目录和文档分层规则。
- `domain/DOMAIN_FREEZE.md`：当前 Domain 字段冻结契约。
- `oms/OMS_STATE_MACHINE.md`：OMS 状态机契约。
- `oms/OMS_REPOSITORY.md`：OMS Repository / UnitOfWork / Application Service 契约。
- `oms/OMS_TEST_MATRIX.md`：OMS 测试矩阵。
- `risk/README.md`：风控模块文档入口。
- `execution/README.md`：执行与 Mock Exchange 模块文档入口。
- `market_data/INSTRUMENT_RESOLVER_CONTRACT.md`：Instrument Resolver / Market Data Source 合同冻结。
- `position/README.md`：持仓模块文档入口。
- `settlement/README.md`：结算模块文档入口。
- `operations/README.md`：本地开发与运维类文档入口。

## 维护规则

- 文档必须使用中文编写。
- 新模块文档必须进入对应职能目录。
- 不得把未来设计写成当前事实。
- 未经确认不得新增真实交易接口、CTP、SimNow 或 broker adapter 相关目录和流程。
- README 只作为入口索引，不复制大段模块契约。
