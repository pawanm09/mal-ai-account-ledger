from decimal import Decimal

from src.exceptions.invalid_request_exception import InvalidRequestException
from src.externals.clients.ledger_data_client import LedgerDataClient
from src.models.authorization_model import AuthorizationModel
from src.models.entry_model import DecisionModel, EntryModel
from src.models.event_model import EventModel
from src.models.money import split_amount, total_amounts, transaction_amount
from src.models.validation import validate_day, validate_text


class LedgerService:
    """Validate input attempts and append their financial effects and outcomes."""

    def __init__(self, ledger_data_client: LedgerDataClient):
        self.ledger_data_client = ledger_data_client

    def process_event(self, event: EventModel) -> DecisionModel:
        """Audit an attempt, then accept it completely or record a domain rejection.

        Invalid record types raise before audit; valid EventModel attempts are
        always retained. Unexpected programming errors are not disguised as
        business rejections.
        """
        cutoff = self.ledger_data_client.last_sequence
        self.ledger_data_client.record_event(event)
        try:
            self._validate_event(event, cutoff)
            if event.kind == "AUTHORIZATION":
                decision = self._authorize(event)
            else:
                if event.kind == "CREDIT":
                    entries = self._credit_entries(event)
                elif event.kind == "DEBIT":
                    entries = self._debit_entries(event)
                elif event.kind == "SETTLEMENT":
                    entries = self._settlement_entries(event)
                else:
                    entries = self._reversal_entries(event)
                self.ledger_data_client.append_entries(entries)
                status = "SETTLED" if event.kind == "SETTLEMENT" else "ACCEPTED"
                decision = DecisionModel(event.event_id, event.account_id, status,
                                         "Posting accepted", event.authorization_id)
        except InvalidRequestException as error:
            decision = DecisionModel(event.event_id, event.account_id, "REJECTED",
                                     str(error), event.authorization_id)
        self.ledger_data_client.record_decision(decision)
        return decision

    def _validate_event(self, event: EventModel, cutoff: int) -> None:
        validate_text(event.event_id, "Event ID")
        for record in self.ledger_data_client.get_events(cutoff):
            if record.payload.event_id == event.event_id:
                raise InvalidRequestException("Duplicate event ID")
        validate_day(event.booked_day)
        validate_day(event.value_date)
        if event.value_date > event.booked_day:
            raise InvalidRequestException("Future-value events are unsupported")
        account = self.ledger_data_client.get_account(event.account_id)
        if event.currency != account.currency:
            raise InvalidRequestException("Event currency does not match account")
        if event.kind not in ("CREDIT", "DEBIT", "REVERSAL", "AUTHORIZATION", "SETTLEMENT"):
            raise InvalidRequestException("Unsupported event kind")
        if event.instalments < 1:
            raise InvalidRequestException("Instalment count must be positive")
        if event.kind != "CREDIT" and event.instalments != 1:
            raise InvalidRequestException("Only credits support instalments")
        if event.kind in ("AUTHORIZATION", "SETTLEMENT"):
            validate_text(event.authorization_id, "Authorization ID")
        elif event.authorization_id is not None:
            raise InvalidRequestException("Posting events cannot reference an authorization")
        if event.kind != "REVERSAL" and event.reference_id is not None:
            raise InvalidRequestException("Only reversals support an event reference")

    def _credit_entries(self, event: EventModel) -> tuple[EntryModel, ...]:
        amounts = split_amount(event.amount, event.currency, event.instalments)
        return tuple(EntryModel(event.account_id, event.currency, amount,
                                event.value_date, "CREDIT", event.event_id)
                     for amount in amounts)

    def _debit_entries(self, event: EventModel) -> tuple[EntryModel, ...]:
        amount = transaction_amount(event.amount, event.currency)
        # Debits may overdraw. Availability checks apply to authorizations only.
        return (EntryModel(event.account_id, event.currency, amount.copy_negate(),
                           event.value_date, "DEBIT", event.event_id),)

    def _reversal_entries(self, event: EventModel) -> tuple[EntryModel, ...]:
        validate_text(event.reference_id, "Reference event ID")
        if event.amount is not None:
            raise InvalidRequestException("Reversal amount must be derived from its original event")
        original_entries = []
        for record in self.ledger_data_client.get_entries(event.account_id):
            entry = record.payload
            if entry.reference_event_id == event.reference_id and entry.kind == "REVERSAL":
                raise InvalidRequestException("Event has already been reversed")
            if entry.source_event_id == event.reference_id:
                original_entries.append(entry)
        if not original_entries:
            raise InvalidRequestException("No original postings found for this account")
        for entry in original_entries:
            if entry.kind not in ("CREDIT", "DEBIT"):
                raise InvalidRequestException("Only ordinary credits and debits can be reversed")
            if entry.value_date != event.value_date:
                raise InvalidRequestException("Reversal value date must match the original")
        total = total_amounts((entry.amount for entry in original_entries), event.currency)
        return (EntryModel(event.account_id, event.currency, total.copy_negate(),
                           event.value_date, "REVERSAL", event.event_id, event.reference_id),)

    def get_authorizations(self, account_id: str, cutoff: int | None = None) -> tuple[AuthorizationModel, ...]:
        """Rebuild immutable authorization states known at the journal cutoff.

        Input -> APPROVED or DECLINED; APPROVED -> SETTLED.
        REJECTED attempts never change an existing authorization state.
        """
        account = self.ledger_data_client.get_account(account_id)
        events = {}
        states = {}
        for record in self.ledger_data_client.get_records(cutoff):
            payload = record.payload
            if isinstance(payload, EventModel):
                events.setdefault(payload.event_id, payload)
            elif isinstance(payload, DecisionModel) and payload.account_id == account_id:
                if payload.status in ("APPROVED", "DECLINED"):
                    event = events[payload.event_id]
                    amount = transaction_amount(event.amount, account.currency)
                    states[payload.authorization_id] = AuthorizationModel(
                        payload.authorization_id, amount, payload.status)
                elif payload.status == "SETTLED":
                    original = states[payload.authorization_id]
                    states[payload.authorization_id] = AuthorizationModel(
                        original.authorization_id, original.amount, "SETTLED")
        return tuple(states.values())

    def get_active_holds(self, account_id: str, cutoff: int | None = None) -> Decimal:
        """Sum approved, unsettled holds without changing the ledger balance."""
        account = self.ledger_data_client.get_account(account_id)
        amounts = [state.amount for state in self.get_authorizations(account_id, cutoff)
                   if state.status == "APPROVED"]
        return total_amounts(amounts, account.currency)

    def get_available_balance(self, account_id: str, day: int, cutoff: int | None = None) -> Decimal:
        """Subtract holds known at cutoff from the ledger balance effective on day."""
        account = self.ledger_data_client.get_account(account_id)
        ledger = self.ledger_data_client.get_balance(account_id, day, cutoff)
        holds = self.get_active_holds(account_id, cutoff)
        return total_amounts((ledger, holds.copy_negate()), account.currency)

    def _current_day(self) -> int:
        # Valid booked days advance time even if a request is declined/rejected.
        days = [record.payload.booked_day for record in self.ledger_data_client.get_events()
                if 1 <= record.payload.booked_day <= 6]
        return max(days, default=1)

    def _authorize(self, event: EventModel) -> DecisionModel:
        amount = transaction_amount(event.amount, event.currency)
        for state in self.get_authorizations(event.account_id):
            if state.authorization_id == event.authorization_id:
                raise InvalidRequestException("Authorization ID has already been used for this account")
        available = self.get_available_balance(event.account_id, self._current_day())
        if amount > available:
            return DecisionModel(event.event_id, event.account_id, "DECLINED",
                                 "Insufficient available balance", event.authorization_id)
        return DecisionModel(event.event_id, event.account_id, "APPROVED",
                             "Hold approved", event.authorization_id)

    def _settlement_entries(self, event: EventModel) -> tuple[EntryModel, ...]:
        amount = transaction_amount(event.amount, event.currency)
        for state in self.get_authorizations(event.account_id):
            if state.authorization_id != event.authorization_id:
                continue
            if state.status != "APPROVED":
                raise InvalidRequestException("Settlement requires an approved active authorization")
            if amount > state.amount:
                raise InvalidRequestException("Settlement exceeds the approved hold")
            # Approved funds may settle even if later debits made availability negative.
            return (EntryModel(event.account_id, event.currency, amount.copy_negate(),
                               event.value_date, "SETTLEMENT", event.event_id),)
        raise InvalidRequestException("Unknown authorization for this account")
