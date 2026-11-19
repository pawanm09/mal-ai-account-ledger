"""Exact currency arithmetic, independent of the caller's decimal context."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from typing import Iterable

from src.exceptions.invalid_request_exception import InvalidRequestException


def currency_quantum(currency: str) -> Decimal:
    """Return the smallest supported currency unit; reject unknown currencies."""
    if currency == "AED":
        return Decimal("0.01")
    if currency == "BHD":
        return Decimal("0.001")
    raise InvalidRequestException("Unsupported currency")


def _decimal(value: str | Decimal) -> Decimal:
    if not isinstance(value, (str, Decimal)):
        raise InvalidRequestException("Amounts must be decimal strings or Decimal values")
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise InvalidRequestException("Invalid decimal amount") from error
    if not amount.is_finite():
        raise InvalidRequestException("Amount must be finite")
    return amount


def round_amount(value: str | Decimal, currency: str) -> Decimal:
    """Round a calculated amount to currency precision using ROUND_HALF_UP."""
    quantum = currency_quantum(currency)
    amount = _decimal(value)
    scale = -quantum.as_tuple().exponent
    with localcontext() as context:
        # Integer digits + fractional digits + one possible rounding carry.
        context.prec = max(1, amount.adjusted() + 1) + scale + 1
        rounded = amount.quantize(quantum, rounding=ROUND_HALF_UP)
    return rounded.copy_abs() if rounded.is_zero() else rounded


def parse_amount(value: str | Decimal, currency: str) -> Decimal:
    """Store exact minor-unit amounts; reject nonzero excess fractional digits."""
    amount = _decimal(value)
    rounded = round_amount(amount, currency)
    if amount != rounded:
        raise InvalidRequestException("Amount has nonzero digits below currency precision")
    return rounded


def transaction_amount(value: str | Decimal, currency: str) -> Decimal:
    """Validate a strictly positive transaction amount without silently rounding."""
    amount = parse_amount(value, currency)
    if amount <= 0:
        raise InvalidRequestException("Transaction amount must be positive")
    return amount


def total_amounts(values: Iterable[Decimal], currency: str) -> Decimal:
    """Sum stored amounts exactly, allowing enough digits for the entire total."""
    amounts = tuple(parse_amount(value, currency) for value in values)
    zero = parse_amount("0", currency)
    integer_digits = max((amount.adjusted() + 1 for amount in amounts), default=1)
    scale = -zero.as_tuple().exponent
    with localcontext() as context:
        # Summing n amounts needs at most len(str(n)) extra integer digits.
        context.prec = max(1, integer_digits) + scale + len(str(len(amounts)))
        return parse_amount(sum(amounts, zero), currency)


def format_amount(value: str | Decimal, currency: str) -> str:
    """Format a validated amount with its currency and fixed decimal places."""
    return f"{currency} {parse_amount(value, currency):f}"


def split_amount(value: str | Decimal, currency: str, count: int) -> tuple[Decimal, ...]:
    """Split a positive total into positive minor-unit amounts, largest first."""
    amount = transaction_amount(value, currency)
    if type(count) is not int or count < 1:
        raise InvalidRequestException("Instalment count must be a positive integer")
    scale = -currency_quantum(currency).as_tuple().exponent
    units = int(format(amount, "f").replace(".", ""))
    if count > units:
        raise InvalidRequestException("Each instalment must contain at least one minor unit")
    base, remainder = divmod(units, count)
    parts = []
    for index in range(count):
        part_units = base + (1 if index < remainder else 0)
        whole, fraction = divmod(part_units, 10 ** scale)
        parts.append(Decimal(f"{whole}.{fraction:0{scale}d}"))
    return tuple(parts)
