"""Explicit dependency wiring, following the reference repository's layout."""

from decimal import Decimal

from src.externals.clients.ledger_data_client import LedgerDataClient
from src.models.account_model import AccountModel
from src.services.daily_close_service import DailyCloseService
from src.services.ledger_service import LedgerService


def create_ledger() -> DailyCloseService:
    """Construct an isolated ledger for each replay or test invocation."""
    accounts = (
        AccountModel("ACC-001", "AED", Decimal("0.00")),
        AccountModel("ACC-002", "BHD", Decimal("0.000")),
    )
    ledger_data_client = LedgerDataClient(accounts)
    ledger_service = LedgerService(ledger_data_client)
    return DailyCloseService(ledger_service)
