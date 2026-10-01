"""Safe deterministic checks for simple arithmetic claims."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from tradingagents.agents.schemas import ArithmeticOperation


@dataclass(frozen=True)
class ArithmeticCheck:
    computed_result: Decimal | None
    matches_reported: bool | None
    error: str | None = None


def _decimal(value) -> Decimal:
    if isinstance(value, bool):
        raise InvalidOperation
    return Decimal(str(value))


def check_arithmetic(
    operation: ArithmeticOperation | str,
    operands: Iterable[float | int | str],
    reported_result: float | int | str,
) -> ArithmeticCheck:
    """Check one named calculation without evaluating arbitrary expressions."""
    try:
        operation = ArithmeticOperation(operation)
        values = [_decimal(value) for value in operands]
        reported = _decimal(reported_result)

        if operation is ArithmeticOperation.ADD:
            if len(values) < 2:
                raise ValueError("add requires at least two operands")
            computed = sum(values, Decimal(0))
        elif operation is ArithmeticOperation.SUBTRACT:
            if len(values) != 2:
                raise ValueError("subtract requires two operands")
            computed = values[0] - values[1]
        elif operation is ArithmeticOperation.MULTIPLY:
            if len(values) < 2:
                raise ValueError("multiply requires at least two operands")
            computed = Decimal(1)
            for value in values:
                computed *= value
        elif operation in (ArithmeticOperation.DIVIDE, ArithmeticOperation.RATIO):
            if len(values) != 2:
                raise ValueError(f"{operation.value} requires two operands")
            computed = values[0] / values[1]
        elif operation is ArithmeticOperation.PERCENTAGE:
            if len(values) != 2:
                raise ValueError("percentage requires part and whole operands")
            computed = values[0] / values[1] * Decimal(100)
        elif operation is ArithmeticOperation.PERCENTAGE_CHANGE:
            if len(values) != 2:
                raise ValueError("percentage_change requires old and new operands")
            computed = (values[1] - values[0]) / values[0] * Decimal(100)
        else:  # pragma: no cover - enum conversion above keeps this unreachable
            raise ValueError(f"unsupported operation: {operation}")

        tolerance = max(Decimal("0.01"), abs(computed) * Decimal("0.000001"))
        return ArithmeticCheck(computed, abs(computed - reported) <= tolerance)
    except (InvalidOperation, ValueError, ZeroDivisionError) as exc:
        return ArithmeticCheck(None, None, str(exc) or "invalid arithmetic claim")
