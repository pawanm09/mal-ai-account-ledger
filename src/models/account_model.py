from dataclasses import dataclass
from decimal import Decimal

from src.models.money import parse_amount
from src.models.validation import validate_text


@dataclass(frozen=True)
class AccountModel:
    """Immutable account identity and currency-normalized opening balance."""

    account_id: str
    currency: str
    opening_balance: Decimal

    def __post_init__(self) -> None:
        validate_text(self.account_id, "Account ID")
        opening = parse_amount(self.opening_balance, self.currency)
        # Normalization happens only during construction, before journaling.
        object.__setattr__(self, "opening_balance", opening)
