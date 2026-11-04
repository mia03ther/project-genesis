// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

// GENESIS lesson: complete the missing recipient check.
// Practice only in Remix VM. This contract never transfers funds.
// This starter is intentionally incomplete; it is NOT a safe validator.
contract PaymentIntent {
    address public constant APPROVED_RECIPIENT = address(uint160(0x0b0b));
    uint256 public constant APPROVED_VALUE = 1.5 ether;
    uint256 public constant APPROVED_CHAIN_ID = 31337;

    function matches(address recipient, uint256 amount, uint256 chainId)
        public pure returns (bool)
    {
        // TODO: also compare recipient with APPROVED_RECIPIENT.
        return amount == APPROVED_VALUE && chainId == APPROVED_CHAIN_ID;
    }
}
