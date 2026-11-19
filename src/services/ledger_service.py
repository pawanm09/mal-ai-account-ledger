from src.exceptions.invalid_request_exception import InvalidRequestException
from src.externals.clients.ledger_data_client import LedgerDataClient
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
            if event.kind == "CREDIT":
                entries = self._credit_entries(event)
            elif event.kind == "DEBIT":
                entries = self._debit_entries(event)
            else:
                entries = self._reversal_entries(event)
            self.ledger_data_client.append_entries(entries)
            decision = DecisionModel(event.event_id, event.account_id, "ACCEPTED", "Posting accepted")
        except InvalidRequestException as error:
            decision = DecisionModel(event.event_id, event.account_id, "REJECTED", str(error))
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
        if event.kind not in ("CREDIT", "DEBIT", "REVERSAL"):
            raise InvalidRequestException("Unsupported event kind")
        if event.instalments < 1:
            raise InvalidRequestException("Instalment count must be positive")
        if event.kind != "CREDIT" and event.instalments != 1:
            raise InvalidRequestException("Only credits support instalments")
        if event.authorization_id is not None:
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
