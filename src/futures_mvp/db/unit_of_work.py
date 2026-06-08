from collections.abc import Callable
from types import TracebackType

from sqlalchemy.orm import Session

from futures_mvp.db.repositories import (
    SQLAlchemyAccountSnapshotRepository,
    SQLAlchemyExecutionCommandRepository,
    SQLAlchemyExecutionReportRepository,
    SQLAlchemyFeatureSnapshotRepository,
    SQLAlchemyMarginSnapshotRepository,
    SQLAlchemyMarketBarRepository,
    SQLAlchemyMarketTickRepository,
    SQLAlchemyOrderEventRepository,
    SQLAlchemyOrderIntentRepository,
    SQLAlchemyOrderRepository,
    SQLAlchemyPnLSnapshotRepository,
    SQLAlchemyPositionEventRepository,
    SQLAlchemyPositionRepository,
    SQLAlchemySettlementSnapshotRepository,
    SQLAlchemySignalCandidateRepository,
    SQLAlchemySignalEventRepository,
    SQLAlchemyTradeRepository,
    SQLAlchemyTradingRiskResultRepository,
)
from futures_mvp.db.session import SessionLocal

SessionFactory = Callable[[], Session]


class SQLAlchemyUnitOfWork:
    def __init__(
        self,
        session: Session | None = None,
        session_factory: SessionFactory = SessionLocal,
    ) -> None:
        self._provided_session = session
        self._session_factory = session_factory
        self._session: Session | None = None
        self.orders: SQLAlchemyOrderRepository
        self.order_events: SQLAlchemyOrderEventRepository
        self.trades: SQLAlchemyTradeRepository
        self.positions: SQLAlchemyPositionRepository
        self.position_events: SQLAlchemyPositionEventRepository
        self.margin_snapshots: SQLAlchemyMarginSnapshotRepository
        self.pnl_snapshots: SQLAlchemyPnLSnapshotRepository
        self.account_snapshots: SQLAlchemyAccountSnapshotRepository
        self.settlement_snapshots: SQLAlchemySettlementSnapshotRepository
        self.market_ticks: SQLAlchemyMarketTickRepository
        self.market_bars: SQLAlchemyMarketBarRepository
        self.feature_snapshots: SQLAlchemyFeatureSnapshotRepository
        self.signal_candidates: SQLAlchemySignalCandidateRepository
        self.signal_events: SQLAlchemySignalEventRepository
        self.trading_risk_results: SQLAlchemyTradingRiskResultRepository
        self.order_intents: SQLAlchemyOrderIntentRepository
        self.execution_commands: SQLAlchemyExecutionCommandRepository
        self.execution_reports: SQLAlchemyExecutionReportRepository

    def __enter__(self) -> "SQLAlchemyUnitOfWork":
        self._session = self._provided_session or self._session_factory()
        self.orders = SQLAlchemyOrderRepository(self._session)
        self.order_events = SQLAlchemyOrderEventRepository(self._session)
        self.trades = SQLAlchemyTradeRepository(self._session)
        self.positions = SQLAlchemyPositionRepository(self._session)
        self.position_events = SQLAlchemyPositionEventRepository(self._session)
        self.margin_snapshots = SQLAlchemyMarginSnapshotRepository(self._session)
        self.pnl_snapshots = SQLAlchemyPnLSnapshotRepository(self._session)
        self.account_snapshots = SQLAlchemyAccountSnapshotRepository(self._session)
        self.settlement_snapshots = SQLAlchemySettlementSnapshotRepository(self._session)
        self.market_ticks = SQLAlchemyMarketTickRepository(self._session)
        self.market_bars = SQLAlchemyMarketBarRepository(self._session)
        self.feature_snapshots = SQLAlchemyFeatureSnapshotRepository(self._session)
        self.signal_candidates = SQLAlchemySignalCandidateRepository(self._session)
        self.signal_events = SQLAlchemySignalEventRepository(self._session)
        self.trading_risk_results = SQLAlchemyTradingRiskResultRepository(self._session)
        self.order_intents = SQLAlchemyOrderIntentRepository(self._session)
        self.execution_commands = SQLAlchemyExecutionCommandRepository(self._session)
        self.execution_reports = SQLAlchemyExecutionReportRepository(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        del exc, tb
        if self._session is None:
            return None
        if exc_type is not None:
            self.rollback()
        if self._provided_session is None:
            self._session.close()
        return None

    def commit(self) -> None:
        self._require_session().commit()

    def rollback(self) -> None:
        self._require_session().rollback()

    def _require_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("UnitOfWork must be entered before use.")
        return self._session


class SQLAlchemyExecutionReportUnitOfWork:
    def __init__(
        self,
        session: Session | None = None,
        session_factory: SessionFactory = SessionLocal,
    ) -> None:
        self._provided_session = session
        self._session_factory = session_factory
        self._session: Session | None = None
        self.execution_reports: SQLAlchemyExecutionReportRepository

    def __enter__(self) -> "SQLAlchemyExecutionReportUnitOfWork":
        self._session = self._provided_session or self._session_factory()
        self.execution_reports = SQLAlchemyExecutionReportRepository(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        del exc, tb
        if self._session is None:
            return None
        if exc_type is not None:
            self.rollback()
        if self._provided_session is None:
            self._session.close()
        return None

    def commit(self) -> None:
        self._require_session().commit()

    def rollback(self) -> None:
        self._require_session().rollback()

    def _require_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("UnitOfWork must be entered before use.")
        return self._session
