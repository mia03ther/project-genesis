// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

/// @notice Learning-only predicate. No keys, transfers, deposits or external calls.
/// @dev This does NOT authenticate a payer or implement a production payment wallet.
contract PaymentIntent {
    address public constant APPROVED_RECIPIENT = address(uint160(0x0b0b));
    uint256 public constant APPROVED_VALUE = 1.5 ether;
    uint256 public constant APPROVED_CHAIN_ID = 31337;

    function matches(address recipient, uint256 amount, uint256 chainId)
        public pure returns (bool)
    {
        return recipient == APPROVED_RECIPIENT
            && amount == APPROVED_VALUE
            && chainId == APPROVED_CHAIN_ID;
    }
}
