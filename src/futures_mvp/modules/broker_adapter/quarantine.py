from dataclasses import dataclass


@dataclass(frozen=True)
class QuarantinedBrokerCallback:
    reason: str
    evidence: object


class InMemoryUnresolvedBrokerCallbackQuarantine:
    """Test-only unresolved callback quarantine; not a business ledger."""

    def __init__(self) -> None:
        self._items: list[QuarantinedBrokerCallback] = []

    def append(self, evidence: object, *, reason: str) -> QuarantinedBrokerCallback:
        item = QuarantinedBrokerCallback(reason=reason, evidence=evidence)
        self._items.append(item)
        return item

    def list_items(self) -> list[QuarantinedBrokerCallback]:
        return list(self._items)

    def clear(self) -> None:
        self._items.clear()
