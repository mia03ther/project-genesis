"""The daily call auction, order validation and settlement."""

from __future__ import annotations

import random

import pytest

from genesis.economy import (
    AuctionResult,
    Order,
    Trade,
    clear_auction,
    next_reference_price,
    settle_trades,
    validate_orders,
)
from genesis.models import InvariantViolation, OrderRequest, Resident, Resource, Side, SimulationConfig
from tests.conftest import make_order

BUY, SELL, FOOD, WOOD = Side.BUY, Side.SELL, Resource.FOOD, Resource.WOOD


def resident(rid: int, cash: int = 10_000, food: int = 10, wood: int = 10, stone: int = 10) -> Resident:
    return Resident(
        id=rid,
        name=f"r{rid}",
        occupation="farmer",  # type: ignore[arg-type]
        skills={},
        cash=cash,
        inventory={Resource.FOOD: food, Resource.WOOD: wood, Resource.STONE: stone},
    )


# --- clearing price ----------------------------------------------------------------


def test_balanced_cross_clears_at_reference_price() -> None:
    orders = [make_order(1, 1, BUY, 5, 110), make_order(2, 2, SELL, 5, 90)]
    result = clear_auction(FOOD, orders, reference_price=100)
    assert result.clearing_price == 100
    assert result.volume == 5
    assert result.trades == (Trade(FOOD, 1, 2, 5, 100),)


def test_excess_demand_pushes_price_up_to_marginal_bid() -> None:
    orders = [make_order(1, 1, BUY, 10, 105), make_order(2, 2, SELL, 5, 90)]
    result = clear_auction(FOOD, orders, reference_price=100)
    assert result.clearing_price == 105
    assert result.volume == 5


def test_price_rises_to_where_demand_meets_supply() -> None:
    orders = [make_order(1, 1, BUY, 5, 110), make_order(2, 2, BUY, 5, 105), make_order(3, 3, SELL, 5, 90)]
    result = clear_auction(FOOD, orders, reference_price=100)
    assert result.clearing_price == 110
    assert [(t.buyer_id, t.quantity) for t in result.trades] == [(1, 5)]


def test_excess_supply_pushes_price_down() -> None:
    orders = [make_order(1, 1, BUY, 5, 110), make_order(2, 2, SELL, 10, 95)]
    result = clear_auction(FOOD, orders, reference_price=100)
    assert result.clearing_price == 95
    assert result.volume == 5


def test_no_trade_when_bids_are_below_asks() -> None:
    orders = [make_order(1, 1, BUY, 5, 90), make_order(2, 2, SELL, 5, 100)]
    result = clear_auction(FOOD, orders, reference_price=95)
    assert result.clearing_price is None
    assert result.volume == 0 and result.trades == ()
    assert (result.best_bid, result.best_ask) == (90, 100)


def test_auction_only_uses_orders_for_its_resource() -> None:
    orders = [make_order(1, 1, BUY, 5, 110, WOOD), make_order(2, 2, SELL, 5, 90)]
    result = clear_auction(FOOD, orders, reference_price=100)
    assert result.volume == 0 and result.demand == 0 and result.supply == 5


def test_price_priority_then_arrival_order() -> None:
    orders = [
        make_order(1, 1, BUY, 3, 100),
        make_order(2, 2, BUY, 3, 120),
        make_order(3, 3, SELL, 3, 80),
    ]
    result = clear_auction(FOOD, orders, reference_price=100)
    assert [t.buyer_id for t in result.trades] == [2]


def test_marginal_level_is_rationed_pro_rata() -> None:
    orders = [
        make_order(1, 1, SELL, 10, 100),
        make_order(2, 2, SELL, 30, 100),
        make_order(3, 3, BUY, 8, 100),
    ]
    result = clear_auction(FOOD, orders, reference_price=100)
    sold = {t.seller_id: t.quantity for t in result.trades}
    assert sold == {1: 2, 2: 6}


def test_pro_rata_rounding_goes_to_earliest_arrivals() -> None:
    orders = [make_order(seq, seq, SELL, 1, 100) for seq in range(1, 6)] + [make_order(9, 9, BUY, 2, 100)]
    result = clear_auction(FOOD, orders, reference_price=100)
    assert sorted(t.seller_id for t in result.trades) == [1, 2]


