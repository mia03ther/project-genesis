// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title GenesisLedger
/// @notice The on-chain anchor for Project GENESIS: a permanent, public
/// record of a simulated world's state. The simulation itself stays
/// deterministic and off-chain (see `python main.py demo`); anyone can
/// re-run the same seed and check that the digest they compute matches the
/// one anchored here. That is the whole point: the world is reproducible,
/// and the chain is the proof that a particular world existed on a
/// particular day.
///
/// A later anchor for the same day overwrites the earlier one, so the
/// ledger always shows the newest claim for that day; the full history of
/// anchors lives in the `WorldAnchored` events. Nothing here moves money
/// and nothing here is a token.
contract GenesisLedger {
    struct WorldSnapshot {
        bytes32 digest;
        uint32 population;
        uint64 trades;
        uint256 anchoredAt;
        address anchorer;
    }

    /// @notice day => the newest anchored snapshot for that day.
    mapping(uint256 => WorldSnapshot) public snapshots;

    /// @notice The highest day ever anchored.
    uint256 public latestDay;

    /// @notice How many anchors have been recorded in total.
    uint256 public totalAnchors;

    event WorldAnchored(
        address indexed anchorer,
        uint256 indexed day,
        bytes32 digest,
        uint32 population,
        uint64 trades
    );

    /// @notice Anchor one world's state for one day.
    /// @param day The simulated day the digest belongs to.
    /// @param digest The GENESIS state digest for that day (SHA-256, hex).
    /// @param population How many residents were alive that day.
    /// @param trades How many trades had happened by that day.
    function recordWorldDigest(uint256 day, bytes32 digest, uint32 population, uint64 trades)
        external
    {
        snapshots[day] = WorldSnapshot({
            digest: digest,
            population: population,
            trades: trades,
            anchoredAt: block.timestamp,
            anchorer: msg.sender
        });
        if (day > latestDay) {
            latestDay = day;
        }
        totalAnchors += 1;
        emit WorldAnchored(msg.sender, day, digest, population, trades);
    }

    /// @notice The digest anchored for a day, or zero when nothing was anchored.
    function getDigest(uint256 day) external view returns (bytes32) {
        return snapshots[day].digest;
    }
}
