import json
import multiprocessing
import os
import sys
import tempfile
import uuid
from contextlib import closing
from contextlib import redirect_stderr
import io
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import workflow
import history
import assessments
import config
import execution
from execution import append_event, create_or_validate_manifest, rules_digest
from review import REFRESH_REQUEST_TEXT, normalize_snapshot


def _try_account_lock_in_child(account,queue):
    try:
        with execution.account_transaction([account]):pass
        queue.put('acquired')
    except ValueError:
        queue.put('blocked')


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        # Calendar-bound fixture dates remain stable when CI runs in later months.
        import datetime as calendar
        class FixtureDateTime(calendar.datetime):
            @classmethod
            def now(cls,tz=None):
                value=cls(2026,11,19,12,tzinfo=calendar.timezone.utc)
                return value.astimezone(tz) if tz else value.replace(tzinfo=None)
        clock=patch.object(execution.dt,'datetime',FixtureDateTime)
        clock.start();self.addCleanup(clock.stop)
        config_patcher=patch.dict(config.CONFIG,{'account':'synthetic@example.test','mailbox_prefix':'imap://synthetic@example.test/','database':'/synthetic/not-used','state_root':'/synthetic/state','timezone':'UTC','folder_map':{'INBOX':'INBOX','Archive':'Archive','Junk':'Junk','Trash':'Trash'}})
        config_patcher.start();self.addCleanup(config_patcher.stop)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        config.CONFIG['state_root']=str(self.root)
        locks=patch.object(execution,'account_lock_root',return_value=(self.root/'account-locks').resolve());locks.start();self.addCleanup(locks.stop)
        self.snapshot={'run_id':'run-flow','scope':'Synthetic','snapshot_as_of':'2026-11-18T12:00:00+00:00','timezone':'UTC','account_scope':['synthetic@example.test'],'refreshed_at':'2026-11-18T12:00:00+00:00','records':[
          {'item':'M001','account':'synthetic@example.test','message_id':'full:mid@example.test','current_id':17,'observed_mailbox':'INBOX','to_display':'recipient@example.test','subject':'Synthetic','received':'2026-11-18T11:00:00+00:00','size_bytes':123,'gist':'Synthetic summary',
           'email_context':{'sender':'sender@example.test','to':['recipient@example.test'],'cc':[],'prior_triage_gist':'Not previously reviewed.','triage_reason':'Synthetic','original_disposition':'Inbox','attachment_names':[],'prior_attachment_assessment':'Not inspected.','local_source':{'path':None,'file_url':None,'format':None,'partial':None,'availability':'not-located','access':'Synthetic'},'content_note':'Synthetic content.'}}]}
        self.normalized=normalize_snapshot(self.snapshot)
        self.plan={'snapshot_id':self.normalized['snapshot_id'],'started_at':'2026-11-18T12:05:00+00:00','authorization':'Synthetic user authorization','actions':[{'item':'M001','destination':'Archive','reason':'Synthetic completed filing'}]}
        self.bundle={'kind':'email-triage-review-bundle','version':1,'run_id':self.normalized['run_id'],'snapshot_id':self.normalized['snapshot_id'],'exported_at':'2026-11-18T12:05:00.000Z',
          'moves':[{'item':'M001','account':'synthetic@example.test','message_id':'full:mid@example.test','snapshot_mailbox':'INBOX','snapshot_numeric_id':17,'destination':'archive'}],
          'opt_outs':[{'item':'M001','account':'synthetic@example.test','message_id':'full:mid@example.test','snapshot_mailbox':'INBOX','snapshot_numeric_id':17}],
          'tasks':[{'item':'M001','account':'synthetic@example.test','message_id':'full:mid@example.test','snapshot_mailbox':'INBOX','snapshot_numeric_id':17,'instruction':'Review the confirmation.'}],
          'comments':[{'item':'M001','account':'synthetic@example.test','message_id':'full:mid@example.test','snapshot_mailbox':'INBOX','snapshot_numeric_id':17,'original_summary':'Synthetic summary','comment':'Correction: this is still pending.'}],
          'refresh_request':{'version':1,'kind':'email-triage-refresh-request','mode':'read-only','run_id':'run-flow','snapshot_id':self.normalized['snapshot_id'],'requested_at':'2026-11-18T12:05:00.000Z','account_scope':['synthetic@example.test'],'request':REFRESH_REQUEST_TEXT,'pending_review':{'version':1,'run_id':'run-flow','snapshot_id':self.normalized['snapshot_id'],'exported_at':'2026-11-18T12:05:00.000Z','changes':[{'item':'M001','account':'synthetic@example.test','message_id':'full:mid@example.test','snapshot_mailbox':'INBOX','snapshot_numeric_id':17,'original_gist':'Synthetic summary','gist':'Correction: this is still pending.','requested_move':'archive','opt_out':True}]}}}
        self.snapshot_path=self.root/'snapshot.json';self.snapshot_path.write_text(json.dumps(self.snapshot))
        self.plan_path=self.root/'plan.json';self.plan_path.write_text(json.dumps(self.plan))
        self.bundle_path=self.root/'bundle.json';self.bundle_path.write_text(json.dumps(self.bundle))
        # A mutating action export is a distinct, explicit authorization. The
        # refresh-bearing export above is reserved for the read-only path.
        self.action_bundle={k:v for k,v in self.bundle.items() if k!='refresh_request'}
        self.action_bundle['refresh_request']=None
        self.action_bundle_path=self.root/'action-bundle.json';self.action_bundle_path.write_text(json.dumps(self.action_bundle))
        self.rules=self.root/'rules.md';self.rules.write_text('Synthetic rule profile\n')
        self.db=self.root/'history.sqlite3';self.journal=self.root/'runs'/'journal.jsonl';self.recovery=self.root/'recovery'
        self.manifest=self.root/'runs'/'manifest.json';self.review_path=self.root/'runs'/'run-flow'/'review.html';self.review_path.parent.mkdir(parents=True)
        original=history.review_path;patcher=patch.object(history,'review_path',side_effect=lambda path:original(path,self.root));patcher.start();self.addCleanup(patcher.stop)

    def _success_adapters(self):
        def apply_adapter(source,plan,journal,recovery,**kwargs):
            intent={'item':'M001','account':'synthetic@example.test','message_id':'full:mid@example.test','old_id':17,'old_mailbox':'INBOX','destination':'Archive','reason':'Synthetic','snapshot_id':source['snapshot_id'],'attempt_id':'attempt-success','pre_destination_ids':[],'pre_source_junk':False,'at':'2026-11-18T12:06:00+00:00'}
            append_event(journal,{**intent,'status':'intent'})
            receipt={k:intent[k] for k in ('item','account','message_id','old_id','old_mailbox','destination','snapshot_id','attempt_id','pre_destination_ids','pre_source_junk')}
            receipt.update(status='move-receipt',new_id=42,junk=False,completed_at='2026-11-18T12:06:01+00:00');append_event(journal,receipt)
            terminal={**intent,'status':'verified-moved','new_id':42,'junk':False,'completed_at':receipt['completed_at']};append_event(journal,terminal)
            return [terminal]
        def refresh_adapter(base):
            self.assertEqual((base['records'][0]['current_id'],base['records'][0]['observed_mailbox']),(42,'Archive'))
            base['refreshed_at']='2026-11-18T12:07:00+00:00';base['records'][0]['received']='2026-11-18T11:00:00+00:00'
            return base
        return apply_adapter,refresh_adapter

    def test_apply_refresh_history_render_bundle_and_readiness_end_to_end(self):
        apply_adapter,refresh_adapter=self._success_adapters()
        digest=__import__('hashlib').sha256(self.action_bundle_path.read_bytes()).hexdigest()
        result=workflow.run_pipeline(self.snapshot_path,None,self.rules,self.manifest,self.journal,self.recovery,None,self.review_path,self.db,
          bundle_path=self.action_bundle_path,apply_adapter=apply_adapter,refresh_adapter=refresh_adapter,authorized=True,expected_plan_digest=digest)
        self.assertEqual(result['verified_actions'],1);self.assertEqual(result['followups'],1);self.assertEqual(result['pending_opt_out_reviews'],1);self.assertEqual(result['comments'],1)
        self.assertEqual(result['assessment_readiness']['awaiting_assessment'],1)
        self.assertIsNone(result['refresh_request']);self.assertTrue(self.review_path.is_file())
        out=history.export_history(self.db);self.assertEqual(len(out),1);self.assertEqual(out[0]['actions'][0]['new_id'],42)
        receipt=history.get_export_receipt(self.db,digest)
        self.assertIsNotNone(receipt);self.assertEqual(receipt['run_id'],result['run_id'])
        self.assertEqual(receipt['outcome']['item_outcomes'],[{'item':'M001','action':'verified-moved','error':None,'annotations':'persisted'}])
        self.assertEqual(out[0]['reviewed_at'],'2026-11-18T12:05:00.000Z')
        self.assertEqual([t['current_id'] for t in out[0]['tasks']],[42,42]);self.assertTrue(all(t['status']=='ready' for t in out[0]['tasks']))
        self.assertTrue(any('Do not unsubscribe' in t['next_action'] for t in out[0]['tasks']))
        for task in history.list_followups(self.db):
            task.update(status='waiting_vendor',deadline='2026-12-01T00:00:00+00:00',waiting_on='supplier',result_link='https://example.test/result',updated_at='2026-11-18T13:00:00+00:00')
            history.upsert_followup(self.db,task)
        progress_before=history.list_followups(self.db)
        self.assertEqual(out[0]['assessments'],[])
        html=self.review_path.read_text();self.assertIn('awaiting_assessment',html);self.assertIn('synthetic@example.test',html)
        self.assertIn('Provider / model / effort: Not recorded',html);self.assertIn('UTC',html)
        def must_not_replay(*args,**kwargs):self.fail('completed journal actions were replayed')
        rerun=workflow.run_pipeline(self.snapshot_path,None,self.rules,self.manifest,self.root/'other-journal.jsonl',self.recovery,None,self.review_path,self.db,
          bundle_path=self.action_bundle_path,apply_adapter=must_not_replay,refresh_adapter=must_not_replay,authorized=True,expected_plan_digest=digest)
        self.assertTrue(rerun['already_processed']);self.assertEqual(rerun['verified_snapshot_id'],result['verified_snapshot_id'])
        self.assertEqual(len(history.export_history(self.db)),1)
        self.assertEqual(history.list_followups(self.db),progress_before)

    def test_refresh_review_is_strictly_read_only_and_preserves_bound_pending_bundle(self):
        digest=__import__('hashlib').sha256(self.bundle_path.read_bytes()).hexdigest()
        history.register(self.db,self.snapshot,self.review_path)
        output=self.root/'read-only-refresh.json'
        def refreshed(base):
            value=json.loads(json.dumps(base));value['refreshed_at']='2026-11-18T14:00:00+00:00'
            return value
        with patch.object(workflow,'apply',side_effect=AssertionError('read-only refresh must not apply')):
            result=workflow.refresh_review(self.snapshot_path,self.bundle_path,output,self.db,refresh_adapter=refreshed)
        self.assertFalse(result['mail_changed']);self.assertEqual(result['bundle_sha256'],digest)
        self.assertEqual(Path(result['pending_review_bundle']).read_bytes(),self.bundle_path.read_bytes())
        self.assertTrue(all(row['status']=='preserved-unapplied' for row in result['item_outcomes']))
        self.assertEqual(json.loads(output.read_text())['snapshot_id'],result['refreshed_snapshot_id'])
        self.assertIsNotNone(history.get_export_receipt(self.db,digest,operation='refresh'))
        with patch.object(sys,'argv',['workflow.py','refresh-review','--snapshot',str(self.snapshot_path),'--bundle',str(self.bundle_path),'--output',str(output),'--database',str(self.db),'--apply']),redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as rejected:workflow.main()
        self.assertEqual(rejected.exception.code,2)

    def test_task_only_refresh_selection_is_visible_with_exact_copy_outcome(self):
        history.register(self.db,self.snapshot,self.review_path)
        task_bundle=json.loads(self.bundle_path.read_text())
        task_bundle['moves']=[];task_bundle['opt_outs']=[];task_bundle['comments']=[]
        task_bundle['refresh_request']['pending_review']['changes']=[]
        task_path=self.root/'task-only-bundle.json';task_path.write_text(json.dumps(task_bundle))
        output=self.root/'task-only-refresh.json'
        result=workflow.refresh_review(self.snapshot_path,task_path,output,self.db,refresh_adapter=lambda source:{**source,'refreshed_at':'2026-11-18T14:00:00+00:00'})
        page=Path(result['review']).read_text()
        self.assertIn('Review the confirmation.',page)
        self.assertEqual(result['item_outcomes'],[{'item':'M001','account':'synthetic@example.test','message_id':'full:mid@example.test',
            'snapshot_mailbox':'INBOX','snapshot_numeric_id':17,'status':'preserved-unapplied','reason':None}])
        self.assertEqual(Path(result['pending_review_bundle']).read_bytes(),task_path.read_bytes())

    def test_relative_refresh_output_is_normalized_and_retry_safe(self):
        history.register(self.db,self.snapshot,self.review_path)
        old=Path.cwd()
        try:
            os.chdir(self.root)
            result=workflow.refresh_review(self.snapshot_path,self.bundle_path,'relative-refresh.json',self.db,
                refresh_adapter=lambda source:{**source,'refreshed_at':'2026-11-18T14:00:00+00:00'})
        finally:os.chdir(old)
        for key in ('snapshot','pending_review_bundle','review','lineage'):
            self.assertTrue(Path(result[key]).is_absolute(),key)
            self.assertTrue(Path(result[key]).is_file(),key)
        replay=workflow.refresh_review(self.snapshot_path,self.bundle_path,'relative-refresh.json',self.db,
            refresh_adapter=lambda _:self.fail('refresh receipt should make exact retry idempotent'))
        self.assertTrue(replay['already_processed'])

    def test_refresh_preflight_rejects_source_database_and_sidecar_aliases(self):
        history.register(self.db,self.snapshot,self.review_path)
        sidecar_source=self.root/'bundle.pending-review.json';sidecar_source.write_bytes(self.bundle_path.read_bytes())
        hardlink=self.root/'snapshot-hardlink.json';os.link(self.snapshot_path,hardlink)
        symlink=self.root/'snapshot-symlink.json';symlink.symlink_to(self.snapshot_path)
        targets=[self.snapshot_path,self.db,sidecar_source,hardlink,symlink,Path(str(self.db)+'-wal')]
        for index,target in enumerate(targets):
            before_snapshot=self.snapshot_path.read_bytes();before_bundle=self.bundle_path.read_bytes();before_db=self.db.read_bytes()
            with self.subTest(target=str(target)),self.assertRaisesRegex(ValueError,'collid|alias|same file|overwrite'):
                workflow.refresh_review(self.snapshot_path,self.bundle_path,target,self.db,refresh_adapter=lambda source:source)
            self.assertEqual(self.snapshot_path.read_bytes(),before_snapshot)
            self.assertEqual(self.bundle_path.read_bytes(),before_bundle)
            self.assertEqual(self.db.read_bytes(),before_db)
        fixed_uuid=uuid.UUID('12345678123456781234567812345678')
        review_collision=self.root/'runs'/('refresh-'+fixed_uuid.hex)/'review.html';review_collision.parent.mkdir(parents=True);review_collision.write_text('immutable previous review')
        with patch.object(workflow.uuid,'uuid4',return_value=fixed_uuid):
            with self.assertRaisesRegex(ValueError,'existing artifact'):
                workflow.refresh_review(self.snapshot_path,self.bundle_path,self.root/'review-collision-output.json',self.db,
                    refresh_adapter=lambda _:self.fail('collision should be found before refresh'))
        self.assertEqual(review_collision.read_text(),'immutable previous review')
        before=sidecar_source.read_bytes()
        with self.assertRaisesRegex(ValueError,'collid|alias|same file'):
            workflow.refresh_review(self.snapshot_path,sidecar_source,self.root/'bundle.json',self.db,refresh_adapter=lambda source:source)
        self.assertEqual(sidecar_source.read_bytes(),before)

    def test_registered_baseline_bundle_creates_immutable_application_revision(self):
        self.review_path.write_text('BASELINE HTML - DO NOT OVERWRITE')
        history.register(self.db,self.snapshot,self.review_path)
        baseline_json=json.dumps(normalize_snapshot(self.snapshot),sort_keys=True)
        baseline_review=self.review_path.read_text();bundle_digest=__import__('hashlib').sha256(self.action_bundle_path.read_bytes()).hexdigest()
        apply_adapter,refresh_adapter=self._success_adapters()
        result=workflow.run_pipeline(self.snapshot_path,None,self.rules,self.manifest,self.journal,self.recovery,None,self.review_path,self.db,
          bundle_path=self.action_bundle_path,apply_adapter=apply_adapter,refresh_adapter=refresh_adapter,authorized=True,expected_plan_digest=bundle_digest)
        self.assertEqual(result['baseline_run_id'],'run-flow');self.assertNotEqual(result['run_id'],'run-flow')
        self.assertEqual(self.review_path.read_text(),baseline_review)
        self.assertEqual(json.dumps(history.get_registered_snapshot(self.db,'run-flow'),sort_keys=True),baseline_json)
        self.assertTrue(Path(result['lineage']).is_file());self.assertTrue(Path(result['review']).is_file())
        runs=history.export_history(self.db);self.assertEqual(len(runs),2)
        baseline=next(run for run in runs if run['run_id']=='run-flow')
        self.assertEqual(baseline['reviewed_at'],'2026-11-18T12:05:00.000Z')
        import sqlite3
        with closing(sqlite3.connect(self.db)) as connection:
            self.assertEqual(connection.execute('SELECT sha256 FROM exports WHERE run_id=?',('run-flow',)).fetchone()[0],bundle_digest)
        app=next(run for run in runs if run['run_id']==result['run_id'])
        self.assertEqual([task['current_id'] for task in app['tasks']],[42,42])
        self.assertTrue(all(task['run_id']==result['run_id'] for task in app['tasks']))
        self.assertEqual(baseline['tasks'],[])
        first_snapshot_id=result['verified_snapshot_id']
        def must_not_replay(*args,**kwargs):self.fail('registered baseline application replayed actions')
        replay=workflow.run_pipeline(self.snapshot_path,None,self.rules,self.manifest,self.root/'second-journal.jsonl',self.recovery,None,self.review_path,self.db,
          bundle_path=self.action_bundle_path,apply_adapter=must_not_replay,refresh_adapter=must_not_replay,authorized=True,expected_plan_digest=bundle_digest)
        self.assertTrue(replay['already_processed'])
        self.assertEqual(replay['verified_snapshot_id'],first_snapshot_id)
        self.assertEqual(self.review_path.read_text(),baseline_review)
        self.assertEqual(len(history.export_history(self.db)),2)
        self.assertEqual(len(history.list_followups(self.db)),2)

    def test_apply_failure_does_not_refresh_or_record_completed_history(self):
        def failed(source,plan,journal,recovery,**kwargs):
            append_event(journal,{'item':'M001','account':'synthetic@example.test','message_id':'full:mid@example.test','old_id':17,'old_mailbox':'INBOX','destination':'Archive','snapshot_id':source['snapshot_id'],'status':'conflict-or-failed','error':'synthetic failure'})
            raise ValueError('synthetic failure')
        refresh_called=[]
        with self.assertRaisesRegex(ValueError,'synthetic failure'):
            workflow.run_pipeline(self.snapshot_path,None,self.rules,self.manifest,self.journal,self.recovery,None,self.review_path,self.db,bundle_path=self.action_bundle_path,apply_adapter=failed,refresh_adapter=lambda base:refresh_called.append(base),authorized=True,expected_plan_digest=__import__('hashlib').sha256(self.action_bundle_path.read_bytes()).hexdigest())
        self.assertEqual(refresh_called,[]);self.assertFalse(self.review_path.exists());self.assertEqual(history.export_history(self.db),[])

    def test_successful_real_journal_intent_retry_does_not_block_checkpoint_reuse(self):
        apply_adapter,refresh_adapter=self._success_adapters();digest=__import__('hashlib').sha256(self.plan_path.read_bytes()).hexdigest()
        first=workflow.run_pipeline(self.snapshot_path,self.plan_path,self.rules,self.manifest,self.journal,self.recovery,None,self.review_path,self.db,
            apply_adapter=apply_adapter,refresh_adapter=refresh_adapter,authorized=True,expected_plan_digest=digest)
        def must_not_replay(*args,**kwargs):self.fail('real successful intent was replayed on checkpoint retry')
        second=workflow.run_pipeline(self.snapshot_path,self.plan_path,self.rules,self.manifest,self.journal,self.recovery,None,self.review_path,self.db,
            apply_adapter=must_not_replay,refresh_adapter=must_not_replay,authorized=True,expected_plan_digest=digest)
        self.assertEqual(first['verified_snapshot_id'],second['verified_snapshot_id'])
        self.assertEqual(len(history.export_history(self.db)[0]['actions']),1)

    def test_coordinator_account_lock_covers_refresh_and_releases_on_success(self):
        context=multiprocessing.get_context('fork');apply_adapter,_=self._success_adapters();child_results=[]
        original_snapshot_lookup=workflow.get_registered_snapshot
        lookup_lock_results=[]
        def locked_snapshot_lookup(*args,**kwargs):
            queue=context.Queue();child=context.Process(target=_try_account_lock_in_child,args=('synthetic@example.test',queue));child.start();child.join(3)
            self.assertFalse(child.is_alive(),'cross-process contender did not finish during history baseline lookup')
            self.assertEqual(child.exitcode,0);lookup_lock_results.append(queue.get(timeout=1))
            return original_snapshot_lookup(*args,**kwargs)
        def blocked_refresh(base):
            queue=context.Queue();child=context.Process(target=_try_account_lock_in_child,args=('synthetic@example.test',queue));child.start();child.join(3)
            self.assertFalse(child.is_alive(),'cross-process lock contender did not finish')
            self.assertEqual(child.exitcode,0);child_results.append(queue.get(timeout=1))
            base['refreshed_at']='2026-11-18T12:07:00+00:00';return base
        digest=__import__('hashlib').sha256(self.plan_path.read_bytes()).hexdigest()
        with patch.object(workflow,'get_registered_snapshot',side_effect=locked_snapshot_lookup):
            result=workflow.run_pipeline(self.snapshot_path,self.plan_path,self.rules,self.manifest,self.journal,self.recovery,None,self.review_path,self.db,
                apply_adapter=apply_adapter,refresh_adapter=blocked_refresh,authorized=True,expected_plan_digest=digest)
        self.assertEqual(result['verified_actions'],1);self.assertEqual(child_results,['blocked']);self.assertEqual(lookup_lock_results,['blocked'])
        queue=context.Queue();child=context.Process(target=_try_account_lock_in_child,args=('synthetic@example.test',queue));child.start();child.join(3)
        self.assertFalse(child.is_alive());self.assertEqual(child.exitcode,0);self.assertEqual(queue.get(timeout=1),'acquired')

    def test_coordinator_account_lock_releases_when_post_action_refresh_fails(self):
        apply_adapter,_=self._success_adapters()
        def failed_refresh(*args,**kwargs):raise RuntimeError('synthetic refresh failure')
        digest=__import__('hashlib').sha256(self.plan_path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(RuntimeError,'synthetic refresh failure'):
            workflow.run_pipeline(self.snapshot_path,self.plan_path,self.rules,self.manifest,self.journal,self.recovery,None,self.review_path,self.db,
                apply_adapter=apply_adapter,refresh_adapter=failed_refresh,authorized=True,expected_plan_digest=digest)
        context=multiprocessing.get_context('fork');queue=context.Queue();child=context.Process(target=_try_account_lock_in_child,args=('synthetic@example.test',queue));child.start();child.join(3)
        self.assertFalse(child.is_alive());self.assertEqual(child.exitcode,0);self.assertEqual(queue.get(timeout=1),'acquired')

    def test_partial_conflict_does_not_hide_or_verify_independent_success(self):
        source={**self.snapshot,'run_id':'partial-run','records':[dict(self.snapshot['records'][0]),dict(self.snapshot['records'][0],item='M002',message_id='second:mid@example.test',current_id=18,subject='Second')]}
        source_path=self.root/'partial-snapshot.json';source_path.write_text(json.dumps(source));normalized=normalize_snapshot(source)
        plan={'snapshot_id':normalized['snapshot_id'],'started_at':'2026-11-18T12:05:00+00:00','authorization':'Two independent synthetic actions',
          'actions':[{'item':'M001','destination':'Archive','reason':'First filing'},{'item':'M002','destination':'Archive','reason':'Second filing'}]}
        plan_path=self.root/'partial-plan.json';plan_path.write_text(json.dumps(plan));manifest=self.root/'partial-manifest.json';journal=self.root/'partial-journal.jsonl'
        def apply_partial(snapshot,authorized,journal_path,recovery,**kwargs):
            first=snapshot['records'][0]
            append_event(journal_path,{'item':first['item'],'account':first['account'],'message_id':first['message_id'],'old_id':first['current_id'],'old_mailbox':'INBOX','destination':'Archive','snapshot_id':snapshot['snapshot_id'],'status':'conflict-or-failed','error':'Stale exact source identity'})
            second=snapshot['records'][1]
            intent={'item':second['item'],'account':second['account'],'message_id':second['message_id'],'old_id':second['current_id'],'old_mailbox':'INBOX','destination':'Archive','reason':'Second filing','snapshot_id':snapshot['snapshot_id'],'attempt_id':'independent-success','pre_destination_ids':[],'pre_source_junk':False,'at':'2026-11-18T12:06:00+00:00'}
            append_event(journal_path,{**intent,'status':'intent'})
            append_event(journal_path,{k:intent[k] for k in ('item','account','message_id','old_id','old_mailbox','destination','snapshot_id','attempt_id','pre_destination_ids','pre_source_junk')}|{'status':'move-receipt','new_id':52,'junk':False,'completed_at':'2026-11-18T12:06:01+00:00'})
            append_event(journal_path,{**intent,'status':'verified-moved','new_id':52,'junk':False,'completed_at':'2026-11-18T12:06:01+00:00'})
            return []
        def refreshed(base):
            base['refreshed_at']='2026-11-18T12:07:00+00:00';base['records'][1]['current_id']=52;base['records'][1]['observed_mailbox']='Archive';return base
        digest=__import__('hashlib').sha256(plan_path.read_bytes()).hexdigest()
        result=workflow.run_pipeline(source_path,plan_path,self.rules,manifest,journal,self.recovery,None,self.root/'runs'/'partial-run'/'review.html',self.db,
            apply_adapter=apply_partial,refresh_adapter=refreshed,authorized=True,expected_plan_digest=digest)
        self.assertEqual(result['verified_actions'],1)
        self.assertEqual({row['item']:row['action'] for row in result['item_outcomes']},{'M001':'conflict-or-failed','M002':'verified-moved'})
        actions=history.export_history(self.db)[0]['actions'];self.assertEqual([event['item'] for event in actions],['M002'])
        self.assertNotIn('M001',{event['item'] for event in actions})

    def test_post_intent_conflict_returns_partial_without_false_refresh(self):
        source={**self.snapshot,'run_id':'partial-unresolved','records':[dict(self.snapshot['records'][0]),dict(self.snapshot['records'][0],item='M002',message_id='second:mid@example.test',current_id=18,subject='Second')]}
        source_path=self.root/'partial-unresolved-snapshot.json';source_path.write_text(json.dumps(source));normalized=normalize_snapshot(source)
        plan={'snapshot_id':normalized['snapshot_id'],'started_at':'2026-11-18T12:05:00+00:00','authorization':'Two independent synthetic actions',
          'actions':[{'item':'M001','destination':'Archive','reason':'First filing'},{'item':'M002','destination':'Archive','reason':'Second filing'}]}
        plan_path=self.root/'partial-unresolved-plan.json';plan_path.write_text(json.dumps(plan));manifest=self.root/'partial-unresolved-manifest.json';journal=self.root/'partial-unresolved-journal.jsonl'
        def apply_partial(snapshot,authorized,journal_path,recovery,**kwargs):
            first=snapshot['records'][0]
            intent={'item':first['item'],'account':first['account'],'message_id':first['message_id'],'old_id':first['current_id'],'old_mailbox':'INBOX','destination':'Archive','snapshot_id':snapshot['snapshot_id'],'attempt_id':'conflict-attempt','pre_destination_ids':[],'pre_source_junk':False,'reason':'First filing','at':'2026-11-18T12:06:00+00:00'}
            append_event(journal_path,{**intent,'status':'intent'});append_event(journal_path,{**intent,'status':'conflict-or-failed','error':'Destination changed during move'})
            second=snapshot['records'][1];other={**intent,'item':second['item'],'message_id':second['message_id'],'old_id':second['current_id'],'attempt_id':'independent-success','reason':'Second filing'}
            append_event(journal_path,{**other,'status':'intent'})
            receipt={k:other[k] for k in ('item','account','message_id','old_id','old_mailbox','destination','snapshot_id','attempt_id','pre_destination_ids','pre_source_junk')}
            receipt.update(status='move-receipt',new_id=52,junk=False,completed_at='2026-11-18T12:06:02+00:00');append_event(journal_path,receipt)
            append_event(journal_path,{**other,'status':'verified-moved','new_id':52,'junk':False,'completed_at':receipt['completed_at']})
        digest=__import__('hashlib').sha256(plan_path.read_bytes()).hexdigest()
        result=workflow.run_pipeline(source_path,plan_path,self.rules,manifest,journal,self.recovery,None,self.root/'runs'/'partial-unresolved'/'review.html',self.db,
            apply_adapter=apply_partial,refresh_adapter=lambda base:self.fail('Unresolved action must not be called verified by a refresh'),authorized=True,expected_plan_digest=digest)
        self.assertEqual(result['status'],'partial');self.assertEqual(result['verified_items'],['M002']);self.assertEqual(result['unresolved_items'],['M001'])
        self.assertFalse(result['refresh_published']);self.assertFalse(result['history_registered'])
        self.assertTrue(result['mail_changed']);self.assertEqual(result['mail_change_status'],'confirmed-changed')

    def test_receiptless_partial_reports_mail_change_as_unknown(self):
        source={**self.snapshot,'run_id':'receiptless-partial'}
        source_path=self.root/'receiptless-snapshot.json';source_path.write_text(json.dumps(source));normalized=normalize_snapshot(source)
        plan={'snapshot_id':normalized['snapshot_id'],'started_at':'2026-11-18T12:05:00+00:00','authorization':'Synthetic missing receipt',
          'actions':[{'item':'M001','destination':'Archive','reason':'Synthetic filing'}]}
        plan_path=self.root/'receiptless-plan.json';plan_path.write_text(json.dumps(plan));manifest=self.root/'receiptless-manifest.json';journal=self.root/'receiptless-journal.jsonl'
        def receiptless(snapshot,authorized,journal_path,recovery,**kwargs):
            row=snapshot['records'][0]
            intent={'item':row['item'],'account':row['account'],'message_id':row['message_id'],'old_id':row['current_id'],
              'old_mailbox':'INBOX','destination':'Archive','snapshot_id':snapshot['snapshot_id'],'attempt_id':'missing-receipt',
              'pre_destination_ids':[],'pre_source_junk':False,'reason':'Synthetic filing','at':'2026-11-18T12:06:00+00:00'}
            append_event(journal_path,{**intent,'status':'intent'})
            append_event(journal_path,{**intent,'status':'verified-moved','new_id':42,'junk':False})
        digest=__import__('hashlib').sha256(plan_path.read_bytes()).hexdigest()
        result=workflow.run_pipeline(source_path,plan_path,self.rules,manifest,journal,self.recovery,None,
          self.root/'runs'/'receiptless-partial'/'review.html',self.db,apply_adapter=receiptless,
          refresh_adapter=lambda _:self.fail('receiptless intent must not refresh'),authorized=True,expected_plan_digest=digest)
        self.assertEqual(result['status'],'partial');self.assertEqual(result['verified_items'],[])
        self.assertEqual(result['unresolved_items'],['M001']);self.assertEqual(result['mail_changed'],None)
        self.assertEqual(result['mail_change_status'],'unknown-awaiting-reconciliation')

    def test_legacy_timezone_setting_preserves_explicit_snapshot_zone(self):
        source={**self.snapshot,'run_id':'legacy-zone-run','timezone':'America/New_York'}
        normalized=normalize_snapshot(source);source_path=self.root/'legacy-zone-snapshot.json';source_path.write_text(json.dumps(source))
        plan={'snapshot_id':normalized['snapshot_id'],'started_at':'2026-11-18T12:05:00+00:00','authorization':'Legacy configuration timezone compatibility',
            'actions':[{'item':'M001','destination':'Archive','reason':'Synthetic authorized filing'}]}
        plan_path=self.root/'legacy-zone-plan.json';plan_path.write_text(json.dumps(plan));apply_adapter,refresh_adapter=self._success_adapters()
        digest=__import__('hashlib').sha256(plan_path.read_bytes()).hexdigest()
        with patch.object(config,'CONFIG_TIMEZONE_EXPLICIT',False):
            result=workflow.run_pipeline(source_path,plan_path,self.rules,self.root/'legacy-zone-manifest.json',self.root/'legacy-zone-journal.jsonl',self.recovery,None,self.root/'runs'/'legacy-zone-run'/'review.html',self.db,
                apply_adapter=apply_adapter,refresh_adapter=refresh_adapter,authorized=True,expected_plan_digest=digest)
        self.assertEqual(result['verified_actions'],1)
        self.assertEqual(history.get_registered_snapshot(self.db,'legacy-zone-run')['timezone'],'America/New_York')

    def test_legacy_timezone_setting_preserves_zone_during_read_only_refresh(self):
        source={**self.snapshot,'run_id':'legacy-zone-refresh','timezone':'America/New_York'};normalized=normalize_snapshot(source)
        snapshot_path=self.root/'legacy-zone-refresh-snapshot.json';snapshot_path.write_text(json.dumps(source))
        bundle=json.loads(json.dumps(self.bundle));bundle['run_id']=source['run_id'];bundle['snapshot_id']=normalized['snapshot_id']
        request=bundle['refresh_request'];request['run_id']=source['run_id'];request['snapshot_id']=normalized['snapshot_id']
        pending=request['pending_review'];pending['run_id']=source['run_id'];pending['snapshot_id']=normalized['snapshot_id']
        bundle_path=self.root/'legacy-zone-refresh-bundle.json';bundle_path.write_text(json.dumps(bundle))
        baseline_review=self.root/'runs'/source['run_id']/'review.html';baseline_review.parent.mkdir(parents=True);baseline_review.write_text('synthetic legacy baseline')
        history.register(self.db,source,baseline_review);output=self.root/'legacy-zone-refresh-output.json'
        with patch.object(config,'CONFIG_TIMEZONE_EXPLICIT',False):
            result=workflow.refresh_review(snapshot_path,bundle_path,output,self.db,
                refresh_adapter=lambda base:{**base,'refreshed_at':'2026-11-18T14:00:00+00:00'})
        refreshed=history.get_registered_snapshot(self.db,result['run_id'])
        self.assertEqual(refreshed['timezone'],'America/New_York')
        self.assertTrue(Path(result['review']).is_file())

    def test_explicit_timezone_mismatch_fails_before_apply(self):
        source={**self.snapshot,'timezone':'America/New_York'};source_path=self.root/'explicit-zone-snapshot.json';source_path.write_text(json.dumps(source))
        normalized=normalize_snapshot(source);plan={**self.plan,'snapshot_id':normalized['snapshot_id']};plan_path=self.root/'explicit-zone-plan.json';plan_path.write_text(json.dumps(plan))
        digest=__import__('hashlib').sha256(plan_path.read_bytes()).hexdigest()
        with patch.object(config,'CONFIG_TIMEZONE_EXPLICIT',True),patch.dict(config.CONFIG,{'timezone':'UTC'}):
            with self.assertRaisesRegex(ValueError,'differs from explicitly selected configuration'):
                workflow.run_pipeline(source_path,plan_path,self.rules,self.root/'explicit-zone-manifest.json',self.root/'explicit-zone-journal.jsonl',self.recovery,None,self.review_path,self.db,
                  apply_adapter=lambda *args,**kwargs:self.fail('timezone mismatch reached adapter'),authorized=True,expected_plan_digest=digest)

    def test_selected_account_mismatch_fails_before_apply(self):
        import config
        digest=__import__('hashlib').sha256(self.plan_path.read_bytes()).hexdigest()
        with patch.dict(config.CONFIG,{'account':'different@example.test'}):
            with self.assertRaisesRegex(ValueError,'selected Mail account'):
                workflow.run_pipeline(self.snapshot_path,self.plan_path,self.rules,self.manifest,self.journal,self.recovery,None,self.review_path,self.db,
                  apply_adapter=lambda *args,**kwargs:self.fail('apply must not run'),authorized=True,expected_plan_digest=digest)
        self.assertFalse(self.journal.exists());self.assertFalse(self.manifest.exists())

    def test_missing_explicit_account_scope_fails_before_apply(self):
        source=dict(self.snapshot);source.pop('account_scope')
        normalized=normalize_snapshot(source)
        plan={'snapshot_id':normalized['snapshot_id'],'started_at':'2026-11-18T12:05:00+00:00','authorization':'Synthetic','actions':[{'item':'M001','destination':'Archive','reason':'Synthetic'}]}
        source_path=self.root/'scope-missing.json';source_path.write_text(json.dumps(source));plan_path=self.root/'scope-missing-plan.json';plan_path.write_text(json.dumps(plan))
        with self.assertRaisesRegex(ValueError,'must name exactly the single selected Mail account'):
            workflow.run_pipeline(source_path,plan_path,self.rules,self.manifest,self.journal,self.recovery,None,self.review_path,self.db,
              apply_adapter=lambda *args,**kwargs:self.fail('apply must not run'),authorized=True,expected_plan_digest=__import__('hashlib').sha256(plan_path.read_bytes()).hexdigest())
        self.assertFalse(self.journal.exists());self.assertFalse(self.manifest.exists())

    def test_coordinator_reuses_only_matching_assessment_evidence_after_copy_id_changes(self):
        identity={'account':'synthetic@example.test','message_id':'full:mid@example.test','current_id':17};rules_digest=__import__('hashlib').sha256(self.rules.read_bytes()).hexdigest()
        # Assessments store the actual rules SHA; cache reuse requires all exact values to match.
        fp=assessments.fingerprint('content-digest',rules_digest,'thread-digest','0')
        history.record_assessment(self.db,'run-flow',identity,fingerprint=fp,assessed_at='2026-11-18T12:00:00+00:00',rules_digest=rules_digest,content_digest='content-digest',thread_digest='thread-digest',correction_version='0',evidence=[{'source':'synthetic','reference':'body-summary'}],result={'status':'uncertain'})
        evidence={'M001':{'account':'synthetic@example.test','message_id':'full:mid@example.test','current_id':42,'content_digest':'content-digest','thread_digest':'thread-digest','correction_version':'0'}}
        evidence_path=self.root/'assessment-evidence.json';evidence_path.write_text(json.dumps(evidence))
        apply_adapter,refresh_adapter=self._success_adapters();digest=__import__('hashlib').sha256(self.plan_path.read_bytes()).hexdigest()
        result=workflow.run_pipeline(self.snapshot_path,self.plan_path,self.rules,self.manifest,self.journal,self.recovery,None,self.review_path,self.db,
          assessment_evidence_path=evidence_path,apply_adapter=apply_adapter,refresh_adapter=refresh_adapter,authorized=True,expected_plan_digest=digest)
        self.assertEqual(result['assessment_readiness']['reusable'],1)
        run=history.export_history(self.db)[0];self.assertEqual(run['assessments'][0]['result']['status'],'uncertain')
        self.assertIn('reusable',self.review_path.read_text())

    def _prepare_resume_fixture(self):
        source={'run_id':'resume-source','scope':'Synthetic','snapshot_as_of':'2026-11-18T12:00:00+00:00','timezone':'UTC','account_scope':['synthetic@example.test'],'records':[
          {'item':'M001','account':'synthetic@example.test','message_id':'resume:mid@example.test','current_id':17,'observed_mailbox':'INBOX','to_display':'r@example.test','subject':'Synthetic','received':'2026-11-18T11:00:00+00:00','size_bytes':1,'gist':'Synthetic'}]}
        source_path=self.root/'resume-source.json';source_path.write_text(json.dumps(source));normalized=normalize_snapshot(source)
        plan={'snapshot_id':normalized['snapshot_id'],'started_at':'2026-11-18T12:05:00+00:00','authorization':'Explicit synthetic authorization','actions':[{'item':'M001','destination':'Archive','reason':'Authorized action'}]}
        plan_path=self.root/'resume-plan.json';plan_path.write_text(json.dumps(plan));manifest=self.root/'original-manifest.json';create_or_validate_manifest(manifest,normalized,plan,rules_digest(self.rules))
        journal=self.root/'interrupted.jsonl';append_event(journal,{'item':'M001','account':'synthetic@example.test','message_id':'resume:mid@example.test','old_id':17,'old_mailbox':'INBOX','destination':'Archive','pre_destination_ids':[],'pre_source_junk':False,'snapshot_id':normalized['snapshot_id'],'attempt_id':'retry-1','status':'intent'})
        return source_path,plan_path,manifest,journal

    def test_resume_creates_lineage_plan_for_only_verified_not_started_actions(self):
        source,plan,manifest,journal=self._prepare_resume_fixture()
        result=workflow.prepare_resume(source,plan,manifest,self.rules,journal,self.root/'resume-out',lambda intent:{'destination_ids':[],'destination_copies':[],'source_present':True,'source_exact':True,'source_junk':False,'identity_matches':True})
        self.assertEqual(result['status'],'ready');self.assertEqual(result['remaining_actions'],1)
        resume_plan=json.loads(Path(result['plan']).read_text());self.assertEqual([a['item'] for a in resume_plan['actions']],['M001'])
        lineage=json.loads(Path(result['lineage']).read_text());self.assertEqual(lineage['cutoff_at'],json.loads(manifest.read_text())['cutoff_at'])
        self.assertEqual(lineage['classifications'][0]['status'],'verified-not-started')

    def test_resume_inherits_verified_manifest_clock_after_runtime_advances(self):
        import datetime as dt
        start=dt.datetime(2026,11,18,12,0,tzinfo=dt.timezone.utc)
        class FrozenDateTime(dt.datetime):
            now_value=start
            @classmethod
            def now(cls,tz=None):
                value=cls.now_value
                return cls.fromtimestamp(value.timestamp(),tz) if tz else cls.fromtimestamp(value.timestamp())
        source={'run_id':'resume-clock','scope':'Synthetic','snapshot_as_of':start.isoformat(),'timezone':'UTC',
          'account_scope':['synthetic@example.test'],'records':[{'item':'M001','account':'synthetic@example.test',
          'message_id':'clock:mid@example.test','current_id':17,'observed_mailbox':'INBOX','to_display':'r@example.test',
          'subject':'Synthetic','received':(start-dt.timedelta(days=29)).isoformat(),'size_bytes':1,'gist':'Synthetic'}]}
        source_path=self.root/'resume-clock-source.json';source_path.write_text(json.dumps(source));normalized=normalize_snapshot(source)
        plan={'snapshot_id':normalized['snapshot_id'],'started_at':start.isoformat(),'authorization':'Explicit synthetic authorization',
          'actions':[{'item':'M001','destination':'Archive','reason':'Authorized action'}]}
        plan_path=self.root/'resume-clock-plan.json';plan_path.write_text(json.dumps(plan));manifest=self.root/'resume-clock-manifest.json'
        with patch.object(execution.dt,'datetime',FrozenDateTime):
            create_or_validate_manifest(manifest,normalized,plan,rules_digest(self.rules))
        original=json.loads(manifest.read_text());self.assertEqual(original['started_at'],start.isoformat())
        FrozenDateTime.now_value=start+dt.timedelta(days=2)
        with patch.object(execution.dt,'datetime',FrozenDateTime):
            result=workflow.prepare_resume(source_path,plan_path,manifest,self.rules,self.root/'resume-clock-journal.jsonl',
              self.root/'resume-clock-out',lambda intent:{'destination_ids':[],'destination_copies':[],
              'source_present':True,'source_exact':True,'source_junk':False,'identity_matches':True})
        self.assertEqual(result['status'],'ready')
        child_manifest=json.loads(Path(result['manifest']).read_text())
        child_lineage=json.loads(Path(result['lineage']).read_text())
        self.assertEqual(child_manifest['started_at'],original['started_at'])
        self.assertEqual(child_manifest['cutoff_at'],original['cutoff_at'])
        self.assertEqual(child_manifest['parent_manifest_sha256'],__import__('hashlib').sha256(manifest.read_bytes()).hexdigest())
        self.assertEqual(child_lineage['cutoff_at'],original['cutoff_at'])
        from apply_mail import validate_plan
        child_snapshot=json.loads(Path(result['snapshot']).read_text());child_plan=json.loads(Path(result['plan']).read_text())
        validate_plan(child_snapshot,child_plan,trusted_started_at=child_manifest['started_at'])
        apply_calls=[];journal=self.root/'resume-clock-apply.jsonl'
        def apply_remaining(current,authorized,journal_path,recovery,**kwargs):
            apply_calls.extend(action['item'] for action in authorized['actions'])
            row=current['records'][0];action=authorized['actions'][0]
            intent={'item':row['item'],'account':row['account'],'message_id':row['message_id'],'old_id':row['current_id'],
              'old_mailbox':row['observed_mailbox'],'destination':action['destination'],'snapshot_id':current['snapshot_id'],
              'attempt_id':'continued-after-clock-advance','pre_destination_ids':[],'pre_source_junk':False,
              'reason':action['reason'],'at':(start+dt.timedelta(days=2)).isoformat()}
            append_event(journal_path,{**intent,'status':'intent'})
            receipt={k:intent[k] for k in ('item','account','message_id','old_id','old_mailbox','destination','snapshot_id','attempt_id','pre_destination_ids','pre_source_junk')}
            receipt.update(status='move-receipt',new_id=42,junk=False,completed_at=(start+dt.timedelta(days=2,seconds=1)).isoformat())
            append_event(journal_path,receipt);append_event(journal_path,{**intent,'status':'verified-moved','new_id':42,'junk':False,'completed_at':receipt['completed_at']})
        def refresh_remaining(current):
            current['records'][0]['current_id']=42;current['records'][0]['observed_mailbox']='Archive'
            current['refreshed_at']=(start+dt.timedelta(days=2,seconds=2)).isoformat();return current
        review=self.root/'runs'/child_snapshot['run_id']/'review.html';review.parent.mkdir(parents=True)
        child_plan_path=Path(result['plan']);digest=__import__('hashlib').sha256(child_plan_path.read_bytes()).hexdigest()
        with patch.object(execution.dt,'datetime',FrozenDateTime):
            validated=workflow.run_pipeline(result['snapshot'],result['plan'],self.rules,result['manifest'],journal,self.recovery,
              None,review,self.db)
            self.assertTrue(validated['validated'])
            self.assertEqual(validated['plan_sha256'],digest)
            self.assertFalse(journal.exists())
            applied=workflow.run_pipeline(result['snapshot'],result['plan'],self.rules,result['manifest'],journal,self.recovery,
              None,review,self.db,apply_adapter=apply_remaining,refresh_adapter=refresh_remaining,authorized=True,expected_plan_digest=digest)
        self.assertEqual(apply_calls,['M001']);self.assertEqual(applied['verified_actions'],1)
        self.assertEqual(history.get_registered_snapshot(self.db,child_snapshot['run_id'])['records'][0]['current_id'],42)

    def test_resume_rejects_backdated_plan_claim_against_manifest_clock(self):
        import datetime as dt
        start=dt.datetime(2026,11,20,12,0,tzinfo=dt.timezone.utc)
        received=(start-dt.timedelta(days=31)).isoformat()
        source={'run_id':'resume-fabricated-clock','scope':'Synthetic','snapshot_as_of':start.isoformat(),'timezone':'UTC',
          'account_scope':['synthetic@example.test'],'records':[{'item':'M001','account':'synthetic@example.test',
          'message_id':'fabricated:mid@example.test','current_id':17,'observed_mailbox':'INBOX','to_display':'r@example.test',
          'subject':'Synthetic','received':received,'size_bytes':1,'gist':'Synthetic'}]}
        source_path=self.root/'resume-fabricated-source.json';source_path.write_text(json.dumps(source));normalized=normalize_snapshot(source)
        plan={'snapshot_id':normalized['snapshot_id'],'started_at':'2026-11-18T12:00:00+00:00',
          'authorization':'Fabricated backdated claim','actions':[{'item':'M001','destination':'Archive','reason':'Authorized action'}]}
        plan_path=self.root/'resume-fabricated-plan.json';plan_path.write_text(json.dumps(plan));manifest=self.root/'resume-fabricated-manifest.json'
        # The manifest clock is the trusted policy clock. A plan's older claimed date
        # must not make a 31-day-old item eligible.
        class FrozenDateTime(dt.datetime):
            @classmethod
            def now(cls,tz=None):return start.astimezone(tz) if tz else start.replace(tzinfo=None)
        with patch.object(execution.dt,'datetime',FrozenDateTime):
            created=create_or_validate_manifest(manifest,normalized,plan,rules_digest(self.rules))
        from apply_mail import validate_plan
        with self.assertRaisesRegex(ValueError,'Older/unknown-date mail is protected'):
            validate_plan(normalized,plan,trusted_started_at=created['started_at'])

    def test_resume_blocks_ambiguous_duplicate_destination(self):
        source,plan,manifest,journal=self._prepare_resume_fixture()
        result=workflow.prepare_resume(source,plan,manifest,self.rules,journal,self.root/'resume-blocked',lambda intent:{'destination_ids':[80,81],'destination_copies':[{'numeric_id':80,'message_id':'resume:mid@example.test','junk':False},{'numeric_id':81,'message_id':'resume:mid@example.test','junk':False}],'source_present':False,'source_exact':False,'source_junk':False,'identity_matches':True})
        self.assertEqual(result['status'],'blocked');self.assertIsNone(result['remaining_plan'])
        self.assertEqual(result['classifications'][0]['status'],'ambiguous')

    def test_pre_intent_conflict_can_continue_only_after_exact_source_recheck(self):
        source,plan,manifest,journal=self._prepare_resume_fixture()
        journal.unlink();append_event(journal,{'item':'M001','account':'synthetic@example.test','message_id':'resume:mid@example.test','old_id':17,'old_mailbox':'INBOX','destination':'Archive','snapshot_id':normalize_snapshot(json.loads(Path(source).read_text()))['snapshot_id'],'status':'conflict-or-failed','reason':'Cached path unavailable'})
        result=workflow.prepare_resume(source,plan,manifest,self.rules,journal,self.root/'resume-conflict',lambda intent:{'destination_ids':[70],'destination_copies':[{'numeric_id':70,'message_id':'resume:mid@example.test','junk':False}],'source_present':True,'source_exact':True,'source_junk':False,'identity_matches':True})
        self.assertEqual(result['status'],'ready');self.assertEqual(result['remaining_actions'],1)
        self.assertIn('verified-not-started',[event['status'] for event in workflow._read_journal(journal)])

    def test_resume_rebases_verified_completion_and_keeps_only_unstarted_authorized_action(self):
        source=json.loads(self.snapshot_path.read_text());source['run_id']='resume-two';source['records'].append(dict(source['records'][0],item='M002',message_id='second:mid@example.test',current_id=18,subject='Second'))
        source_path=self.root/'resume-two.json';source_path.write_text(json.dumps(source));normalized=normalize_snapshot(source)
        plan={'snapshot_id':normalized['snapshot_id'],'started_at':'2026-11-18T12:05:00+00:00','authorization':'Explicit synthetic authorization','actions':[{'item':'M001','destination':'Archive','reason':'First'},{'item':'M002','destination':'Trash','reason':'Second'}]}
        plan_path=self.root/'resume-two-plan.json';plan_path.write_text(json.dumps(plan));manifest=self.root/'resume-two-manifest.json';create_or_validate_manifest(manifest,normalized,plan,rules_digest(self.rules))
        journal=self.root/'resume-two-journal.jsonl'
        first={'item':'M001','account':'synthetic@example.test','message_id':'full:mid@example.test','old_id':17,'old_mailbox':'INBOX','destination':'Archive','snapshot_id':normalized['snapshot_id'],'attempt_id':'first','reason':'First','at':'2026-11-18T12:06:00+00:00','pre_destination_ids':[],'pre_source_junk':False}
        append_event(journal,{**first,'status':'intent'})
        append_event(journal,{k:first[k] for k in ('item','account','message_id','old_id','old_mailbox','destination','snapshot_id','attempt_id','pre_destination_ids','pre_source_junk')}|{'status':'move-receipt','new_id':42,'junk':False,'completed_at':'2026-11-18T12:06:01+00:00'})
        append_event(journal,{**first,'status':'verified-moved','new_id':42,'junk':False,'completed_at':'2026-11-18T12:06:01+00:00'})
        append_event(journal,{'item':'M002','account':'synthetic@example.test','message_id':'second:mid@example.test','old_id':18,'old_mailbox':'INBOX','destination':'Trash','pre_destination_ids':[],'pre_source_junk':False,'snapshot_id':normalized['snapshot_id'],'attempt_id':'second','status':'intent','reason':'Second','at':'2026-11-18T12:06:00+00:00'})
        result=workflow.prepare_resume(source_path,plan_path,manifest,self.rules,journal,self.root/'resume-two-out',lambda intent:{'destination_ids':[],'destination_copies':[],'source_present':True,'source_exact':True,'source_junk':False,'identity_matches':True})
        self.assertEqual(result['status'],'ready');resume_snapshot=json.loads(Path(result['snapshot']).read_text());resume_plan=json.loads(Path(result['plan']).read_text())
        self.assertEqual((resume_snapshot['records'][0]['current_id'],resume_snapshot['records'][0]['observed_mailbox']),(42,'Archive'))
        self.assertEqual([a['item'] for a in resume_plan['actions']],['M002'])
        self.assertEqual(resume_plan['started_at'],plan['started_at'])

    def test_resume_remaining_plan_can_apply_only_authorized_not_started_actions(self):
        source={**self.snapshot,'run_id':'resume-apply-source','records':[dict(self.snapshot['records'][0]),dict(self.snapshot['records'][0],item='M002',message_id='second:mid@example.test',current_id=18,subject='Second')]}
        source_path=self.root/'resume-apply-source.json';source_path.write_text(json.dumps(source));normalized=normalize_snapshot(source)
        plan_value={'snapshot_id':normalized['snapshot_id'],'started_at':'2026-11-18T12:05:00+00:00','authorization':'Explicit synthetic authorization','actions':[{'item':'M001','destination':'Archive','reason':'First'},{'item':'M002','destination':'Trash','reason':'Second'}]}
        plan=self.root/'resume-apply-plan.json';plan.write_text(json.dumps(plan_value));manifest=self.root/'resume-apply-manifest.json';create_or_validate_manifest(manifest,normalized,plan_value,rules_digest(self.rules))
        journal=self.root/'resume-apply-original.jsonl'
        first={'item':'M001','account':'synthetic@example.test','message_id':'full:mid@example.test','old_id':17,'old_mailbox':'INBOX','destination':'Archive','new_id':42,'snapshot_id':normalized['snapshot_id'],'attempt_id':'first','reason':'First','at':'2026-11-18T12:06:00+00:00','pre_destination_ids':[],'pre_source_junk':False}
        append_event(journal,{**first,'status':'intent'})
        append_event(journal,{k:first[k] for k in ('item','account','message_id','old_id','old_mailbox','destination','snapshot_id','attempt_id','pre_destination_ids','pre_source_junk')}|{'status':'move-receipt','new_id':42,'junk':False,'completed_at':'2026-11-18T12:06:01+00:00'})
        append_event(journal,{**first,'status':'verified-moved','junk':False,'completed_at':'2026-11-18T12:06:01+00:00'})
        append_event(journal,{'item':'M002','account':'synthetic@example.test','message_id':'second:mid@example.test','old_id':18,'old_mailbox':'INBOX','destination':'Trash','pre_destination_ids':[],'pre_source_junk':False,'snapshot_id':normalized['snapshot_id'],'attempt_id':'second','reason':'Second','at':'2026-11-18T12:06:00+00:00','status':'intent'})
        prepared=workflow.prepare_resume(source_path,plan,manifest,self.rules,journal,self.root/'resume-apply',lambda intent:{'destination_ids':[],'destination_copies':[],'source_present':True,'source_exact':True,'source_junk':False,'identity_matches':True})
        resume_snapshot=json.loads(Path(prepared['snapshot']).read_text());final={**resume_snapshot,'refreshed_at':'2026-11-18T12:08:00+00:00','records':[dict(resume_snapshot['records'][0]),dict(resume_snapshot['records'][1],observed_mailbox='Trash',current_id=52)]}
        final_path=self.root/'resume-final.json';final_path.write_text(json.dumps(final));new_journal=self.root/'resume-apply-journal.jsonl'
        calls=[]
        def apply_adapter(snapshot,remaining,journal_path,recovery,**kwargs):
            calls.extend(a['item'] for a in remaining['actions'])
            a=remaining['actions'][0];r=next(row for row in snapshot['records'] if row['item']==a['item'])
            intent={'item':r['item'],'account':r['account'],'message_id':r['message_id'],'old_id':r['current_id'],'old_mailbox':r['observed_mailbox'],'destination':a['destination'],'reason':a['reason'],'snapshot_id':snapshot['snapshot_id'],'attempt_id':'resume-second','pre_destination_ids':[],'pre_source_junk':False,'at':'2026-11-18T12:08:00+00:00'}
            append_event(journal_path,{**intent,'status':'intent'})
            append_event(journal_path,{k:intent[k] for k in ('item','account','message_id','old_id','old_mailbox','destination','snapshot_id','attempt_id','pre_destination_ids','pre_source_junk')}|{'status':'move-receipt','new_id':52,'junk':False,'completed_at':'2026-11-18T12:08:01+00:00'})
            append_event(journal_path,{**intent,'status':'verified-moved','new_id':52,'junk':False,'completed_at':'2026-11-18T12:08:01+00:00'})
            return []
        review_path=self.root/'runs'/resume_snapshot['run_id']/'review.html';review_path.parent.mkdir(parents=True)
        digest=__import__('hashlib').sha256(Path(prepared['plan']).read_bytes()).hexdigest()
        result=workflow.run_pipeline(prepared['snapshot'],prepared['plan'],self.rules,prepared['manifest'],new_journal,self.recovery,final_path,review_path,self.db,apply_adapter=apply_adapter,authorized=True,expected_plan_digest=digest)
        self.assertEqual(calls,['M002']);self.assertEqual(result['verified_actions'],2)
        actions={a['item']:a for a in history.export_history(self.db)[0]['actions']}
        self.assertEqual(set(actions),{'M001','M002'})
        self.assertEqual(actions['M001']['status'],'verified-completed')
        self.assertEqual(actions['M002']['status'],'verified-moved')

    def test_resume_preserves_item_specific_old_mail_override_and_exact_export_evidence(self):
        source={'run_id':'old-review-source','scope':'Synthetic','snapshot_as_of':'2026-11-18T12:00:00+00:00','timezone':'UTC','account_scope':['synthetic@example.test'],'records':[
          {'item':'M001','account':'synthetic@example.test','message_id':'old:first@example.test','current_id':71,'observed_mailbox':'INBOX','to_display':'r@example.test','subject':'Old first','received':'2026-10-01T11:00:00+00:00','size_bytes':1,'gist':'Protected old item'},
          {'item':'M002','account':'synthetic@example.test','message_id':'old:second@example.test','current_id':72,'observed_mailbox':'INBOX','to_display':'r@example.test','subject':'Old second','received':'2026-10-01T11:01:00+00:00','size_bytes':1,'gist':'Protected old item'}]}
        normalized=normalize_snapshot(source);source_path=self.root/'old-review-source.json';source_bytes=json.dumps(source,separators=(',',':')).encode();source_path.write_bytes(source_bytes)
        bundle={'kind':'email-triage-review-bundle','version':1,'run_id':source['run_id'],'snapshot_id':normalized['snapshot_id'],'exported_at':'2026-11-18T12:05:00.000Z',
          'moves':[{'item':'M001','account':'synthetic@example.test','message_id':'old:first@example.test','snapshot_mailbox':'INBOX','snapshot_numeric_id':71,'destination':'archive'},
                   {'item':'M002','account':'synthetic@example.test','message_id':'old:second@example.test','snapshot_mailbox':'INBOX','snapshot_numeric_id':72,'destination':'archive'}],
          'opt_outs':[],'tasks':[],'comments':[],'refresh_request':None}
        bundle_path=self.root/'old-review-bundle.json';bundle_bytes=json.dumps(bundle,separators=(',',':')).encode();bundle_path.write_bytes(bundle_bytes)
        plan=workflow.plan_undo(bundle,source,bundle_bytes,source_bytes);self.assertTrue(all('age_override' in action for action in plan['actions']))
        plan_path=self.root/'old-review-plan.json';plan_path.write_text(json.dumps(plan));manifest=self.root/'old-review-manifest.json'
        create_or_validate_manifest(manifest,normalized,plan,rules_digest(self.rules))
        journal=self.root/'old-review-journal.jsonl'
        first={'item':'M001','account':'synthetic@example.test','message_id':'old:first@example.test','old_id':71,'old_mailbox':'INBOX','destination':'Archive','pre_destination_ids':[],'pre_source_junk':False,'snapshot_id':normalized['snapshot_id'],'attempt_id':'old-first','reason':'Move first','at':'2026-11-18T12:06:00+00:00'}
        append_event(journal,{**first,'status':'intent'})
        append_event(journal,{k:first[k] for k in ('item','account','message_id','old_id','old_mailbox','destination','snapshot_id','attempt_id','pre_destination_ids','pre_source_junk')}|{'status':'move-receipt','new_id':81,'junk':False,'completed_at':'2026-11-18T12:06:01+00:00'})
        second={'item':'M002','account':'synthetic@example.test','message_id':'old:second@example.test','old_id':72,'old_mailbox':'INBOX','destination':'Archive','pre_destination_ids':[],'pre_source_junk':False,'snapshot_id':normalized['snapshot_id'],'attempt_id':'old-second','reason':'Move second','at':'2026-11-18T12:06:00+00:00'}
        append_event(journal,{**second,'status':'intent'})
        result=workflow.prepare_resume(source_path,plan_path,manifest,self.rules,journal,self.root/'old-review-resume',lambda intent:({'destination_ids':[81],'destination_copies':[{'numeric_id':81,'message_id':'old:first@example.test','junk':False}],'source_present':False,'source_exact':False,'source_junk':False,'identity_matches':True,'new_id':81} if intent['item']=='M001' else {'destination_ids':[],'destination_copies':[],'source_present':True,'source_exact':True,'source_junk':False,'identity_matches':True}))
        resumed=json.loads(Path(result['plan']).read_text());self.assertEqual([a['item'] for a in resumed['actions']],['M002'])
        self.assertEqual(resumed['actions'][0]['age_override']['item'],'M002')
        self.assertEqual(resumed['user_review_evidence']['export_sha256'],__import__('hashlib').sha256(bundle_bytes).hexdigest())
        self.assertEqual(resumed['user_review_evidence']['snapshot_sha256'],__import__('hashlib').sha256(source_bytes).hexdigest())

    def test_undo_bundle_is_exact_identity_bound(self):
        source={**self.snapshot,'records':[dict(self.snapshot['records'][0],observed_mailbox='Archive',current_id=42)]};normalized=normalize_snapshot(source)
        bundle={'kind':'email-triage-review-bundle','version':1,'run_id':normalized['run_id'],'snapshot_id':normalized['snapshot_id'],'exported_at':'2026-11-18T12:00:00.000Z','moves':[{'item':'M001','account':'synthetic@example.test','message_id':'full:mid@example.test','snapshot_mailbox':'Archive','snapshot_numeric_id':42,'destination':'inbox'}],'opt_outs':[],'tasks':[],'comments':[],'refresh_request':None}
        plan=workflow.plan_undo(bundle,source);self.assertEqual(plan['actions'][0]['destination'],'INBOX')
        bundle['moves'][0]['snapshot_numeric_id']=43
        with self.assertRaisesRegex(ValueError,'Changed snapshot identity'):workflow.plan_undo(bundle,source)

    def test_verified_terminal_requires_one_exact_durable_receipt(self):
        intent={'status':'intent','item':'M001','account':'synthetic@example.test','message_id':'full:mid@example.test','old_id':17,
            'old_mailbox':'INBOX','destination':'Archive','snapshot_id':'snapshot','attempt_id':'attempt','pre_destination_ids':[],'pre_source_junk':False}
        terminal={**intent,'status':'verified-moved','new_id':42,'junk':False}
        receipt={k:intent[k] for k in ('item','account','message_id','old_id','old_mailbox','destination','snapshot_id','attempt_id','pre_destination_ids','pre_source_junk')}
        receipt.update(status='move-receipt',new_id=42,junk=False,completed_at='2026-11-18T12:00:00+00:00')
        invalid=[ [intent,terminal], [intent,receipt,receipt,terminal], [intent,{**receipt,'new_id':43},terminal],
            [intent,{**receipt,'attempt_id':'other'},terminal], [intent,{**receipt,'old_id':18},terminal],
            [intent,receipt,terminal,{**terminal,'status':'ambiguous'}] ]
        for events in invalid:
            state=workflow._attempt_state(events,'snapshot')
            with self.subTest(events=events):
                self.assertEqual(state['verified'],[])
                self.assertIn('M001',{event.get('item') for event in state['ambiguous']})
                self.assertIn('M001',{event.get('item') for event in state['unresolved']})

    def test_mutating_coordinator_rejects_read_only_refresh_bundle(self):
        digest=__import__('hashlib').sha256(self.bundle_path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'[Rr]ead-only refresh'):
            workflow.run_pipeline(self.snapshot_path,None,self.rules,self.manifest,self.journal,self.recovery,None,self.review_path,self.db,
                bundle_path=self.bundle_path,apply_adapter=lambda *a,**k:self.fail('refresh envelope reached mutating adapter'),
                refresh_adapter=lambda *a,**k:self.fail('refresh envelope reached post-action refresh'),authorized=True,expected_plan_digest=digest)

    def test_read_only_refresh_registers_html_and_separate_action_export_can_apply(self):
        self.review_path.write_text('BASELINE HTML - DO NOT OVERWRITE')
        history.register(self.db,self.snapshot,self.review_path)
        baseline_html=self.review_path.read_bytes();baseline_snapshot=history.get_registered_snapshot(self.db,'run-flow')
        original_bundle=self.bundle_path.read_bytes();output=self.root/'refresh'/'snapshot.json'
        def refreshed(base):
            value=json.loads(json.dumps(base));value['records'][0]['current_id']=88;value['refreshed_at']='2026-11-18T14:00:00+00:00';return value
        refresh=workflow.refresh_review(self.snapshot_path,self.bundle_path,output,self.db,refresh_adapter=refreshed)
        self.assertTrue(Path(refresh['review']).is_file())
        self.assertIn('Pending edits preserved',Path(refresh['review']).read_text())
        self.assertIn('after you explicitly authorize application',Path(refresh['review']).read_text())
        self.assertIn('conflict-unapplied',Path(refresh['review']).read_text())
        self.assertEqual(refresh['item_outcomes'][0]['status'],'conflict-unapplied')
        self.assertEqual(Path(refresh['pending_review_bundle']).read_bytes(),original_bundle)
        self.assertEqual(self.review_path.read_bytes(),baseline_html)
        self.assertEqual(history.get_registered_snapshot(self.db,'run-flow'),baseline_snapshot)
        refreshed_snapshot=json.loads(output.read_text())
        self.assertNotEqual(refreshed_snapshot['run_id'],'run-flow')
        # The later export is a new explicit action authorization, bound to the
        # refreshed snapshot and current numeric copy identity. No marker stripping.
        identity={'item':'M001','account':'synthetic@example.test','message_id':'full:mid@example.test','snapshot_mailbox':'INBOX','snapshot_numeric_id':88}
        action={'kind':'email-triage-review-bundle','version':1,'run_id':refreshed_snapshot['run_id'],'snapshot_id':refreshed_snapshot['snapshot_id'],'exported_at':'2026-11-18T14:30:00.000Z',
            'moves':[dict(identity,destination='archive')],'opt_outs':[dict(identity)],
            'tasks':[dict(identity,instruction='Review the confirmation.')],
            'comments':[dict(identity,original_summary='Synthetic summary',comment='Correction: this is still pending.')],
            'refresh_request':None}
        action_path=self.root/'explicit-action.json';action_path.write_text(json.dumps(action))
        action_snapshot_path=self.root/'refreshed-snapshot.json';action_snapshot_path.write_text(json.dumps(refreshed_snapshot))
        move_calls=[]
        # This is a newly authored action-only export for the refreshed run.
        digest=__import__('hashlib').sha256(action_path.read_bytes()).hexdigest()
        def apply_with_receipt(source,plan,journal,recovery,**kwargs):
            move_calls.extend(plan['actions'])
            row=source['records'][0];intent={'item':row['item'],'account':row['account'],'message_id':row['message_id'],'old_id':row['current_id'],'old_mailbox':'INBOX','destination':'Archive','reason':'explicit','snapshot_id':source['snapshot_id'],'attempt_id':'later-explicit','pre_destination_ids':[],'pre_source_junk':False,'at':'2026-11-18T15:00:00+00:00'}
            append_event(journal,{**intent,'status':'intent'})
            append_event(journal,{k:intent[k] for k in ('item','account','message_id','old_id','old_mailbox','destination','snapshot_id','attempt_id','pre_destination_ids','pre_source_junk')}|{'status':'move-receipt','new_id':99,'junk':False,'completed_at':'2026-11-18T15:00:01+00:00'})
            append_event(journal,{**intent,'status':'verified-moved','new_id':99,'junk':False,'completed_at':'2026-11-18T15:00:01+00:00'})
        def moved(base):
            value=json.loads(json.dumps(base));value['records'][0]['current_id']=99;value['records'][0]['observed_mailbox']='Archive';value['refreshed_at']='2026-11-18T15:01:00+00:00';return value
        second=workflow.run_pipeline(action_snapshot_path,None,self.rules,self.root/'runs'/'explicit-manifest.json',self.root/'runs'/'explicit-journal.jsonl',self.recovery,None,self.root/'runs'/refreshed_snapshot['run_id']/'review.html',self.db,
            bundle_path=action_path,apply_adapter=apply_with_receipt,refresh_adapter=moved,authorized=True,expected_plan_digest=digest)
        self.assertEqual(second['verified_actions'],1);self.assertEqual(len(move_calls),1)
        self.assertFalse(second.get('already_processed',False))
        self.assertIsNotNone(history.get_export_receipt(self.db,__import__('hashlib').sha256(original_bundle).hexdigest(),operation='refresh'))
        self.assertIsNotNone(history.get_export_receipt(self.db,digest,operation='apply'))

    def test_receipt_backed_completion_rebases_refresh_and_history(self):
        import refresh_mail
        history.register(self.db,self.snapshot,self.review_path)
        intent={'item':'M001','account':'synthetic@example.test','message_id':'full:mid@example.test','old_id':17,'old_mailbox':'INBOX','destination':'Archive','reason':'synthetic interrupted move','snapshot_id':self.normalized['snapshot_id'],'attempt_id':'interrupted','pre_destination_ids':[],'pre_source_junk':False,'at':'2026-11-18T12:06:00+00:00'}
        append_event(self.journal,{**intent,'status':'intent'})
        append_event(self.journal,{k:intent[k] for k in ('item','account','message_id','old_id','old_mailbox','destination','snapshot_id','attempt_id','pre_destination_ids','pre_source_junk')}|{'status':'move-receipt','new_id':42,'junk':False,'completed_at':'2026-11-18T12:06:01+00:00'})
        def inspect(_):return {'destination_ids':[42],'destination_copies':[{'numeric_id':42,'message_id':'full:mid@example.test','junk':False}],
            'source_present':False,'source_exact':False,'source_junk':False,'identity_matches':True}
        workflow.continue_run(self.journal,inspect)
        def must_not_apply(*args,**kwargs):self.fail('receipt-backed completion was replayed')
        def fresh_inventory(base,database,*,account,prefix,verify_mail,local_files,include_prior,item_allocator):
            self.assertEqual(base['records'],[]);self.assertFalse(include_prior)
            base['refreshed_at']='2026-11-18T12:07:00+00:00';return base
        # Reuse original explicit plan only as a validation token; this journal
        # has already proven completion, so the adapter must not be called.
        digest=__import__('hashlib').sha256(self.plan_path.read_bytes()).hexdigest()
        with patch.object(refresh_mail,'DATABASE',str(self.root/'synthetic-mail.sqlite3')),patch.object(refresh_mail,'ACCOUNT','synthetic@example.test'),patch.object(refresh_mail,'PREFIX','imap://synthetic@example.test/'),patch.object(refresh_mail,'resolve_local_files',return_value={}),patch.object(refresh_mail,'refresh_snapshot',side_effect=fresh_inventory),patch('apply_mail.lookup_many',return_value={('synthetic@example.test','full:mid@example.test',42):False}) as current_checks:
            result=workflow.run_pipeline(self.snapshot_path,self.plan_path,self.rules,self.manifest,self.journal,self.recovery,None,self.review_path,self.db,
                apply_adapter=must_not_apply,authorized=True,expected_plan_digest=digest)
        self.assertEqual(result['verified_actions'],1)
        self.assertEqual(current_checks.call_args.args[0][0]['current_id'],42)
        published=history.get_registered_snapshot(self.db,result['run_id'])
        self.assertEqual((published['records'][0]['current_id'],published['records'][0]['observed_mailbox']),(42,'Archive'))
        action=next(run['actions'][0] for run in history.export_history(self.db) if run['actions'])
        self.assertEqual((action['status'],action['old_id'],action['new_id']),('verified-completed',17,42))
        self.assertEqual((action['attempt_id'],action['receipt_new_id']),('interrupted',42))
        rendered=Path(result['review']).read_text()
        self.assertIn('verified-completed',rendered);self.assertIn('"receipt_new_id": 42',rendered)
        self.assertIn('verified moves',rendered);self.assertIn('Request undo for ${action.item}',rendered)

    def test_post_action_copy_change_blocks_stale_publication_without_replay(self):
        import refresh_mail
        apply_adapter,_=self._success_adapters()
        apply_calls=[]
        def applied(*args,**kwargs):
            apply_calls.append(True)
            return apply_adapter(*args,**kwargs)
        def inventory(base,*args,**kwargs):
            base['refreshed_at']='2026-11-18T12:07:00+00:00'
            return base
        digest=__import__('hashlib').sha256(self.plan_path.read_bytes()).hexdigest()
        # A missing exact copy, changed Junk flag, or incomplete lookup cannot
        # turn the historical move receipt into a fresh placement assertion.
        for checked in (ValueError('Exact copy moved elsewhere'),True,None):
            with self.subTest(checked=repr(checked)):
                with patch.object(refresh_mail,'DATABASE',str(self.root/'synthetic-mail.sqlite3')),patch.object(refresh_mail,'ACCOUNT','synthetic@example.test'),patch.object(refresh_mail,'PREFIX','imap://synthetic@example.test/'),patch.object(refresh_mail,'resolve_local_files',return_value={}),patch.object(refresh_mail,'refresh_snapshot',side_effect=inventory),patch('apply_mail.lookup_many',return_value={('synthetic@example.test','full:mid@example.test',42):checked}):
                    with self.assertRaisesRegex(ValueError,'Post-action exact-copy'):
                        workflow.run_pipeline(self.snapshot_path,self.plan_path,self.rules,self.manifest,self.journal,self.recovery,None,self.review_path,self.db,
                            apply_adapter=applied,authorized=True,expected_plan_digest=digest)
                self.assertIsNone(history.get_registered_snapshot(self.db,'run-flow'))
                self.assertFalse(self.review_path.exists())
                self.assertFalse(self.manifest.with_suffix('.verified-snapshot.json').exists())
        self.assertEqual(len(apply_calls),1)
        self.assertTrue(any(event['status']=='verified-moved' for event in workflow._read_journal(self.journal)))

    def test_vanished_conflicted_copy_does_not_substitute_duplicate_for_successful_action(self):
        source={**self.snapshot,'run_id':'vanished-run','records':[dict(self.snapshot['records'][0]),dict(self.snapshot['records'][0],item='M002',message_id='second:mid@example.test',current_id=18,subject='Second')]}
        source_path=self.root/'vanished-snapshot.json';source_path.write_text(json.dumps(source));normalized=normalize_snapshot(source)
        plan={'snapshot_id':normalized['snapshot_id'],'started_at':'2026-11-18T12:05:00+00:00','authorization':'Independent test actions',
            'actions':[{'item':'M001','destination':'Archive','reason':'First'},{'item':'M002','destination':'Archive','reason':'Second'}]}
        plan_path=self.root/'vanished-plan.json';plan_path.write_text(json.dumps(plan));journal=self.root/'vanished-journal.jsonl'
        def partial(snapshot,authorized,journal_path,recovery,**kwargs):
            row=snapshot['records'][0];append_event(journal_path,{'item':'M001','account':row['account'],'message_id':row['message_id'],'old_id':17,'old_mailbox':'INBOX','destination':'Archive','snapshot_id':snapshot['snapshot_id'],'status':'conflict-or-failed','error':'exact copy vanished'})
            row=snapshot['records'][1];intent={'item':'M002','account':row['account'],'message_id':row['message_id'],'old_id':18,'old_mailbox':'INBOX','destination':'Archive','reason':'Second','snapshot_id':snapshot['snapshot_id'],'attempt_id':'success-second','pre_destination_ids':[],'pre_source_junk':False,'at':'2026-11-18T12:06:00+00:00'}
            append_event(journal_path,{**intent,'status':'intent'});append_event(journal_path,{k:intent[k] for k in ('item','account','message_id','old_id','old_mailbox','destination','snapshot_id','attempt_id','pre_destination_ids','pre_source_junk')}|{'status':'move-receipt','new_id':52,'junk':False,'completed_at':'2026-11-18T12:06:01+00:00'});append_event(journal_path,{**intent,'status':'verified-moved','new_id':52,'junk':False,'completed_at':'2026-11-18T12:06:01+00:00'})
        def current(base):
            # Original M001 copy is gone. A duplicate MID with another numeric
            # ID is current, but cannot stand in for that selected exact copy.
            base['records']=[dict(base['records'][0],item='M003',current_id=77,message_id='full:mid@example.test'),dict(base['records'][1],current_id=52,observed_mailbox='Archive')]
            base['refreshed_at']='2026-11-18T12:07:00+00:00';return base
        digest=__import__('hashlib').sha256(plan_path.read_bytes()).hexdigest()
        result=workflow.run_pipeline(source_path,plan_path,self.rules,self.root/'vanished-manifest.json',journal,self.recovery,None,self.root/'runs'/'vanished-run'/'review.html',self.db,
            apply_adapter=partial,refresh_adapter=current,authorized=True,expected_plan_digest=digest)
        self.assertEqual(result['verified_actions'],1)
        rows=history.get_registered_snapshot(self.db,'vanished-run')['records']
        self.assertNotIn('M001',{row['item'] for row in rows});self.assertIn('M003',{row['item'] for row in rows})
        self.assertEqual([action['item'] for action in history.export_history(self.db)[0]['actions']],['M002'])

    def test_real_inventory_path_publishes_success_when_conflicted_exact_copy_vanishes(self):
        import refresh_mail
        source={**self.snapshot,'run_id':'real-inventory-partial','records':[dict(self.snapshot['records'][0]),dict(self.snapshot['records'][0],item='M002',message_id='second:mid@example.test',current_id=18,subject='Second')]}
        source_path=self.root/'real-inventory-partial.json';source_path.write_text(json.dumps(source));normalized=normalize_snapshot(source)
        plan={'snapshot_id':normalized['snapshot_id'],'started_at':'2026-11-18T12:05:00+00:00','authorization':'Independent synthetic actions',
            'actions':[{'item':'M001','destination':'Archive','reason':'First'},{'item':'M002','destination':'Archive','reason':'Second'}]}
        plan_path=self.root/'real-inventory-partial-plan.json';plan_path.write_text(json.dumps(plan));journal=self.root/'real-inventory-partial-journal.jsonl'
        def partial(snapshot,authorized,journal_path,recovery,**kwargs):
            first=snapshot['records'][0];append_event(journal_path,{'item':'M001','account':first['account'],'message_id':first['message_id'],'old_id':17,'old_mailbox':'INBOX','destination':'Archive','snapshot_id':snapshot['snapshot_id'],'status':'conflict-or-failed','error':'exact copy vanished'})
            second=snapshot['records'][1];intent={'item':'M002','account':second['account'],'message_id':second['message_id'],'old_id':18,'old_mailbox':'INBOX','destination':'Archive','reason':'Second','snapshot_id':snapshot['snapshot_id'],'attempt_id':'real-success-second','pre_destination_ids':[],'pre_source_junk':False,'at':'2026-11-18T12:06:00+00:00'}
            append_event(journal_path,{**intent,'status':'intent'});append_event(journal_path,{k:intent[k] for k in ('item','account','message_id','old_id','old_mailbox','destination','snapshot_id','attempt_id','pre_destination_ids','pre_source_junk')}|{'status':'move-receipt','new_id':52,'junk':False,'completed_at':'2026-11-18T12:06:01+00:00'});append_event(journal_path,{**intent,'status':'verified-moved','new_id':52,'junk':False,'completed_at':'2026-11-18T12:06:01+00:00'})
        calls=[]
        def inventory(base,database,*,account,prefix,verify_mail,local_files,include_prior,item_allocator):
            calls.append({'items':[row['item'] for row in base['records']],'include_prior':include_prior})
            self.assertEqual([row['item'] for row in base['records']],['M001'])
            self.assertFalse(include_prior)
            value=json.loads(json.dumps(base));duplicate=dict(value['records'][0]);duplicate['item']=item_allocator({'account':duplicate['account'],'message_id':duplicate['message_id'],'current_id':77});duplicate['current_id']=77
            value['records']=[duplicate];value['refreshed_at']='2026-11-18T12:07:00+00:00';return value
        digest=__import__('hashlib').sha256(plan_path.read_bytes()).hexdigest()
        with patch.object(refresh_mail,'DATABASE',str(self.root/'synthetic-mail.sqlite3')),patch.object(refresh_mail,'ACCOUNT','synthetic@example.test'),patch.object(refresh_mail,'PREFIX','imap://synthetic@example.test/'),patch.object(refresh_mail,'resolve_local_files',return_value={}),patch.object(refresh_mail,'refresh_snapshot',side_effect=inventory),patch('apply_mail.lookup_many',return_value={('synthetic@example.test','second:mid@example.test',52):False}):
            result=workflow.run_pipeline(source_path,plan_path,self.rules,self.root/'real-inventory-partial-manifest.json',journal,self.recovery,None,self.root/'runs'/'real-inventory-partial'/'review.html',self.db,
                apply_adapter=partial,authorized=True,expected_plan_digest=digest)
        rows=history.get_registered_snapshot(self.db,'real-inventory-partial')['records']
        self.assertEqual(calls,[{'items':['M001'],'include_prior':False}])
        self.assertEqual({row['item']:row['current_id'] for row in rows},{'M002':52,'M003':77})
        actions=next(run['actions'] for run in history.export_history(self.db) if run['run_id']=='real-inventory-partial')
        self.assertEqual([action['item'] for action in actions],['M002'])


if __name__=='__main__':unittest.main()
