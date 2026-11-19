"""Replay the supplied events and print original, corrected, and final views."""

import sys
from typing import TextIO

from src.container import create_ledger
from src.models.entry_model import ControlModel
from src.models.event_model import EventModel
from src.models.money import format_amount, total_amounts
from src.services.daily_close_service import DailyCloseService


def supplied_events() -> tuple[EventModel, ...]:
    """Return the assessment input in explicit arrival order, including late E10."""
    return (
        EventModel("E1", 1, "CREDIT", "ACC-001", "AED", 1, "1200.00"),
        EventModel("E2", 1, "DEBIT", "ACC-001", "AED", 1, "950.00"),
        EventModel("E3", 2, "AUTHORIZATION", "ACC-001", "AED", 2, "200.00", "Auth-A"),
        EventModel("E4", 3, "CREDIT", "ACC-001", "AED", 3, "400.00"),
        EventModel("E5", 4, "SETTLEMENT", "ACC-001", "AED", 4, "185.00", "Auth-A"),
        EventModel("E6", 4, "SETTLEMENT", "ACC-001", "AED", 4, "180.00", "Auth-Z"),
        EventModel("E7", 5, "DEBIT", "ACC-001", "AED", 2, "620.00"),
        EventModel("E8", 5, "AUTHORIZATION", "ACC-001", "AED", 5, "90.00", "Auth-B"),
        EventModel("E9", 6, "REVERSAL", "ACC-001", "AED", 2, reference_id="E7"),
        EventModel("E10", 5, "CREDIT", "ACC-002", "BHD", 5, "10.000", instalments=3),
    )


def day_errors(daily: DailyCloseService, account_id: str, day: int, cutoff: int) -> str:
    """Describe request errors booked on day and fee errors assessed for day."""
    client = daily.ledger_data_client
    events = {}
    for record in client.get_events(cutoff):
        events.setdefault(record.payload.event_id, record.payload)
    errors = []
    for record in client.get_decisions(cutoff):
        decision = record.payload
        if decision.account_id != account_id:
            continue
        event = events.get(decision.event_id)
        request_error = (decision.status in ("REJECTED", "DECLINED")
                         and event is not None and event.booked_day == day)
        fee_error = decision.status == "FEE_ERROR" and decision.message.startswith(f"Day {day}:")
        if request_error or fee_error:
            errors.append(f"{decision.event_id} {decision.status}: {decision.message} (recorded #{record.sequence})")
    return "; ".join(errors) or "none"


def print_day(daily: DailyCloseService, day: int, cutoff: int, label: str, output: TextIO) -> None:
    """Print value-dated money and as-known authorization state at one cutoff."""
    client = daily.ledger_data_client
    ledger = daily.ledger_service
    print(f"\n{label} | Day {day} | journal cutoff #{cutoff}", file=output)
    for account in client.get_accounts():
        account_id = account.account_id
        currency = account.currency
        balance = client.get_balance(account_id, day, cutoff)
        holds = ledger.get_active_holds(account_id, cutoff)
        available = ledger.get_available_balance(account_id, day, cutoff)
        print(f"  {account_id} | closing ledger {format_amount(balance, currency)}"
              f" | holds {format_amount(holds, currency)}"
              f" | available {format_amount(available, currency)}", file=output)
        fee_descriptions = []
        for record in client.get_entries(account_id, cutoff):
            entry = record.payload
            if entry.kind == "FEE" and entry.value_date == day:
                fee_descriptions.append(f"{format_amount(entry.amount.copy_abs(), currency)}"
                                        f" assessed Day {day}, recorded #{record.sequence}")
        print(f"    Fees assessed this day: {'; '.join(fee_descriptions) or 'none'}", file=output)
        states = [f"{state.authorization_id}={state.status}"
                  for state in ledger.get_authorizations(account_id, cutoff)]
        print(f"    Authorization states at cutoff: {', '.join(states) or 'none'}", file=output)
        print(f"    Errors booked/assessed this day: {day_errors(daily, account_id, day, cutoff)}", file=output)
        accrual = daily.daily_accruals(account_id, cutoff)[day - 1]
        print(f"    Rounded daily interest: {format_amount(accrual, currency)}", file=output)


def print_new_closes(daily: DailyCloseService, after: int, output: TextIO) -> None:
    """Recover original close snapshots from immutable control-record cutoffs."""
    for record in daily.ledger_data_client.get_records():
        if (record.sequence > after and isinstance(record.payload, ControlModel)
                and record.payload.kind == "DAY_CLOSED"):
            print_day(daily, record.payload.day, record.sequence, "ORIGINAL CLOSE", output)


def print_totals(daily: DailyCloseService, output: TextIO) -> None:
    """Print assessed fees and capitalization, separately from closing balances."""
    client = daily.ledger_data_client
    print("\nWINDOW TOTALS", file=output)
    for account in client.get_accounts():
        entries = client.get_entries(account.account_id)
        fees = total_amounts((record.payload.amount.copy_abs() for record in entries
                              if record.payload.kind == "FEE"), account.currency)
        interest = total_amounts((record.payload.amount for record in entries
                                  if record.payload.kind == "INTEREST"), account.currency)
        final_balance = client.get_balance(account.account_id, 6)
        print(f"  {account.account_id} | fees {format_amount(fees, account.currency)}"
              f" | capitalized {format_amount(interest, account.currency)}"
              f" | final {format_amount(final_balance, account.currency)}", file=output)


def run_replay(output: TextIO | None = None) -> DailyCloseService:
    """Replay exactly once on a fresh ledger, print evidence, and return the core."""
    if output is None:
        output = sys.stdout
    daily = create_ledger()
    client = daily.ledger_data_client
    print("SIX-DAY ACCOUNT LEDGER | arrival order E1 through E10", file=output)
    print("Cutoffs are inclusive journal sequences, not event numbers.", file=output)
    print("Balances use value dates; holds/states use the labeled cutoff.", file=output)
    print("Original/correction interest is provisional; final rows use all arrivals.", file=output)
    print("Errors are grouped by booked day (fee errors by assessment day).", file=output)
    for event in supplied_events():
        before = client.last_sequence
        decision = daily.process_event(event)
        print_new_closes(daily, before, output)
        print(f"\nARRIVAL {event.event_id} | booked Day {event.booked_day}"
              f" | value Day {event.value_date} | {event.kind} | {decision.status}"
              f" | {decision.message}", file=output)
        if decision.status in ("ACCEPTED", "SETTLED") and event.value_date <= daily.closed_day:
            for day in range(event.value_date, daily.closed_day + 1):
                print_day(daily, day, client.last_sequence, f"CORRECTION AFTER {event.event_id}", output)
    before = client.last_sequence
    if not daily.finalize():
        raise RuntimeError("Finalization failed; inspect fee-policy errors in the journal")
    print_new_closes(daily, before, output)
    for day in range(1, 7):
        print_day(daily, day, client.last_sequence, "FINAL RESTATED", output)
    print_totals(daily, output)
    return daily


if __name__ == "__main__":
    run_replay()
