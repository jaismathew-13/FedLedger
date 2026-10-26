// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
interface IHospitalMembership {
    function memberships(address owner) external view returns(bytes32, bool, uint256);
}
/// @notice Delegated local training keys, explicitly authorized by the hospital owner.
contract ClientAuthorization {
    address public immutable administrator = msg.sender;
    IHospitalMembership public immutable directory;
    mapping(address => address) public delegates;
    mapping(address => bytes32) public consentHashes;
    event DelegateAuthorized(address indexed owner, address indexed delegate, bytes32 consentHash);
    constructor(address membershipDirectory) { directory = IHospitalMembership(membershipDirectory); }
    function authorize(address owner, address delegate, bytes32 consentHash) external {
        require(msg.sender == administrator && delegate != address(0), "Unauthorized");
        (, bool approved,) = directory.memberships(owner);
        require(approved && consentHash != 0, "Owner not approved");
        delegates[owner] = delegate;
        consentHashes[owner] = consentHash;
        emit DelegateAuthorized(owner, delegate, consentHash);
    }
    function eligible(address owner, address delegate) external view returns(bool) {
        (, bool approved,) = directory.memberships(owner);
        return approved && delegates[owner] == delegate;
    }
}
