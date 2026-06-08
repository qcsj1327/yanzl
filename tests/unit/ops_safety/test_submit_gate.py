from __future__ import annotations

from datetime import UTC, datetime

from futures_mvp.modules.ops_safety import (
    LiveGateConfig,
    MigrationReadinessReport,
    OperatorApproval,
    SafetyConfig,
    validate_live_submit_gate,
)


def _migration() -> MigrationReadinessReport:
    return MigrationReadinessReport(
        compatible=True,
        current_revision="0016_stage_n_report_identity_conflict",
        expected_revision="0016_stage_n_report_identity_conflict",
    )


def _approval() -> OperatorApproval:
    return OperatorApproval(
        environment="test",
        account_id="account-1",
        adapter_target="mock",
        allowed_stage="execution_gateway",
        command_surface="SUBMIT_ORDER",
        approved_at=datetime.now(UTC),
        decision_id="decision-1",
    )


def test_live_gate_rejects_without_approval() -> None:
    config = SafetyConfig(
        live_gate=LiveGateConfig(
            broker_enabled=True,
            live_submit_enabled=True,
            explicit_live_flag=True,
            broker_credentials_handle="secret-ref",
        )
    )

    decision = validate_live_submit_gate(
        config=config,
        environment="test",
        account_id="account-1",
        adapter_target="mock",
        stage_name="execution_gateway",
        command_surface="SUBMIT_ORDER",
        approval=None,
        migration=_migration(),
    )

    assert decision.allowed is False
    assert decision.reason == "operator approval is required"


def test_live_gate_rejects_broker_disabled() -> None:
    decision = validate_live_submit_gate(
        config=SafetyConfig(live_gate=LiveGateConfig(explicit_live_flag=True)),
        environment="test",
        account_id="account-1",
        adapter_target="mock",
        stage_name="execution_gateway",
        command_surface="SUBMIT_ORDER",
        approval=_approval(),
        migration=_migration(),
    )

    assert decision.allowed is False
    assert decision.reason == "broker is disabled"


def test_live_gate_rejects_missing_credentials() -> None:
    config = SafetyConfig(
        live_gate=LiveGateConfig(
            broker_enabled=True,
            live_submit_enabled=True,
            explicit_live_flag=True,
        )
    )

    decision = validate_live_submit_gate(
        config=config,
        environment="test",
        account_id="account-1",
        adapter_target="mock",
        stage_name="execution_gateway",
        command_surface="SUBMIT_ORDER",
        approval=_approval(),
        migration=_migration(),
    )

    assert decision.allowed is False
    assert decision.reason == "broker credentials are absent"


def test_live_gate_accepts_only_explicit_approved_config() -> None:
    config = SafetyConfig(
        live_gate=LiveGateConfig(
            broker_enabled=True,
            live_submit_enabled=True,
            explicit_live_flag=True,
            broker_credentials_handle="secret-ref",
        )
    )

    decision = validate_live_submit_gate(
        config=config,
        environment="test",
        account_id="account-1",
        adapter_target="mock",
        stage_name="execution_gateway",
        command_surface="SUBMIT_ORDER",
        approval=_approval(),
        migration=_migration(),
    )

    assert decision.allowed is True


def test_live_gate_rejects_migration_mismatch() -> None:
    config = SafetyConfig(
        live_gate=LiveGateConfig(
            broker_enabled=True,
            live_submit_enabled=True,
            explicit_live_flag=True,
            broker_credentials_handle="secret-ref",
        )
    )

    decision = validate_live_submit_gate(
        config=config,
        environment="test",
        account_id="account-1",
        adapter_target="mock",
        stage_name="execution_gateway",
        command_surface="SUBMIT_ORDER",
        approval=_approval(),
        migration=MigrationReadinessReport(
            compatible=False,
            current_revision="old",
            expected_revision="head",
            reason="db migration revision is incompatible",
        ),
    )

    assert decision.allowed is False
    assert decision.reason == "migration readiness is incompatible"

