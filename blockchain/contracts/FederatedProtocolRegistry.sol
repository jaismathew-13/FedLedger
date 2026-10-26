// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice Local simulation protocol. Attestations do not prove honest evaluation.
contract FederatedProtocolRegistry {
    address public immutable coordinator = msg.sender;
    struct Run { bool exists; bytes32 policyHash; address[3] hospitals; bool initialized; uint256 latestRound; }
    struct Global { string cid; bytes32 digest; bytes32 evidenceHash; bool exists; }
    struct Update { string cid; bytes32 digest; uint256 samples; bytes32 parentDigest; uint8 reviews; uint8 approvals; bool exists; }
    struct Review { bool submitted; bool approved; uint256 scorePpb; bytes32 evidenceHash; }
    mapping(bytes32 => Run) private runs;
    mapping(bytes32 => mapping(uint256 => Global)) private globals;
    mapping(bytes32 => mapping(uint256 => mapping(uint8 => Update))) private updates;
    mapping(bytes32 => mapping(uint256 => mapping(uint8 => mapping(uint8 => Review)))) private reviews;
    event RunOpened(bytes32 indexed runId, bytes32 policyHash, address[3] hospitals);
    event UpdateSubmitted(bytes32 indexed runId, uint256 indexed round, uint8 indexed hospital, string cid, bytes32 digest, uint256 samples);
    event PeerReviewed(bytes32 indexed runId, uint256 indexed round, uint8 indexed hospital, uint8 reviewer, bool approved, bytes32 evidenceHash);
    event GlobalPublished(bytes32 indexed runId, uint256 indexed round, string cid, bytes32 digest, bytes32 evidenceHash);

    modifier onlyCoordinator() { require(msg.sender == coordinator, "Coordinator only"); _; }

    function openRun(bytes32 runId, bytes32 policyHash, address[3] calldata hospitals) external onlyCoordinator {
        require(runId != 0 && policyHash != 0 && !runs[runId].exists, "Invalid or duplicate run");
        for (uint8 i; i < 3; i++) {
            require(hospitals[i] != address(0) && hospitals[i] != coordinator, "Invalid hospital");
            for (uint8 j; j < i; j++) require(hospitals[i] != hospitals[j], "Duplicate hospital");
        }
        Run storage run = runs[runId];
        run.exists = true; run.policyHash = policyHash; run.hospitals = hospitals;
        emit RunOpened(runId, policyHash, hospitals);
    }

    function submitUpdate(bytes32 runId, uint256 round, uint8 hospital, string calldata cid,
        bytes32 digest, uint256 samples, bytes32 parentDigest) external {
        Run storage run = runs[runId];
        require(run.initialized && round == run.latestRound + 1 && hospital < 3, "Invalid round/hospital");
        require(msg.sender == run.hospitals[hospital], "Wrong hospital signer");
        require(samples > 0 && digest != 0 && bytes(cid).length > 0 && bytes(cid).length <= 128, "Invalid update");
        require(parentDigest == globals[runId][round - 1].digest, "Wrong input global");
        require(!updates[runId][round][hospital].exists, "Duplicate update");
        updates[runId][round][hospital] = Update(cid, digest, samples, parentDigest, 0, 0, true);
        emit UpdateSubmitted(runId, round, hospital, cid, digest, samples);
    }

    // Counts are [TP,FN,TN,FP]. Both models must evaluate the same class totals.
    // Integer cross-products compare balanced accuracy without floating-point rounding.
    function submitReview(bytes32 runId, uint256 round, uint8 hospital, uint8 reviewer,
        bool valid, uint256[4] calldata baseline, uint256[4] calldata candidate, bytes32 evidenceHash) external {
        Run storage run = runs[runId];
        require(run.initialized && round == run.latestRound + 1 && hospital < 3 && reviewer < 3 && hospital != reviewer, "Invalid review");
        require(msg.sender == run.hospitals[reviewer], "Wrong reviewer signer");
        Update storage update = updates[runId][round][hospital];
        require(update.exists && !reviews[runId][round][hospital][reviewer].submitted && evidenceHash != 0, "Missing/duplicate review");
        bool approve; uint256 score;
        if (valid) {
            for (uint8 i; i < 4; i++) require(baseline[i] <= 1e9 && candidate[i] <= 1e9, "Count overflow");
            uint256 positives = baseline[0] + baseline[1];
            uint256 negatives = baseline[2] + baseline[3];
            require(positives > 0 && negatives > 0, "Both classes required");
            require(candidate[0] + candidate[1] == positives && candidate[2] + candidate[3] == negatives, "Different validation populations");
            uint256 numerator = candidate[0] * negatives + candidate[2] * positives;
            uint256 previous = baseline[0] * negatives + baseline[2] * positives;
            approve = numerator > positives * negatives && numerator >= previous;
            score = numerator * 1e9 / (2 * positives * negatives);
        }
        reviews[runId][round][hospital][reviewer] = Review(true, approve, score, evidenceHash);
        update.reviews++; if (approve) update.approvals++;
        emit PeerReviewed(runId, round, hospital, reviewer, approve, evidenceHash);
    }

    function publishGlobal(bytes32 runId, uint256 round, string calldata cid, bytes32 digest,
        bytes32 evidenceHash) external onlyCoordinator {
        Run storage run = runs[runId];
        require(run.exists && !globals[runId][round].exists && digest != 0 && evidenceHash != 0, "Invalid global");
        require(bytes(cid).length > 0 && bytes(cid).length <= 128, "Invalid CID");
        if (!run.initialized) { require(round == 0, "Initial round must be zero"); run.initialized = true; }
        else {
            require(round == run.latestRound + 1, "Wrong global round");
            uint8 accepted;
            for (uint8 i; i < 3; i++) {
                Update storage update = updates[runId][round][i];
                require(update.exists && update.reviews == 2, "Incomplete peer reviews");
                if (update.approvals == 2) accepted++;
            }
            if (accepted == 0) require(digest == globals[runId][round - 1].digest, "All rejected: retain global");
        }
        globals[runId][round] = Global(cid, digest, evidenceHash, true);
        run.latestRound = round;
        emit GlobalPublished(runId, round, cid, digest, evidenceHash);
    }

    function getRun(bytes32 id) external view returns (Run memory) { return runs[id]; }
    function getGlobal(bytes32 id, uint256 round) external view returns (Global memory) { return globals[id][round]; }
    function getUpdate(bytes32 id, uint256 round, uint8 hospital) external view returns (Update memory, bool) {
        Update memory update = updates[id][round][hospital];
        return (update, update.exists && update.reviews == 2 && update.approvals == 2);
    }
    function getReview(bytes32 id, uint256 round, uint8 hospital, uint8 reviewer) external view returns (Review memory) {
        return reviews[id][round][hospital][reviewer];
    }
}
