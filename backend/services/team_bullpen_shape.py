"""Backend-authored team bullpen shape reads for board consumers."""


from services.workload_concentration import RECENT_WORKLOAD_WINDOW_DAYS


READ_KEYS = [
    'trustAvailability',
    'cleanOptions',
    'bullpenPressure',
    'workloadConcentration',
    'coverageSafety',
    'depthSafety',
]

TEAM_BULLPEN_PUBLIC_LABELS = {
    'trustAvailability': [
        'Strong Trust Arm Availability',
        'Stable Trust Arm Availability',
        'Thin Trust Arm Availability',
        'Limited Trust Arm Availability',
        'Limited Read',
    ],
    'cleanOptions': [
        'Deep Clean Options',
        'Healthy Clean Options',
        'Thin Clean Options',
        'Very Thin Clean Options',
        'Limited Read',
    ],
    'bullpenPressure': [
        'High Trust-Lane Pressure',
        'Elevated Trust-Lane Pressure',
        'Manageable Trust-Lane Pressure',
        'Low Trust-Lane Pressure',
        'Limited Read',
    ],
    'workloadConcentration': [
        'Heavily Concentrated Workload',
        'Concentrated Workload',
        'Some Workload Concentration',
        'No Workload Concentration',
        'Limited Read',
    ],
    'coverageSafety': [
        'Strong Coverage Safety',
        'Stable Coverage Safety',
        'Thin Coverage Safety',
        'Limited Coverage Safety',
        'Limited Read',
    ],
    'depthSafety': [
        'Strong Depth Safety',
        'Stable Depth Safety',
        'Thin Depth Safety',
        'Limited Depth Safety',
        'Limited Read',
    ],
}

READ_LABELS = {
    'clean': 'Clean Option',
    'watch': 'Watch Arm',
    'restricted': 'Rest-Restricted',
    'unavailable': 'Unavailable',
    'limited': 'Limited Read',
}

ROLE_KEYS = ['trust', 'bridge', 'coverage', 'depth']
ROLE_KEY_BY_LABEL_KEY = {
    'trust_arm': 'trust',
    'bridge_arm': 'bridge',
    'coverage_arm': 'coverage',
    'depth_arm': 'depth',
}

READ_KEY_BY_LABEL_KEY = {
    'clean_option': READ_LABELS['clean'],
    'watch_arm': READ_LABELS['watch'],
    'rest_restricted': READ_LABELS['restricted'],
    'unavailable': READ_LABELS['unavailable'],
    'limited_read': READ_LABELS['limited'],
}

READ_USABILITY = {
    'clean_option': 1,
    'watch_arm': 0.5,
    'rest_restricted': 0,
    'unavailable': 0,
    'limited_read': 0,
}

ROLE_INFLUENCE = {
    'trust_arm': 3,
    'bridge_arm': 2,
    'coverage_arm': 2,
    'depth_arm': 1,
    'limited_read': 0,
}

CLEAN_OPTIONS_TIERS = [
    'Very Thin Clean Options',
    'Thin Clean Options',
    'Healthy Clean Options',
    'Deep Clean Options',
]
CLEAN_TIER_VERY_THIN = 0
CLEAN_TIER_THIN = 1
CLEAN_TIER_HEALTHY = 2
CLEAN_TIER_DEEP = 3

TRUST_PRESSURE_HIGH = 4.5
TRUST_PRESSURE_ELEVATED = 2.5
ROLE_STRESS_ELEVATED = 2
PRESSURE_SHARE_HIGH = 0.45
PRESSURE_SHARE_ELEVATED = 0.25


def _empty_counts(labels):
    return {label: 0 for label in labels}


def _as_number(value):
    return value if isinstance(value, (int, float)) else 0


def _flatten_cards(groups):
    cards = []
    for group in groups or []:
        cards.extend(group.get('pitchers') or [])
    return cards


def _label_key(card, kind):
    labels = card.get('pitcher_labels') or {}
    payload = labels.get(kind) or {}
    return payload.get('key') or 'limited_read'


def _card_fatigue(card):
    return _as_number(
        card.get('fatigue_score')
        or card.get('raw_score')
        or (card.get('availability') or {}).get('fatigue_score')
    )


