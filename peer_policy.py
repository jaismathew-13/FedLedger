"""Decision and weighting rules for the separately registered architecture run.

These rules are a project extension, not a claim about standard FedProx.
No training, blockchain or IPFS operations are performed by this module.
"""
import math


def decide_update(hospital_id, reviews, hospital_ids):
    """Require non-degradation and above-chance performance at both other peers.

    Each review has reviewer_id, baseline_balanced_accuracy and
    update_balanced_accuracy. Missing, repeated, self or invalid reviews reject.
    """
    expected = set(hospital_ids) - {hospital_id}
    if hospital_id not in hospital_ids or len(set(hospital_ids)) != 3 or len(expected) != 2:
        raise ValueError('Expected three distinct hospital identities including the submitter.')
    if len(reviews) != 2 or {review.get('reviewer_id') for review in reviews} != expected:
        return {'accepted': False, 'reason': 'missing_duplicate_or_invalid_reviewer', 'peer_score': None}
    scores = []
    for review in reviews:
        try:
            baseline = float(review['baseline_balanced_accuracy'])
            score = float(review['update_balanced_accuracy'])
        except (KeyError, TypeError, ValueError):
            return {'accepted': False, 'reason': 'invalid_review_score', 'peer_score': None}
        if not all(math.isfinite(value) and 0 <= value <= 1 for value in (baseline, score)):
            return {'accepted': False, 'reason': 'invalid_review_score', 'peer_score': None}
        scores.append(score)
        if score <= 0.5 or score < baseline:
            return {'accepted': False, 'reason': 'peer_below_chance_or_baseline', 'peer_score': None}
    return {'accepted': True, 'reason': 'both_peers_approve', 'peer_score': math.fsum(scores) / 2}


def aggregation_weights(updates):
    """Return accepted update weights; an empty dict means retain prior global.

    Input records have hospital_id, accepted, sample_count and peer_score.
    Structural/finite tensor checks must happen before these decisions are used.
    """
    masses = {}
    identities = set()
    for update in updates:
        identity = update['hospital_id']
        if identity in identities:
            raise ValueError('Duplicate hospital update in the same round.')
        identities.add(identity)
        if update['accepted'] is not True:
            continue
        count = update['sample_count']
        score = float(update['peer_score'])
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise ValueError('Accepted updates require a positive integer sample count.')
        if not math.isfinite(score) or not 0.5 < score <= 1:
            raise ValueError('Accepted peer score must be finite and above chance.')
        masses[identity] = count * score
    total = math.fsum(masses.values())
    return {identity: mass / total for identity, mass in masses.items()} if masses else {}