def _random_book(rng: random.Random) -> list[Order]:
    orders = []
    for seq in range(1, rng.randint(1, 14) + 1):
        side = rng.choice([BUY, SELL])
        orders.append(make_order(seq, seq, side, rng.randint(1, 20), rng.randint(80, 130)))
    return orders


@pytest.mark.parametrize("book_seed", range(300))
def test_random_books_satisfy_auction_properties(book_seed: int) -> None:
    rng = random.Random(book_seed)
    orders = _random_book(rng)
    reference = rng.randint(80, 130)
    result = clear_auction(FOOD, orders, reference)
    bids = [o for o in orders if o.side is BUY]
    asks = [o for o in orders if o.side is SELL]
    by_seq = {o.resident_id: o for o in orders}

    assert result.demand == sum(o.quantity for o in bids)
    assert result.supply == sum(o.quantity for o in asks)
    assert sum(t.quantity for t in result.trades) == result.volume <= min(result.demand, result.supply)
    if result.volume == 0:
        assert result.clearing_price is None
        assert not bids or not asks or max(o.limit_price for o in bids) < min(o.limit_price for o in asks)
        return

    price = result.clearing_price
    assert price is not None
    filled: dict[int, int] = {}
    for trade in result.trades:
        assert trade.price == price  # uniform price
        assert trade.quantity > 0
        assert by_seq[trade.buyer_id].side is BUY and by_seq[trade.seller_id].side is SELL
        assert by_seq[trade.buyer_id].limit_price >= price  # never above a buyer's limit
        assert by_seq[trade.seller_id].limit_price <= price  # never below a seller's limit
        filled[trade.buyer_id] = filled.get(trade.buyer_id, 0) + trade.quantity
        filled[trade.seller_id] = filled.get(trade.seller_id, 0) + trade.quantity
    for order_id, quantity in filled.items():
        assert quantity <= by_seq[order_id].quantity  # never over-filled

    # The clearing price maximises volume: no integer price trades more.
    def volume_at(p: int) -> int:
        return min(
            sum(o.quantity for o in bids if o.limit_price >= p),
            sum(o.quantity for o in asks if o.limit_price <= p),
        )

    assert result.volume == max(volume_at(p) for p in range(70, 141))


# --- reference price -----------------------------------------------------------


def _result(
    clearing: int | None, demand: int, supply: int, bid: int | None, ask: int | None
) -> AuctionResult:
    return AuctionResult(FOOD, clearing, demand, supply, 0 if clearing is None else 1, (), bid, ask)


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (_result(120, 5, 5, 130, 90), 120),  # traded: the clearing price
        (_result(None, 5, 0, 110, None), 105),  # buyers only: up 5 %
        (_result(None, 0, 5, None, 90), 95),  # sellers only: down 5 %
        (_result(None, 5, 5, 90, 120), 105),  # no cross: toward the spread midpoint, capped
        (_result(None, 0, 0, None, None), 100),  # empty market: unchanged
    ],
)
def test_next_reference_price(result: AuctionResult, expected: int) -> None:
    assert next_reference_price(100, result, SimulationConfig()) == expected


def test_reference_price_moves_at_least_one_cent_and_stays_in_bounds() -> None:
    config = SimulationConfig()
    assert next_reference_price(3, _result(None, 5, 0, 5, None), config) == 4
    assert next_reference_price(1, _result(None, 0, 5, None, 1), config) == config.min_price


# --- validation and escrow --------------------------------------------------------


def _validate(
    r: Resident, *requests: object, config: SimulationConfig | None = None
) -> tuple[list[Order], list[str]]:
    accepted, rejected = validate_orders([(r, list(requests))], config or SimulationConfig())
    return accepted, [rejection.reason for rejection in rejected]


def test_valid_orders_are_accepted_in_sequence() -> None:
    accepted, reasons = _validate(
        resident(1), OrderRequest(BUY, WOOD, 2, 100), OrderRequest(SELL, FOOD, 3, 90)
    )
    assert reasons == []
    assert [o.seq for o in accepted] == [1, 2]


