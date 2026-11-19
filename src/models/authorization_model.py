from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class AuthorizationModel:
    """Derived authorization snapshot, rebuilt from input and decision records.

    Amount is the original request, not the remaining hold. Only APPROVED
    authorizations reserve that amount; DECLINED and SETTLED reserve nothing.
    """

    authorization_id: str
    amount: Decimal
    status: str
