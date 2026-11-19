from dataclasses import dataclass

from src.exceptions.invalid_request_exception import InvalidRequestException


@dataclass(frozen=True)
class EventModel:
    """Immutable input attempt; business validation occurs after it is recorded.

    Bad amounts, unknown currencies, and out-of-window days remain representable
    so the service can retain the original input alongside its rejection.
    Only scalar field types are checked here to prevent mutable nested payloads.
    """

    event_id: str
    booked_day: int
    kind: str
    account_id: str
    currency: str
    value_date: int
    amount: str | None = None
    authorization_id: str | None = None
    reference_id: str | None = None
    instalments: int = 1

    def __post_init__(self) -> None:
        for value in (self.event_id, self.kind, self.account_id, self.currency):
            if not isinstance(value, str):
                raise InvalidRequestException("Event identifiers and kind must be strings")
        for value in (self.booked_day, self.value_date, self.instalments):
            if type(value) is not int:
                raise InvalidRequestException("Event days and instalment count must be integers")
        for value in (self.amount, self.authorization_id, self.reference_id):
            if value is not None and not isinstance(value, str):
                raise InvalidRequestException("Optional event fields must be strings")
