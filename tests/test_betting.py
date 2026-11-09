"""Epochs and play-money betting: winner derivation, parimutuel settlement.

All money is integer cents of play credits ("演示积分 · 不是真钱").
Settlement is parimutuel with house fee 0; see genesis/betting.py.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from genesis.betting import Bet, place_bet, settle_epoch
from genesis.chain import load_chain_facts, real_testnet_text
from genesis.epoch import (
    CIV_NAMES,
    PLAY_MONEY_NOTE,
    civ_seed,
    derive_winner,
    epoch_id_for,
    run_epoch,
    survival_score,
)

DIGEST_A = "a" * 64
DIGEST_B = "b" * 64


def fake_epoch(winner: int, num_civs: int = 4) -> dict:
    return {
        "epoch_id": epoch_id_for(42, 60, num_civs, 5, 0, 10),
        "winner": winner,
        "civs": [{"id": i, "name": CIV_NAMES[i]} for i in range(num_civs)],
    }


def tiebreak_hash(digest: str, civ_id: int) -> str:
    return hashlib.sha256(f"genesis:epoch-winner:{digest}:{civ_id}".encode("utf-8")).hexdigest()


# --- winner derivation -------------------------------------------------------


def test_derive_winner_highest_score_wins() -> None:
    assert derive_winner([(0, 10), (1, 20), (2, 15)], DIGEST_A) == 1


def test_derive_winner_is_reproducible() -> None:
    scores = [(0, 5_000_000), (1, 5_000_000), (2, 4_000_000)]
    first = derive_winner(scores, DIGEST_A)
    assert derive_winner(scores, DIGEST_A) == first
    assert derive_winner(scores, DIGEST_B) == derive_winner(scores, DIGEST_B)


def test_derive_winner_tiebreak_is_smallest_digest_hash() -> None:
    # Tied top scores: the winner must be the tied civ with the smallest hash.
    tied = [0, 1, 2]
    expected = min(tied, key=lambda civ: tiebreak_hash(DIGEST_A, civ))
    assert derive_winner([(civ, 100) for civ in tied], DIGEST_A) == expected
    # A different digest can break the same tie differently.
    other = min(tied, key=lambda civ: tiebreak_hash(DIGEST_B, civ))
    assert derive_winner([(civ, 100) for civ in tied], DIGEST_B) == other


def test_derive_winner_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        derive_winner([], DIGEST_A)
    with pytest.raises(ValueError):
        derive_winner([(0, 1)], "not-a-digest")
    with pytest.raises(ValueError):
        derive_winner([(0, 1), (0, 2)], DIGEST_A)
    with pytest.raises(ValueError):
        derive_winner([(0, 1.5)], DIGEST_A)


def test_survival_score_population_dominates() -> None:
    # One extra survivor beats any wealth gap below 1,000,000 cents — far
    # above what a 5-resident civilization holds in a 30-90 day epoch
    # (golden epochs: ~145,000 cents of wealth).
    one_alive_rich = survival_score(1, 900_000, 100)
    two_alive_broke = survival_score(2, 0, 0)
    assert two_alive_broke > one_alive_rich
    assert survival_score(3, 100, 50) == 3_000_000 + 100 + 5_000


def test_civ_seed_is_stable_and_distinct() -> None:
    assert civ_seed(42, 0) == 42_000
    assert civ_seed(42, 1) == 42_001
    assert len({civ_seed(42, i) for i in range(4)}) == 4
    assert civ_seed(7, 0) != civ_seed(42, 0)


# --- place_bet ---------------------------------------------------------------


def test_place_bet_appends_and_is_pure() -> None:
    bets: list[Bet] = []
    epoch_id = epoch_id_for(42, 60, 4, 5, 0, 10)
    placed = place_bet(bets, player="alice", civ=0, amount=1000, epoch_id=epoch_id, valid_civs=[0, 1, 2, 3])
    assert bets == []  # the input list is not mutated
    assert placed == [Bet(player="alice", civ=0, amount=1000, epoch_id=epoch_id)]


def test_place_bet_rejects_bad_bets() -> None:
    epoch_id = epoch_id_for(42, 60, 4, 5, 0, 10)
    good = dict(player="alice", civ=0, amount=1000, epoch_id=epoch_id, valid_civs=[0, 1, 2, 3])
    for bad in (
        {**good, "player": ""},
        {**good, "player": "   "},
        {**good, "civ": 9},
        {**good, "civ": 0.5},
        {**good, "amount": 0},
        {**good, "amount": -5},
        {**good, "amount": 10.5},
        {**good, "amount": True},
        {**good, "epoch_id": ""},
    ):
        with pytest.raises(ValueError):
            place_bet([], **bad)


def test_place_bet_rejects_mixed_epochs() -> None:
    epoch_a = epoch_id_for(42, 60, 4, 5, 0, 10)
    epoch_b = epoch_id_for(7, 60, 4, 5, 0, 10)
    bets = place_bet([], player="alice", civ=0, amount=100, epoch_id=epoch_a, valid_civs=[0, 1, 2, 3])
    with pytest.raises(ValueError):
        place_bet(bets, player="bob", civ=1, amount=100, epoch_id=epoch_b, valid_civs=[0, 1, 2, 3])


# --- settle_epoch ------------------------------------------------------------


def _bets(epoch_id: str, *specs: tuple[str, int, int]) -> list[Bet]:
    return [Bet(player=p, civ=c, amount=a, epoch_id=epoch_id) for p, c, a in specs]


def test_settle_parimutuel_exact_math() -> None:
    """Pool 1000, winner stakes 400: winners get stake * 1000 // 400 each."""
    epoch = fake_epoch(winner=1)
    bets = _bets(epoch["epoch_id"], ("alice", 1, 100), ("bob", 1, 300), ("carol", 0, 600))
    result = settle_epoch(epoch, bets)
    assert result["outcome"] == "settled"
    assert result["pool"] == 1000
    assert result["winner_pool"] == 400
    assert result["loser_pool"] == 600
    assert result["house_fee_cents"] == 0
    assert result["rollover_cents"] == 0
    assert result["play_money_note"] == PLAY_MONEY_NOTE
    payouts = {p["player"]: p for p in result["payouts"]}
    assert payouts["alice"]["payout"] == 250  # 100 * 1000 // 400
    assert payouts["bob"]["payout"] == 750  # 300 * 1000 // 400
    assert payouts["carol"]["payout"] == 0
    assert payouts["alice"]["profit"] == 150
    assert payouts["carol"]["profit"] == -600
    assert sum(p["payout"] for p in result["payouts"]) == 1000


