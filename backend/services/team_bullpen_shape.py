"""Backend-authored team bullpen shape reads for board consumers."""

from services.bullpen_coverage_safety import build_bullpen_coverage_safety_read
from services.bullpen_eligibility_vocabulary import record_is_swing_bulk
from services.pitcher_public_labels import ROLE_PUBLIC_LABELS
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
        'Strong Late-Inning Availability',
        'Stable Late-Inning Availability',
        'Thin Late-Inning Availability',
        'Limited Late-Inning Availability',
        'Limited Read',
    ],
    'cleanOptions': [
        'Deep Rested Bullpen',
        'Healthy Rested Bullpen',
        'Thin Rested Bullpen',
        'Very Thin Rested Bullpen',
        'Limited Read',
    ],
    'bullpenPressure': [
        'High Late-Inning Pressure',
        'Elevated Late-Inning Pressure',
        'Manageable Late-Inning Pressure',
        'Low Late-Inning Pressure',
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
    'clean': 'Rested',
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

# Role-count display labels come from the one canonical public role vocabulary;
# this module never maintains its own role wording.
ROLE_COUNT_LABELS = {
    label_key: ROLE_PUBLIC_LABELS[label_key]['label']
    for label_key in ('trust_arm', 'bridge_arm', 'coverage_arm', 'depth_arm', 'limited_read')
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

DATA_LIMITED_DISCLAIMER = (
    'This is a data-limited note, not a statement about injury status or manager intent.'
)

ROLE_INFLUENCE = {
    'trust_arm': 3,
    'bridge_arm': 2,
    'coverage_arm': 2,
    'depth_arm': 1,
    'limited_read': 0,
}

CLEAN_OPTIONS_TIERS = [
    'Very Thin Rested Bullpen',
    'Thin Rested Bullpen',
    'Healthy Rested Bullpen',
    'Deep Rested Bullpen',
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


def _count_word(value):
    words = {
        0: 'no',
        1: 'one',
        2: 'two',
        3: 'three',
        4: 'four',
        5: 'five',
        6: 'six',
        7: 'seven',
        8: 'eight',
        9: 'nine',
        10: 'ten',
        11: 'eleven',
        12: 'twelve',
        13: 'thirteen',
        14: 'fourteen',
        15: 'fifteen',
        16: 'sixteen',
        17: 'seventeen',
        18: 'eighteen',
        19: 'nineteen',
        20: 'twenty',
    }
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 'unknown'
    return words.get(count, 'more than twenty')


def _arm_phrase(count, noun='arm', plural=None):
    plural = plural or f'{noun}s'
    try:
        value = int(count)
    except (TypeError, ValueError):
        return f'unknown {plural}'
    return f'{_count_word(value)} {noun if value == 1 else plural}'


def _is_are(count):
    try:
        return 'is' if int(count) == 1 else 'are'
    except (TypeError, ValueError):
        return 'are'


def _has_have(count):
    try:
        return 'has' if int(count) == 1 else 'have'
    except (TypeError, ValueError):
        return 'have'


def _sentence_start(text):
    text = str(text or '').strip()
    if not text:
        return text
    return f'{text[0].upper()}{text[1:]}'


def _coverage_layer_phrase(count):
    if count <= 0:
        return 'no rested long reliever'
    if count == 1:
        return 'one rested long reliever'
    return f'{_count_word(count)} rested long relievers'


def _late_path_phrase(count):
    if count <= 0:
        return 'no clear rested late-inning anchor'
    if count == 1:
        return 'one rested arm who fits the late-inning bridge'
    return f'{_count_word(count)} rested arms who fit the late-inning bridge'


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
    role_counts = _empty_counts(ROLE_COUNT_LABELS.values())
    role_read_counts = {
        role: _empty_counts(READ_LABELS.values())
        for role in ROLE_KEYS
    }
    high_fatigue_arms = 0

    for card in cards:
        role_key = _label_key(card, 'role')
        read_key = _label_key(card, 'read')
        role_label = ROLE_COUNT_LABELS.get(role_key, ROLE_COUNT_LABELS['limited_read'])
        read_label = READ_KEY_BY_LABEL_KEY.get(read_key, 'Limited Read')
        # Swing/Bulk arms support coverage/depth context but are held out of the
        # trust/bridge lanes and the clean-option headline.
        is_swing_bulk = record_is_swing_bulk(card)
        suppress_trust_bridge = is_swing_bulk and role_key in ('trust_arm', 'bridge_arm')
        if not suppress_trust_bridge:
            role_counts[role_label] += 1
        if read_label in read_counts and not (is_swing_bulk and read_label == READ_LABELS['clean']):
            read_counts[read_label] += 1
        role_bucket = ROLE_KEY_BY_LABEL_KEY.get(role_key)
        if role_bucket and not (is_swing_bulk and role_bucket in ('trust', 'bridge')):
            role_read_counts[role_bucket][read_label] += 1
        if _card_fatigue(card) >= 70:
            high_fatigue_arms += 1

    total = len(cards)
    unavailable = read_counts[READ_LABELS['unavailable']]
    active = max(0, total - unavailable)
    role_known = total - role_counts[ROLE_COUNT_LABELS['limited_read']]
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
    return (
        f'There is not enough recent workload data to read {concept} yet. '
        f'{DATA_LIMITED_DISCLAIMER}'
    )


def _trust_availability(summary):
    trust_reads = summary['roleReadCounts']['trust']
    trust_arms = summary['roleCounts'][ROLE_COUNT_LABELS['trust_arm']]
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
            _role_limited_explanation(counts['roleKnownCount'], counts['totalBullpenArms'], 'late-inning availability'),
            counts,
        )

    rested_phrase = _arm_phrase(clean, 'late-inning arm')
    monitor_phrase = _arm_phrase(watch, 'late-inning arm')
    restricted_total = restricted + unavailable
    if restricted_total:
        restriction = (
            f'{_arm_phrase(restricted_total, "late-inning arm")} {_is_are(restricted_total)} '
            'carrying enough recent workload to narrow the late-game path'
        )
    else:
        restriction = 'none of that group is blocked by a heavy recent workload signal'
    explanation = (
        f'The late-inning group has {rested_phrase} fully rested and '
        f'{monitor_phrase} worth monitoring. {_sentence_start(restriction)}.'
    )
    if trust_arms == 0 or available == 0:
        return _read('trustAvailability', 'Limited Late-Inning Availability', explanation, counts)
    if trust_arms >= 2 and clean >= 2 and restricted == 0 and unavailable == 0:
        return _read('trustAvailability', 'Strong Late-Inning Availability', explanation, counts)
    if trust_arms >= 2 and available >= 2 and unavailable == 0:
        return _read('trustAvailability', 'Stable Late-Inning Availability', explanation, counts)
    if available >= 1:
        return _read('trustAvailability', 'Thin Late-Inning Availability', explanation, counts)
    return _read('trustAvailability', 'Limited Late-Inning Availability', explanation, counts)


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
            (
                'BaseballOS cannot yet say how many rested late-inning arms are ready '
                f'from the stored data. {DATA_LIMITED_DISCLAIMER}'
            ),
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

    late_path_count = clean_trust + clean_bridge
    rested_phrase = _arm_phrase(clean, 'arm')
    late_path = _late_path_phrase(late_path_count)
    if tier >= CLEAN_TIER_HEALTHY:
        explanation = (
            f'The bullpen has {rested_phrase} fully rested, with {late_path}. '
            'That gives the late innings more cushion if the starter exits early.'
        )
    elif clean > 0:
        explanation = (
            f'Only {rested_phrase} {_is_are(clean)} fully rested, with {late_path}. '
            'The rest of the group looks more like depth coverage than leverage cushion.'
        )
    else:
        explanation = (
            'Not enough of the bullpen is fully rested to build a comfortable late-game path. '
            'The late innings leave less margin if the starter exits early.'
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
        summary['roleCounts'][ROLE_COUNT_LABELS['trust_arm']] * ROLE_INFLUENCE['trust_arm']
        + summary['roleCounts'][ROLE_COUNT_LABELS['bridge_arm']] * ROLE_INFLUENCE['bridge_arm']
        + summary['roleCounts'][ROLE_COUNT_LABELS['coverage_arm']] * ROLE_INFLUENCE['coverage_arm']
        + summary['roleCounts'][ROLE_COUNT_LABELS['depth_arm']] * ROLE_INFLUENCE['depth_arm']
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
            (
                'BaseballOS cannot yet say how much late-inning pressure is on this '
                f'bullpen from the stored data. {DATA_LIMITED_DISCLAIMER}'
            ),
            counts,
        )

    restricted_late = restricted_trust + unavailable_trust
    stressed_handoff = stressed_bridge + stressed_coverage
    explanation = (
        f'The primary late-inning pocket has {_arm_phrase(clean_trust, "arm")} fully rested and '
        f'{_arm_phrase(restricted_late, "arm")} carrying enough recent workload to narrow the path. '
        f'The handoff innings add {_arm_phrase(stressed_handoff, "arm")} with recent stress, '
        f'and {_arm_phrase(summary["highFatigueArms"], "arm")} {_is_are(summary["highFatigueArms"])} '
        'carrying heavy recent workload.'
    )
    if (
        trust_pressure >= TRUST_PRESSURE_HIGH
        or pressure_share >= PRESSURE_SHARE_HIGH
        or summary['stressState'] == 'constrained'
    ):
        return _read('bullpenPressure', 'High Late-Inning Pressure', explanation, counts)
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
        return _read('bullpenPressure', 'Elevated Late-Inning Pressure', explanation, counts)
    if (
        counts['restRestrictedCount'] == 0
        and counts['unavailableCount'] == 0
        and counts['watchArmCount'] <= 1
        and summary['highFatigueArms'] == 0
        and usable_trust > 0
    ):
        return _read('bullpenPressure', 'Low Late-Inning Pressure', explanation, counts)
    return _read('bullpenPressure', 'Manageable Late-Inning Pressure', explanation, counts)


def _pct(value):
    return round(float(value or 0) * 100)


def _workload_concentration(workload):
    workload = workload or {}
    unknown_pitch_count = bool(workload.get('unknown_pitch_count'))
    window_days = int(workload.get('window_days') or RECENT_WORKLOAD_WINDOW_DAYS)
    if unknown_pitch_count:
        counts = {
            'totalRecentPitches': None,
            'participantCount': None,
            'topArmCount': None,
            'topPitchTotal': None,
            'topShare': None,
            'topSharePct': None,
            'topOneShare': None,
            'perArmPitches': None,
            'windowDays': window_days,
            'concentrationLevel': 'unknown',
            'concentrationDescriptor': 'unknown workload concentration',
            'unknownPitchCount': True,
        }
        return _limited_read(
            'workloadConcentration',
            'Recent relief pitch-count workload is incomplete, so BaseballOS cannot tell whether the same arms are carrying the work.',
            counts,
        )

    total_pitches = int(workload.get('total_pitches') or 0)
    participant_count = int(workload.get('participant_count') or 0)
    top_arm_count = int(workload.get('top_arm_count') or 0)
    top_pitch_total = int(workload.get('top_pitch_total') or 0)
    top_share = float(workload.get('top_share') or 0)
    top_one_share = float(workload.get('top_one_share') or 0)
    level = workload.get('concentration_level') or 'none'
    descriptor = workload.get('concentration_descriptor') or 'no concentration'
    per_arm = float(workload.get('per_arm_pitches') or 0)
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
            'No recent relief workload was available in the workload window, so BaseballOS cannot tell whether the same arms are carrying the work.',
            counts,
        )

    label = label_by_level.get(level, 'Limited Read')
    explanation = (
        f'{_arm_phrase(top_arm_count).capitalize()} {_has_have(top_arm_count)} carried '
        f'{counts["topSharePct"]}% of the recent relief work across '
        f'{_arm_phrase(participant_count, "bullpen arm")}.'
    )
    return _read('workloadConcentration', label, explanation, counts)


def _legacy_coverage_safety(summary):
    coverage_reads = summary['roleReadCounts']['coverage']
    bridge_reads = summary['roleReadCounts']['bridge']
    coverage_arms = summary['roleCounts'][ROLE_COUNT_LABELS['coverage_arm']]
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

    rested_length = _coverage_layer_phrase(clean)
    monitor_length = (
        'no other long reliever is close to rested'
        if watch <= 0 else f'{_arm_phrase(watch, "long reliever")} {_is_are(watch)} close to rested'
    )
    restricted_length = restricted + unavailable
    if restricted_length:
        restriction = (
            f'{_arm_phrase(restricted_length, "long reliever")} {_is_are(restricted_length)} '
            'carrying enough recent workload to limit coverage'
        )
    else:
        restriction = 'the long relief layer does not show a heavy recent workload block'
    explanation = (
        f'The bullpen has {rested_length} and {monitor_length}. {_sentence_start(restriction)}.'
    )
    if coverage_arms >= 2 and clean >= 2 and restricted == 0 and unavailable == 0:
        return _read('coverageSafety', 'Strong Coverage Safety', explanation, counts)
    if coverage_arms >= 2 and available >= 2 and unavailable == 0:
        return _read('coverageSafety', 'Stable Coverage Safety', explanation, counts)
    if coverage_arms >= 1 and available >= 1:
        return _read('coverageSafety', 'Thin Coverage Safety', explanation, counts)
    if has_substitute:
        fallback = ' and '.join(filter(None, [
            f'{_arm_phrase(clean_bridge, "shorter bridge arm")} rested' if clean_bridge > 0 else None,
            f'{_arm_phrase(watch_bridge, "shorter bridge arm")} {_is_are(watch_bridge)} close to rested' if watch_bridge > 0 else None,
        ]))
        lifted = (
            f'{explanation} No clear long reliever is ready, but {fallback} can help chain '
            'emergency innings, so the coverage note stays Thin rather than Limited.'
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
    depth_arms = summary['roleCounts'][ROLE_COUNT_LABELS['depth_arm']]
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
        f'The lower-leverage layer has {_arm_phrase(available, "arm")} who can cover softer innings, '
        f'while {_arm_phrase(restricted + unavailable, "arm")} {_is_are(restricted + unavailable)} '
        'carrying enough recent workload to limit the fallback cushion.'
    )
    strong_by_volume = summary['totalBullpenArms'] >= 8 and depth_arms >= 3 and available >= 2
    if strong_by_volume and anchored:
        return _read('depthSafety', 'Strong Depth Safety', explanation, counts)
    if strong_by_volume and not anchored:
        stable = (
            f'{explanation} The late-inning cushion is thin, so this depth note stays Stable '
            'rather than Strong.'
        )
        return _read('depthSafety', 'Stable Depth Safety', stable, counts)
    if summary['totalBullpenArms'] >= 7 and depth_arms >= 2 and available >= 1:
        return _read('depthSafety', 'Stable Depth Safety', explanation, counts)
    if depth_arms >= 1 and available >= 1:
        return _read('depthSafety', 'Thin Depth Safety', explanation, counts)
    return _read('depthSafety', 'Limited Depth Safety', explanation, counts)


def _without_data_limited_disclaimer(text):
    text = str(text or '')
    if DATA_LIMITED_DISCLAIMER not in text:
        return text
    return ' '.join(text.replace(DATA_LIMITED_DISCLAIMER, '').split()).strip()


def _dedupe_data_limited_disclaimers(reads):
    """Keep the trust-first disclaimer once across one team-shape card."""
    seen = False
    output = []
    for read in reads:
        item = dict(read)
        explanation = str(item.get('explanation') or '')
        if DATA_LIMITED_DISCLAIMER in explanation:
            if seen:
                item['explanation'] = _without_data_limited_disclaimer(explanation)
            else:
                seen = True
        reasons = []
        for reason in item.get('reasons') or []:
            reason_text = str(reason)
            if DATA_LIMITED_DISCLAIMER in reason_text and item.get('explanation') != reason_text:
                reason_text = _without_data_limited_disclaimer(reason_text)
            reasons.append(reason_text)
        item['reasons'] = reasons
        output.append(item)
    return output


def build_team_bullpen_shape(
    groups,
    context=None,
    workload_concentration=None,
    capacity_intelligence=None,
    bullpen_environment=None,
):
    """Return backend-authored public team reads for a board payload."""
    summary = _summarize_cards(groups, context=context)
    coverage_safety = (
        build_bullpen_coverage_safety_read(
            capacity_intelligence,
            bullpen_environment=bullpen_environment,
        )
        or _legacy_coverage_safety(summary)
    )
    reads = _dedupe_data_limited_disclaimers([
        _trust_availability(summary),
        _clean_options(summary),
        _bullpen_pressure(summary),
        _workload_concentration(workload_concentration),
        coverage_safety,
        _depth_safety(summary),
    ])
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
