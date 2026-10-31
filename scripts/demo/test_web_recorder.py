"""Offline checks for honest web-demo provenance, including partial fetches."""
import unittest

from record_web_demo import validate_web


class WebProvenanceTests(unittest.TestCase):
    def receipt(self) -> tuple[dict, dict]:
        detail = {'run':{'llm_mode':'LIVE','status':'PARTIAL','stop_reason':'HTTP_STATUS_403'},
                  'steps':[
                      {'step':'web:search','actor':'llm','error':None,'detail':{'mode':'LIVE','replayed':False}},
                      {'step':'web:snapshot','actor':'code','detail':{'mode':'LIVE','source_version_id':'source-A'}},
                  ]}
        audit = {'queries':[{'mode':'LIVE'}], 'snapshots':[
            {'source_version_id':'source-A','dataset_origin':'REAL','identity_verified':True,
             'passages':[{'text':'An unchanged stored passage'}]}]}
        return detail,audit

    def test_partial_with_actual_sources_is_presentable(self) -> None:
        validate_web(*self.receipt())

    def test_unrelated_source_identity(self) -> None:
        detail,audit=self.receipt()
        detail['steps'][1]['detail']['source_version_id']='another-source'
        audit['snapshots'][0]['source_version_id']='another-source'
        validate_web(detail,audit)

    def test_recorded_query_is_not_live(self) -> None:
        detail,audit=self.receipt()
        audit['queries'][0]['mode']='REPLAY'
        with self.assertRaises(ValueError): validate_web(detail,audit)

    def test_fallback_query_plan_is_rejected(self) -> None:
        detail,audit=self.receipt()
        detail['steps'].append({'step':'agent:web_scout','actor':'code','detail':{'mode':'FALLBACK'}})
        with self.assertRaises(ValueError): validate_web(detail,audit)

    def test_snapshot_not_stored_by_run_is_rejected(self) -> None:
        detail,audit=self.receipt()
        audit['snapshots'][0]['source_version_id']='unrelated'
        with self.assertRaises(ValueError): validate_web(detail,audit)

    def test_search_without_stored_snapshot_does_not_mean_more_sources(self) -> None:
        detail,audit=self.receipt()
        audit['snapshots']=[]
        with self.assertRaises(ValueError): validate_web(detail,audit)

    def test_unmatched_product_is_not_confirmed(self) -> None:
        detail,audit=self.receipt()
        audit['snapshots'][0]['identity_verified']=False
        with self.assertRaises(ValueError): validate_web(detail,audit)

    def test_running_receipt_is_not_final(self) -> None:
        detail,audit=self.receipt()
        detail['run']['status']='RUNNING'
        with self.assertRaises(ValueError): validate_web(detail,audit)

    def test_queued_receipt_is_not_final(self) -> None:
        detail,audit=self.receipt()
        detail['run']['status']='QUEUED'
        with self.assertRaises(ValueError): validate_web(detail,audit)


if __name__ == '__main__': unittest.main()
