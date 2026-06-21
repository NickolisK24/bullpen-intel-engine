"""Story Quality contract (scoring + gating).

A standalone, reusable quality pass that scores a *finished* story object
against a fixed five-rule rubric and returns a structured scorecard, mirroring
the convention of the existing story audits (a pass/fail per check plus reason
strings, aggregated into an overall score on a 0-100 scale).

This module does **not** write stories, change story selection, alter context
layers, or touch scoring/fatigue/availability. It measures the output the
deployed Story Writer already produces and, when explicitly enabled, gates the
weak ones out of the feed. It refines and complements the existing
``story_evidence`` framework rather than replacing it.

The five rules
--------------
1. ``named_arms``            - the body names >= N specific relievers from the
                               team's reliever set (not "three arms" / "the
                               same core").
2. ``stated_cause``          - the body carries an upstream causal clause tied
                               to a real signal (short starts, blowouts/extra
                               innings, a roster event), not a circular restate
                               of "concentrated".
3. ``baseline_anchor``       - *conditional*: any bare workload figure (a
                               concentration %, pitches-per-reliever) is paired
                               with a comparison anchor. Auto-passes when no
                               such figure is cited.
4. ``forward_constraint``    - the body ends on where the next game structurally
                               routes (a forward conditional clause) AND
                               contains no forecast / probability / betting
                               language (banned lexicon is a hard fail).
5. ``no_redundant_restatement`` - no body sentence restates the semantic content
                               of an adjacent sentence (normalized lexical
                               overlap + shared content n-gram heuristic; see
                               ``_redundant_pair``).

Scope: scores four-beat feed story objects (``score_four_beat_story``) and
narrative-memory continuity / flagship notes (``score_continuity_note``).
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
import re
from typing import Any


CAPABILITY = 'story_quality_scorer_v1'
VERSION = '2026-06-21.v2'
SOURCE = 'backend'

SOURCE_FOUR_BEAT = 'four_beat_story'
SOURCE_CONTINUITY = 'continuity_note'

RULE_NAMED_ARMS = 'named_arms'
RULE_STATED_CAUSE = 'stated_cause'
RULE_BASELINE_ANCHOR = 'baseline_anchor'
RULE_FORWARD_CONSTRAINT = 'forward_constraint'
RULE_NO_REDUNDANT_RESTATEMENT = 'no_redundant_restatement'

RULE_ORDER = (
    RULE_NAMED_ARMS,
    RULE_STATED_CAUSE,
    RULE_BASELINE_ANCHOR,
    RULE_FORWARD_CONSTRAINT,
    RULE_NO_REDUNDANT_RESTATEMENT,
)


# ── Default tunables (overridable via StoryQualityConfig / app config) ────────

DEFAULT_MIN_NAMED_ARMS = 2
DEFAULT_REDUNDANCY_DICE_THRESHOLD = 0.7
DEFAULT_REDUNDANCY_MIN_SHARED_NGRAM = 3
DEFAULT_GATE_THRESHOLD = 60.0
DEFAULT_RULE_WEIGHTS = {
    RULE_NAMED_ARMS: 1.0,
    RULE_STATED_CAUSE: 1.0,
    RULE_BASELINE_ANCHOR: 1.0,
    RULE_FORWARD_CONSTRAINT: 1.0,
    RULE_NO_REDUNDANT_RESTATEMENT: 1.0,
}

# Rule 4B - forecast / probability / betting lexicon. Presence is a hard fail.
# Pitcher names are stripped from the text before this scan so a reliever named
# "Will ..." cannot trip the future-tense ``will`` term.
DEFAULT_FORECAST_TERMS = (
    r'\bwill\b',
    r'\bwo n[\'’]?t\b',
    r'\blikel(?:y|ihood)\b',
    r'\bprobabl[ey]\b',
    r'\bprobability\b',
    r'\bexpect(?:s|ed|ing)?\b',
    r'\bproject(?:ed|ion|ions)\b',
    r'\bforecast(?:ed|s)?\b',
    r'\bpredict(?:s|ed|ion|ions)?\b',
    r'\bshould be unavailable\b',
    r'\bdue for\b',
    r'\bfavored\b',
    r'\bfavorite\b',
    r'\bodds\b',
    r'\bover/under\b',
    r'\bover-under\b',
    r'\bmoneyline\b',
    r'\bbet(?:s|ting)?\b',
    r'\bwager\b',
    r'\bchance of\b',
    r'%\s+chance\b',
)

# Rule 2 - upstream cause signals. Each is genuinely *upstream* of workload
# shape (rotation length, game shape, roster movement); none restate
# "concentrated", so a story that only says it is concentrated cannot pass.
DEFAULT_CAUSE_PATTERNS = (
    # rotation / starter length
    r'\bstarters?\b',
    r'\brotation\b',
    r'\bshorter (?:outings|starts)\b',
    r'\bshort starts?\b',
    r'\bhandoff\b',
    r'\bstarter length\b',
    r'\bbefore the sixth\b',
    r'\bspillover\b',
    r'\binherit(?:s|ing|ed)? more\b',
    r'\babsorb more of the game\b',
    r'\bleaves? behind\b',
    r'\bhow much game the starter\b',
    # game shape
    r'\bextra[- ]innings?\b',
    r'\bblowouts?\b',
    r'\blopsided\b',
    r'\blong relief\b',
    r'\bdoubleheader\b',
    # roster movement
    r'\breintroduc',
    r'\breinstated\b',
    r'\bactivated\b',
    r'\bback into the bullpen\b',
    r'\bplaced on the\b',
    r'\binjured list\b',
    r'\bil stint\b',
    r'\boff the il\b',
    r'\broster mov',
    r'\bcalled up\b',
    r'\bpromoted\b',
    r'\bdesignated\b',
    r'\boptioned\b',
    r'\bfresh arm\b',
    r'\bnew arm\b',
)

# Rule 2 (divergence frame) - the most common interpretive move the generator
# makes: contrast a strong surface results metric against a concentrated
# underlying workload ("strong ERA, but the workload is still tight"). It counts
# as interpretive lift only when BOTH dimensions are present and joined by a
# contrastive turn - a workload-only restatement (no results dimension) stays
# circular and still fails.
DEFAULT_DIVERGENCE_RESULTS_TERMS = (
    r'\bera\b',
    r'\brun prevention\b',
    r'\bresults\b',
    r'\bscoreboard\b',
)
DEFAULT_DIVERGENCE_WORKLOAD_TERMS = (
    r'\bpitches per\b',
    r'\bper participating reliever\b',
    r'\bper reliever\b',
    r'-pitch\b',
    r'\bworkload\b',
    r'%\s+of\b',
    r'\btaking\s+\d+\s?%',
    r'\btight\b',
    r'\bnarrow\b',
    r'\bpocket\b',
    r'\bconcentrated\b',
)
DEFAULT_DIVERGENCE_CONTRAST_TERMS = (
    r'\bbut\b',
    r'\bstill\b',
    r'\btighter\b',
    r'\bnot as broad\b',
    r'\bunderneath\b',
    r'\bthan\b.*\b(?:shows?|suggests?|deserves?|alone)\b',
)

# Rule 4A - forward constraint clause (where the next game structurally routes).
DEFAULT_FORWARD_CONSTRAINT_PATTERNS = (
    r'\bif tonight\b',
    r'\bif the (?:next|game|night|score|club|staff|first)\b',
    r'\bif (?:it|they|that|this) (?:tightens|gets|needs|stretches|moves|gets tight)\b',
    r'\bif similar\b',
    r'\bif the game (?:tightens|gets|needs|stretches|moves|stays)\b',
    r'\bif the same\b',
    r'\bif another\b',
    r'\bif one more\b',
    r'\bnext (?:tight|close|high-leverage|leverage) inning\b',
    r'\bthe next (?:tight|close)\b',
    r'\bnext close (?:route|inning|game)\b',
    r'\bcomes back to\b',
    r'\bpoints back\b',
    r'\b(?:run|runs|running|move|moves) back through\b',
    r'\bstill (?:runs|run|points|comes|routes) (?:back |back to |through )\b',
    r'\bstill runs through\b',
    r'\bstill anchor\b',
    r'\bonce the game\b',
    r'\bwhen the game\b',
    r'\bhas to move (?:back )?through\b',
    r'\bthe next (?:useful read|thing to watch|completed game)\b',
    r'\bto watch (?:next|is|for)\b',
    r'\bwhether the\b',
)

# Rule 3 - a bare workload figure is a percentage or a pitches-per-reliever
# rate. "N of M" ratios carry their own denominator and are self-anchored.
_WORKLOAD_PERCENT_RE = re.compile(r'\b\d{1,3}(?:\.\d+)?\s?%')
_PER_ARM_RE = re.compile(r'\b\d+(?:\.\d+)?\s+pitches\s+per\b', re.IGNORECASE)
_N_OF_M_RE = re.compile(r'\b\d+\s+of\s+\d+\b', re.IGNORECASE)
_BASELINE_ANCHOR_PATTERNS = (
    r'\bvs\.?\b',
    r'\bversus\b',
    r'\bcompared (?:to|with)\b',
    r'\bcompared\b',
    r'\bleague\b',
    r'\btypical(?:ly)?\b',
    r'\baverage\b',
    r'\bbaseline\b',
    r'\bnormal(?:ly)?\b',
    r'\bdown from\b',
    r'\bup from\b',
    r'\bfrom\s+\d+(?:\.\d+)?\s*%?\s+to\s+\d+',
    r'\bprior\b',
    r'\bprevious(?:ly)?\b',
    r'\bearlier\b',
    r'\bthan (?:usual|normal|a)\b',
    r'\babove (?:that|a|the|league)\b',
    r'\bpercentage points\b',
)

_SENTENCE_RE = re.compile(r'[^.!?]+[.!?]')
_NUMBER_RE = re.compile(r'\b\d+(?:\.\d+)?%?\b')
_WORD_RE = re.compile(r"[a-z0-9']+")

_STOPWORDS = frozenset({
    'a', 'an', 'the', 'and', 'or', 'but', 'of', 'in', 'on', 'to', 'for', 'with',
    'that', 'this', 'these', 'those', 'is', 'are', 'was', 'were', 'be', 'been',
    'being', 'has', 'have', 'had', 'it', 'its', 'they', 'their', 'them', 'there',
    'still', 'more', 'most', 'less', 'than', 'as', 'at', 'by', 'from', 'into',
    'over', 'after', 'before', 'because', 'if', 'when', 'while', 'so', 'then',
    'about', 'around', 'back', 'out', 'up', 'down', 'one', 'no', 'not', 'now',
    'who', 'whom', 'which', 'what', 'how', 'where', 'why', 'can', 'could',
    'would', 'should', 'may', 'might', 'must', 'will', 'do', 'does', 'did',
    'get', 'gets', 'got', 'keep', 'keeps', 'kept', 'just', 'only', 'also',
    'his', 'her', 'our', 'your', 'every', 'each', 'some', 'any', 'all', 'both',
    'first', 'next', 'last', 'same', 'other', 'another', 'rest', 'much', 'many',
    'how', 'too', 'very', 'between', 'through', 'across', 'behind', 'past',
})


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _clean_text(value: Any) -> str:
    return ' '.join(str(value or '').strip().split())


def _normalize(value: Any) -> str:
    return _clean_text(value).lower()


def _compile(patterns) -> tuple:
    return tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)


@dataclass(frozen=True)
class StoryQualityConfig:
    """Tunable knobs for the scorer and gate.

    Everything that the rubric depends on - thresholds, the banned forecast
    lexicon, cause signals, and per-rule weights - lives here so it can be
    tuned via config/env without a code change.
    """

    min_named_arms: int = DEFAULT_MIN_NAMED_ARMS
    redundancy_dice_threshold: float = DEFAULT_REDUNDANCY_DICE_THRESHOLD
    redundancy_min_shared_ngram: int = DEFAULT_REDUNDANCY_MIN_SHARED_NGRAM
    gate_enabled: bool = False
    gate_threshold: float = DEFAULT_GATE_THRESHOLD
    rule_weights: dict = field(default_factory=lambda: dict(DEFAULT_RULE_WEIGHTS))
    forecast_terms: tuple = DEFAULT_FORECAST_TERMS
    cause_patterns: tuple = DEFAULT_CAUSE_PATTERNS
    divergence_results_terms: tuple = DEFAULT_DIVERGENCE_RESULTS_TERMS
    divergence_workload_terms: tuple = DEFAULT_DIVERGENCE_WORKLOAD_TERMS
    divergence_contrast_terms: tuple = DEFAULT_DIVERGENCE_CONTRAST_TERMS
    forward_constraint_patterns: tuple = DEFAULT_FORWARD_CONSTRAINT_PATTERNS
    baseline_anchor_patterns: tuple = tuple(_BASELINE_ANCHOR_PATTERNS)

    def weight(self, rule: str) -> float:
        try:
            return float(self.rule_weights.get(rule, 1.0))
        except (TypeError, ValueError):
            return 1.0

    @classmethod
    def from_app_config(cls, app_config: Any) -> 'StoryQualityConfig':
        """Build a config from a Flask app config (or any mapping)."""
        cfg = _dict(app_config) if not hasattr(app_config, 'get') else app_config
        base = cls()
        overrides: dict = {}
        gate_enabled = cfg.get('STORY_QUALITY_GATE_ENABLED')
        if gate_enabled is not None:
            overrides['gate_enabled'] = bool(gate_enabled)
        threshold = cfg.get('STORY_QUALITY_GATE_THRESHOLD')
        if threshold is not None:
            try:
                overrides['gate_threshold'] = float(threshold)
            except (TypeError, ValueError):
                pass
        min_arms = cfg.get('STORY_QUALITY_MIN_NAMED_ARMS')
        if min_arms is not None:
            try:
                overrides['min_named_arms'] = int(min_arms)
            except (TypeError, ValueError):
                pass
        dice = cfg.get('STORY_QUALITY_REDUNDANCY_THRESHOLD')
        if dice is not None:
            try:
                overrides['redundancy_dice_threshold'] = float(dice)
            except (TypeError, ValueError):
                pass
        weights = cfg.get('STORY_QUALITY_RULE_WEIGHTS')
        if isinstance(weights, dict) and weights:
            merged = dict(DEFAULT_RULE_WEIGHTS)
            merged.update(weights)
            overrides['rule_weights'] = merged
        forecast_terms = cfg.get('STORY_QUALITY_FORECAST_TERMS')
        if isinstance(forecast_terms, (list, tuple)) and forecast_terms:
            overrides['forecast_terms'] = tuple(forecast_terms)
        return replace(base, **overrides) if overrides else base


DEFAULT_STORY_QUALITY_CONFIG = StoryQualityConfig()


@dataclass
class StoryView:
    """Normalized view of a finished story object, independent of producer.

    Adapters (``four_beat_story_view`` / ``continuity_note_view``) populate this
    so the rule functions never reach into producer-specific shapes.
    """

    source: str
    story_id: Any = None
    team_id: Any = None
    team_name: Any = None
    team_abbreviation: Any = None
    story_type: Any = None
    is_spread: bool = False
    headline: str = ''
    sentences: list = field(default_factory=list)
    reliever_set: list = field(default_factory=list)

    @property
    def body_text(self) -> str:
        return _clean_text(' '.join(self.sentences))

    @property
    def full_text(self) -> str:
        return _clean_text(' '.join([self.headline, *self.sentences]))


# ── Rule result helper ───────────────────────────────────────────────────────

def _rule(rule: str, passed: bool, reason: str, *, applicable: bool = True, **detail) -> dict:
    result = {
        'rule': rule,
        'passed': bool(passed),
        'applicable': bool(applicable),
        'reason': _clean_text(reason),
    }
    if detail:
        result['detail'] = detail
    return result


# ── Shared text helpers ───────────────────────────────────────────────────────

def _split_sentences(text: str) -> list:
    text = _clean_text(text)
    if not text:
        return []
    matches = [item.strip() for item in _SENTENCE_RE.findall(text) if item.strip()]
    return matches or [text]


def _dedupe_keep_order(sentences) -> list:
    seen = set()
    rows = []
    for sentence in sentences:
        cleaned = _clean_text(sentence)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append(cleaned)
    return rows


def _strip_names(text: str, names) -> str:
    lowered = text
    for name in names:
        name = _clean_text(name)
        if not name:
            continue
        lowered = re.sub(re.escape(name), ' ', lowered, flags=re.IGNORECASE)
        for part in name.split():
            if len(part) > 2:
                lowered = re.sub(rf'\b{re.escape(part)}\b', ' ', lowered, flags=re.IGNORECASE)
    return _clean_text(lowered)


def _names_present(text: str, names) -> list:
    lowered = text.lower()
    present = []
    for name in names:
        name = _clean_text(name)
        if not name:
            continue
        full = re.search(rf'\b{re.escape(name.lower())}\b', lowered)
        last = name.split()[-1] if name.split() else name
        last_hit = len(last) > 2 and re.search(rf'\b{re.escape(last.lower())}\b', lowered)
        if full or last_hit:
            if name not in present:
                present.append(name)
    return present


def _content_tokens(sentence: str, strip_terms) -> list:
    text = _strip_names(sentence, strip_terms)
    text = _NUMBER_RE.sub(' ', text.lower())
    return [
        token
        for token in _WORD_RE.findall(text)
        if token not in _STOPWORDS and len(token) > 2
    ]


def _longest_shared_ngram(a_tokens, b_tokens) -> int:
    """Longest run of contiguous tokens shared between two token lists."""
    if not a_tokens or not b_tokens:
        return 0
    best = 0
    b_len = len(b_tokens)
    for i in range(len(a_tokens)):
        for j in range(b_len):
            length = 0
            while (
                i + length < len(a_tokens)
                and j + length < b_len
                and a_tokens[i + length] == b_tokens[j + length]
            ):
                length += 1
            if length > best:
                best = length
    return best


def _dice(set_a, set_b) -> float:
    if not set_a or not set_b:
        return 0.0
    overlap = len(set_a & set_b)
    return (2 * overlap) / (len(set_a) + len(set_b))


def _any_match(patterns, text: str):
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match
    return None


# ── The five rules ────────────────────────────────────────────────────────────

def _rule_named_arms(view: StoryView, config: StoryQualityConfig, ctx: dict) -> dict:
    present = ctx['names_present']
    needed = config.min_named_arms
    if len(present) >= needed:
        return _rule(
            RULE_NAMED_ARMS, True,
            f"names {', '.join(present[:3])}",
            named=present,
        )
    if not view.reliever_set:
        return _rule(
            RULE_NAMED_ARMS, False,
            'no reliever names available to name in the body',
            named=present,
        )
    if not present:
        return _rule(
            RULE_NAMED_ARMS, False,
            'body names no specific relievers (refers to the group generically)',
            named=present,
        )
    return _rule(
        RULE_NAMED_ARMS, False,
        f"names only {present[0]}; needs at least {needed} of the team's relievers",
        named=present,
    )


def _proximity_windows(sentences) -> list:
    """Each sentence, plus each adjacent pair, so a contrast that spans a
    sentence boundary still reads as "near" without matching across the whole
    document."""
    windows = []
    for index, sentence in enumerate(sentences):
        windows.append(sentence)
        if index + 1 < len(sentences):
            windows.append(f'{sentence} {sentences[index + 1]}')
    return windows


def _divergence_results_label(match) -> str:
    term = _clean_text(match.group(0))
    return term.upper() if term.lower() == 'era' else term


def _has_divergence_frame(sentences_lower, ctx: dict):
    """Return the matched results term when a sentence (or adjacent pair)
    contrasts a results metric against a workload-concentration metric; else
    None. Requires BOTH dimensions plus a contrastive turn, so a workload-only
    restatement (no results dimension) cannot earn divergence credit."""
    for window in _proximity_windows(sentences_lower):
        results_hit = _any_match(ctx['divergence_results_patterns'], window)
        if not results_hit:
            continue
        if not _any_match(ctx['divergence_workload_patterns'], window):
            continue
        if not _any_match(ctx['divergence_contrast_patterns'], window):
            continue
        return results_hit
    return None


def _rule_stated_cause(view: StoryView, config: StoryQualityConfig, ctx: dict) -> dict:
    # Pattern 1 (unchanged): a keyword upstream cause - short starts, game shape,
    # or a roster move.
    match = _any_match(ctx['cause_patterns'], ctx['full_text_lower'])
    if match:
        return _rule(
            RULE_STATED_CAUSE, True,
            f"upstream cause cited (\"{_clean_text(match.group(0))}\")",
            pattern='upstream_cause',
        )
    # Pattern 2 (new): metric-divergence framing - a results metric contrasted
    # against a concentrated workload. Two dimensions, not a circular restate.
    divergence = _has_divergence_frame(ctx['sentences_lower'], ctx)
    if divergence:
        return _rule(
            RULE_STATED_CAUSE, True,
            f'metric-divergence frame ({_divergence_results_label(divergence)} vs. workload)',
            pattern='divergence',
        )
    return _rule(
        RULE_STATED_CAUSE, False,
        'no upstream cause or metric-divergence frame (does not tie the shape to '
        'short starts, game shape, a roster move, or a results-vs-workload '
        'contrast; restating "concentrated" is circular)',
        pattern=None,
    )


def _rule_baseline_anchor(view: StoryView, config: StoryQualityConfig, ctx: dict) -> dict:
    anchor_patterns = ctx['baseline_anchor_patterns']
    unanchored = []
    for sentence in view.sentences:
        figures = _WORKLOAD_PERCENT_RE.findall(sentence) + _PER_ARM_RE.findall(sentence)
        if not figures:
            continue
        window = sentence
        anchored = bool(_any_match(anchor_patterns, window)) or bool(_N_OF_M_RE.search(window))
        if not anchored:
            unanchored.extend(_WORKLOAD_PERCENT_RE.findall(sentence))
            unanchored.extend(
                m.group(0) for m in _PER_ARM_RE.finditer(sentence)
            )
    if not ctx['has_workload_figure']:
        return _rule(
            RULE_BASELINE_ANCHOR, True,
            'no bare workload figure cited (rule does not apply)',
            applicable=False,
        )
    if unanchored:
        sample = _clean_text(unanchored[0])
        return _rule(
            RULE_BASELINE_ANCHOR, False,
            f'workload figure "{sample}" cited with no comparison anchor',
            unanchored=unanchored,
        )
    return _rule(
        RULE_BASELINE_ANCHOR, True,
        'cited workload figures are paired with a comparison anchor',
    )


def _rule_forward_constraint(view: StoryView, config: StoryQualityConfig, ctx: dict) -> dict:
    forecast_hit = _any_match(ctx['forecast_terms'], ctx['forecast_scan_text'])
    if forecast_hit:
        return _rule(
            RULE_FORWARD_CONSTRAINT, False,
            f'forecast/probability language present ("{_clean_text(forecast_hit.group(0))}") - hard fail',
            hard_fail=True,
            banned_term=_clean_text(forecast_hit.group(0)),
        )
    constraint_hit = _any_match(ctx['forward_constraint_patterns'], ctx['full_text_lower'])
    if constraint_hit:
        return _rule(
            RULE_FORWARD_CONSTRAINT, True,
            'forward constraint clause present; no forecast language',
            hard_fail=False,
        )
    return _rule(
        RULE_FORWARD_CONSTRAINT, False,
        'no forward constraint clause (does not say where the next game routes)',
        hard_fail=False,
    )


def _rule_no_redundant_restatement(view: StoryView, config: StoryQualityConfig, ctx: dict) -> dict:
    sentences = view.sentences
    if len(sentences) < 2:
        return _rule(
            RULE_NO_REDUNDANT_RESTATEMENT, True,
            'single sentence - no adjacent pair to compare',
            applicable=False,
        )
    token_lists = [_content_tokens(sentence, ctx['strip_terms']) for sentence in sentences]
    flagged = []
    for index in range(len(sentences) - 1):
        a_tokens, b_tokens = token_lists[index], token_lists[index + 1]
        if not a_tokens or not b_tokens:
            continue
        dice = _dice(set(a_tokens), set(b_tokens))
        shared = _longest_shared_ngram(a_tokens, b_tokens)
        if dice >= config.redundancy_dice_threshold or shared >= config.redundancy_min_shared_ngram:
            flagged.append({
                'pair': [index, index + 1],
                'dice': round(dice, 2),
                'shared_ngram': shared,
                'first': sentences[index],
                'second': sentences[index + 1],
            })
    if flagged:
        worst = flagged[0]
        return _rule(
            RULE_NO_REDUNDANT_RESTATEMENT, False,
            f'adjacent sentences restate each other '
            f'(dice={worst["dice"]}, shared_run={worst["shared_ngram"]})',
            flagged_pairs=flagged,
        )
    return _rule(
        RULE_NO_REDUNDANT_RESTATEMENT, True,
        'no adjacent sentence restates its neighbor',
    )


_RULE_FUNCS = {
    RULE_NAMED_ARMS: _rule_named_arms,
    RULE_STATED_CAUSE: _rule_stated_cause,
    RULE_BASELINE_ANCHOR: _rule_baseline_anchor,
    RULE_FORWARD_CONSTRAINT: _rule_forward_constraint,
    RULE_NO_REDUNDANT_RESTATEMENT: _rule_no_redundant_restatement,
}


# ── Scoring ───────────────────────────────────────────────────────────────────

def score_story_view(view: StoryView, config: StoryQualityConfig | None = None) -> dict:
    """Score one normalized story view against all five rules."""
    config = config or DEFAULT_STORY_QUALITY_CONFIG
    full_text_lower = view.full_text.lower()
    has_workload_figure = bool(
        _WORKLOAD_PERCENT_RE.search(view.body_text) or _PER_ARM_RE.search(view.body_text)
    )
    strip_terms = [
        term for term in [*view.reliever_set, view.team_name, view.team_abbreviation]
        if _clean_text(term)
    ]
    ctx = {
        'full_text_lower': full_text_lower,
        'sentences_lower': [sentence.lower() for sentence in view.sentences],
        'strip_terms': strip_terms,
        'forecast_scan_text': _strip_names(view.full_text, strip_terms).lower(),
        'names_present': _names_present(view.full_text, view.reliever_set),
        'has_workload_figure': has_workload_figure,
        'cause_patterns': _compile(config.cause_patterns),
        'divergence_results_patterns': _compile(config.divergence_results_terms),
        'divergence_workload_patterns': _compile(config.divergence_workload_terms),
        'divergence_contrast_patterns': _compile(config.divergence_contrast_terms),
        'forward_constraint_patterns': _compile(config.forward_constraint_patterns),
        'forecast_terms': _compile(config.forecast_terms),
        'baseline_anchor_patterns': _compile(config.baseline_anchor_patterns),
    }

    rules = {}
    for rule_key in RULE_ORDER:
        rules[rule_key] = _RULE_FUNCS[rule_key](view, config, ctx)

    rules_passed = sum(1 for result in rules.values() if result['passed'])
    rules_evaluated = len(rules)
    total_weight = sum(config.weight(rule_key) for rule_key in RULE_ORDER) or 1.0
    earned_weight = sum(
        config.weight(rule_key) for rule_key, result in rules.items() if result['passed']
    )
    score = round((earned_weight / total_weight) * 100, 1)
    hard_fail = bool(
        _dict(rules[RULE_FORWARD_CONSTRAINT].get('detail')).get('hard_fail')
    )
    fail_reasons = [
        f"{rule_key}: {rules[rule_key]['reason']}"
        for rule_key in RULE_ORDER
        if not rules[rule_key]['passed']
    ]
    meets_threshold = score >= config.gate_threshold and not hard_fail
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': SOURCE,
        'story_source': view.source,
        'story_id': view.story_id,
        'team_id': view.team_id,
        'team_name': view.team_name,
        'team_abbreviation': view.team_abbreviation,
        'story_type': view.story_type,
        'score': score,
        'score_scale': 'weighted_0_100',
        'rules_passed': rules_passed,
        'rules_evaluated': rules_evaluated,
        'rules': rules,
        'fail_reasons': fail_reasons,
        'hard_fail': hard_fail,
        'gate_threshold': config.gate_threshold,
        'meets_threshold': meets_threshold,
    }


# ── Producer adapters ─────────────────────────────────────────────────────────

def reliever_names_from_story(story: dict) -> list:
    """Collect every reliever name a four-beat story object carries.

    Mirrors story_evidence's name sourcing so Rule 1 can validate body names
    against the team's known reliever set rather than guessing at capitalized
    tokens.
    """
    story = _dict(story)
    names: list = []

    def _add(values):
        for value in _list(values):
            name = _clean_text(value)
            if name and name not in names:
                names.append(name)

    _add(_dict(story.get('story_evidence')).get('pitcher_names'))
    _add(_dict(story.get('story_facts')).get('named_pitchers'))
    _add(_dict(story.get('story_voice')).get('pitcher_names'))
    lead_fields = _dict(story.get('lead_fields'))
    computed = _dict(story.get('computed'))
    for source in (
        lead_fields.get('high_risk_arm_names'),
        lead_fields.get('clean_trust_names'),
        lead_fields.get('top_workload_names'),
        computed.get('top_workload_names'),
        computed.get('clean_trust_names'),
        computed.get('high_risk_arm_names'),
    ):
        _add(source)
    return names


def four_beat_story_view(story: dict) -> StoryView:
    """Adapt a four-beat feed story object into a normalized StoryView."""
    story = _dict(story)
    voice = _dict(story.get('story_voice'))
    evidence = _dict(story.get('story_evidence'))
    headline = _clean_text(story.get('title') or voice.get('headline'))

    # The reader-facing body: the voice triple (where the deployed cards'
    # framing/evidence/consequence live) followed by the rendered narrative.
    ordered = [
        voice.get('human_frame'),
        evidence.get('evidence_statement') or voice.get('evidence_sentence'),
        evidence.get('consequence_statement') or voice.get('consequence_sentence'),
    ]
    narrative = _clean_text(story.get('narrative')) or _clean_text(story.get('body'))
    ordered.extend(_split_sentences(narrative))
    disclosure = _clean_text(story.get('disclosure_note'))
    if disclosure:
        ordered.extend(_split_sentences(disclosure))
    sentences = _dedupe_keep_order(ordered)

    category = _normalize(evidence.get('consequence_category'))
    is_spread = category == 'more_stable_bullpen_shape' or 'distribution' in _normalize(
        story.get('rule_key')
    )
    return StoryView(
        source=SOURCE_FOUR_BEAT,
        story_id=story.get('story_id'),
        team_id=story.get('team_id'),
        team_name=story.get('team_name'),
        team_abbreviation=story.get('team_abbreviation'),
        story_type=story.get('rule_key') or voice.get('observation_type'),
        is_spread=is_spread,
        headline=headline,
        sentences=sentences,
        reliever_set=reliever_names_from_story(story),
    )


def _continuity_reliever_set(note: dict) -> list:
    evidence = _dict(_dict(note.get('continuity')).get('evidence'))
    names: list = []
    for row in _list(evidence.get('top_two_pitchers')):
        name = _clean_text(_dict(row).get('pitcher_name'))
        if name and name not in names:
            names.append(name)
    single = _clean_text(evidence.get('pitcher_name'))
    if single and single not in names:
        names.append(single)
    return names


def continuity_note_view(note: dict, *, reliever_set=None) -> StoryView:
    """Adapt a narrative-memory continuity / flagship note into a StoryView."""
    note = _dict(note)
    continuity = _dict(note.get('continuity'))
    text = _clean_text(note.get('continuity_note'))
    names = list(reliever_set) if reliever_set else _continuity_reliever_set(note)
    return StoryView(
        source=SOURCE_CONTINUITY,
        story_id=note.get('story_id') or f"continuity:{note.get('team_id')}:{continuity.get('type')}",
        team_id=note.get('team_id'),
        team_name=note.get('team_name'),
        team_abbreviation=note.get('team_abbreviation'),
        story_type=continuity.get('type'),
        headline='',
        sentences=_split_sentences(text),
        reliever_set=names,
    )


def score_four_beat_story(story: dict, config: StoryQualityConfig | None = None) -> dict:
    return score_story_view(four_beat_story_view(story), config)


def score_continuity_note(note: dict, config: StoryQualityConfig | None = None, *, reliever_set=None) -> dict:
    return score_story_view(continuity_note_view(note, reliever_set=reliever_set), config)


# ── Aggregation + gate ────────────────────────────────────────────────────────

def _score_distribution(scorecards) -> dict:
    distribution = {index: 0 for index in range(0, 6)}
    for card in scorecards:
        distribution[int(card.get('rules_passed', 0))] = (
            distribution.get(int(card.get('rules_passed', 0)), 0) + 1
        )
    return distribution


def _per_rule_fail_counts(scorecards) -> dict:
    counts = {rule_key: 0 for rule_key in RULE_ORDER}
    for card in scorecards:
        for rule_key, result in _dict(card.get('rules')).items():
            if not result.get('passed'):
                counts[rule_key] = counts.get(rule_key, 0) + 1
    return counts


def summarize_scorecards(scorecards, config: StoryQualityConfig | None = None, *, mode='report_only') -> dict:
    """Aggregate scorecards into an audit-style summary surface."""
    config = config or DEFAULT_STORY_QUALITY_CONFIG
    scorecards = list(scorecards)
    scored = len(scorecards)
    meets = [card for card in scorecards if card.get('meets_threshold')]
    below = [card for card in scorecards if not card.get('meets_threshold')]
    avg_score = round(sum(card.get('score', 0) for card in scorecards) / scored, 1) if scored else 0.0
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'mode': mode,
        'gate_enabled': config.gate_enabled,
        'gate_threshold': config.gate_threshold,
        'scored_count': scored,
        'passing_count': len(meets),
        'below_threshold_count': len(below),
        'hard_fail_count': sum(1 for card in scorecards if card.get('hard_fail')),
        'average_score': avg_score,
        'score_distribution_by_rules_passed': _score_distribution(scorecards),
        'rule_fail_counts': _per_rule_fail_counts(scorecards),
        'below_threshold': [
            {
                'story_id': card.get('story_id'),
                'team_id': card.get('team_id'),
                'team_abbreviation': card.get('team_abbreviation'),
                'story_type': card.get('story_type'),
                'score': card.get('score'),
                'rules_passed': card.get('rules_passed'),
                'hard_fail': card.get('hard_fail'),
                'fail_reasons': card.get('fail_reasons'),
            }
            for card in below
        ],
    }


def apply_story_quality_gate(stories, config: StoryQualityConfig | None = None):
    """Score every four-beat story and, when enforcing, hold the weak ones.

    Returns ``(published, held, summary)``. The scorecard is attached to each
    story under ``story['story_quality']`` either way. In report-only mode
    (``gate_enabled`` off - the default) nothing is held and ``published`` is the
    input list unchanged in length and order, so feed behavior is identical to a
    build without the contract. The summary still reports what *would* be held.
    """
    config = config or DEFAULT_STORY_QUALITY_CONFIG
    stories = _list(stories)
    scorecards = []
    published = []
    held = []
    for story in stories:
        card = score_four_beat_story(story, config)
        if isinstance(story, dict):
            story['story_quality'] = card
        scorecards.append(card)
        if config.gate_enabled and not card.get('meets_threshold'):
            held.append({
                'story_id': card.get('story_id'),
                'team_id': card.get('team_id'),
                'team_name': card.get('team_name'),
                'team_abbreviation': card.get('team_abbreviation'),
                'story_type': card.get('story_type'),
                'score': card.get('score'),
                'rules_passed': card.get('rules_passed'),
                'hard_fail': card.get('hard_fail'),
                'fail_reasons': card.get('fail_reasons'),
            })
            continue
        published.append(story)
    mode = 'enforcing' if config.gate_enabled else 'report_only'
    summary = summarize_scorecards(scorecards, config, mode=mode)
    summary['published_count'] = len(published)
    summary['held_count'] = len(held)
    return published, held, summary


def score_continuity_payload(continuity_payload: dict, config: StoryQualityConfig | None = None) -> dict:
    """Score & annotate a dashboard continuity payload (flagship notes).

    Annotates each team's note with ``story_quality`` and returns a summary.
    In enforcing mode, teams whose note is below threshold are marked
    ``story_quality_held=True`` (the note is preserved, not dropped, so callers
    decide how to present it). Report-only leaves the payload's notes intact.
    """
    config = config or DEFAULT_STORY_QUALITY_CONFIG
    payload = deepcopy(_dict(continuity_payload))
    teams = _dict(payload.get('teams'))
    scorecards = []
    for team_key, note in teams.items():
        if not isinstance(note, dict):
            continue
        card = score_continuity_note(note, config)
        note['story_quality'] = card
        if config.gate_enabled and not card.get('meets_threshold'):
            note['story_quality_held'] = True
        scorecards.append(card)
    mode = 'enforcing' if config.gate_enabled else 'report_only'
    payload['story_quality'] = summarize_scorecards(scorecards, config, mode=mode)
    return payload


# ── Debug instrumentation ─────────────────────────────────────────────────────

def build_story_quality_debug_dump(feed_payload: dict, *, team_id=None) -> dict:
    """Dump, per team, the story plus its full rule-by-rule scorecard.

    Reads a four-beat feed payload (items already carry ``story_quality`` once
    the gate has run) so the *why* of a pass/fail is inspectable without
    re-running generation. Pass ``team_id`` to filter to one club.
    """
    payload = _dict(feed_payload)
    rows = []
    for story in _list(payload.get('items')) + _list(payload.get('story_quality_held')):
        story = _dict(story)
        if team_id is not None and story.get('team_id') != team_id:
            continue
        card = _dict(story.get('story_quality'))
        if not card and story.get('rule_key'):
            card = score_four_beat_story(story)
        rows.append({
            'team_id': story.get('team_id'),
            'team_name': story.get('team_name'),
            'team_abbreviation': story.get('team_abbreviation'),
            'story_id': story.get('story_id'),
            'story_type': story.get('rule_key') or story.get('story_type'),
            'title': story.get('title'),
            'narrative': story.get('narrative') or story.get('body'),
            'score': card.get('score'),
            'rules_passed': card.get('rules_passed'),
            'meets_threshold': card.get('meets_threshold'),
            'hard_fail': card.get('hard_fail'),
            'rules': card.get('rules'),
            'fail_reasons': card.get('fail_reasons'),
        })
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': SOURCE,
        'team_id_filter': team_id,
        'story_count': len(rows),
        'story_quality_summary': payload.get('story_quality'),
        'stories': rows,
    }


__all__ = [
    'CAPABILITY',
    'VERSION',
    'RULE_ORDER',
    'RULE_NAMED_ARMS',
    'RULE_STATED_CAUSE',
    'RULE_BASELINE_ANCHOR',
    'RULE_FORWARD_CONSTRAINT',
    'RULE_NO_REDUNDANT_RESTATEMENT',
    'StoryQualityConfig',
    'DEFAULT_STORY_QUALITY_CONFIG',
    'StoryView',
    'four_beat_story_view',
    'continuity_note_view',
    'reliever_names_from_story',
    'score_story_view',
    'score_four_beat_story',
    'score_continuity_note',
    'summarize_scorecards',
    'apply_story_quality_gate',
    'score_continuity_payload',
    'build_story_quality_debug_dump',
]