def test_buy_orders_reserve_cash_across_orders() -> None:
    accepted, reasons = _validate(
        resident(1, cash=1_000), OrderRequest(BUY, FOOD, 5, 150), OrderRequest(BUY, WOOD, 2, 150)
    )
    assert len(accepted) == 1 and reasons == ["insufficient_funds"]


def test_sell_orders_reserve_inventory_across_orders() -> None:
    accepted, reasons = _validate(
        resident(1, food=5), OrderRequest(SELL, FOOD, 4, 90), OrderRequest(SELL, FOOD, 2, 95)
    )
    assert len(accepted) == 1 and reasons == ["insufficient_inventory"]


@pytest.mark.parametrize(
    ("request_", "reason"),
    [
        (OrderRequest(BUY, FOOD, 0, 100), "invalid_quantity"),
        (OrderRequest(BUY, FOOD, -3, 100), "invalid_quantity"),
        (OrderRequest(BUY, FOOD, 2.5, 100), "invalid_quantity"),  # type: ignore[arg-type]
        (OrderRequest(BUY, FOOD, True, 100), "invalid_quantity"),  # type: ignore[arg-type]
        (OrderRequest(BUY, FOOD, 1_001, 1), "invalid_quantity"),
        (OrderRequest(BUY, FOOD, 1, 0), "invalid_price"),
        (OrderRequest(BUY, FOOD, 1, 1_000_001), "invalid_price"),
        (OrderRequest("borrow", FOOD, 1, 100), "malformed_order"),  # type: ignore[arg-type]
        (OrderRequest(BUY, "gold", 1, 100), "malformed_order"),  # type: ignore[arg-type]
        ({"side": "buy"}, "malformed_order"),
        (None, "malformed_order"),
    ],
)
def test_invalid_orders_are_rejected(request_: object, reason: str) -> None:
    accepted, reasons = _validate(resident(1), request_)
    assert accepted == [] and reasons == [reason]


def test_string_sides_and_resources_are_accepted() -> None:
    accepted, reasons = _validate(resident(1), OrderRequest("buy", "food", 1, 100))  # type: ignore[arg-type]
    assert reasons == [] and accepted[0].side is BUY and accepted[0].resource is FOOD


def test_buying_and_selling_one_resource_on_one_day_is_rejected() -> None:
    accepted, reasons = _validate(
        resident(1), OrderRequest(BUY, FOOD, 1, 100), OrderRequest(SELL, FOOD, 1, 100)
    )
    assert len(accepted) == 1 and reasons == ["self_cross"]


def test_orders_past_the_daily_limit_are_rejected_once() -> None:
    config = SimulationConfig(max_orders_per_day=2)
    requests = [OrderRequest(BUY, FOOD, 1, 100) for _ in range(5)]
    accepted, reasons = _validate(resident(1), *requests, config=config)
    assert len(accepted) == 2 and reasons == ["too_many_orders"]


def test_non_sequence_order_list_is_rejected() -> None:
    accepted, rejected = validate_orders([(resident(1), None)], SimulationConfig())
    assert accepted == [] and [r.reason for r in rejected] == ["malformed_order"]


# --- settlement -----------------------------------------------------------------


def test_settlement_moves_goods_and_money_without_creating_either() -> None:
    buyer, seller = resident(1, cash=1_000, food=0), resident(2, cash=0, food=10)
    settle_trades([Trade(FOOD, 1, 2, 4, 150)], {1: buyer, 2: seller})
    assert (buyer.cash, buyer.inventory[FOOD]) == (400, 4)
    assert (seller.cash, seller.inventory[FOOD]) == (600, 6)
    assert buyer.cash + seller.cash == 1_000
    assert buyer.inventory[FOOD] + seller.inventory[FOOD] == 10


@pytest.mark.parametrize(
    "trade",
    [
        Trade(FOOD, 1, 2, 10, 200),  # buyer cannot pay
        Trade(FOOD, 1, 2, 11, 1),  # seller cannot deliver
        Trade(FOOD, 1, 1, 1, 1),  # self-trade
        Trade(FOOD, 1, 2, 0, 100),  # empty trade
    ],
)
def test_settlement_refuses_impossible_trades(trade: Trade) -> None:
    residents = {1: resident(1, cash=1_000), 2: resident(2, food=10)}
    with pytest.raises(InvariantViolation):
        settle_trades([trade], residents)
