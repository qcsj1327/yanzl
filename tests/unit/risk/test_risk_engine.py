import ast
import inspect
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

import futures_mvp.modules.risk.engine as risk_engine_module
from futures_mvp.domain.enums import Direction, Offset, RiskDecision
from futures_mvp.domain.models import Signal
from futures_mvp.modules.risk import PureFuturesRiskEngine, RiskConfig, RiskConfigurationError


def test_risk_config_defaults_match_phase_3_1_contract() -> None:
    config = RiskConfig()

    assert config.disabled_instruments == set()
    assert config.max_order_quantity is None
    assert config.max_notional is None
    assert config.contract_multiplier_by_instrument == {}
    assert config.limit_up_by_instrument == {}
    assert config.limit_down_by_instrument == {}
    assert config.is_trading_session_allowed is True
    assert config.allowed_offsets == set(Offset)
    assert config.available_margin is None
    assert config.required_margin is None
    assert config.current_position is None
    assert config.projected_position is None
    assert config.max_position is None


def test_accepted_happy_path_returns_all_pass_with_no_reason() -> None:
    result = PureFuturesRiskEngine().check_order(_signal())

    assert result.decision == RiskDecision.ACCEPTED
    assert result.rule_name == "all_pass"
    assert result.reason is None


@pytest.mark.parametrize(
    ("config", "expected_rule"),
    [
        (RiskConfig(disabled_instruments={"rb2610"}), "disabled_instrument"),
        (RiskConfig(is_trading_session_allowed=False), "trading_session_closed"),
        (RiskConfig(allowed_offsets={Offset.CLOSE}), "offset_not_allowed"),
        (RiskConfig(max_order_quantity=Decimal("1")), "max_order_quantity"),
        (RiskConfig(limit_up_by_instrument={"rb2610": Decimal("3499")}), "price_limit_up"),
        (RiskConfig(limit_down_by_instrument={"rb2610": Decimal("3501")}), "price_limit_down"),
        (
            RiskConfig(
                max_notional=Decimal("34999"),
                contract_multiplier_by_instrument={"rb2610": Decimal("10")},
            ),
            "max_notional",
        ),
        (
            RiskConfig(
                available_margin=Decimal("999"),
                required_margin=Decimal("1000"),
            ),
            "margin_insufficient",
        ),
        (
            RiskConfig(
                projected_position=Decimal("11"),
                max_position=Decimal("10"),
            ),
            "max_position",
        ),
    ],
)
def test_rejection_rules_return_typed_result(config: RiskConfig, expected_rule: str) -> None:
    result = PureFuturesRiskEngine(config).check_order(_signal(quantity=Decimal("2")))

    assert result.decision == RiskDecision.REJECTED
    assert result.rule_name == expected_rule
    assert result.reason is not None


def test_first_rejection_wins() -> None:
    result = PureFuturesRiskEngine(
        RiskConfig(
            disabled_instruments={"rb2610"},
            is_trading_session_allowed=False,
            max_order_quantity=Decimal("1"),
        )
    ).check_order(_signal(quantity=Decimal("2")))

    assert result.decision == RiskDecision.REJECTED
    assert result.rule_name == "disabled_instrument"


def test_empty_allowed_offsets_rejects_all_offsets() -> None:
    result = PureFuturesRiskEngine(RiskConfig(allowed_offsets=set())).check_order(_signal())

    assert result.decision == RiskDecision.REJECTED
    assert result.rule_name == "offset_not_allowed"


def test_missing_limit_keys_skip_price_limit_rules() -> None:
    result = PureFuturesRiskEngine(
        RiskConfig(
            limit_up_by_instrument={"au2610": Decimal("1")},
            limit_down_by_instrument={"au2610": Decimal("999999")},
        )
    ).check_order(_signal())

    assert result.decision == RiskDecision.ACCEPTED


def test_max_notional_disabled_does_not_require_multiplier() -> None:
    result = PureFuturesRiskEngine(
        RiskConfig(contract_multiplier_by_instrument={})
    ).check_order(_signal())

    assert result.decision == RiskDecision.ACCEPTED