def test_settle_remainder_cents_go_to_earliest_winners() -> None:
    """Pool 100, three equal 10-cent winners: 100 // 3 leaves 1 cent (33*3=99).

    The earliest winning bet in placement order gets the leftover cent.
    """
    epoch = fake_epoch(winner=2)
    bets = _bets(epoch["epoch_id"], ("a", 2, 10), ("b", 2, 10), ("c", 2, 10), ("d", 0, 70))
    result = settle_epoch(epoch, bets)
    assert result["pool"] == 100
    assert [p["payout"] for p in result["payouts"]] == [34, 33, 33, 0]
    assert sum(p["payout"] for p in result["payouts"]) == 100


def test_settle_no_bets() -> None:
    result = settle_epoch(fake_epoch(winner=0), [])
    assert result["outcome"] == "no_bets"
    assert result["pool"] == 0
    assert result["payouts"] == []


def test_settle_no_winner_bets_refunds_every_stake() -> None:
    """Policy: nobody backed the winner -> full refund, nothing rolls over."""
    epoch = fake_epoch(winner=3)
    bets = _bets(epoch["epoch_id"], ("alice", 0, 1000), ("bob", 1, 2500))
    result = settle_epoch(epoch, bets)
    assert result["outcome"] == "refunded_no_winner_bets"
    assert result["pool"] == 3500
    assert result["winner_pool"] == 0
    assert result["rollover_cents"] == 0
    assert [(p["player"], p["payout"], p["profit"]) for p in result["payouts"]] == [
        ("alice", 1000, 0),
        ("bob", 2500, 0),
    ]
    assert sum(p["payout"] for p in result["payouts"]) == 3500


def test_settle_rejects_wrong_epoch_or_civ() -> None:
    epoch = fake_epoch(winner=0)
    other = epoch_id_for(7, 60, 4, 5, 0, 10)
    with pytest.raises(ValueError):
        settle_epoch(epoch, _bets(other, ("alice", 0, 100)))
    with pytest.raises(ValueError):
        settle_epoch(epoch, _bets(epoch["epoch_id"], ("alice", 9, 100)))
    with pytest.raises(ValueError):
        settle_epoch({**epoch, "winner": 9}, _bets(epoch["epoch_id"], ("alice", 0, 100)))


# --- full epoch end-to-end -----------------------------------------------------


def test_run_epoch_is_deterministic() -> None:
    first = run_epoch(seed=42, days=30)
    second = run_epoch(seed=42, days=30)
    assert first == second
    assert first["digest"] == second["digest"]
    assert first["winner"] in [civ["id"] for civ in first["civs"]]
    assert first["epoch_id"] == epoch_id_for(42, 30, 4, 5, 0, 10)
    assert first["play_money_note"] == PLAY_MONEY_NOTE
    assert first["currency"] == "play_credits"


