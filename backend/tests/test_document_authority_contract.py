"""Document-authority contracts (H-12).

The H-12 audit found nine ways the documentation set could tell a contributor
two different current truths. Prose cannot guard itself, so the defect classes
that are mechanically checkable are pinned here.

What this file guards, and why each one earned a test:

  * **Game-driven mode.** `GAME_DRIVEN_DAILY_INGESTION.md` said the lane was
    `off` in three places while the workflow ran it in `shadow` — and said
    `shadow` in a fourth place, in the same file. The workflow is the fact; the
    document must agree with it.

  * **D-051.** Canonical 04 listed "manual founder/admin sync" as a supported
    operational mode and `SYNC_PIPELINE.md` required a manual daily recovery run
    as OPS-002 proof, both after D-051 retired authoritative manual daily
    execution. The Authority Order sends a reader to canonical 04 first, so the
    stale side was the one they would reach.

  * **Named reads.** Canonical 06 kept its own named-bullpen-read table, and it
    had drifted from 02/03 — including the team-level `Clean Options` that the
    two higher-ranked standards forbid borrowing from the arm-read family.

  * **Code-cited document paths.** API metadata told consumers its governing
    policy lived at seven paths that no longer exist.

These are exact, named checks, not a generic markdown parser. A document may
still describe a retired posture as history; every assertion below is scoped to
current-state text or bounded by an explicit historical marker.
"""

from pathlib import Path
import re

REPO_ROOT = Path(__file__).resolve().parents[2]

DOCS = REPO_ROOT / 'docs'
CANONICAL = DOCS / 'canonical'
CURRENT = DOCS / 'current'
WORKFLOW_PATH = REPO_ROOT / '.github' / 'workflows' / 'baseballos-sync.yml'

GAME_DRIVEN_DOC = CURRENT / 'GAME_DRIVEN_DAILY_INGESTION.md'
SYNC_PIPELINE_DOC = CURRENT / 'SYNC_PIPELINE.md'
TRUSTED_SERVING_DOC = CURRENT / 'TRUSTED_PUBLIC_SERVING_AUTHORITY.md'
ARCHITECTURE_DOC = CANONICAL / '04_PLATFORM_ARCHITECTURE_OPERATIONS.md'
INTELLIGENCE_DOC = CANONICAL / '02_BULLPEN_INTELLIGENCE_STANDARD.md'
EXPERIENCE_DOC = CANONICAL / '03_PRODUCT_EXPERIENCE_STANDARD.md'
EDITORIAL_DOC = CANONICAL / '06_EDITORIAL_DISTRIBUTION_STANDARD.md'


def read(path):
    return path.read_text(encoding='utf-8')


class TestGameDrivenModeAgreement:
    """The workflow is the fact. The document must not contradict it."""

    def test_workflow_runs_daily_and_postgame_in_shadow(self):
        workflow = read(WORKFLOW_PATH)
        shadow_settings = re.findall(
            r"GAME_DRIVEN_INGESTION_MODE:\s*'shadow'", workflow
        )

        # Two runner steps, daily and postgame, and nowhere else.
        assert len(shadow_settings) == 2

    def test_workflow_sets_backfill_off_explicitly(self):
        workflow = read(WORKFLOW_PATH)

        assert re.search(r"GAME_DRIVEN_INGESTION_MODE:\s*'off'", workflow)

    def test_document_states_shadow_as_the_current_production_value(self):
        doc = read(GAME_DRIVEN_DOC)

        assert 'daily `shadow`, postgame `shadow`, explicit backfill `off`' in doc
        assert 'The lane runs automatically in `shadow`' in doc

    def test_document_makes_no_current_off_claim_for_the_observed_cycles(self):
        """The three sentences that said production was `off`, plus their shape.

        Each of these was a current-state claim at the time it was written and
        became false when shadow activation shipped. They are pinned by their
        exact retired wording so the same sentence cannot return, and by a
        pattern so a reworded twin cannot either.
        """
        doc = read(GAME_DRIVEN_DOC)

        assert '**`GAME_DRIVEN_INGESTION_MODE` remains `off`.**' not in doc
        assert '`off` | nothing. **This is the current production value.**' not in doc
        assert 'Production is `off` and stays `off`' not in doc

        # No sentence may pair "current production" with `off` again.
        assert not re.search(
            r'current production value[^\n]*`off`|`off`[^\n]*current production value',
            doc,
        )


