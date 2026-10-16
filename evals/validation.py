"""Small shared numeric contracts for offline research and compute inputs."""

import math


def count(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be a nonboolean integer >= {minimum}")
    return value


def finite_real(value, name, *, minimum=None, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite nonboolean real number")
    try:
        finite = math.isfinite(value)
    except OverflowError as exc:
        raise ValueError(f"{name} cannot be represented as a finite real number") from exc
    if not finite or (minimum is not None and value < minimum) or (positive and value <= 0):
        raise ValueError(f"{name} outside finite numeric contract")
    return value


def duration(tokens, rate, name):
    """Reject overflow in derived service time even when the rate itself is finite."""
    try:
        seconds = tokens / rate
    except OverflowError as exc:
        raise ValueError(f"{name} duration overflow") from exc
    return finite_real(seconds, name, minimum=0)
