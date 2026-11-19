"""Small shared checks for immutable records and historical queries."""

from src.exceptions.invalid_request_exception import InvalidRequestException


def validate_text(value: str, field: str) -> None:
    """Require a nonempty string without changing the supplied identifier."""
    if not isinstance(value, str) or not value.strip():
        raise InvalidRequestException(f"{field} must be a nonempty string")


def validate_day(day: int) -> None:
    """Require an integer day inside the supplied six-day window."""
    if type(day) is not int or not 1 <= day <= 6:
        raise InvalidRequestException("Day must be an integer from 1 through 6")
