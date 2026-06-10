from decimal import Decimal

from futures_mvp.domain.models import ExecutionCommand, stable_json_sha256
from futures_mvp.modules.broker_adapter import BrokerCallbackEvidence


class SharedExecutionEvidenceBuilder:
    """Construct deterministic typed execution evidence for local harnesses."""

    def __init__(self, *, namespace: str, adapter_name: str) -> None:
        if not namespace:
            raise ValueError("namespace is required")
        if not adapter_name:
            raise ValueError("adapter_name is required")
        self._namespace = namespace
        self._adapter_name = adapter_name

    def build_acknowledged(
        self,
        command: ExecutionCommand,
        *,
        adapter_order_ref: str,
        sequence: int = 1,
    ) -> BrokerCallbackEvidence:
        self._validate_adapter_order_ref(adapter_order_ref)
        self._validate_sequence(sequence)
        return self._build_evidence(
            command,
            adapter_order_ref=adapter_order_ref,
            report_type="acked",
            sequence=sequence,
            filled_qty=Decimal("0"),
            fill_price=None,
            cumulative_filled_qty=Decimal("0"),
            remaining_qty=command.quantity,
            include_fill_identity=False,
        )

    def build_filled(
        self,
        command: ExecutionCommand,
        *,
        adapter_order_ref: str,
        sequence: int = 1,
        filled_qty: Decimal | None = None,
        fill_price: Decimal | None = None,
        cumulative_filled_qty: Decimal | None = None,
        remaining_qty: Decimal = Decimal("0"),
    ) -> BrokerCallbackEvidence:
        filled = filled_qty or command.quantity
        cumulative = cumulative_filled_qty or command.quantity
        price = fill_price or command.price
        self._validate_fill_report(
            sequence=sequence,
            filled_qty=filled,
            cumulative_filled_qty=cumulative,
            remaining_qty=remaining_qty,
        )
        return self._build_evidence(
            command,
            adapter_order_ref=adapter_order_ref,
            report_type="filled",
            sequence=sequence,
            filled_qty=filled,
            fill_price=price,
            cumulative_filled_qty=cumulative,
            remaining_qty=remaining_qty,
            include_fill_identity=True,
        )

    def build_partially_filled(
        self,
        command: ExecutionCommand,
        *,
        adapter_order_ref: str,
        sequence: int,
        filled_qty: Decimal,
        fill_price: Decimal | None = None,
        cumulative_filled_qty: Decimal,
        remaining_qty: Decimal,
    ) -> BrokerCallbackEvidence:
        self._validate_fill_report(
            sequence=sequence,
            filled_qty=filled_qty,
            cumulative_filled_qty=cumulative_filled_qty,
            remaining_qty=remaining_qty,
        )
        return self._build_evidence(
            command,
            adapter_order_ref=adapter_order_ref,
            report_type="partial_fill",
            sequence=sequence,
            filled_qty=filled_qty,
            fill_price=fill_price or command.price,
            cumulative_filled_qty=cumulative_filled_qty,
            remaining_qty=remaining_qty,
            include_fill_identity=True,
        )

    def build_rejected(
        self,
        command: ExecutionCommand,
        *,
        adapter_order_ref: str,
        sequence: int = 1,
    ) -> BrokerCallbackEvidence:
        self._validate_adapter_order_ref(adapter_order_ref)
        self._validate_sequence(sequence)
        return self._build_evidence(
            command,
            adapter_order_ref=adapter_order_ref,
            report_type="rejected",
            sequence=sequence,
            filled_qty=Decimal("0"),
            fill_price=None,
            cumulative_filled_qty=Decimal("0"),
            remaining_qty=command.quantity,
            include_fill_identity=False,
        )

    def build_fill_report_sequence(
        self,
        command: ExecutionCommand,
        *,
        adapter_order_ref: str,
        fill_quantities: tuple[Decimal, ...],
        fill_prices: tuple[Decimal, ...] | None = None,
        include_acknowledged: bool = True,
    ) -> tuple[BrokerCallbackEvidence, ...]:
        self._validate_adapter_order_ref(adapter_order_ref)
        if not fill_quantities:
            raise ValueError("fill_quantities is required")
        if fill_prices is not None and len(fill_prices) != len(fill_quantities):
            raise ValueError("fill_prices length must match fill_quantities")

        reports: list[BrokerCallbackEvidence] = []
        if include_acknowledged:
            reports.append(
                self.build_acknowledged(command, adapter_order_ref=adapter_order_ref)
            )

        cumulative = Decimal("0")
        for index, quantity in enumerate(fill_quantities, start=1):
            if quantity <= 0:
                raise ValueError("filled_qty must be positive")
            cumulative += quantity
            if cumulative > command.quantity:
                raise ValueError("overfill is forbidden")
            remaining = command.quantity - cumulative
            price = fill_prices[index - 1] if fill_prices is not None else command.price
            if remaining == 0:
                reports.append(
                    self.build_filled(
                        command,
                        adapter_order_ref=adapter_order_ref,
                        sequence=index,
                        filled_qty=quantity,
                        fill_price=price,
                        cumulative_filled_qty=cumulative,
                        remaining_qty=remaining,
                    )
                )
            else:
                reports.append(
                    self.build_partially_filled(
                        command,
                        adapter_order_ref=adapter_order_ref,
                        sequence=index,
                        filled_qty=quantity,
                        fill_price=price,
                        cumulative_filled_qty=cumulative,
                        remaining_qty=remaining,
                    )
                )
        if cumulative != command.quantity:
            raise ValueError("final filled cumulative quantity must equal order quantity")
        return tuple(reports)

    def _build_evidence(
        self,
        command: ExecutionCommand,
        *,
        adapter_order_ref: str,
        report_type: str,
        sequence: int,
        filled_qty: Decimal,
        fill_price: Decimal | None,
        cumulative_filled_qty: Decimal,
        remaining_qty: Decimal,
        include_fill_identity: bool,
    ) -> BrokerCallbackEvidence:
        self._validate_adapter_order_ref(adapter_order_ref)
        self._validate_sequence(sequence)
        if remaining_qty < 0:
            raise ValueError("remaining_qty must be non-negative")
        return BrokerCallbackEvidence(
            adapter_name=self._adapter_name,
            execution_target=command.execution_target,
            command_id=command.command_id,
            order_id=command.order_id,
            client_order_id=command.client_order_id,
            adapter_order_ref=adapter_order_ref,
            exchange_order_id=self._exchange_order_id(command),
            exchange_trade_id=(
                self._exchange_trade_id(command, sequence=sequence)
                if include_fill_identity
                else None
            ),
            fill_id=(
                self._fill_id(command, sequence=sequence)
                if include_fill_identity
                else None
            ),
            report_type=report_type,
            filled_qty=filled_qty,
            fill_price=fill_price,
            cumulative_filled_qty=cumulative_filled_qty,
            remaining_qty=remaining_qty,
            report_ts=command.created_at,
            received_at=command.created_at,
            raw_payload=None,
            raw_report_id=self._raw_report_id(
                command,
                report_type=report_type,
                sequence=sequence,
            ),
        )

    def _exchange_order_id(self, command: ExecutionCommand) -> str:
        return (
            f"{self._namespace}_order_"
            + stable_json_sha256({"command_id": command.command_id})[:40]
        )

    def _exchange_trade_id(self, command: ExecutionCommand, *, sequence: int) -> str:
        return (
            f"{self._namespace}_trade_"
            + stable_json_sha256(
                {"command_id": command.command_id, "sequence": sequence}
            )[:40]
        )

    def _fill_id(self, command: ExecutionCommand, *, sequence: int) -> str:
        return (
            f"{self._namespace}_fill_"
            + stable_json_sha256(
                {"command_id": command.command_id, "sequence": sequence}
            )[:40]
        )

    def _raw_report_id(
        self,
        command: ExecutionCommand,
        *,
        report_type: str,
        sequence: int,
    ) -> str:
        return (
            f"{self._namespace}_raw_"
            + stable_json_sha256(
                {
                    "command_id": command.command_id,
                    "order_id": command.order_id,
                    "policy_report_type": report_type,
                    "sequence": sequence,
                }
            )[:48]
        )

    @staticmethod
    def _validate_adapter_order_ref(adapter_order_ref: str) -> None:
        if not adapter_order_ref:
            raise ValueError("adapter_order_ref is required")

    @staticmethod
    def _validate_sequence(sequence: int) -> None:
        if sequence < 1:
            raise ValueError("sequence must be >= 1")

    def _validate_fill_report(
        self,
        *,
        sequence: int,
        filled_qty: Decimal,
        cumulative_filled_qty: Decimal,
        remaining_qty: Decimal,
    ) -> None:
        self._validate_sequence(sequence)
        if filled_qty <= 0:
            raise ValueError("filled_qty must be positive")
        if cumulative_filled_qty <= 0:
            raise ValueError("cumulative_filled_qty must be positive")
        if remaining_qty < 0:
            raise ValueError("remaining_qty must be non-negative")
