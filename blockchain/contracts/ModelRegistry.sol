// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice Prototype audit registry. Does not verify training or model quality.
contract ModelRegistry {
    address public immutable coordinator;
    mapping(address => bool) public authorized;

    struct ModelRecord {
        bytes32 checkpointSha256;
        bytes32 manifestSha256;
        address publisher;
        uint256 registeredAt;
    }

    // A run identifier plus round identifies one immutable checkpoint record.
    mapping(bytes32 => mapping(uint256 => ModelRecord)) private records;

    event PublisherAuthorization(address indexed publisher, bool allowed);
    event ModelRegistered(bytes32 indexed runId, uint256 indexed round,
        bytes32 checkpointSha256, bytes32 manifestSha256, address publisher);

    constructor() {
        coordinator = msg.sender;
        authorized[msg.sender] = true;
    }

    function setPublisher(address publisher, bool allowed) external {
        require(msg.sender == coordinator, "Coordinator only");
        require(publisher != address(0), "Zero publisher");
        authorized[publisher] = allowed;
        emit PublisherAuthorization(publisher, allowed);
    }

    function registerModel(bytes32 runId, uint256 round,
        bytes32 checkpointSha256, bytes32 manifestSha256) external {
        require(authorized[msg.sender], "Unauthorized publisher");
        require(runId != bytes32(0) && round > 0, "Invalid run or round");
        require(checkpointSha256 != bytes32(0) && manifestSha256 != bytes32(0), "Empty digest");
        require(records[runId][round].publisher == address(0), "Already registered");
        records[runId][round] = ModelRecord(checkpointSha256, manifestSha256, msg.sender, block.timestamp);
        emit ModelRegistered(runId, round, checkpointSha256, manifestSha256, msg.sender);
    }

    function getModel(bytes32 runId, uint256 round) external view returns (ModelRecord memory) {
        require(records[runId][round].publisher != address(0), "Unknown model");
        return records[runId][round];
    }
}
