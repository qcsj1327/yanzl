from futures_mvp.domain.enums import SignalLifecycleStatus, SignalResultStatus
from futures_mvp.domain.models import SignalLifecycleEvent, TriggerResult


class SignalLifecycleRules:
    @staticmethod
    def can_trigger(latest_event: SignalLifecycleEvent | None) -> TriggerResult | None:
        if latest_event is None:
            return None
        if latest_event.lifecycle_status is SignalLifecycleStatus.EXPIRED:
            return TriggerResult(
                status=SignalResultStatus.EXPIRED,
                signal_id=latest_event.signal_id,
                reason="expired signal cannot trigger",
            )
        if latest_event.lifecycle_status is SignalLifecycleStatus.BLOCKED:
            return TriggerResult(
                status=SignalResultStatus.BLOCKED,
                signal_id=latest_event.signal_id,
                reason="blocked signal cannot trigger",
            )
        if latest_event.lifecycle_status is SignalLifecycleStatus.TRIGGERED:
            return TriggerResult(
                status=SignalResultStatus.DUPLICATE,
                signal_id=latest_event.signal_id,
                reason="already_triggered",
            )
        return None
