"""Deliberately failing requirement probe: partial capture is not supported."""

from decimal import Decimal

from src.container import create_ledger
from src.models.event_model import EventModel


def test_partial_settlement_preserves_uncaptured_hold():
    """Demonstrate the consequence of treating every settlement as final."""
    daily = create_ledger()
    ledger = daily.ledger_service
    assert daily.process_event(
        EventModel("C", 1, "CREDIT", "ACC-001", "AED", 1, "250.00")
    ).status == "ACCEPTED"
    assert daily.process_event(
        EventModel("A", 1, "AUTHORIZATION", "ACC-001", "AED", 1,
                   "200.00", authorization_id="Partial-Capture")
    ).status == "APPROVED"
    assert daily.process_event(
        EventModel("S", 2, "SETTLEMENT", "ACC-001", "AED", 2,
                   "100.00", authorization_id="Partial-Capture")
    ).status == "SETTLED"
    assert daily.ledger_data_client.get_balance("ACC-001", 2) == Decimal("150.00")

    # INTENTIONAL FAILURE against our design, not an assertion from the brief:
    # A partial-capture contract would retain 200 - 100 = 100 of reserved funds.
    # Our chosen contract treats settlement as final and releases all 200, so
    # get_active_holds returns 0.00 and another authorization may spend all 150.
    # Supporting partial capture requires an explicit partial/final distinction,
    # cumulative captured amounts, a remaining-hold projection, and rules for
    # subsequent captures and cancellation. Changing only this assertion would
    # hide the limitation. This is intentionally neither skipped nor xfailed.
    assert ledger.get_active_holds("ACC-001") == Decimal("100.00")
