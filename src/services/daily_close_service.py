from decimal import Decimal, localcontext

from src.exceptions.invalid_request_exception import InvalidRequestException
from src.models.entry_model import ControlModel, DecisionModel, EntryModel
from src.models.event_model import EventModel
from src.models.money import round_amount, total_amounts
from src.models.validation import validate_day
from src.services.ledger_service import LedgerService


OVERDRAFT_FEE = Decimal("25.00")
DAILY_INTEREST_RATE = Decimal("0.0004")


class DailyCloseService:
    """Coordinate arrivals, historical fee assessment, and final capitalization."""

    def __init__(self, ledger_service: LedgerService):
        self.ledger_service = ledger_service
        self.ledger_data_client = ledger_service.ledger_data_client

    @property
    def closed_day(self) -> int:
        """Return the latest completed day, or zero before the first close."""
        days = [marker.day for marker in self.ledger_data_client.get_controls()
                if marker.kind == "DAY_CLOSED"]
        return max(days, default=0)

    @property
    def finalized(self) -> bool:
        """Report whether the final capitalization boundary has been recorded."""
        return any(marker.kind == "FINALIZED" for marker in self.ledger_data_client.get_controls())

    def process_event(self, event: EventModel) -> DecisionModel:
        """Close preceding days, process one arrival, then reconcile closed days.

        An unsupported fee policy blocks close/finalization, but input processing
        continues so a later correction can restore a nonnegative BHD balance.
        """
        if not isinstance(event, EventModel):
            raise InvalidRequestException("Expected an event record")
        if not self.finalized and 1 < event.booked_day <= 6:
            self.close_through(event.booked_day - 1)
        decision = self.ledger_service.process_event(event)
        if not self.finalized and decision.status in ("ACCEPTED", "SETTLED"):
            self.reconcile()
        return decision

    def close_through(self, day: int) -> bool:
        """Assess days in order; record each completed close at most once."""
        validate_day(day)
        if self.finalized:
            return True
        if not self.reconcile():
            return False
        for closing_day in range(self.closed_day + 1, day + 1):
            if not self._assess_day(closing_day):
                return False
            self.ledger_data_client.record_control(ControlModel("DAY_CLOSED", closing_day))
        return True

    def reconcile(self) -> bool:
        """Reassess all closed days chronologically, retaining previously booked fees."""
        if self.finalized:
            return True
        complete = True
        for day in range(1, self.closed_day + 1):
            if not self._assess_day(day):
                complete = False
        return complete

    def _assess_day(self, day: int) -> bool:
        complete = True
        for account in self.ledger_data_client.get_accounts():
            entries = self.ledger_data_client.get_entries(account.account_id)
            if any(record.payload.kind == "FEE" and record.payload.value_date == day
                   for record in entries):
                continue
            if self.ledger_data_client.get_balance(account.account_id, day) >= 0:
                continue
            if account.currency != "AED":
                self._record_fee_error(account.account_id, day)
                complete = False
                continue
            fee = EntryModel(account.account_id, account.currency, OVERDRAFT_FEE.copy_negate(),
                             day, "FEE", f"FEE:{account.account_id}:{day}")
            self.ledger_data_client.append_entries((fee,))
        return complete

    def _record_fee_error(self, account_id: str, day: int) -> None:
        error = DecisionModel(f"FEE:{account_id}:{day}", account_id, "FEE_ERROR",
                              f"Day {day}: overdraft fee is not configured for this currency")
        if not any(record.payload == error for record in self.ledger_data_client.get_decisions()):
            self.ledger_data_client.record_decision(error)

    def daily_accruals(self, account_id: str, cutoff: int | None = None) -> tuple[Decimal, ...]:
        """Derive six rounded accruals, excluding capitalization from their bases.

        Before finalization these are provisional projections at the given cutoff.
        Earlier snapshots are reproduced by passing their recording sequence.
        """
        account = self.ledger_data_client.get_account(account_id)
        entries = self.ledger_data_client.get_entries(account_id, cutoff)
        accruals = []
        for day in range(1, 7):
            amounts = [account.opening_balance]
            amounts.extend(record.payload.amount for record in entries
                           if record.payload.value_date <= day and record.payload.kind != "INTEREST")
            balance = total_amounts(amounts, account.currency)
            if balance <= 0:
                accruals.append(round_amount("0", account.currency))
                continue
            with localcontext() as context:
                context.prec = len(balance.as_tuple().digits) + len(DAILY_INTEREST_RATE.as_tuple().digits)
                accruals.append(round_amount(balance * DAILY_INTEREST_RATE, account.currency))
        return tuple(accruals)

    def finalize(self) -> bool:
        """Close through Day 6, post each positive accrual total once, and seal the window."""
        if self.finalized:
            return True
        if not self.close_through(6):
            return False
        entries = []
        for account in self.ledger_data_client.get_accounts():
            total = total_amounts(self.daily_accruals(account.account_id), account.currency)
            if total > 0:
                entries.append(EntryModel(account.account_id, account.currency, total, 6,
                                          "INTEREST", f"INTEREST:{account.account_id}:6"))
        self.ledger_data_client.append_entries(entries)
        self.ledger_data_client.record_control(ControlModel("FINALIZED", 6))
        return True
