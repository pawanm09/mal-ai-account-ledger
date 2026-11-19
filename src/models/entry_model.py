from dataclasses import dataclass
from decimal import Decimal

from src.exceptions.invalid_request_exception import InvalidRequestException
from src.models.event_model import EventModel
from src.models.money import parse_amount
from src.models.validation import validate_day, validate_text


@dataclass(frozen=True)
class EntryModel:
    """A signed financial posting; positive credits and negative debits."""

    account_id: str
    currency: str
    amount: Decimal
    value_date: int
    kind: str
    source_event_id: str

    def __post_init__(self) -> None:
        validate_text(self.account_id, "Account ID")
        validate_text(self.kind, "Entry kind")
        validate_text(self.source_event_id, "Source event ID")
        validate_day(self.value_date)
        object.__setattr__(self, "amount", parse_amount(self.amount, self.currency))


@dataclass(frozen=True)
class DecisionModel:
    """A non-financial outcome or error, including for an unknown account."""

    event_id: str
    account_id: str
    status: str
    message: str
    authorization_id: str | None = None

    def __post_init__(self) -> None:
        # Empty IDs may be the reason an input was rejected; retain them.
        for value in (self.event_id, self.account_id, self.message):
            if not isinstance(value, str):
                raise InvalidRequestException("Decision fields must be strings")
        validate_text(self.status, "Decision status")
        if self.authorization_id is not None and not isinstance(self.authorization_id, str):
            raise InvalidRequestException("Authorization ID must be a string")


@dataclass(frozen=True)
class JournalRecord:
    """Storage-assigned sequence and an immutable event, posting, or decision."""

    sequence: int
    payload: EventModel | EntryModel | DecisionModel