def _summarize_cards(groups, context=None):
    cards = _flatten_cards(groups)
    read_counts = _empty_counts(READ_LABELS.values())
    role_counts = _empty_counts(['Trust Arm', 'Bridge Arm', 'Coverage Arm', 'Depth Arm', 'Limited Read'])
    role_read_counts = {
        role: _empty_counts(READ_LABELS.values())
        for role in ROLE_KEYS
    }
    high_fatigue_arms = 0

    for card in cards:
        role_key = _label_key(card, 'role')
        read_key = _label_key(card, 'read')
        role_label = (card.get('pitcher_labels') or {}).get('role', {}).get('label') or 'Limited Read'
        read_label = READ_KEY_BY_LABEL_KEY.get(read_key, 'Limited Read')
        if role_label in role_counts:
            role_counts[role_label] += 1
        if read_label in read_counts:
            read_counts[read_label] += 1
        role_bucket = ROLE_KEY_BY_LABEL_KEY.get(role_key)
        if role_bucket:
            role_read_counts[role_bucket][read_label] += 1
        if _card_fatigue(card) >= 70:
            high_fatigue_arms += 1

    total = len(cards)
    unavailable = read_counts[READ_LABELS['unavailable']]
    active = max(0, total - unavailable)
    role_known = total - role_counts['Limited Read']
    read_known = total - read_counts['Limited Read']
    tiny = total > 0 and total < 4

    return {
        'totalBullpenArms': total,
        'activeBullpenArms': active,
        'roleCounts': role_counts,
        'readCounts': read_counts,
        'roleReadCounts': role_read_counts,
        'highFatigueArms': high_fatigue_arms,
        'stressState': (context or {}).get('health', {}).get('state'),
        'dataQuality': {
            'roleKnownCount': role_known,
            'readKnownCount': read_known,
            'roleSparse': total == 0 or tiny or role_known < _ceil_half(total),
            'readSparse': total == 0 or tiny or read_known < _ceil_half(total),
        },
    }