class TestManualDailyExecutionAgreement:
    """D-051 retired authoritative manual daily execution. Every current
    operations document must agree, and the canonical one must say so itself."""

    def test_architecture_does_not_list_manual_daily_sync_as_supported(self):
        doc = read(ARCHITECTURE_DOC)
        # Scoped to the standard's body: the revision history is allowed to
        # name the mode it removed, which is how the removal stays legible.
        body = doc.split('## Revision History', 1)[0]

        assert 'manual founder/admin sync' not in body
        assert (
            '**Authoritative manual daily execution is not a supported mode.**'
            in doc
        )

    def test_architecture_carries_the_current_writer_authority_answer(self):
        """Canonical 04 was silent on the highest-risk operations question, so
        the rank-7 runbooks answered it alone — and disagreed."""
        doc = read(ARCHITECTURE_DOC)

        assert '### Current baseball-data authority' in doc
        assert 'legacy daily/postgame path remains the authoritative baseball-data writer' in doc
        assert '`shadow` on the daily and postgame cycles' in doc
        assert 'Shadow observation grants no durable write authority' in doc

    def test_sync_pipeline_does_not_require_a_manual_daily_recovery_run(self):
        doc = read(SYNC_PIPELINE_DOC)
        proof_section = doc.split('## 10. OPS-002 Production Proof', 1)[1]
        requirement, _, history = proof_section.partition('**Historical note.**')

        # The live requirement list is free of it; the historical note may name
        # the retired criterion, which is how a supersession stays legible.
        assert 'manual daily recovery run' not in requirement
        assert 'controlled manual daily recovery run' in history

    def test_sync_pipeline_daily_trigger_is_schedule_only(self):
        doc = read(SYNC_PIPELINE_DOC)

        assert (
            '| `daily` | scheduled morning run only (first attempt) |' in doc
        )

    def test_trusted_serving_still_owns_the_current_ops_002_criteria(self):
        doc = read(TRUSTED_SERVING_DOC)

        assert (
            'D-051 retires the controlled-manual-daily recovery criterion' in doc
        )
        assert 'A manually re-run scheduled job is not eligible proof.' in doc


class TestNamedReadAgreement:
    """Canonical 06 may repeat the named reads. It may not define a second set."""

    CANONICAL_SUPPORTING_READS = (
        'Late-Inning Availability',
        'Rested Options',
        'Late-Inning Pressure',
        'Workload Concentration',
        'Coverage Safety',
        'Depth Safety',
        'Late-Inning Options',
    )

    def test_higher_ranked_standards_agree_on_the_supporting_read_set(self):
        intelligence = read(INTELLIGENCE_DOC)
        experience = read(EXPERIENCE_DOC)

        for term in self.CANONICAL_SUPPORTING_READS:
            assert term in intelligence
            assert term in experience

    def test_editorial_named_reads_match_the_canonical_set(self):
        doc = read(EDITORIAL_DOC)
        row = next(
            line for line in doc.splitlines()
            if line.startswith('| Named bullpen reads |')
        )
        listed = [term.strip() for term in row.split('|')[2].split(',')]

        assert listed == list(self.CANONICAL_SUPPORTING_READS)

    def test_editorial_does_not_borrow_the_arm_read_word_for_a_team_read(self):
        """`Clean Option` is a pitcher current read. `Clean Options` was the
        retired team-level borrow of it, and 02/03 forbid the borrowing."""
        doc = read(EDITORIAL_DOC)
        row = next(
            line for line in doc.splitlines()
            if line.startswith('| Named bullpen reads |')
        )

        assert 'Clean Options' not in row

    def test_editorial_defers_to_the_higher_ranked_owners(self):
        doc = read(EDITORIAL_DOC)

        assert 'Bullpen Intelligence Standard' in doc
        assert 'the canonical owners are authoritative' in doc


