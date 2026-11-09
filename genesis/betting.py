"""Play-money betting on epochs: place bets, settle parimutuel, no house.

A bet is ``(player, civ, amount, epoch_id)`` with ``amount`` in integer
cents of play credits — "演示积分 · 不是真钱" (demo points, not real money).
Everything here is pure: no network, no randomness, no stored state.
``place_bet`` returns a new bet list; ``settle_epoch`` returns a new
settlement dict.

Settlement (parimutuel, house takes 0)
--------------------------------------
Let ``pool`` be the sum of all stakes and ``winner_pool`` the sum of stakes
on the winning civilization. Winners split the whole pool in proportion to
their stake: each winning bet pays ``stake * pool // winner_pool``
(integer floor division). The leftover cents from the floor divisions —
always fewer than the number of winning bets — go one cent each to the
earliest winning bets in placement order, so the payouts always sum to
exactly ``pool``. Losers get 0. There is no house fee (``house_fee_cents``
is always 0).

Edge cases (all documented, all tested)
---------------------------------------
- Zero bets: outcome ``"no_bets"``, empty payouts, pool 0.
- Bets exist but nobody bet on the winner: outcome
  ``"refunded_no_winner_bets"`` — every bettor is refunded their full
  stake, nothing rolls over, the house holds no float. (Refund was chosen
  over rollover because a demo game should never hold a player's points
  hostage to a future epoch.)
- Ties for the win cannot reach settlement: the epoch winner is already
  unique by the time ``settle_epoch`` sees it (``derive_winner`` breaks
  score ties by digest hash), so settlement never has to split a win.

Rounding rule (shared with the JS port)
----------------------------------------
Integer cents only; ``//`` is floor division and the remainder cents are
handed out in bet-placement order. The JS port mirrors this with its
``floorDiv`` helper, so Python and JS payouts agree bit-for-bit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from collections.abc import Mapping, Sequence

from genesis.epoch import PLAY_MONEY_CURRENCY, PLAY_MONEY_NOTE
from genesis.models import is_int


@dataclass(frozen=True, slots=True)
class Bet:
    """One play-money bet: ``player`` backs civilization ``civ`` with ``amount`` cents."""

    player: str
    civ: int
    amount: int
    epoch_id: str

    def to_dict(self) -> dict[str, Any]:
        return {"player": self.player, "civ": self.civ, "amount": self.amount, "epoch_id": self.epoch_id}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Bet":
        if not isinstance(data, Mapping):
            raise ValueError("a bet must be an object")
        if set(data) != {"player", "civ", "amount", "epoch_id"}:
            raise ValueError("a bet must have exactly the fields player, civ, amount, epoch_id")
        return cls(
            player=str(data["player"]),
            civ=int(data["civ"]),  # type: ignore[arg-type]
            amount=int(data["amount"]),  # type: ignore[arg-type]
            epoch_id=str(data["epoch_id"]),
        )


def place_bet(
    bets: Sequence[Bet],
    *,
    player: str,
    civ: int,
    amount: int,
    epoch_id: str,
    valid_civs: Sequence[int],
) -> list[Bet]:
    """Return ``bets`` plus one new bet, validating everything.

    Raises ``ValueError`` when the amount is not a positive integer, the
    player or epoch id is empty, the civilization is not in ``valid_civs``,
    or the new bet's epoch differs from the bets already placed.
    """
    if not isinstance(player, str) or not player.strip():
        raise ValueError(f"player must be a non-empty string, got {player!r}")
    if not is_int(civ) or civ not in list(valid_civs):
        raise ValueError(f"civ must be one of {list(valid_civs)}, got {civ!r}")
    if not is_int(amount) or amount <= 0:
        raise ValueError(f"amount must be a positive integer (cents), got {amount!r}")
    if not isinstance(epoch_id, str) or not epoch_id:
        raise ValueError(f"epoch_id must be a non-empty string, got {epoch_id!r}")
    for existing in bets:
        if not isinstance(existing, Bet):
            raise ValueError(f"bets must be Bet objects, got {existing!r}")
        if existing.epoch_id != epoch_id:
            raise ValueError(
                f"cannot mix epochs: existing bets are for {existing.epoch_id!r}, "
                f"new bet is for {epoch_id!r}"
            )
    return [*bets, Bet(player=player, civ=civ, amount=amount, epoch_id=epoch_id)]


def settle_epoch(epoch: Mapping[str, Any], bets: Sequence[Bet]) -> dict[str, Any]:
    """Settle ``bets`` against a finished epoch result (see module docstring).

    ``epoch`` is a :func:`genesis.epoch.run_epoch` result (needs
    ``epoch_id``, ``winner`` and ``civs`` with ``id``). Returns a JSON-ready
    settlement dict; the payouts list is in bet-placement order and always
    sums to exactly the pool.
    """
    epoch_id = epoch["epoch_id"]
    winner = epoch["winner"]
    civ_ids = [civ["id"] for civ in epoch["civs"]]
    if winner not in civ_ids:
        raise ValueError(f"epoch winner {winner!r} is not one of the civilizations {civ_ids!r}")
    for bet in bets:
        if not isinstance(bet, Bet):
            raise ValueError(f"bets must be Bet objects, got {bet!r}")
        if bet.epoch_id != epoch_id:
            raise ValueError(f"bet epoch {bet.epoch_id!r} does not match epoch {epoch_id!r}")
        if bet.civ not in civ_ids:
            raise ValueError(f"bet civ {bet.civ!r} is not one of the civilizations {civ_ids!r}")
        if bet.amount <= 0:
            raise ValueError(f"bet amount must be positive, got {bet.amount!r}")

    pool = sum(bet.amount for bet in bets)
    winner_pool = sum(bet.amount for bet in bets if bet.civ == winner)
    base: dict[str, Any] = {
        "epoch_id": epoch_id,
        "winner": winner,
        "currency": PLAY_MONEY_CURRENCY,
        "play_money_note": PLAY_MONEY_NOTE,
        "house_fee_cents": 0,
        "rollover_cents": 0,
        "pool": pool,
        "winner_pool": winner_pool,
        "loser_pool": pool - winner_pool,
        "payouts": [],
    }
    if not bets:
        return {**base, "outcome": "no_bets"}
    if winner_pool == 0:
        # Nobody backed the winner: refund every stake in full, roll over nothing.
        return {
            **base,
            "outcome": "refunded_no_winner_bets",
            "payouts": [
                {"player": bet.player, "civ": bet.civ, "stake": bet.amount,
                 "payout": bet.amount, "profit": 0}
                for bet in bets
            ],
        }
    payouts: list[dict[str, Any]] = []
    winning_positions = [i for i, bet in enumerate(bets) if bet.civ == winner]
    shares = {i: bets[i].amount * pool // winner_pool for i in winning_positions}
    leftover = pool - sum(shares.values())
    # One leftover cent each to the earliest winning bets, in placement order.
    bonus = {i: 1 for i in winning_positions[:leftover]}
    paid_out = 0
    for i, bet in enumerate(bets):
        if bet.civ == winner:
            payout = shares[i] + bonus.get(i, 0)
            payouts.append(
                {"player": bet.player, "civ": bet.civ, "stake": bet.amount,
                 "payout": payout, "profit": payout - bet.amount}
            )
            paid_out += payout
        else:
            payouts.append(
                {"player": bet.player, "civ": bet.civ, "stake": bet.amount,
                 "payout": 0, "profit": -bet.amount}
            )
    assert paid_out == pool, f"payouts do not sum to the pool (paid {paid_out}, pool {pool})"
    return {**base, "outcome": "settled", "payouts": payouts}