def test_max_notional_enabled_missing_multiplier_raises_configuration_error() -> None:
    with pytest.raises(RiskConfigurationError):
        PureFuturesRiskEngine(RiskConfig(max_notional=Decimal("1"))).check_order(_signal())


def test_available_margin_without_required_margin_raises_configuration_error() -> None:
    with pytest.raises(RiskConfigurationError):
        PureFuturesRiskEngine(
            RiskConfig(available_margin=Decimal("1000"))
        ).check_order(_signal())


def test_required_margin_without_available_margin_raises_configuration_error() -> None:
    with pytest.raises(RiskConfigurationError):
        PureFuturesRiskEngine(RiskConfig(required_margin=Decimal("1000"))).check_order(_signal())


def test_projected_position_without_max_position_raises_configuration_error() -> None:
    with pytest.raises(RiskConfigurationError):
        PureFuturesRiskEngine(
            RiskConfig(projected_position=Decimal("10"))
        ).check_order(_signal())


def test_max_position_without_projected_position_raises_configuration_error() -> None:
    with pytest.raises(RiskConfigurationError):
        PureFuturesRiskEngine(RiskConfig(max_position=Decimal("10"))).check_order(_signal())


def test_current_position_is_diagnostic_only() -> None:
    result = PureFuturesRiskEngine(
        RiskConfig(
            current_position=Decimal("1000000"),
            projected_position=Decimal("1"),
            max_position=Decimal("1"),
        )
    ).check_order(_signal())

    assert result.decision == RiskDecision.ACCEPTED


@pytest.mark.parametrize(
    "config",
    [
        RiskConfig(max_order_quantity=Decimal("2")),
        RiskConfig(
            max_notional=Decimal("70000"),
            contract_multiplier_by_instrument={"rb2610": Decimal("10")},
        ),
        RiskConfig(available_margin=Decimal("1000"), required_margin=Decimal("1000")),
        RiskConfig(projected_position=Decimal("1"), max_position=Decimal("1")),
    ],
)
def test_decimal_values_are_accepted(config: RiskConfig) -> None:
    result = PureFuturesRiskEngine(config).check_order(_signal(quantity=Decimal("2")))

    assert result.decision == RiskDecision.ACCEPTED


@pytest.mark.parametrize(
    "config",
    [
        RiskConfig(max_order_quantity=Decimal("2.0")),
        RiskConfig(
            max_notional=Decimal("70000.00"),
            contract_multiplier_by_instrument={"rb2610": Decimal("10.0")},
        ),
    ],
)
def test_decimal_equivalent_values_work_without_string_comparison(config: RiskConfig) -> None:
    result = PureFuturesRiskEngine(config).check_order(
        _signal(limit_price=Decimal("3500.00"), quantity=Decimal("2.00"))
    )

    assert result.decision == RiskDecision.ACCEPTED


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_order_quantity": 1.0},
        {"max_notional": 1.0},
        {"contract_multiplier_by_instrument": {"rb2610": 10.0}},
        {"limit_up_by_instrument": {"rb2610": 3500.0}},
        {"limit_down_by_instrument": {"rb2610": 3500.0}},
        {"available_margin": 1.0},
        {"required_margin": 1.0},
        {"current_position": 1.0},
        {"projected_position": 1.0},
        {"max_position": 1.0},
    ],
)
def test_config_rejects_float_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(RiskConfigurationError):
        RiskConfig(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"disabled_instruments": ["rb2610"]},
        {"disabled_instruments": {1}},
        {"allowed_offsets": ["OPEN"]},
        {"allowed_offsets": {"OPEN"}},
        {"contract_multiplier_by_instrument": [("rb2610", Decimal("10"))]},
        {"contract_multiplier_by_instrument": {1: Decimal("10")}},
        {"limit_up_by_instrument": [("rb2610", Decimal("3500"))]},
        {"limit_up_by_instrument": {1: Decimal("3500")}},
        {"limit_down_by_instrument": [("rb2610", Decimal("3500"))]},
        {"limit_down_by_instrument": {1: Decimal("3500")}},
        {"is_trading_session_allowed": 1},
    ],
)
def test_config_rejects_invalid_container_and_bool_types(kwargs: dict[str, object]) -> None:
    with pytest.raises(RiskConfigurationError):
        RiskConfig(**kwargs)


