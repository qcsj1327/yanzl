import pytest


@pytest.mark.xfail(reason="MockFuturesExchange matching behavior is planned for a later phase.")
@pytest.mark.parametrize(
    "scenario",
    [
        "partial_fill",
        "full_fill",
        "reject_order",
        "cancel_order",
        "cancel_reject",
        "price_limit_reject",
        "submit_timeout",
        "duplicate_report",
        "out_of_order_report",
        "daily_settlement",
        "roll_today_to_yesterday",
    ],
)
def test_mock_exchange_scenario_contracts_pending(scenario: str) -> None:
    raise NotImplementedError(scenario)
