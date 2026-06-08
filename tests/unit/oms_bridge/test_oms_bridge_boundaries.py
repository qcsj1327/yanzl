from pathlib import Path


def _bridge_source() -> str:
    module_dir = Path("src/futures_mvp/modules/oms_bridge")
    return "\n".join(path.read_text() for path in module_dir.glob("*.py"))


def test_oms_bridge_has_no_forbidden_imports_or_runtime_calls() -> None:
    source = _bridge_source()

    for forbidden in [
        "modules.execution",
        "modules.risk",
        "RiskEngine",
        "FeatureSnapshot",
        "Broker",
        "Accounting",
        "submit(",
        "apply_order_event",
        "apply_risk_result",
    ]:
        assert forbidden not in source


def test_oms_bridge_does_not_define_repository_or_migration() -> None:
    source = _bridge_source()

    assert "OMSBridgeEventRepository" not in source
    assert "OMSBridgeAuditRepository" not in source
    assert "oms_bridge_events" not in source
    assert not list(Path("alembic/versions").glob("*oms_bridge*"))
