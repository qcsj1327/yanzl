from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from futures_mvp.modules.operator_console.config_assembly import ConsoleDryRunConfig
from futures_mvp.modules.operator_console.dry_run_wiring import (
    PaperDryRunWiring,
    SimDryRunWiring,
    create_paper_config_dry_run_provider,
    create_paper_dry_run_provider,
    create_sim_config_dry_run_provider,
    create_sim_dry_run_provider,
)
from futures_mvp.modules.paper_trading.job import PaperJobResult, PaperJobStatus
from futures_mvp.modules.paper_trading.session import (
    PaperSessionConfig,
    PaperSessionResult,
    PaperSessionStatus,
)
from futures_mvp.modules.sim_trading.job import SimJobResult, SimJobStatus
from futures_mvp.modules.sim_trading.session import (
    SimSessionConfig,
    SimSessionResult,
    SimSessionStatus,
)

TRADING_DAY = date(2026, 6, 11)


@dataclass(frozen=True)
class FakeCommand:
    execution_target: str = "MOCK"


class FakePaperSession:
    calls = 0
    configs: list[PaperSessionConfig] = []

    def __init__(self, **kwargs: object) -> None:
        self._config = kwargs["config"]

    def run(self) -> PaperSessionResult:
        FakePaperSession.calls += 1
        assert isinstance(self._config, PaperSessionConfig)
        FakePaperSession.configs.append(self._config)
        return PaperSessionResult(
            session_name=self._config.session_name,
            status=PaperSessionStatus.DRY_RUN_COMPLETED,
            job_results=(
                PaperJobResult(
                    job_name="paper-runtime",
                    status=PaperJobStatus.DRY_RUN,
                    processed_command_count=1,
                ),
            ),
            processed_commands=1,
        )


class FakeSimSession:
    calls = 0
    configs: list[SimSessionConfig] = []

    def __init__(self, **kwargs: object) -> None:
        self._config = kwargs["config"]

    def run(self) -> SimSessionResult:
        FakeSimSession.calls += 1
        assert isinstance(self._config, SimSessionConfig)
        FakeSimSession.configs.append(self._config)
        return SimSessionResult(
            session_name=self._config.session_name,
            status=SimSessionStatus.DRY_RUN_COMPLETED,
            job_results=(
                SimJobResult(
                    job_name="sim-runtime",
                    status=SimJobStatus.DRY_RUN,
                    processed_command_count=1,
                ),
            ),
            processed_commands=1,
        )


def test_paper_dry_run_provider_uses_local_session_path_with_safe_config() -> None:
    FakePaperSession.calls = 0
    FakePaperSession.configs = []

    result = create_paper_dry_run_provider(
        PaperDryRunWiring(
            config=_paper_config(),
            job_factory=_paper_job_factory,
            commands=(FakeCommand(),),  # type: ignore[arg-type]
            session_factory=FakePaperSession,
        )
    )()

    assert FakePaperSession.calls == 1
    assert FakePaperSession.configs[0].dry_run is True
    assert FakePaperSession.configs[0].apply_confirmed is False
    assert result.session_status == "DRY_RUN_COMPLETED"
    assert result.job_status == "DRY_RUN"
    assert result.run_status == "DRY_RUN"
    assert result.db_delta == 0
    assert result.target == "MOCK only"


def test_sim_dry_run_provider_uses_local_session_path_with_safe_config() -> None:
    FakeSimSession.calls = 0
    FakeSimSession.configs = []

    result = create_sim_dry_run_provider(
        SimDryRunWiring(
            config=_sim_config(),
            job_factory=_sim_job_factory,
            commands=(FakeCommand(),),  # type: ignore[arg-type]
            session_factory=FakeSimSession,
        )
    )()

    assert FakeSimSession.calls == 1
    assert FakeSimSession.configs[0].dry_run is True
    assert FakeSimSession.configs[0].apply_confirmed is False
    assert result.session_status == "DRY_RUN_COMPLETED"
    assert result.job_status == "DRY_RUN"
    assert result.run_status == "DRY_RUN"
    assert result.db_delta == 0
    assert result.target == "MOCK only"


