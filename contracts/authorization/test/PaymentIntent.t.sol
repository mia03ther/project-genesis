// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {PaymentIntent} from "../src/PaymentIntent.sol";
import {PaymentIntent as Exercise} from "../exercise/PaymentIntent.sol";

contract PaymentIntentTest {
    PaymentIntent private guard = new PaymentIntent();

    function testAuthorizedRequest() public view {
        require(guard.matches(address(uint160(0x0b0b)), 1.5 ether, 31337));
    }

    function testLookalikeRecipientIsRefused() public view {
        require(!guard.matches(address(uint160(0x0f0b0b)), 1.5 ether, 31337));
    }

    function testWrongAmountIsRefused() public view {
        require(!guard.matches(address(uint160(0x0b0b)), 1 ether, 31337));
    }

    function testWrongChainIsRefused() public view {
        require(!guard.matches(address(uint160(0x0b0b)), 1.5 ether, 1));
    }

    function testStarterDemonstratesMissingCheck() public {
        Exercise starter = new Exercise();
        require(starter.matches(address(uint160(0x0f0b0b)), 1.5 ether, 31337));
    }

    function testFuzzOtherRecipientsAreRefused(address recipient) public view {
        if (recipient != address(uint160(0x0b0b))) {
            require(!guard.matches(recipient, 1.5 ether, 31337));
        }
    }
}
