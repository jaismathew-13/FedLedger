// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice Local onboarding directory. Does not modify historical FL membership.
contract HospitalDirectory {
    address public immutable administrator = msg.sender;
    struct Membership { bytes32 organizationHash; bool authorized; uint256 revision; }
    mapping(address => Membership) public memberships;
    event MembershipChanged(address indexed wallet, bytes32 indexed organizationHash,
                            bool authorized, uint256 revision);

    function setMembership(address wallet, bytes32 organizationHash, bool authorized) external {
        require(msg.sender == administrator, "Administrator only");
        require(wallet != address(0) && organizationHash != 0, "Invalid organization");
        Membership storage member = memberships[wallet];
        require(member.organizationHash == 0 || member.organizationHash == organizationHash,
                "Wallet belongs to another organization");
        member.organizationHash = organizationHash;
        member.authorized = authorized;
        member.revision++;
        emit MembershipChanged(wallet, organizationHash, authorized, member.revision);
    }
}