class TestWorkloadDataHasACanonicalHome:
    """#659 shipped the Workload Data family into the product with no canonical
    definition behind it. The catalogue lives in shared frontend utilities; the
    meaning has to live in the standards."""

    def test_intelligence_standard_defines_the_family(self):
        doc = read(INTELLIGENCE_DOC)

        assert '### Workload Data' in doc
        assert '| Workload Data |' in doc

    def test_experience_standard_defines_the_public_field(self):
        doc = read(EXPERIENCE_DOC)

        assert '### Workload Data' in doc

    def test_both_standards_separate_workload_data_from_data_status(self):
        """The two answer different questions about different subjects — one
        arm's workload record versus the published read — which is the entire
        reason the family was split out in the first place."""
        intelligence = read(INTELLIGENCE_DOC)
        experience = read(EXPERIENCE_DOC)

        assert 'Workload Data is not Data Status' in intelligence
        assert 'Workload Data is not Data Status' in experience


class TestCanonicalVersionIntegrity:
    """Canonical README requires a version, an effective date, and a revision
    history entry for every content change. Canonical 06 was edited on
    August 11 with none of the three."""

    TOUCHED = (
        (CANONICAL / '01_BASEBALLOS_CONSTITUTION.md', '1.1', 'August 14, 2026'),
        (ARCHITECTURE_DOC, '1.6', 'August 14, 2026'),
        (EDITORIAL_DOC, '1.3', 'August 14, 2026'),
        (INTELLIGENCE_DOC, '1.4', 'August 14, 2026'),
        (EXPERIENCE_DOC, '1.5', 'August 14, 2026'),
    )

    def test_touched_canonical_documents_declare_their_version_and_date(self):
        for path, version, effective in self.TOUCHED:
            doc = read(path)
            assert f'| Version | {version} |' in doc, path.name
            assert f'| Effective date | {effective} |' in doc, path.name

    def test_touched_canonical_documents_record_the_revision(self):
        for path, version, effective in self.TOUCHED:
            doc = read(path)
            history = doc.split('## Revision History', 1)[1]
            assert f'| {version} | {effective} |' in history, path.name

    def test_editorial_records_the_unversioned_august_11_edit(self):
        """The correction is appended, not silently rewritten: the August 11
        content change is named in the history that omitted it."""
        history = read(EDITORIAL_DOC).split('## Revision History', 1)[1]

        assert 'August 11, 2026' in history


