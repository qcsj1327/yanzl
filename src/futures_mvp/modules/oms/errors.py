from futures_mvp.domain.enums import OrderStatus


class OMSError(Exception):
    """Base error for OMS module failures."""


class InvalidOrderTransition(OMSError):
    def __init__(self, from_status: OrderStatus, to_status: OrderStatus) -> None:
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(
            f"invalid order status transition: {from_status.value} -> {to_status.value}"
        )