def test_missing_config_or_provider_is_blocked_before_session_run() -> None:
    FakePaperSession.calls = 0

    missing_config = create_paper_dry_run_provider(
        PaperDryRunWiring(
            job_factory=_paper_job_factory,
            commands=(FakeCommand(),),  # type: ignore[arg-type]
            session_factory=FakePaperSession,
        )
    )()
    missing_factory = create_paper_dry_run_provider(
        PaperDryRunWiring(
            config=_paper_config(),
            commands=(FakeCommand(),),  # type: ignore[arg-type]
            session_factory=FakePaperSession,
        )
    )()

    assert missing_config.session_status == "BLOCKED"
    assert missing_factory.session_status == "BLOCKED"
    assert FakePaperSession.calls == 0


def test_apply_requested_and_non_mock_target_are_blocked() -> None:
    FakeSimSession.calls = 0

    apply_requested = create_sim_dry_run_provider(
        SimDryRunWiring(
            config=_sim_config(),
            job_factory=_sim_job_factory,
            commands=(FakeCommand(),),  # type: ignore[arg-type]
            session_factory=FakeSimSession,
            apply_requested=True,
        )
    )()
    non_mock_target = create_sim_dry_run_provider(
        SimDryRunWiring(
            config=_sim_config(),
            job_factory=_sim_job_factory,
            commands=(FakeCommand("SIM"),),  # type: ignore[arg-type]
            session_factory=FakeSimSession,
        )
    )()

    assert apply_requested.session_status == "BLOCKED"
    assert non_mock_target.session_status == "BLOCKED"
    assert FakeSimSession.calls == 0


def test_config_provider_blocks_when_runtime_dependencies_are_missing() -> None:
    FakePaperSession.calls = 0

    result = create_paper_config_dry_run_provider(
        _console_config(),
        session_factory=FakePaperSession,
    )()

    assert result.session_status == "BLOCKED"
    assert result.target == "MOCK only"
    assert result.reason == "paper dry-run requires a session job factory"
    assert FakePaperSession.calls == 0


def test_config_provider_uses_typed_ui_config_when_dependencies_are_injected() -> None:
    FakePaperSession.calls = 0
    FakePaperSession.configs = []

    result = create_paper_config_dry_run_provider(
        _console_config(),
        job_factory=_paper_job_factory,
        session_factory=FakePaperSession,
    )()

    assert FakePaperSession.calls == 1
    assert FakePaperSession.configs[0].account_id == "account-1"
    assert FakePaperSession.configs[0].dry_run is True
    assert FakePaperSession.configs[0].apply_confirmed is False
    assert result.session_status == "DRY_RUN_COMPLETED"
    assert result.target == "MOCK only"


def test_invalid_config_provider_blocks_before_session_run() -> None:
    FakeSimSession.calls = 0

    result = create_sim_config_dry_run_provider(
        _console_config(quantity="0"),
        job_factory=_sim_job_factory,
        session_factory=FakeSimSession,
    )()

    assert result.session_status == "BLOCKED"
    assert result.reason == "数量必须大于 0：quantity"
    assert FakeSimSession.calls == 0


def _paper_config() -> PaperSessionConfig:
    return PaperSessionConfig(
        session_name="console-paper-dry-run",
        runtime_id="runtime-1",
        trading_day=TRADING_DAY,
        account_id="account-1",
        dry_run=True,
        apply_confirmed=False,
    )


def _sim_config() -> SimSessionConfig:
    return SimSessionConfig(
        session_name="console-sim-dry-run",
        runtime_id="runtime-1",
        trading_day=TRADING_DAY,
        account_id="account-1",
        dry_run=True,
        apply_confirmed=False,
    )


def _console_config(**overrides: object) -> ConsoleDryRunConfig:
    values: dict[str, object] = {
        "account_id": "account-1",
        "trading_day": "2026-06-12",
        "instrument_id": "au2608",
        "trade_instrument_id": "au2608",
        "symbol": "au",
        "exchange": "SHFE",
        "quantity": "1",
        "price": "500",
        "max_order_size": "1",
        "max_position_size": "1",
        "max_daily_loss": "1000",
        "allowed_instruments": ("au2608",),
    }
    values.update(overrides)
    return ConsoleDryRunConfig(**values)


def _paper_job_factory(*_args: object, **_kwargs: object) -> object:
    raise AssertionError("fake session should own the dry-run result")


def _sim_job_factory(*_args: object, **_kwargs: object) -> object:
    raise AssertionError("fake session should own the dry-run result")