class TestCodeCitedDocumentPaths:
    """Every document path a live code constant advertises must resolve.

    Seven of these were dead. They were not comments: `recommendations.py`,
    `team_operations.py`, and `api_assembly.py` ship them in response metadata,
    so the API was naming its governing policy at paths that did not exist —
    and the documents behind them were archived phase records rather than the
    canonical library that reserves current authority to itself.

    An explicit list, not a string scan. A generic sweep over the repository
    would flag fixture paths and prose and teach the next contributor to ignore
    it.
    """

    def _constants(self):
        from api import recommendations, team_operations
        from observations import api_assembly
        from recommendation.engine import RecommendationEngine
        from services import availability_post_adoption_readiness as readiness

        cited = [
            ('recommendations.CONTRACT_DOCUMENT', recommendations.CONTRACT_DOCUMENT),
            ('recommendations.POLICY_DOCUMENT', recommendations.POLICY_DOCUMENT),
            (
                'recommendations.V2_CONTRACT_DOCUMENT',
                recommendations.V2_CONTRACT_DOCUMENT,
            ),
            (
                'team_operations.TEAM_OPERATIONS_READINESS_DOCUMENT',
                team_operations.TEAM_OPERATIONS_READINESS_DOCUMENT,
            ),
            (
                'team_operations.TEAM_OPERATIONS_CONTRACT_DOCUMENT',
                team_operations.TEAM_OPERATIONS_CONTRACT_DOCUMENT,
            ),
            (
                'api_assembly.OBSERVATION_API_DOCUMENT',
                api_assembly.OBSERVATION_API_DOCUMENT,
            ),
            (
                'RecommendationEngine.policy_document',
                RecommendationEngine.policy_document,
            ),
        ]
        cited += [
            (f'readiness.CURRENT_THRESHOLD_DOCS[{index}]', value)
            for index, value in enumerate(readiness.CURRENT_THRESHOLD_DOCS)
        ]
        return cited

    def test_every_cited_document_exists(self):
        for name, relative in self._constants():
            assert (REPO_ROOT / relative).is_file(), f'{name} -> {relative}'

    def test_no_cited_document_is_an_archived_phase_record(self):
        """Archived records may be read as history. They may not be advertised
        to an API consumer as the contract the response obeys."""
        for name, relative in self._constants():
            assert not relative.startswith('docs/archive/'), f'{name} -> {relative}'

    def test_cited_documents_are_canonical_or_current_methodology(self):
        allowed = ('docs/canonical/', 'docs/methodology/', 'docs/current/')
        for name, relative in self._constants():
            assert relative.startswith(allowed), f'{name} -> {relative}'

    def test_the_retired_dead_paths_do_not_return(self):
        from api import recommendations, team_operations
        from observations import api_assembly

        sources = [
            REPO_ROOT / 'backend' / 'api' / 'recommendations.py',
            REPO_ROOT / 'backend' / 'api' / 'team_operations.py',
            REPO_ROOT / 'backend' / 'observations' / 'api_assembly.py',
            REPO_ROOT / 'backend' / 'recommendation' / 'engine.py',
        ]
        retired = (
            "'docs/RECOMMENDATION_ENGINE_V1_POLICY.md'",
            "'docs/RECOMMENDATION_ENGINE_V1_API_CONTRACT.md'",
            "'docs/RECOMMENDATION_ENGINE_V1_IMPLEMENTATION_PLAN.md'",
            "'docs/RECOMMENDATION_ENGINE_V2_API_CONTRACT.md'",
            "'docs/V5_PHASE_6_OBSERVATION_API_SURFACE.md'",
        )
        for path in sources:
            text = read(path)
            for dead in retired:
                assert dead not in text, f'{path.name}: {dead}'

        # And the modules import cleanly with the constants in place.
        assert recommendations.recommendations_bp is not None
        assert team_operations.team_operations_bp is not None
        assert api_assembly.OBSERVATION_API_ROUTE == '/api/observations'