def test_signal_float_bypass_raises_configuration_error() -> None:
    signal = Signal.model_construct(
        signal_id="sig-1",
        account_id="acct-1",
        instrument_id="rb2610",
        exchange="SHFE",
        direction=Direction.BUY,
        offset=Offset.OPEN,
        limit_price=3500.0,
        quantity=Decimal("1"),
        created_at=datetime.now(UTC),
    )

    with pytest.raises(RiskConfigurationError):
        PureFuturesRiskEngine().check_order(signal)


def test_signal_quantity_float_bypass_raises_configuration_error() -> None:
    signal = Signal.model_construct(
        signal_id="sig-1",
        account_id="acct-1",
        instrument_id="rb2610",
        exchange="SHFE",
        direction=Direction.BUY,
        offset=Offset.OPEN,
        limit_price=Decimal("3500"),
        quantity=1.0,
        created_at=datetime.now(UTC),
    )

    with pytest.raises(RiskConfigurationError):
        PureFuturesRiskEngine().check_order(signal)


def test_check_order_signature_accepts_only_signal_argument() -> None:
    signature = inspect.signature(PureFuturesRiskEngine.check_order)

    assert list(signature.parameters) == ["self", "signal"]


def test_risk_module_does_not_import_forbidden_dependencies() -> None:
    imports = _risk_module_imports()

    forbidden_import_prefixes = [
        "futures_mvp.db",
        "futures_mvp.interfaces.repositories",
        "futures_mvp.db.repositories",
        "futures_mvp.db.unit_of_work",
        "futures_mvp.modules.oms",
        "sqlalchemy",
    ]

    for imported_name in imports:
        assert not any(
            imported_name == prefix or imported_name.startswith(f"{prefix}.")
            for prefix in forbidden_import_prefixes
        )


def test_risk_module_source_has_no_forbidden_trading_or_service_symbols() -> None:
    source = "\n".join(path.read_text() for path in _risk_module_files())

    forbidden_fragments = [
        "OMSService",
        "Repository",
        "UnitOfWork",
        "risk_events",
        "RiskEvent",
        "EMS",
        "MockExchange",
        "PositionManager",
        "MarginEngine",
        "PnLEngine",
        "SettlementEngine",
        "risk_events",
        "RiskEvent",
        "CTP",
        "SimNow",
        "broker",
        "getenv",
        "environ",
        "open(",
        "Redis",
        "requests",
        "httpx",
    ]

    for fragment in forbidden_fragments:
        assert fragment not in source


def test_no_live_production_remote_kms_cloud_files_added() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    forbidden_path_fragments = ("live", "production", "remote", "kms", "cloud")
    skipped_dirs = {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
    }

    paths: list[str] = []
    for path in repo_root.rglob("*"):
        if any(part in skipped_dirs for part in path.relative_to(repo_root).parts):
            continue
        paths.append(path.relative_to(repo_root).as_posix().lower())

    assert not any(
        fragment in path
        for path in paths
        for fragment in forbidden_path_fragments
    )


def test_risk_config_does_not_add_domain_fields() -> None:
    assert "max_order_quantity" not in Signal.model_fields
    assert "available_margin" not in Signal.model_fields
    assert "projected_position" not in Signal.model_fields


def _risk_module_files() -> list[Path]:
    risk_module_dir = Path(risk_engine_module.__file__).parent
    return sorted(path for path in risk_module_dir.glob("*.py") if path.is_file())


def _risk_module_imports() -> set[str]:
    imports: set[str] = set()
    for path in _risk_module_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                imports.add(node.module)
                imports.update(f"{node.module}.{alias.name}" for alias in node.names)
    return imports


def _signal(
    *,
    limit_price: Decimal = Decimal("3500"),
    quantity: Decimal = Decimal("1"),
    offset: Offset = Offset.OPEN,
) -> Signal:
    return Signal(
        signal_id="sig-1",
        account_id="acct-1",
        instrument_id="rb2610",
        exchange="SHFE",
        direction=Direction.BUY,
        offset=offset,
        limit_price=limit_price,
        quantity=quantity,
        created_at=datetime.now(UTC),
    )
