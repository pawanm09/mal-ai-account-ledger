from decimal import Decimal
from typing import Iterable

from src.exceptions.invalid_request_exception import InvalidRequestException
from src.models.account_model import AccountModel
from src.models.entry_model import ControlModel, DecisionModel, EntryModel, JournalRecord
from src.models.event_model import EventModel
from src.models.money import total_amounts
from src.models.validation import validate_day


class LedgerDataClient:
    """Single-threaded append-only journal with value-date and sequence queries."""

    def __init__(self, accounts: Iterable[AccountModel]):
        self._accounts = {}
        self._records = []
        for account in accounts:
            if not isinstance(account, AccountModel):
                raise InvalidRequestException("Expected an account record")
            if account.account_id in self._accounts:
                raise InvalidRequestException("Duplicate account ID")
            self._accounts[account.account_id] = account

    @property
    def last_sequence(self) -> int:
        """Return the current journal cutoff; zero means no records yet."""
        return len(self._records)

    def get_accounts(self) -> tuple[AccountModel, ...]:
        """Return accounts in construction order as an immutable snapshot."""
        return tuple(self._accounts.values())

    def get_account(self, account_id: str) -> AccountModel:
        """Look up an account, raising a domain error when it is unknown."""
        if not isinstance(account_id, str) or account_id not in self._accounts:
            raise InvalidRequestException("Unknown account")
        return self._accounts[account_id]

    def _append(self, payload: EventModel | EntryModel | DecisionModel | ControlModel) -> JournalRecord:
        record = JournalRecord(self.last_sequence + 1, payload)
        self._records.append(record)
        return record

    def record_event(self, event: EventModel) -> JournalRecord:
        """Retain an input attempt, even if its business fields are invalid.

        Duplicate input attempts are allowed in the audit. The service will
        reject their financial effects rather than removing those attempts.
        """
        if not isinstance(event, EventModel):
            raise InvalidRequestException("Expected an event record")
        return self._append(event)

    def record_decision(self, decision: DecisionModel) -> JournalRecord:
        """Record an outcome without changing any financial balance."""
        if not isinstance(decision, DecisionModel):
            raise InvalidRequestException("Expected a decision record")
        return self._append(decision)

    def record_control(self, control: ControlModel) -> JournalRecord:
        """Append an explicit closing/finalization boundary."""
        if not isinstance(control, ControlModel):
            raise InvalidRequestException("Expected a control marker")
        return self._append(control)

    def get_controls(self) -> tuple[ControlModel, ...]:
        """Return immutable closing/finalization markers in recording order."""
        return tuple(record.payload for record in self._records
                     if isinstance(record.payload, ControlModel))

    def append_entries(self, entries: Iterable[EntryModel]) -> tuple[JournalRecord, ...]:
        """Validate an entire posting batch before appending any of its entries."""
        entries = tuple(entries)
        for entry in entries:
            if not isinstance(entry, EntryModel):
                raise InvalidRequestException("Expected an entry record")
            account = self.get_account(entry.account_id)
            if account.currency != entry.currency:
                raise InvalidRequestException("Entry currency does not match account")
        return tuple(self._append(entry) for entry in entries)

    def get_records(self, cutoff: int | None = None) -> tuple[JournalRecord, ...]:
        """Return a stable snapshot through an inclusive recording cutoff."""
        if cutoff is None:
            cutoff = self.last_sequence
        if type(cutoff) is not int or not 0 <= cutoff <= self.last_sequence:
            raise InvalidRequestException("Cutoff must be an existing sequence or zero")
        return tuple(self._records[:cutoff])

    def get_events(self, cutoff: int | None = None) -> tuple[JournalRecord, ...]:
        """Return input attempts with their recording sequences."""
        return tuple(record for record in self.get_records(cutoff)
                     if isinstance(record.payload, EventModel))

    def get_decisions(self, cutoff: int | None = None) -> tuple[JournalRecord, ...]:
        """Return non-financial decisions and errors with their sequences."""
        return tuple(record for record in self.get_records(cutoff)
                     if isinstance(record.payload, DecisionModel))

    def get_entries(self, account_id: str, cutoff: int | None = None) -> tuple[JournalRecord, ...]:
        """Return one account's financial postings known at the cutoff."""
        self.get_account(account_id)
        return tuple(record for record in self.get_records(cutoff)
                     if isinstance(record.payload, EntryModel)
                     and record.payload.account_id == account_id)

    def get_balance(self, account_id: str, day: int, cutoff: int | None = None) -> Decimal:
        """Sum the opening balance and known postings effective on or before day."""
        account = self.get_account(account_id)
        validate_day(day)
        amounts = [account.opening_balance]
        for record in self.get_entries(account_id, cutoff):
            if record.payload.value_date <= day:
                amounts.append(record.payload.amount)
        return total_amounts(amounts, account.currency)
