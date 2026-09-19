"""Decimal-only arithmetic and conservative exchange increments (UD-15)."""

from decimal import Context, Decimal, localcontext

CONTEXT = Context(prec=34)
ZERO = Decimal("0")
ONE = Decimal("1")


def D(value: str | int | Decimal) -> Decimal:
    if isinstance(value, (float, bool)) or not isinstance(value, (str, int, Decimal)):
        raise TypeError("Financial values must be Decimal, integer or decimal text")
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError("Non-finite financial value")
    return result


def require_decimal(value: Decimal, *, positive=False, nonnegative=False) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise TypeError("Finite Decimal required")
    if (positive and value <= 0) or (nonnegative and value < 0):
        raise ValueError("Financial value outside its domain")


def quantize_step(value: Decimal, step: Decimal, *, up: bool = False) -> Decimal:
    require_decimal(value)
    require_decimal(step, positive=True)
    # Integer ratios avoid a rounded division crossing a step boundary.
    a, b = value.as_integer_ratio()
    c, d = step.as_integer_ratio()
    numerator, denominator = a * d, b * c
    units = -((-numerator) // denominator) if up else numerator // denominator
    with localcontext(CONTEXT):
        result = Decimal(units) * step
    if (up and result < value) or (not up and result > value):
        raise ArithmeticError("34-digit context cannot represent conservative rounding")
    return result


def median(values: list[Decimal]) -> Decimal:
    if not values:
        raise ValueError("Median requires observations")
    for x in values:
        require_decimal(x)
    ordered = sorted(values)
    n = len(ordered)
    with localcontext(CONTEXT):
        return ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2


def nearest_rank(values: list[Decimal], percentile: Decimal) -> Decimal:
    require_decimal(percentile, positive=True)
    if not values or percentile > 1:
        raise ValueError("Invalid quantile")
    for x in values:
        require_decimal(x)
    a, b = percentile.as_integer_ratio()
    rank = -((-a * len(values)) // b)
    return sorted(values)[rank - 1]


def population_std(values: list[Decimal]) -> Decimal:
    if not values:
        raise ValueError("Standard deviation requires observations")
    for x in values:
        require_decimal(x)
    with localcontext(CONTEXT):
        mean = sum(values, ZERO) / len(values)
        return (sum(((x - mean) ** 2 for x in values), ZERO) / len(values)).sqrt()
