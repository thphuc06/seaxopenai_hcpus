"""Offline provenance checks for the P4 video boundary; no server/model calls."""
import unittest

from record_live_demo import admitted_run_id, require_live, require_saved_state


class LiveEvidenceTests(unittest.TestCase):
    def detail(self, mode: str = 'LIVE', status: str = 'COMPLETED', tokens: int = 37,
               replayed: bool | None = False) -> dict:
        return {'run': {'llm_mode': mode, 'status': status}, 'steps': [
            {'actor': 'llm', 'tokens_in': tokens, 'detail': {'replayed': replayed}}]}

    def test_live_provider_evidence(self) -> None:
        require_live(self.detail())

    def test_unrelated_token_count(self) -> None:
        require_live(self.detail(tokens=9201))

    def test_replay_mode_rejected(self) -> None:
        with self.assertRaises(ValueError):
            require_live(self.detail(mode='REPLAY'))

    def test_partial_not_promoted(self) -> None:
        with self.assertRaises(ValueError):
            require_live(self.detail(status='PARTIAL'))

    def test_published_review_result_is_preserved(self) -> None:
        require_live(self.detail(status='WAITING_REVIEW'))

    def test_published_missing_evidence_is_preserved(self) -> None:
        require_live(self.detail(status='WAITING_EVIDENCE'))

    def test_missing_provider_tokens(self) -> None:
        with self.assertRaises(ValueError):
            require_live(self.detail(tokens=0))

    def test_missing_replay_marker(self) -> None:
        with self.assertRaises(ValueError):
            require_live(self.detail(replayed=None))

    def test_mixed_replay_rejected(self) -> None:
        detail = self.detail()
        detail['steps'].append({'actor': 'llm', 'tokens_in': 0, 'detail': {'replayed': True}})
        with self.assertRaises(ValueError):
            require_live(detail)

    def test_mixed_fallback_rejected(self) -> None:
        detail = self.detail()
        detail['steps'].append({'actor': 'code', 'tokens_in': 0, 'detail': {'extractor': 'FALLBACK'}})
        with self.assertRaises(ValueError):
            require_live(detail)

    def test_code_step_fallback_mode_is_rejected(self) -> None:
        detail = self.detail()
        detail['steps'].append({'actor':'code','tokens_in':0,'detail':{'mode':'FALLBACK'}})
        with self.assertRaises(ValueError): require_live(detail)

    def test_code_step_replay_mode_is_rejected(self) -> None:
        detail = self.detail()
        detail['steps'].append({'actor':'code','tokens_in':0,'detail':{'mode':'REPLAY'}})
        with self.assertRaises(ValueError): require_live(detail)

    def test_event_external_id_maps_to_storage_run(self) -> None:
        self.assertEqual(admitted_run_id('external-A', [
            {'event_id':'unrelated', 'run_id':'run-B'},
            {'event_id':'external-A', 'run_id':'run-A'},
        ]), 'run-A')

    def test_new_event_waits_for_log(self) -> None:
        self.assertIsNone(admitted_run_id('fresh', [{'event_id':'old', 'run_id':'run-old'}]))

    def test_pending_event_waits_for_run(self) -> None:
        self.assertIsNone(admitted_run_id('queued', [{'event_id':'queued', 'run_id':None}]))


class SavedStateTests(unittest.TestCase):
    def run_receipt(self) -> dict:
        return {'id':'run-A','case_id':'case-A','case_revision':4,'status':'PARTIAL',
                'stop_reason':'HTTP_STATUS_403','llm_mode':'LIVE'}

    def test_same_receipt_is_accepted(self) -> None:
        run = self.run_receipt()
        require_saved_state(run,[run],{'fields':['stored']},{'fields':['stored']})

    def test_other_case_newer_revision_is_irrelevant(self) -> None:
        run = self.run_receipt()
        other = {**run,'id':'run-B','case_id':'unrelated','case_revision':99}
        require_saved_state(run,[other,run],{}, {})

    def test_same_status_new_revision_is_rejected(self) -> None:
        run = self.run_receipt()
        newer = {**run,'id':'run-B','case_revision':5}
        with self.assertRaises(ValueError): require_saved_state(run,[newer,run],{}, {})

    def test_same_revision_competing_run_is_rejected(self) -> None:
        run = self.run_receipt()
        with self.assertRaises(ValueError): require_saved_state(run,[{**run,'id':'run-B'},run],{}, {})

    def test_passport_change_without_new_run_is_rejected(self) -> None:
        run = self.run_receipt()
        with self.assertRaises(ValueError): require_saved_state(run,[run],{'review':'old'},{'review':'new'})

    def test_audit_change_is_rejected(self) -> None:
        run = self.run_receipt()
        with self.assertRaises(ValueError):
            require_saved_state(run,[run],{}, {},saved_audit={'snapshots':[]},current_audit={'snapshots':['new']})

    def test_missing_run_is_rejected(self) -> None:
        with self.assertRaises(ValueError): require_saved_state(self.run_receipt(),[],{}, {})


if __name__ == '__main__':
    unittest.main()
