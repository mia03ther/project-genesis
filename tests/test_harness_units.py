"""Exact amount parsing and formatting."""

from __future__ import annotations

import pytest

from genesis.harness.units import describe_wei, format_wei, parse_amount


@pytest.mark.parametrize(
    ("text", "wei"),
    [
        ("1 ether", 10**18),
        ("1.5 ether", 15 * 10**17),
        ("0 ether", 0),
        ("10 ether", 10 * 10**18),
        ("21000 wei", 21_000),
        ("2.5 gwei", 2_500_000_000),
        ("0.000000000000000001 ether", 1),
        ("1.50 ETHER", 15 * 10**17),
        ("  3   ether ", 3 * 10**18),
        ("123456789012345678901234567890 wei", 123456789012345678901234567890),
    ],
)
def test_parse_amount(text: str, wei: int) -> None:
    assert parse_amount(text) == wei


@pytest.mark.parametrize(
    "text",
    ["1", "ether", "-1 ether", "+1 ether", "1e18 wei", "1.5 wei", "0.0000000000000000001 ether", "1,5 ether",
     "1 eth", "one ether", "", 5, None, f"{2**256} wei"],
)  # fmt: skip
def test_parse_amount_rejects(text: object) -> None:
    with pytest.raises(ValueError):
        parse_amount(text)


@pytest.mark.parametrize(
    ("wei", "text"),
    [(15 * 10**17, "1.5 ether"), (0, "0 ether"), (1, "0.000000000000000001 ether"), (-(10**18), "-1 ether")],
)
def test_format_wei(wei: int, text: str) -> None:
    assert format_wei(wei) == text


@pytest.mark.parametrize("wei", [0, 1, 21_000, 15 * 10**17, 10**30 + 7])
def test_format_and_parse_round_trip(wei: int) -> None:
    assert parse_amount(format_wei(wei)) == wei


def test_describe_wei() -> None:
    assert describe_wei(15 * 10**17) == "1500000000000000000 wei (1.5 ether)"