class TestSecondaryDocumentStatus:
    """The specific documents H-12 found reading as current authority.

    Narrow on purpose. This is a regression guard on known authority-risk
    files, not a repository-wide formatting rule: requiring a banner on every
    markdown file would produce a lot of banners and no more clarity.
    """

    # Each file, and a phrase that must appear near the top establishing what
    # it is. The phrase is specific to the file's actual classification — a
    # single shared banner string would let a wrong classification pass.
    BANNERED = (
        ('docs/governance/CERTIFICATION_LEDGER.md',
         'Status: Historical evidence — not current product authority.'),
        ('docs/governance/OPERATIONAL_REVIEWS.md',
         'Status: Historical evidence — not current product authority.'),
        ('docs/product/BASEBALLOS_STORY_RULES.md',
         'Subsystem implementation reference — secondary authority.'),
        ('docs/methodology/ROSTER_AUTHORITY_V1.md',
         'Implementation contract for roster authority'),
        ('backend/COIN_Philosophy.md',
         'Status: Philosophy and reference note — not canonical authority.'),
        ('frontend/docs/dashboard_trust_strip_polish.md',
         'Status: Historical implementation record — superseded wording.'),
        ('docs/archive/2026-08/PRODUCT_ROADMAP_DECISION_LEDGER_PRE_V3.md',
         'Archived historical snapshot — superseded by'),
    )

    HEAD_LINES = 30

    def test_each_ambiguous_document_declares_its_status_near_the_top(self):
        for relative, phrase in self.BANNERED:
            path = REPO_ROOT / relative
            assert path.is_file(), relative
            head = '\n'.join(read(path).splitlines()[:self.HEAD_LINES])
            assert phrase in head, relative

    def test_each_superseded_design_spec_is_bannered(self):
        design = DOCS / 'design'
        specs = sorted(design.glob('*.md'))

        assert specs, 'docs/design is expected to still exist as history'
        for path in specs:
            head = '\n'.join(read(path).splitlines()[:self.HEAD_LINES])
            assert 'Status: Superseded' in head, path.name
            assert '03_PRODUCT_EXPERIENCE_STANDARD.md' in head, path.name

    def test_governance_ledgers_do_not_present_june_state_as_current(self):
        for relative in (
            'docs/governance/CERTIFICATION_LEDGER.md',
            'docs/governance/OPERATIONAL_REVIEWS.md',
        ):
            text = read(REPO_ROOT / relative)
            assert '## Current Certification Summary' not in text, relative
            assert '## Current Operational Status' not in text, relative

    def test_roster_authority_does_not_claim_the_global_source_of_truth(self):
        """Only the six canonical documents may call themselves the source of
        truth. This one is the in-code roster object's contract."""
        text = read(REPO_ROOT / 'docs/methodology/ROSTER_AUTHORITY_V1.md')

        assert 'Single source of roster truth' not in text
        assert '02_BULLPEN_INTELLIGENCE_STANDARD.md' in text


class TestDocumentationMapCompleteness:
    """The map is the repository's navigation authority. Its own paths must
    resolve, and the documentation living outside `docs/` must be classified
    rather than left for a reader to guess at."""

    MAP = DOCS / 'REPOSITORY_DOCUMENTATION_MAP.md'

    def test_the_map_no_longer_names_a_directory_that_does_not_exist(self):
        text = read(self.MAP)

        assert '`docs/reports/`,' not in text
        assert not (DOCS / 'reports').exists()
        assert (REPO_ROOT / 'backend' / 'reports').is_dir()

    def test_out_of_docs_documentation_is_classified(self):
        text = read(self.MAP)

        for location in (
            '`docs/design/`',
            '`backend/reports/`',
            '`backend/COIN_Philosophy.md`',
            '`frontend/docs/`',
            '`artifacts/`',
        ):
            assert location in text, location


class TestAuthorityOrderHasACanonicalHome:
    """The order was explicit and consistent, and homed only in two navigation
    files that the order itself ranks below the six."""

    CONSTITUTION = CANONICAL / '01_BASEBALLOS_CONSTITUTION.md'

    ORDER = (
        'Constitution',
        'Bullpen Intelligence Standard',
        'Product Experience Standard',
        'Platform Architecture & Operations Manual',
        'Editorial & Distribution Standard',
        'Product Roadmap & Decision Ledger',
    )

    def test_the_constitution_states_the_authority_order(self):
        text = read(self.CONSTITUTION)

        assert '### Authority order' in text
        for index, name in enumerate(self.ORDER, start=1):
            assert f'{index}. {name}' in text, name

    def test_the_navigation_readmes_defer_to_it(self):
        for relative in ('docs/README.md', 'docs/canonical/README.md'):
            text = read(REPO_ROOT / relative)
            assert '01_BASEBALLOS_CONSTITUTION.md' in text, relative
            assert 'Section 15' in text, relative

    def test_the_restatements_still_match_the_constitutional_order(self):
        """A navigation copy that drifts is worse than no copy."""
        for relative in ('docs/README.md', 'docs/canonical/README.md'):
            text = read(REPO_ROOT / relative)
            for index, name in enumerate(self.ORDER, start=1):
                assert f'{index}. {name}' in text, f'{relative}: {name}'
