from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

from futures_mvp.modules.market_data.data_center import DataCenterService
from futures_mvp.modules.market_data.ingestion import (
    HistoricalDataIngestionResult,
    HistoricalIngestionStatus,
)


class _Repository:
    def list_coverage(
        self,
        *,
        symbols: tuple[str, ...],
        timeframe: str,
        source: str,
    ) -> tuple[dict[str, object], ...]:
        assert symbols == ("ao", "rb", "ag", "cu")
        assert timeframe == "1m"
        assert source == "real_market_data"
        return (
            {
                "symbol": "ao",
                "coverage_start": date(2024, 1, 1),
                "coverage_end": date(2026, 6, 30),
                "bar_count": 365000,
                "latest_sync": "2026-06-29T10:00:00",
                "source": source,
            },
        )

    def get_quality_summary(
        self,
        *,
        symbol: str,
        timeframe: str,
        source: str,
    ) -> dict[str, object]:
        assert timeframe == "1m"
        assert source == "real_market_data"
        if symbol == "ao":
            return {
                "missing_bars": 0,
                "duplicate_bars": 0,
                "abnormal_bars": 0,
                "gap_count": 0,
                "continuity": "连续",
                "coverage_ratio": "100%",
                "sync_status": "正常",
            }
        return {}


class _IngestionService:
    def ingest_symbol(
        self,
        symbol: str,
        trading_day: date,
        timeframe: str,
        *,
        end_trading_day: date | None = None,
    ) -> HistoricalDataIngestionResult:
        assert symbol == "ao"
        assert trading_day == date(2024, 1, 1)
        assert end_trading_day == date(2026, 6, 30)
        assert timeframe == "1m"
        return HistoricalDataIngestionResult(
            status=HistoricalIngestionStatus.COMPLETED,
            diagnostics=("历史行情同步完成",),
            bars_written=10,
            bars_updated=0,
            bars_skipped=2,
        )


def test_data_center_snapshot_contains_source_mapping_coverage_quality_and_diagnostics() -> None:
    snapshot = DataCenterService(repository=_Repository()).snapshot(timeframe="1m")

    assert snapshot.data_sources[0].name == "AkShare"
    assert snapshot.data_sources[0].status == "未配置"
    assert tuple(row.symbol for row in snapshot.instruments) == ("AO", "RB", "AG", "CU")
    assert snapshot.instruments[0].mapping == "AO0"
    assert snapshot.coverage[0].coverage_start == "2024-01-01"
    assert snapshot.coverage[0].bar_count == 365000
    assert snapshot.quality[0].coverage_ratio == "100%"
    assert snapshot.coverage_chart[0][0] == "AO"
    assert snapshot.diagnostics.repository == "已配置"
    assert snapshot.diagnostics.sync_service == "未配置"


def test_data_center_sync_is_user_triggered_and_reports_chinese_result() -> None:
    result = DataCenterService(
        repository=_Repository(),
        ingestion_service=_IngestionService(),
    ).sync_history(
        symbol="ao",
        start=date(2024, 1, 1),
        end=date(2026, 6, 30),
        timeframe="1m",
    )

    assert result.status == "完成"
    assert result.added == 10
    assert result.updated == 0
    assert result.skipped == 2
    assert result.failed == 0
    assert "历史行情同步完成" in result.diagnostics
    assert "数据中心只管理历史行情、覆盖和质量" in result.diagnostics
    assert "未进入 Broker，未启用 ExecutionTarget" in result.diagnostics


def test_data_center_sync_blocks_when_service_is_missing() -> None:
    result = DataCenterService().sync_history(
        symbol="ao",
        start=date(2024, 1, 1),
        end=date(2026, 6, 30),
        timeframe="1m",
    )

    assert result.status == "已阻断"
    assert result.failed == 1
    assert result.diagnostics == (
        "历史行情同步服务未配置",
        "不会自动联网",
        "未进入 Broker",
        "未进入交易链路",
    )


def test_data_center_service_does_not_enable_trading_or_schema_paths() -> None:
    path = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "futures_mvp"
        / "modules"
        / "market_data"
        / "data_center.py"
    )
    tree = ast.parse(path.read_text(), filename=str(path))
    source = path.read_text()

    assert "alembic" not in source.lower()
    assert "Base.metadata" not in source
    assert "ExecutionTarget.PAPER" not in source
    assert "ExecutionTarget.SIM" not in source
    assert "ExecutionTarget.LIVE" not in source
    for node in ast.walk(tree):
        assert not (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "ExecutionTarget"
        )