def _ceil_half(value):
    return int((value + 1) // 2)


def _read(key, label, explanation, supporting_counts, reasons=None):
    return {
        'key': key,
        'label': label,
        'explanation': explanation,
        'supportingCounts': supporting_counts,
        'reasons': list(reasons or [explanation]),
    }


def _limited_read(key, explanation, supporting_counts):
    return _read(key, 'Limited Read', explanation, supporting_counts)


def _role_limited_explanation(role_known_count, total, concept):
    return f'Only {role_known_count} of {total} bullpen arms have clear role labels, so {concept} is a Limited Read.'


def _trust_availability(summary):
    trust_reads = summary['roleReadCounts']['trust']
    trust_arms = summary['roleCounts']['Trust Arm']
    clean = trust_reads[READ_LABELS['clean']]
    watch = trust_reads[READ_LABELS['watch']]
    restricted = trust_reads[READ_LABELS['restricted']]
    unavailable = trust_reads[READ_LABELS['unavailable']]
    limited = trust_reads[READ_LABELS['limited']]
    available = clean + watch
    counts = {
        'trustArms': trust_arms,
        'availableTrustArms': available,
        'cleanTrustArms': clean,
        'watchTrustArms': watch,
        'restRestrictedTrustArms': restricted,
        'unavailableTrustArms': unavailable,
        'limitedReadTrustArms': limited,
        'roleKnownCount': summary['dataQuality']['roleKnownCount'],
        'totalBullpenArms': summary['totalBullpenArms'],
    }
    if summary['dataQuality']['roleSparse']:
        return _limited_read(
            'trustAvailability',
            _role_limited_explanation(counts['roleKnownCount'], counts['totalBullpenArms'], 'Trust Arm Availability'),
            counts,
        )

    explanation = (
        f'{clean} of {trust_arms} Trust Arms are Clean Options; {watch} are Watch Arms, '
        f'{restricted} are Rest-Restricted, and {unavailable} are Unavailable.'
    )
    if trust_arms == 0 or available == 0:
        return _read('trustAvailability', 'Limited Trust Arm Availability', explanation, counts)
    if trust_arms >= 2 and clean >= 2 and restricted == 0 and unavailable == 0:
        return _read('trustAvailability', 'Strong Trust Arm Availability', explanation, counts)
    if trust_arms >= 2 and available >= 2 and unavailable == 0:
        return _read('trustAvailability', 'Stable Trust Arm Availability', explanation, counts)
    if available >= 1:
        return _read('trustAvailability', 'Thin Trust Arm Availability', explanation, counts)
    return _read('trustAvailability', 'Limited Trust Arm Availability', explanation, counts)


def _clean_options(summary):
    clean = summary['readCounts'][READ_LABELS['clean']]
    restricted = summary['readCounts'][READ_LABELS['restricted']]
    unavailable = summary['readCounts'][READ_LABELS['unavailable']]
    limited = summary['readCounts'][READ_LABELS['limited']]
    clean_trust = summary['roleReadCounts']['trust'][READ_LABELS['clean']]
    clean_bridge = summary['roleReadCounts']['bridge'][READ_LABELS['clean']]
    clean_coverage = summary['roleReadCounts']['coverage'][READ_LABELS['clean']]
    clean_depth = summary['roleReadCounts']['depth'][READ_LABELS['clean']]
    meaningful_clean = clean_trust >= 1 or clean_bridge >= 1 or clean_coverage >= 1
    counts = {
        'cleanOptionCount': clean,
        'activeBullpenArms': summary['activeBullpenArms'],
        'totalBullpenArms': summary['totalBullpenArms'],
        'restRestrictedCount': restricted,
        'unavailableCount': unavailable,
        'limitedReadCount': limited,
        'cleanTrustArms': clean_trust,
        'cleanBridgeArms': clean_bridge,
        'cleanCoverageArms': clean_coverage,
        'cleanDepthArms': clean_depth,
        'meaningfulCleanBacking': meaningful_clean,
    }
    if summary['dataQuality']['readSparse']:
        return _limited_read(
            'cleanOptions',
            f"Only {summary['dataQuality']['readKnownCount']} of {summary['totalBullpenArms']} bullpen arms have clear workload or availability labels, so Clean Options is a Limited Read.",
            counts,
        )

    if clean >= 6 or (summary['activeBullpenArms'] >= 7 and clean >= 5):
        tier = CLEAN_TIER_DEEP
    elif clean >= 4:
        tier = CLEAN_TIER_HEALTHY
    elif clean >= 2:
        tier = CLEAN_TIER_THIN
    else:
        tier = CLEAN_TIER_VERY_THIN

    if clean_trust >= 2 and tier < CLEAN_TIER_HEALTHY:
        tier = CLEAN_TIER_HEALTHY
    if tier == CLEAN_TIER_DEEP and clean_trust < 2:
        tier = CLEAN_TIER_HEALTHY
    if not meaningful_clean and tier > CLEAN_TIER_THIN:
        tier = CLEAN_TIER_THIN

    explanation = (
        f"{clean} Clean Options out of {summary['activeBullpenArms']} active bullpen arms - "
        f'{clean_trust} Trust, {clean_bridge} Bridge, {clean_coverage} Coverage, {clean_depth} Depth, '
        f'with {restricted} Rest-Restricted and {unavailable} Unavailable. '
        'Interpretation weighs clean Trust Arms above clean Depth Arms.'
    )
    return _read('cleanOptions', CLEAN_OPTIONS_TIERS[tier], explanation, counts)


def _role_pressure(reads, weight):
    load = (
        reads[READ_LABELS['watch']] * (1 - READ_USABILITY['watch_arm'])
        + reads[READ_LABELS['restricted']] * (1 - READ_USABILITY['rest_restricted'])
        + reads[READ_LABELS['unavailable']] * (1 - READ_USABILITY['unavailable'])
    )
    return weight * load


def _bullpen_pressure(summary):
    read_counts = summary['readCounts']
    trust_reads = summary['roleReadCounts']['trust']
    bridge_reads = summary['roleReadCounts']['bridge']
    coverage_reads = summary['roleReadCounts']['coverage']
    depth_reads = summary['roleReadCounts']['depth']
    trust_pressure = _role_pressure(trust_reads, ROLE_INFLUENCE['trust_arm'])
    bridge_pressure = _role_pressure(bridge_reads, ROLE_INFLUENCE['bridge_arm'])
    coverage_pressure = _role_pressure(coverage_reads, ROLE_INFLUENCE['coverage_arm'])
    depth_pressure = _role_pressure(depth_reads, ROLE_INFLUENCE['depth_arm'])
    weighted_pressure = trust_pressure + bridge_pressure + coverage_pressure + depth_pressure
    full_influence = (
        summary['roleCounts']['Trust Arm'] * ROLE_INFLUENCE['trust_arm']
        + summary['roleCounts']['Bridge Arm'] * ROLE_INFLUENCE['bridge_arm']
        + summary['roleCounts']['Coverage Arm'] * ROLE_INFLUENCE['coverage_arm']
        + summary['roleCounts']['Depth Arm'] * ROLE_INFLUENCE['depth_arm']
    )
    pressure_share = weighted_pressure / full_influence if full_influence > 0 else 0
    clean_trust = trust_reads[READ_LABELS['clean']]
    watch_trust = trust_reads[READ_LABELS['watch']]
    restricted_trust = trust_reads[READ_LABELS['restricted']]
    unavailable_trust = trust_reads[READ_LABELS['unavailable']]
    usable_trust = clean_trust + watch_trust
    stressed_bridge = bridge_reads[READ_LABELS['restricted']] + bridge_reads[READ_LABELS['unavailable']]
    stressed_coverage = coverage_reads[READ_LABELS['restricted']] + coverage_reads[READ_LABELS['unavailable']]
    no_usable_trust = usable_trust == 0
    counts = {
        'watchArmCount': read_counts[READ_LABELS['watch']],
        'restRestrictedCount': read_counts[READ_LABELS['restricted']],
        'unavailableCount': read_counts[READ_LABELS['unavailable']],
        'highFatigueArms': summary['highFatigueArms'],
        'limitedReadCount': read_counts[READ_LABELS['limited']],
        'totalBullpenArms': summary['totalBullpenArms'],
        'cleanTrustArms': clean_trust,
        'restrictedTrustArms': restricted_trust,
        'unavailableTrustArms': unavailable_trust,
        'usableTrustArms': usable_trust,
        'stressedBridgeArms': stressed_bridge,
        'stressedCoverageArms': stressed_coverage,
        'noUsableTrust': no_usable_trust,
    }
    if summary['dataQuality']['readSparse']:
        return _limited_read(
            'bullpenPressure',
            f"Only {summary['dataQuality']['readKnownCount']} of {summary['totalBullpenArms']} bullpen arms have clear workload or availability labels, so Trust-Lane Pressure is a Limited Read.",
            counts,
        )

    explanation = (
        f'Trust Arms show {clean_trust} clean, {restricted_trust} Rest-Restricted, and '
        f'{unavailable_trust} Unavailable; {stressed_bridge} Bridge Arms and {stressed_coverage} '
        f'Coverage Arms are stressed, alongside {summary["highFatigueArms"]} high-fatigue arms. '
        'Pressure weighs Trust and Bridge Arm stress above Depth Arm stress.'
    )
    if (
        trust_pressure >= TRUST_PRESSURE_HIGH
        or pressure_share >= PRESSURE_SHARE_HIGH
        or summary['stressState'] == 'constrained'
    ):
        return _read('bullpenPressure', 'High Trust-Lane Pressure', explanation, counts)
    if (
        trust_pressure >= TRUST_PRESSURE_ELEVATED
        or bridge_pressure >= ROLE_STRESS_ELEVATED
        or coverage_pressure >= ROLE_STRESS_ELEVATED
        or pressure_share >= PRESSURE_SHARE_ELEVATED
        or no_usable_trust
        or counts['watchArmCount'] >= 3
        or summary['highFatigueArms'] >= 2
        or summary['stressState'] in {'elevated', 'monitoring'}
    ):
        return _read('bullpenPressure', 'Elevated Trust-Lane Pressure', explanation, counts)
    if (
        counts['restRestrictedCount'] == 0
        and counts['unavailableCount'] == 0
        and counts['watchArmCount'] <= 1
        and summary['highFatigueArms'] == 0
        and usable_trust > 0
    ):
        return _read('bullpenPressure', 'Low Trust-Lane Pressure', explanation, counts)
    return _read('bullpenPressure', 'Manageable Trust-Lane Pressure', explanation, counts)


def _pct(value):
    return round(float(value or 0) * 100)


def _workload_concentration(workload):
    workload = workload or {}
    total_pitches = int(workload.get('total_pitches') or 0)
    participant_count = int(workload.get('participant_count') or 0)
    top_arm_count = int(workload.get('top_arm_count') or 0)
    top_pitch_total = int(workload.get('top_pitch_total') or 0)
    top_share = float(workload.get('top_share') or 0)
    top_one_share = float(workload.get('top_one_share') or 0)
    level = workload.get('concentration_level') or 'none'
    descriptor = workload.get('concentration_descriptor') or 'no concentration'
    per_arm = float(workload.get('per_arm_pitches') or 0)
    window_days = int(workload.get('window_days') or RECENT_WORKLOAD_WINDOW_DAYS)
    label_by_level = {
        'severe': 'Heavily Concentrated Workload',
        'concentrated': 'Concentrated Workload',
        'moderate': 'Some Workload Concentration',
        'none': 'No Workload Concentration',
    }
    counts = {
        'totalRecentPitches': total_pitches,
        'participantCount': participant_count,
        'topArmCount': top_arm_count,
        'topPitchTotal': top_pitch_total,
        'topShare': top_share,
        'topSharePct': _pct(top_share),
        'topOneShare': top_one_share,
        'perArmPitches': per_arm,
        'windowDays': window_days,
        'concentrationLevel': level,
        'concentrationDescriptor': descriptor,
    }

    if total_pitches <= 0 or participant_count <= 0:
        return _limited_read(
            'workloadConcentration',
            'No recent relief workload was available in the workload window, so Workload Concentration is a Limited Read.',
            counts,
        )

    label = label_by_level.get(level, 'Limited Read')
    explanation = (
        f'The top {top_arm_count} relief arms carried {counts["topSharePct"]}% of recent relief pitches '
        f'({top_pitch_total} of {total_pitches}) across {participant_count} participating arms.'
    )
    return _read('workloadConcentration', label, explanation, counts)


def _coverage_safety(summary):
    coverage_reads = summary['roleReadCounts']['coverage']
    bridge_reads = summary['roleReadCounts']['bridge']
    coverage_arms = summary['roleCounts']['Coverage Arm']
    clean = coverage_reads[READ_LABELS['clean']]
    watch = coverage_reads[READ_LABELS['watch']]
    restricted = coverage_reads[READ_LABELS['restricted']]
    unavailable = coverage_reads[READ_LABELS['unavailable']]
    limited = coverage_reads[READ_LABELS['limited']]
    available = clean + watch
    clean_bridge = bridge_reads[READ_LABELS['clean']]
    watch_bridge = bridge_reads[READ_LABELS['watch']]
    has_substitute = clean_bridge >= 1 or watch_bridge >= 2
    counts = {
        'coverageArms': coverage_arms,
        'availableCoverageArms': available,
        'cleanCoverageArms': clean,
        'watchCoverageArms': watch,
        'restRestrictedCoverageArms': restricted,
        'unavailableCoverageArms': unavailable,
        'limitedReadCoverageArms': limited,
        'cleanBridgeArms': clean_bridge,
        'watchBridgeArms': watch_bridge,
        'substituteCoverageApplied': False,
        'roleKnownCount': summary['dataQuality']['roleKnownCount'],
        'totalBullpenArms': summary['totalBullpenArms'],
    }
    if summary['dataQuality']['roleSparse']:
        return _limited_read(
            'coverageSafety',
            _role_limited_explanation(counts['roleKnownCount'], counts['totalBullpenArms'], 'Coverage Safety'),
            counts,
        )

    explanation = (
        f'{clean} of {coverage_arms} Coverage Arms are Clean Options; {watch} are Watch Arms, '
        f'{restricted} are Rest-Restricted, and {unavailable} are Unavailable.'
    )
    if coverage_arms >= 2 and clean >= 2 and restricted == 0 and unavailable == 0:
        return _read('coverageSafety', 'Strong Coverage Safety', explanation, counts)
    if coverage_arms >= 2 and available >= 2 and unavailable == 0:
        return _read('coverageSafety', 'Stable Coverage Safety', explanation, counts)
    if coverage_arms >= 1 and available >= 1:
        return _read('coverageSafety', 'Thin Coverage Safety', explanation, counts)
    if has_substitute:
        fallback = ' and '.join(filter(None, [
            f'{clean_bridge} clean Bridge Arm{"s" if clean_bridge != 1 else ""}' if clean_bridge > 0 else None,
            f'{watch_bridge} Bridge Arm{"s" if watch_bridge != 1 else ""} on watch' if watch_bridge > 0 else None,
        ]))
        lifted = (
            f'{explanation} No designated Coverage Arm is available, but {fallback} can chain '
            'emergency innings, so coverage reads Thin rather than Limited - substitute capacity, not designated length.'
        )
        return _read(
            'coverageSafety',
            'Thin Coverage Safety',
            lifted,
            {**counts, 'substituteCoverageApplied': True},
        )
    return _read('coverageSafety', 'Limited Coverage Safety', explanation, counts)


def _depth_safety(summary):
    depth_reads = summary['roleReadCounts']['depth']
    trust_reads = summary['roleReadCounts']['trust']
    depth_arms = summary['roleCounts']['Depth Arm']
    clean = depth_reads[READ_LABELS['clean']]
    watch = depth_reads[READ_LABELS['watch']]
    restricted = depth_reads[READ_LABELS['restricted']]
    unavailable = depth_reads[READ_LABELS['unavailable']]
    limited = depth_reads[READ_LABELS['limited']]
    available = clean + watch
    usable_trust = trust_reads[READ_LABELS['clean']] + trust_reads[READ_LABELS['watch']]
    anchored = usable_trust > 0
    counts = {
        'depthArms': depth_arms,
        'availableDepthArms': available,
        'cleanDepthArms': clean,
        'watchDepthArms': watch,
        'restRestrictedDepthArms': restricted,
        'unavailableDepthArms': unavailable,
        'limitedReadDepthArms': limited,
        'usableTrustArms': usable_trust,
        'anchoredByTrust': anchored,
        'activeBullpenArms': summary['activeBullpenArms'],
        'totalBullpenArms': summary['totalBullpenArms'],
        'roleKnownCount': summary['dataQuality']['roleKnownCount'],
    }
    if summary['dataQuality']['roleSparse']:
        return _limited_read(
            'depthSafety',
            _role_limited_explanation(counts['roleKnownCount'], counts['totalBullpenArms'], 'Depth Safety'),
            counts,
        )

    explanation = (
        f'{depth_arms} Depth Arms in a {summary["totalBullpenArms"]}-arm bullpen; {available} are '
        f'Clean Options or Watch Arms, {restricted} are Rest-Restricted, and {unavailable} are Unavailable.'
    )
    strong_by_volume = summary['totalBullpenArms'] >= 8 and depth_arms >= 3 and available >= 2
    if strong_by_volume and anchored:
        return _read('depthSafety', 'Strong Depth Safety', explanation, counts)
    if strong_by_volume and not anchored:
        stable = (
            f'{explanation} No usable Trust Arm anchors the bullpen, so this depth reads Stable '
            'rather than Strong - fallback volume without a primary corps in front of it.'
        )
        return _read('depthSafety', 'Stable Depth Safety', stable, counts)
    if summary['totalBullpenArms'] >= 7 and depth_arms >= 2 and available >= 1:
        return _read('depthSafety', 'Stable Depth Safety', explanation, counts)
    if depth_arms >= 1 and available >= 1:
        return _read('depthSafety', 'Thin Depth Safety', explanation, counts)
    return _read('depthSafety', 'Limited Depth Safety', explanation, counts)


def build_team_bullpen_shape(groups, context=None, workload_concentration=None):
    """Return backend-authored public team reads for a board payload."""
    summary = _summarize_cards(groups, context=context)
    reads = [
        _trust_availability(summary),
        _clean_options(summary),
        _bullpen_pressure(summary),
        _workload_concentration(workload_concentration),
        _coverage_safety(summary),
        _depth_safety(summary),
    ]
    by_key = {item['key']: item for item in reads}
    return {
        'reads': reads,
        'byKey': by_key,
        'trustAvailability': by_key['trustAvailability'],
        'cleanOptions': by_key['cleanOptions'],
        'bullpenPressure': by_key['bullpenPressure'],
        'workloadConcentration': by_key['workloadConcentration'],
        'coverageSafety': by_key['coverageSafety'],
        'depthSafety': by_key['depthSafety'],
        'supportingCounts': {
            'totalBullpenArms': summary['totalBullpenArms'],
            'activeBullpenArms': summary['activeBullpenArms'],
            'roleKnownCount': summary['dataQuality']['roleKnownCount'],
            'readKnownCount': summary['dataQuality']['readKnownCount'],
        },
        'source': 'backend',
    }