def test_run_epoch_scores_and_winner_agree() -> None:
    epoch = run_epoch(seed=7, days=30)
    for civ in epoch["civs"]:
        assert civ["score"] == survival_score(civ["alive"], civ["wealth"], civ["health"])
    best = max(civ["score"] for civ in epoch["civs"])
    assert epoch["civs"][epoch["winner"]]["score"] == best
    assert derive_winner([(c["id"], c["score"]) for c in epoch["civs"]], epoch["digest"]) == epoch["winner"]


def test_run_epoch_rejects_bad_params() -> None:
    for kwargs in (
        {"days": 29},
        {"days": 91},
        {"days": 60.5},
        {"num_civs": 1},
        {"num_civs": 5},
        {"residents_per_civ": 0},
        {"residents_per_civ": 21},
        {"tax_rate_bps": -1},
        {"tax_rate_bps": 10_001},
        {"seed": 10**9 + 1},
        {"max_orders_per_day": 11},
    ):
        with pytest.raises(ValueError):
            run_epoch(**kwargs)


def test_full_epoch_end_to_end_payouts_sum_to_pool() -> None:
    epoch = run_epoch(seed=42, days=30)
    epoch_id = str(epoch["epoch_id"])
    valid = [civ["id"] for civ in epoch["civs"]]
    bets: list[Bet] = []
    for player, civ, amount in (
        ("alice", 0, 1000),
        ("bob", 1, 2500),
        ("carol", 2, 500),
        ("dan", 0, 10_000),
        ("alice", 3, 750),
        ("bob", 2, 3000),
    ):
        bets = place_bet(bets, player=player, civ=civ, amount=amount, epoch_id=epoch_id, valid_civs=valid)
    result = settle_epoch(epoch, bets)
    pool = sum(bet.amount for bet in bets)
    assert result["pool"] == pool
    assert sum(p["payout"] for p in result["payouts"]) == pool
    assert result["outcome"] in ("settled", "refunded_no_winner_bets")
    if result["outcome"] == "settled":
        for payout, bet in zip(result["payouts"], bets):
            if bet.civ == epoch["winner"]:
                assert payout["payout"] >= bet.amount or pool == 0
            else:
                assert payout["payout"] == 0


def test_golden_epochs_file_reproduces() -> None:
    """The golden epochs the JS port is verified against must reproduce here."""
    path = Path(__file__).resolve().parent / "golden_epochs.json"
    goldens = json.loads(path.read_text(encoding="utf-8"))
    assert len(goldens) >= 3
    for golden in goldens:
        replayed = run_epoch(
            seed=golden["epoch"]["seed"],
            days=golden["epoch"]["days"],
            num_civs=golden["epoch"]["num_civs"],
            residents_per_civ=golden["epoch"]["residents_per_civ"],
            tax_rate_bps=golden["epoch"]["tax_rate_bps"],
            max_orders_per_day=golden["epoch"]["max_orders_per_day"],
        )
        assert replayed == golden["epoch"]
        bets = [Bet.from_dict(b) for b in golden["bets"]]
        assert settle_epoch(replayed, bets) == golden["settlement"]


# --- shared chain facts --------------------------------------------------------


def test_chain_facts_are_the_verified_ones() -> None:
    facts = load_chain_facts()
    assert facts["chain"]["id"] == 10143
    assert facts["chain"]["rpc"] == "https://testnet-rpc.monad.xyz"
    assert facts["chain"]["explorer"] == "https://testnet.monadexplorer.com"
    assert facts["contract"]["address"] == "0x0D903C5f9ae82e52aA69D39068EF80B85fAFaBA1"
    assert facts["anchor"]["tx"] == "0xd035cdda274104d6958300f0022562a3cebde1e3f370d49fe2061bcad5fc433f"
    assert facts["first_live_transfer"]["tx"] == (
        "0x4b66b46fba5301e60452ae5d38c5e58e4f636302b7f80425777ef1a4355eae11"
    )
    assert facts["first_live_transfer"]["block"] == 78228932
    assert facts["seed42_100day"] == {"trades": 3867, "units": 3890, "value_credits": 12350.97}


def test_real_testnet_text_claims_no_real_bet() -> None:
    text = real_testnet_text(load_chain_facts())
    assert "0x0D903C5f9ae82e52aA69D39068EF80B85fAFaBA1" in text
    assert "0xd035cdda274104d6958300f0022562a3cebde1e3f370d49fe2061bcad5fc433f" in text
    assert "No real bet has been placed" in text
    assert "cast call" in text
    assert "monad verify" in text
