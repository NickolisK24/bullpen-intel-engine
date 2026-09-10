"""Versioned rule and claim-template registry for Phase 0D evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from string import Formatter

from models.evidence_contract import EvidenceObject
from services.evidence_language import assert_claim_language_allowed


class EvidenceRuleError(AssertionError):
    """Raised when an evidence rule or template violates the contract."""


class EvidenceRuleNotRegistered(EvidenceRuleError):
    """Raised when a caller tries to emit evidence for an unregistered rule."""


@dataclass(frozen=True)
class EvidenceRule:
    rule_id: str
    rule_version: int
    evidence_type: str
    plain_language_definition: str
    required_input_families: tuple[str, ...]
    required_cited_fields: tuple[str, ...]
    allowed_completeness: tuple[str, ...] = (
        EvidenceObject.COMPLETENESS_COMPLETE,
        EvidenceObject.COMPLETENESS_PARTIAL,
        EvidenceObject.COMPLETENESS_UNKNOWN,
        EvidenceObject.COMPLETENESS_CONFLICT,
        EvidenceObject.COMPLETENESS_WITHHELD,
    )
    posture_default: str = EvidenceObject.POSTURE_INTERNAL_ONLY
    thresholds: dict = field(default_factory=dict)

    @property
    def definition_hash(self) -> str:
        payload = '|'.join((
            self.rule_id,
            str(self.rule_version),
            self.evidence_type,
            self.plain_language_definition,
            ','.join(self.required_input_families),
            ','.join(self.required_cited_fields),
            ','.join(self.allowed_completeness),
            self.posture_default,
            repr(sorted((self.thresholds or {}).items())),
        ))
        return sha256(payload.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class ClaimTemplate:
    template_id: str
    template_version: int
    template_text: str

    @property
    def placeholders(self) -> set[str]:
        return {
            field_name
            for _, field_name, _, _ in Formatter().parse(self.template_text)
            if field_name
        }


class EvidenceRuleRegistry:
    def __init__(self):
        self._rules: dict[tuple[str, int], EvidenceRule] = {}

    def register(self, rule: EvidenceRule) -> EvidenceRule:
        validate_evidence_rule(rule)
        key = (rule.rule_id, rule.rule_version)
        if key in self._rules:
            raise EvidenceRuleError(
                f'duplicate evidence rule: {rule.rule_id} v{rule.rule_version}'
            )
        self._rules[key] = rule
        return rule

    def get(self, rule_id: str, rule_version: int | None = None) -> EvidenceRule:
        if rule_version is not None:
            try:
                return self._rules[(rule_id, rule_version)]
            except KeyError as exc:
                raise EvidenceRuleNotRegistered(
                    f'evidence rule not registered: {rule_id} v{rule_version}'
                ) from exc
        matches = [
            rule
            for (registered_rule_id, _), rule in self._rules.items()
            if registered_rule_id == rule_id
        ]
        if not matches:
            raise EvidenceRuleNotRegistered(f'evidence rule not registered: {rule_id}')
        return sorted(matches, key=lambda item: item.rule_version)[-1]

    def all_rules(self) -> tuple[EvidenceRule, ...]:
        return tuple(
            self._rules[key]
            for key in sorted(self._rules, key=lambda item: (item[0], item[1]))
        )


class ClaimTemplateRegistry:
    def __init__(self):
        self._templates: dict[tuple[str, int], ClaimTemplate] = {}

    def register(self, template: ClaimTemplate) -> ClaimTemplate:
        validate_claim_template(template)
        key = (template.template_id, template.template_version)
        if key in self._templates:
            raise EvidenceRuleError(
                f'duplicate claim template: {template.template_id} v{template.template_version}'
            )
        self._templates[key] = template
        return template

    def get(self, template_id: str, template_version: int | None = None) -> ClaimTemplate:
        if template_version is not None:
            try:
                return self._templates[(template_id, template_version)]
            except KeyError as exc:
                raise EvidenceRuleError(
                    f'claim template not registered: {template_id} v{template_version}'
                ) from exc
        matches = [
            template
            for (registered_template_id, _), template in self._templates.items()
            if registered_template_id == template_id
        ]
        if not matches:
            raise EvidenceRuleError(f'claim template not registered: {template_id}')
        return sorted(matches, key=lambda item: item.template_version)[-1]


evidence_rule_registry = EvidenceRuleRegistry()
claim_template_registry = ClaimTemplateRegistry()


def validate_evidence_rule(rule: EvidenceRule) -> bool:
    if not rule.rule_id:
        raise EvidenceRuleError('evidence rule requires rule_id')
    if not isinstance(rule.rule_version, int) or rule.rule_version <= 0:
        raise EvidenceRuleError('evidence rule requires positive integer rule_version')
    if not rule.evidence_type:
        raise EvidenceRuleError('evidence rule requires evidence_type')
    if not (rule.plain_language_definition or '').strip():
        raise EvidenceRuleError('evidence rule requires plain-language definition')
    if not rule.required_input_families:
        raise EvidenceRuleError('evidence rule requires input source families')
    if not rule.required_cited_fields:
        raise EvidenceRuleError('evidence rule requires cited fields')
    if rule.posture_default not in (
        EvidenceObject.POSTURE_INTERNAL_ONLY,
        EvidenceObject.POSTURE_PUBLIC_CANDIDATE,
    ):
        raise EvidenceRuleError(f'unsupported evidence posture: {rule.posture_default}')
    allowed_states = {
        EvidenceObject.COMPLETENESS_COMPLETE,
        EvidenceObject.COMPLETENESS_PARTIAL,
        EvidenceObject.COMPLETENESS_UNKNOWN,
        EvidenceObject.COMPLETENESS_CONFLICT,
        EvidenceObject.COMPLETENESS_WITHHELD,
    }
    if not set(rule.allowed_completeness).issubset(allowed_states):
        raise EvidenceRuleError('evidence rule allows unsupported completeness state')
    definition = rule.plain_language_definition
    for threshold_name, threshold_value in (rule.thresholds or {}).items():
        if str(threshold_value) not in definition:
            raise EvidenceRuleError(
                f'threshold {threshold_name}={threshold_value!r} must appear in definition'
            )
    return True


def validate_claim_template(template: ClaimTemplate) -> bool:
    if not template.template_id:
        raise EvidenceRuleError('claim template requires template_id')
    if not isinstance(template.template_version, int) or template.template_version <= 0:
        raise EvidenceRuleError('claim template requires positive integer template_version')
    if not (template.template_text or '').strip():
        raise EvidenceRuleError('claim template requires template text')
    assert_claim_language_allowed(template.template_text)
    return True


def render_claim_template(template: ClaimTemplate, values: dict) -> str:
    validate_claim_template(template)
    missing = sorted(template.placeholders - set(values))
    if missing:
        raise EvidenceRuleError(f'claim template missing values: {missing}')
    rendered = template.template_text.format_map(_StrictFormatValues(values))
    assert_claim_language_allowed(rendered)
    return rendered


def register_evidence_rule(rule: EvidenceRule) -> EvidenceRule:
    return evidence_rule_registry.register(rule)


def register_claim_template(template: ClaimTemplate) -> ClaimTemplate:
    return claim_template_registry.register(template)


class _StrictFormatValues(dict):
    def __missing__(self, key):
        raise EvidenceRuleError(f'claim template missing value: {key}')
