"""Exact conversion between human-readable amounts and integer wei.

Amounts in manifests are strings such as ``"1.5 ether"`` so that authors can
write them naturally and no value is ever squeezed through a float or a 64-bit
integer. Conversion uses integer arithmetic only.
"""

from __future__ import annotations

import re

WEI_PER_UNIT: dict[str, int] = {"wei": 1, "gwei": 10**9, "ether": 10**18}
MAX_UINT256 = 2**256 - 1

_NUMBER = re.compile(r"(\d+)(?:\.(\d+))?")


def parse_amount(text: object) -> int:
    """Convert ``"<number> <unit>"`` to wei, e.g. ``"1.5 ether" -> 1500000000000000000``.

    Units are ``wei``, ``gwei`` and ``ether``. Raises ``ValueError`` for
    negative or malformed amounts, amounts that are not a whole number of wei,
    and amounts that do not fit an unsigned 256-bit integer.
    """
    if not isinstance(text, str):
        raise ValueError(f"amount must be a string such as '1.5 ether', got {text!r}")
    parts = text.split()
    if len(parts) != 2:
        raise ValueError(f"amount {text!r} must look like '<number> <unit>', e.g. '1.5 ether'")
    number, unit = parts[0], parts[1].lower()
    if unit not in WEI_PER_UNIT:
        raise ValueError(f"amount {text!r} has unknown unit {parts[1]!r}; use wei, gwei or ether")
    match = _NUMBER.fullmatch(number)
    if match is None:
        raise ValueError(f"amount {text!r} must be a non-negative decimal number")
    whole, fraction = match.group(1), (match.group(2) or "").rstrip("0")
    scale = WEI_PER_UNIT[unit]
    decimals = len(str(scale)) - 1
    if len(fraction) > decimals:
        raise ValueError(f"amount {text!r} is not a whole number of wei")
    wei = int(whole) * scale + (int(fraction.ljust(decimals, "0")) if fraction else 0)
    if wei > MAX_UINT256:
        raise ValueError(f"amount {text!r} does not fit in 256 bits")
    return wei


def format_wei(wei: int) -> str:
    """Render wei as an exact ether amount, e.g. ``1500000000000000000 -> '1.5 ether'``."""
    sign = "-" if wei < 0 else ""
    whole, fraction = divmod(abs(wei), WEI_PER_UNIT["ether"])
    digits = f".{fraction:018d}".rstrip("0") if fraction else ""
    return f"{sign}{whole}{digits} ether"


def describe_wei(wei: int) -> str:
    """Both forms, for reports: ``'1500000000000000000 wei (1.5 ether)'``."""
    return f"{wei} wei ({format_wei(wei)})"
