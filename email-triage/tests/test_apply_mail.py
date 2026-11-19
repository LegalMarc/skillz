import datetime as dt
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import shutil
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import apply_mail as a
import execution
import config
from review import normalize_snapshot

class ApplyTests(unittest.TestCase):
    def setUp(self):
        # Calendar-bound fixture dates remain stable when CI runs in later months.
        import datetime as calendar
        class FixtureDateTime(calendar.datetime):
            @classmethod
            def now(cls,tz=None):
                value=cls(2026,11,19,12,tzinfo=calendar.timezone.utc)
                return value.astimezone(tz) if tz else value.replace(tzinfo=None)
        clock=patch.object(dt,'datetime',FixtureDateTime)
        clock.start();self.addCleanup(clock.stop)
        self.lock_root=Path(tempfile.mkdtemp(prefix='email-triage-global-lock-test-')).resolve()
        self.addCleanup(shutil.rmtree,self.lock_root,ignore_errors=True)
        self.config_patch=patch.dict(config.CONFIG,{'account':'test','database':'/tmp/synthetic/Mail/Envelope Index','mailbox_prefix':'imap://synthetic-account/','state_root':str(self.lock_root/'state')})
        self.config_patch.start();self.addCleanup(self.config_patch.stop)
        self.lock_patch=patch.object(execution,'account_lock_root',return_value=self.lock_root/'locks')
        self.lock_patch.start();self.addCleanup(self.lock_patch.stop)
        self.source={'run_id':'test','scope':'Synthetic','snapshot_as_of':'2026-11-17','account_scope':['test'],'records':[{'item':'M1','account':'test','message_id':'full:odd@example.test','current_id':9,'observed_mailbox':'INBOX','to_display':'test@example.test','subject':'Synthetic','received':'2026-11-16T12:00:00+00:00','size_bytes':10,'gist':'Synthetic'}]}
        self.plan={'snapshot_id':normalize_snapshot(self.source)['snapshot_id'],'started_at':'2026-11-17T12:00:00+00:00','authorization':'Explicit synthetic test','actions':[{'item':'M1','destination':'Archive','reason':'Synthetic'}]}
    def test_rolling_boundary_and_unknown_dates(self):
        self.assertFalse(a.protected('2026-10-18T12:00:00+00:00',self.plan['started_at']))
        self.assertTrue(a.protected('2026-10-18T11:59:59+00:00',self.plan['started_at']))
        self.assertTrue(a.protected(None,self.plan['started_at']))
        with self.assertRaises(ValueError):a.protected('2026-10-18',self.plan['started_at'])
    def test_old_mail_only_can_be_restored_or_retained(self):
        self.source['records'][0]['received']='2022-01-01T00:00:00+00:00'
        self.plan['snapshot_id']=normalize_snapshot(self.source)['snapshot_id']
        for folder in ['Archive','Junk','Trash']:
            self.plan['actions'][0]['destination']=folder
            with self.assertRaisesRegex(ValueError,'protected'):a.validate_plan(self.source,self.plan)
        self.plan['actions'][0]['destination']='INBOX';a.validate_plan(self.source,self.plan)

    def test_unknown_date_generic_disposition_is_rejected(self):
        source={**self.source,'records':[dict(self.source['records'][0],received=None)]}
        plan={**self.plan,'snapshot_id':normalize_snapshot(source)['snapshot_id']}
        with self.assertRaisesRegex(ValueError,'protected'):
            a.validate_plan(source,plan,trusted_started_at='2026-11-19T12:00:00+00:00')

    def test_caller_backdated_plan_time_does_not_move_cutoff(self):
        source={**self.source,'records':[dict(self.source['records'][0],received='2020-01-01T00:00:00+00:00')]}
        plan={**self.plan,'snapshot_id':normalize_snapshot(source)['snapshot_id'],'started_at':'2000-01-01T00:00:00+00:00'}
        with self.assertRaisesRegex(ValueError,'protected'):
            a.validate_plan(source,plan,trusted_started_at='2026-11-19T12:00:00+00:00')

    def _user_override_plan(self):
        source={**self.source,'records':[dict(self.source['records'][0],received=None)]}
        snapshot=normalize_snapshot(source)
        request={'item':'M1','account':'test','message_id':'full:odd@example.test','snapshot_mailbox':'INBOX','snapshot_numeric_id':9,'destination':'archive'}
        bundle={'version':1,'kind':'email-triage-review-bundle','run_id':'test','snapshot_id':snapshot['snapshot_id'],'exported_at':'2026-11-17T12:00:00.000Z','moves':[request],'opt_outs':[],'tasks':[],'comments':[],'refresh_request':None}
        bundle_bytes=json.dumps(bundle,separators=(',',':')).encode()
        source_bytes=json.dumps(source,separators=(',',':')).encode()
        digest=__import__('hashlib').sha256(bundle_bytes).hexdigest()
        source_digest=__import__('hashlib').sha256(source_bytes).hexdigest()
        plan={'snapshot_id':snapshot['snapshot_id'],'started_at':bundle['exported_at'],'authorization':'Validated exact-snapshot user review bundle.','actions':[{'item':'M1','destination':'Archive','reason':'User-requested move','age_override':{'source':'validated-user-review','export_sha256':digest,'item':'M1','account':'test','message_id':'full:odd@example.test','numeric_id':9}}],
          'user_review_evidence':{'bundle_json':bundle_bytes.decode(),'export_sha256':digest,'snapshot_json':source_bytes.decode(),'snapshot_sha256':source_digest}}
        return source,plan

    def test_exact_typed_user_move_can_override_unknown_date(self):
        source,plan=self._user_override_plan()
        a.validate_plan(source,plan)

    def test_direct_user_instruction_override_is_honest_and_exact_copy_bound(self):
        source={**self.source,'records':[dict(self.source['records'][0],received=None)]}
        snapshot=normalize_snapshot(source)
        action={'item':'M1','destination':'Trash','reason':'Explicit item instruction','age_override':{
          'source':'direct-user-instruction','attestation':'caller-attested-not-cryptographically-verified','item':'M1','account':'test',
          'message_id':'full:odd@example.test','numeric_id':9,'destination':'Trash','instruction':'Move this exact older message to recoverable Trash.'}}
        plan={'snapshot_id':snapshot['snapshot_id'],'started_at':'2026-11-19T12:00:00+00:00','authorization':'Explicit item-scoped request','actions':[action]}
        a.validate_plan(source,plan)
        with tempfile.TemporaryDirectory() as tmp:
            manifest=execution.create_or_validate_manifest(Path(tmp).resolve()/'manifest.json',snapshot,plan,'a'*64,authorized_accounts=['test'])
            self.assertEqual(manifest['age_overrides'],[action['age_override']])
        changed=json.loads(json.dumps(plan));changed['actions'][0]['age_override']['message_id']='other'
        with self.assertRaisesRegex(ValueError,'exact item and destination'):a.validate_plan(source,changed)

    def test_age_override_rejects_mismatched_copy_or_blanket_claim(self):
        source,plan=self._user_override_plan()
        for field,value in [('item','M2'),('account','other'),('message_id','different'),('numeric_id',10)]:
            altered=json.loads(json.dumps(plan));altered['actions'][0]['age_override'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):a.validate_plan(source,altered)
        blanket=json.loads(json.dumps(plan));blanket.pop('user_review_evidence');blanket['authorization']='User says override old messages'
        with self.assertRaises(ValueError):a.validate_plan(source,blanket)
        wrong_digest=json.loads(json.dumps(plan));wrong_digest['user_review_evidence']['export_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'digest mismatch'):a.validate_plan(source,wrong_digest)
        mismatched_source=json.loads(json.dumps(plan))
        original=json.loads(mismatched_source['user_review_evidence']['snapshot_json'])
        original['records'][0]['current_id']=10
        original_snapshot=normalize_snapshot(original)
        review=json.loads(mismatched_source['user_review_evidence']['bundle_json'])
        review['snapshot_id']=original_snapshot['snapshot_id'];review['moves'][0]['snapshot_numeric_id']=10
        source_bytes=json.dumps(original,separators=(',',':')).encode()
        bundle_bytes=json.dumps(review,separators=(',',':')).encode()
        evidence=mismatched_source['user_review_evidence']
        evidence['snapshot_json']=source_bytes.decode();evidence['snapshot_sha256']=__import__('hashlib').sha256(source_bytes).hexdigest()
        evidence['bundle_json']=bundle_bytes.decode();evidence['export_sha256']=__import__('hashlib').sha256(bundle_bytes).hexdigest()
        mismatched_source['actions'][0]['age_override']['export_sha256']=evidence['export_sha256']
        with self.assertRaisesRegex(ValueError,'exact selected move'):a.validate_plan(source,mismatched_source)

    def test_standalone_apply_requires_trusted_selected_account_scope(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(config.CONFIG,{},clear=True), patch.object(a,'api') as mail_api:
            with self.assertRaisesRegex(ValueError,'explicitly configured selected account'):
                a.apply(self.source,self.plan,Path(tmp)/'j',Path(tmp)/'r')
            mail_api.assert_not_called()

    def test_registered_baseline_mismatch_blocks_standalone_mutation_before_mail_api(self):
        import history
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve(); db=root/'state'/'history.sqlite3'
            patcher=patch.dict(config.CONFIG,{'state_root':str(root/'state')});patcher.start()
            self.addCleanup(patcher.stop)
            source=json.loads(json.dumps(self.source));source['refreshed_at']='2026-11-17T12:00:00+00:00'
            changed=json.loads(json.dumps(source));changed['records'][0]['gist']='Changed after registered baseline'
            plan=dict(self.plan,snapshot_id=normalize_snapshot(changed)['snapshot_id'])
            with patch.object(history,'review_path',return_value=str(root/'review.html')):
                history.register(db,source,root/'review.html')
            with patch.object(a,'api') as mail_api:
                with self.assertRaisesRegex(ValueError,'registered history baseline'):
                    a.apply(changed,plan,root/'journal.jsonl',root/'recovery')
                mail_api.assert_not_called()

    def test_initial_run_without_registered_baseline_remains_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve(); db=root/'state'/'history.sqlite3'
            patcher=patch.dict(config.CONFIG,{'state_root':str(root/'state')});patcher.start()
            self.addCleanup(patcher.stop)
            # A missing history database has no registered baseline and permits the first run.
            with patch.object(a,'lookup',return_value=False),patch.object(a,'destination_ids',return_value=[]),patch.object(a,'move',return_value={'numeric_id':10,'junk':False}):
                result=a.apply(self.source,self.plan,root/'journal.jsonl',root/'recovery')
            self.assertEqual(result[0]['status'],'verified-moved')

    def test_nonempty_unrecognized_history_database_fails_closed(self):
        from contextlib import closing
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();db=root/'state'/'history.sqlite3';db.parent.mkdir()
            with closing(sqlite3.connect(db)) as connection: connection.execute('CREATE TABLE unrelated (value TEXT)')
            patcher=patch.dict(config.CONFIG,{'state_root':str(root/'state')});patcher.start();self.addCleanup(patcher.stop)
            with patch.object(a,'api') as mail_api:
                with self.assertRaisesRegex(ValueError,'no authoritative run registry'):
                    a.apply(self.source,self.plan,root/'journal.jsonl',root/'recovery')
                mail_api.assert_not_called()

    def test_matching_registered_baseline_allows_exact_run(self):
        import history
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();db=root/'state'/'history.sqlite3'
            patcher=patch.dict(config.CONFIG,{'state_root':str(root/'state')});patcher.start();self.addCleanup(patcher.stop)
            source=json.loads(json.dumps(self.source));source['refreshed_at']='2026-11-17T12:00:00+00:00'
            plan=dict(self.plan,snapshot_id=normalize_snapshot(source)['snapshot_id'])
            with patch.object(history,'review_path',return_value=str(root/'review.html')):
                history.register(db,source,root/'review.html')
            with patch.object(a,'lookup',return_value=False),patch.object(a,'destination_ids',return_value=[]),patch.object(a,'move',return_value={'numeric_id':10,'junk':False}):
                result=a.apply(source,plan,root/'journal.jsonl',root/'recovery')
            self.assertEqual(result[0]['status'],'verified-moved')

    def test_existing_validated_manifest_keeps_original_cutoff_after_clock_advance(self):
        import datetime as datetime_module
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();state=root/'state'
            patcher=patch.dict(config.CONFIG,{'state_root':str(state)});patcher.start();self.addCleanup(patcher.stop)
            t0=datetime_module.datetime.now(datetime_module.timezone.utc).replace(microsecond=0)
            source=json.loads(json.dumps(self.source));source['records'][0]['received']=(t0-datetime_module.timedelta(days=29)).isoformat()
            snapshot=normalize_snapshot(source);plan={**self.plan,'snapshot_id':snapshot['snapshot_id'],'started_at':t0.isoformat()}
            original=datetime_module.datetime
            class AtStart(original):
                @classmethod
                def now(cls,tz=None):return t0
            parent_manifest=root/'original-manifest.json';rules=a.rules_digest(Path(__file__).parents[1]/'rules.md')
            with patch.object(execution.dt,'datetime',AtStart):
                parent=execution.create_or_validate_manifest(parent_manifest,snapshot,plan,rules,authorized_accounts=['test'])
            child_source=json.loads(json.dumps(source));child_source['run_id']='test.r1'
            child_snapshot=normalize_snapshot(child_source)
            child_plan={**plan,'snapshot_id':child_snapshot['snapshot_id'],'authorization':plan['authorization']+' continuation'}
            child_manifest=root/'continuation-manifest.json'
            execution.create_or_validate_manifest(child_manifest,child_snapshot,child_plan,rules,authorized_accounts=['test'],
                inherited_manifest=parent,parent_manifest_sha256=__import__('hashlib').sha256(parent_manifest.read_bytes()).hexdigest())
            class AfterCutoff(original):
                @classmethod
                def now(cls,tz=None):return t0+datetime_module.timedelta(days=2)
            with patch.object(execution.dt,'datetime',AfterCutoff),patch.object(a,'lookup',return_value=False),patch.object(a,'destination_ids',return_value=[]),patch.object(a,'move',return_value={'numeric_id':10,'junk':False}):
                outcome=a.apply(child_source,child_plan,root/'journal.jsonl',root/'recovery',manifest_path=child_manifest,rules_path=Path(__file__).parents[1]/'rules.md')
            self.assertEqual(outcome[0]['status'],'verified-moved')

    def test_supplied_history_context_cannot_select_an_arbitrary_empty_database(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(a,'api') as mail_api:
            root=Path(tmp).resolve()
            with self.assertRaisesRegex(ValueError,'configured authoritative baseline'):
                a.apply(self.source,self.plan,root/'journal.jsonl',root/'recovery',history_database=root/'attacker-selected-empty.sqlite3')
            mail_api.assert_not_called()

    def test_override_manifest_binds_export_and_exact_authorized_item(self):
        source,plan=self._user_override_plan()
        snapshot=a.validate_plan(source,plan)
        with tempfile.TemporaryDirectory() as tmp:
            manifest=execution.create_or_validate_manifest(Path(tmp)/'manifest.json',snapshot,plan,'a'*64,authorized_accounts=['test'])
            self.assertEqual(manifest['user_review_export_sha256'],plan['user_review_evidence']['export_sha256'])
            self.assertEqual(manifest['age_overrides'],[plan['actions'][0]['age_override']])
            changed=json.loads(json.dumps(plan));changed['actions'][0]['age_override']['numeric_id']=100
            with self.assertRaisesRegex(ValueError,'manifest mismatch'):
                execution.create_or_validate_manifest(Path(tmp)/'manifest.json',snapshot,changed,'a'*64,authorized_accounts=['test'])
    def test_duplicate_plan_and_wrong_snapshot(self):
        self.plan['actions']*=2
        with self.assertRaises(ValueError):a.validate_plan(self.source,self.plan)
        self.plan['actions']=self.plan['actions'][:1];self.plan['snapshot_id']='wrong'
        with self.assertRaises(ValueError):a.validate_plan(self.source,self.plan)
    def test_exact_lookup_rejects_different_numeric_copy(self):
        with patch.object(a,'api',return_value='10\tfalse'),self.assertRaises(ValueError):a.lookup(self.source['records'][0])

    def test_move_checks_exact_destination_prestate_in_same_mail_api_call(self):
        with patch.object(a,'api',return_value='42\tfalse') as call:
            result=a.move(self.source['records'][0],'Archive',pre_destination_ids=[5,7])
        self.assertEqual(result['numeric_id'],42)
        self.assertEqual(call.call_args.args[-1],'5\t7')
        self.assertIn('Destination prestate changed',call.call_args.args[0])

    def test_custom_physical_folders_keep_canonical_junk_flag_behavior(self):
        folder_map={'INBOX':'Inbox','Archive':'All Mail','Junk':'Spam','Trash':'Deleted Messages'}
        record=self.source['records'][0]
        with patch.object(a,'api',return_value='44\ttrue') as call:
            a.move(record,'Junk',folder_map,[])
        script,*args=call.call_args.args
        self.assertEqual(tuple(args),('test','Inbox','Spam',9,'full:odd@example.test','Junk',''))
        self.assertIn('if (item 6 of argv) is "Junk" then set junk mail status of m to true',script)
        self.assertIn('if (item 6 of argv) is not "Junk" then set junk mail status of m to false',script)
        with patch.object(a,'api',return_value='45\tfalse') as call:
            a.move(record,'Archive',folder_map,[])
        self.assertEqual(call.call_args.args[1:4],('test','Inbox','All Mail'))
        self.assertEqual(call.call_args.args[6],'Archive')
    def test_failed_move_has_durable_intent_and_is_not_replayed(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal=Path(tmp)/'journal.jsonl'
            with patch.object(a,'api',return_value='-1\t-1\tfalse\tfalse'),patch.object(a,'lookup',return_value=False),patch.object(a,'destination_ids',return_value=[]),patch.object(a,'move',side_effect=ValueError('identity conflict')):
                with self.assertRaises(ValueError):a.apply(self.source,self.plan,journal,Path(tmp)/'recovery')
            events=[json.loads(x) for x in journal.read_text().splitlines()]
            self.assertEqual([x['status'] for x in events],['intent'])
            with self.assertRaisesRegex(ValueError,'reconcile'):a.apply(self.source,self.plan,journal,Path(tmp)/'recovery')
    def test_success_records_verified_destination_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal=Path(tmp)/'journal.jsonl'
            with patch.object(a,'api',return_value='-1\t-1\tfalse\tfalse'),patch.object(a,'lookup',return_value=False),patch.object(a,'destination_ids',return_value=[]),patch.object(a,'move',return_value={'mailbox':'Archive','numeric_id':42,'junk':False}):
                result=a.apply(self.source,self.plan,journal,Path(tmp)/'recovery')
            self.assertEqual(result[0]['new_id'],42)
            self.assertEqual(result[0]['status'],'verified-moved')
            self.assertEqual([json.loads(x)['status'] for x in journal.read_text().splitlines()],['intent','move-receipt','verified-moved'])
            self.assertEqual(execution.reconcile(journal,lambda _:self.fail('verified move is already receipt-closed')),[])

    def test_per_item_conflict_does_not_stop_independent_later_move(self):
        source=json.loads(json.dumps(self.source));source['records'].append({**source['records'][0],'item':'M2','current_id':10,'message_id':'second@example.test'})
        plan={'snapshot_id':normalize_snapshot(source)['snapshot_id'],'started_at':self.plan['started_at'],'authorization':'two exact actions','actions':[
          {'item':'M1','destination':'INBOX','reason':'retain'}, {'item':'M2','destination':'Archive','reason':'independent'}]}
        with tempfile.TemporaryDirectory() as tmp:
            journal=Path(tmp)/'journal.jsonl'
            checks={('test','full:odd@example.test',9):True,('test','second@example.test',10):False}
            with patch.object(a,'api',return_value='-1\t-1\tfalse\tfalse'),patch.object(a,'lookup_many',return_value=checks),patch.object(a,'lookup',return_value=False),patch.object(a,'destination_ids',return_value=[]),patch.object(a,'move',return_value={'mailbox':'Archive','numeric_id':11,'junk':False}):
                outcomes=a.apply(source,plan,journal,Path(tmp)/'recovery')
            self.assertEqual([e['status'] for e in outcomes],['conflict-or-failed','verified-moved'])

    def test_batched_lookup_returns_per_copy_result(self):
        records=[self.source['records'][0],{**self.source['records'][0],'item':'M2','current_id':10,'message_id':'<second>'}]
        with patch.object(a,'api',return_value='9\tfalse\tOK\n0\tfalse\tERROR'):
            result=a.lookup_many(records)
        self.assertEqual(result[('test','full:odd@example.test',9)],False)
        self.assertIsInstance(result[('test','<second>',10)],ValueError)

    def test_retained_junk_and_inbox_require_correct_junk_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal=Path(tmp)/'journal.jsonl'
            self.plan['actions'][0]['destination']='INBOX'
            with patch.object(a,'api',return_value='-1\t-1\tfalse\tfalse'),patch.object(a,'lookup_many',return_value={('test','full:odd@example.test',9):True}):
                result=a.apply(self.source,self.plan,journal,Path(tmp)/'recovery')
            self.assertEqual(result[0]['status'],'conflict-or-failed')
            journal.unlink()
            journal=Path(tmp)/'journal-junk.jsonl'
            self.plan['actions'][0]['destination']='Junk'
            self.source['records'][0]['observed_mailbox']='Junk'
            self.plan['snapshot_id']=normalize_snapshot(self.source)['snapshot_id']
            with patch.object(a,'api',return_value='-1\t-1\tfalse\tfalse'),patch.object(a,'lookup_many',return_value={('test','full:odd@example.test',9):False}):
                result=a.apply(self.source,self.plan,journal,Path(tmp)/'recovery')
            self.assertEqual(result[0]['status'],'conflict-or-failed')

    def test_moved_copy_is_reconciled_after_result_journal_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal=Path(tmp)/'journal.jsonl'
            append=a.append_event
            failed={'once':False}
            def flaky(path,event):
                if event.get('status')=='verified-moved' and not failed['once']:
                    failed['once']=True
                    raise OSError('synthetic result write failure')
                return append(path,event)
            with patch.object(a,'api',return_value='-1\t-1\tfalse\tfalse'),patch.object(a,'lookup',return_value=False),patch.object(a,'destination_ids',return_value=[3]),patch.object(a,'move',return_value={'mailbox':'Archive','numeric_id':42,'junk':False}),patch.object(a,'append_event',side_effect=flaky):
                with self.assertRaisesRegex(OSError,'result write'):
                    a.apply(self.source,self.plan,journal,Path(tmp)/'recovery')
            events=[json.loads(x) for x in journal.read_text().splitlines()]
            intent=next(x for x in events if x['status']=='intent')
            self.assertEqual(intent['pre_destination_ids'],[3])
            result=execution.reconcile(journal,lambda _: {'destination_ids':[3,42],'destination_copies':[{'numeric_id':3,'message_id':'other','junk':False},{'numeric_id':42,'message_id':self.source['records'][0]['message_id'],'junk':False}],'source_present':False,'source_exact':False,'source_junk':None,'identity_matches':True})
            self.assertEqual(result[0]['status'],'verified-completed')

    def test_recovery_item_identifier_must_be_canonical(self):
        record=self.source['records'][0]
        record['item']='../escape'
        record['email_context']={'local_source':{'availability':'verified-existing-header-identity','path':'unused','partial':False}}
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(ValueError,'Invalid recovery item'):
            a.backup(record,Path(tmp))

    def test_recovery_root_and_target_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp).resolve(); real=base/'real'; real.mkdir(); link=base/'link'; link.symlink_to(real)
            cache=base/'cache';cache.mkdir();source=cache/'9.emlx';source.write_bytes(b'synthetic');source=source.resolve()
            record={**self.source['records'][0],'email_context':{'local_source':{'availability':'verified-existing-header-identity','path':str(source),'partial':False}}}
            with patch.object(a,'header_identity',return_value=record['message_id']),self.assertRaisesRegex(ValueError,'Recovery root path'):
                a.backup(record,link,account_cache_root=cache)
            outside=base/'outside'; outside.mkdir(); (real/'M1').symlink_to(outside,target_is_directory=True)
            with patch.object(a,'header_identity',return_value=record['message_id']),self.assertRaisesRegex(ValueError,'target may not be a symlink'):
                a.backup(record,real,account_cache_root=cache)

    def test_allocator_id_and_numeric_source_identity_are_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();cache=root/'cache';cache.mkdir();source=cache/'9.emlx';source.write_bytes(b'emlx bytes');source=source.resolve()
            record={**self.source['records'][0],'item':'M001','email_context':{'local_source':{'availability':'verified-existing-header-identity','path':str(source),'partial':False}}}
            with patch.object(a,'header_identity',return_value=record['message_id']):
                outcome=a.backup(record,root/'recovery',account_cache_root=cache)
            manifest=json.loads(Path(outcome['manifest']).read_text())
            self.assertEqual((manifest['item'],manifest['numeric_id']),('M001',9))
            self.assertEqual(manifest['completeness']['provider_attachment_completeness'],'unknown')
            wrong={**record,'email_context':{'local_source':{'availability':'verified-existing-header-identity','path':str(cache/'99.emlx'),'partial':False}}}
            (cache/'99.emlx').write_bytes(b'wrong copy')
            with patch.object(a,'header_identity',return_value=record['message_id']),self.assertRaisesRegex(ValueError,'numeric ID'):
                a.backup(wrong,root/'other',account_cache_root=cache)
            other_cache=root/'other-account';other_cache.mkdir();wrong_account=other_cache/'9.emlx';wrong_account.write_bytes(b'other')
            wrong_record={**record,'email_context':{'local_source':{'availability':'verified-existing-header-identity','path':str(wrong_account.resolve()),'partial':False}}}
            with patch.object(a,'header_identity',return_value=record['message_id']),self.assertRaisesRegex(ValueError,'outside the selected account cache'):
                a.backup(wrong_record,root/'wrong-account-recovery',account_cache_root=cache)

    def test_symlinked_attachment_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();cache=root/'account';mail=cache/'Messages';mail.mkdir(parents=True)
            source=mail/'9.emlx';source.write_bytes(b'emlx bytes');source=source.resolve()
            attachments=cache/'Attachments';attachments.mkdir();outside=root/'outside';outside.mkdir();(outside/'secret').write_bytes(b'opaque')
            (attachments/'9').symlink_to(outside,target_is_directory=True)
            record={**self.source['records'][0],'item':'M001','email_context':{'local_source':{'availability':'verified-existing-header-identity','path':str(source),'partial':False}}}
            with patch.object(a,'header_identity',return_value=record['message_id']),self.assertRaisesRegex(ValueError,'Symlink'):
                a.backup(record,root/'recovery',account_cache_root=cache)

    def test_recovery_copy_source_requires_exact_manifest_lineage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()/'recovery';item=root/'M001';item.mkdir(parents=True)
            source=item/'original.emlx.bin';source.write_bytes(b'opaque')
            manifest={'item':'M001','account':'test','message_id':'full:odd@example.test','numeric_id':9,
              'completeness':{'cached_parts_directory_present':False,'discovered_cached_files_copied':True,'provider_attachment_completeness':'unknown'},
              'files':[{'path':str(source),'sha256':__import__('hashlib').sha256(source.read_bytes()).hexdigest()}]}
            (item/'manifest.json').write_text(json.dumps(manifest))
            record={**self.source['records'][0],'item':'M001'}
            with patch.object(a,'header_identity',return_value=record['message_id']):
                self.assertEqual(a.verify_source_copy(record,source,account_cache_root=None,recovery_root=root),source)
            manifest['numeric_id']=99;(item/'manifest.json').write_text(json.dumps(manifest))
            with patch.object(a,'header_identity',return_value=record['message_id']),self.assertRaisesRegex(ValueError,'lineage identity mismatch'):
                a.verify_source_copy(record,source,recovery_root=root)

    def test_rebackup_from_recovery_copy_preserves_every_verified_manifest_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();cache=root/'cache';mail=cache/'Messages';mail.mkdir(parents=True)
            source=mail/'9.emlx';source.write_bytes(b'opaque emlx')
            part=cache/'Attachments'/'9'/'opaque.part';part.parent.mkdir(parents=True);part.write_bytes(b'opaque external part')
            record={**self.source['records'][0],'item':'M001','email_context':{'local_source':{'availability':'verified-existing-header-identity','path':str(source.resolve()),'partial':False}}}
            with patch.object(a,'header_identity',return_value=record['message_id']):
                first=a.backup(record,root/'recovery1',account_cache_root=cache)
                first_manifest=json.loads(Path(first['manifest']).read_text())
                record['email_context']['local_source']['path']=str(root/'recovery1'/'M001'/'original.emlx.bin')
                second=a.backup(record,root/'recovery2',recovery_root=root/'recovery1')
            second_manifest=json.loads(Path(second['manifest']).read_text())
            self.assertEqual(len(first_manifest['files']),2)
            self.assertEqual(len(second_manifest['files']),2)
            self.assertEqual(second_manifest['completeness']['discovered_cached_files_copied'],True)
            self.assertEqual({Path(f['path']).relative_to(root/'recovery2'/'M001').as_posix():f['sha256'] for f in second_manifest['files']},
                {Path(f['path']).relative_to(root/'recovery1'/'M001').as_posix():f['sha256'] for f in first_manifest['files']})
            first_manifest['completeness']['discovered_cached_files_copied']=False
            Path(first['manifest']).write_text(json.dumps(first_manifest))
            with patch.object(a,'header_identity',return_value=record['message_id']):
                third=a.backup(record,root/'recovery3',recovery_root=root/'recovery1')
            third_manifest=json.loads(Path(third['manifest']).read_text())
            self.assertFalse(third_manifest['completeness']['discovered_cached_files_copied'])

    def test_rebackup_rejects_unconfined_or_corrupt_manifest_parts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();cache=root/'cache';mail=cache/'Messages';mail.mkdir(parents=True)
            source=mail/'9.emlx';source.write_bytes(b'opaque emlx')
            record={**self.source['records'][0],'item':'M001','email_context':{'local_source':{'availability':'verified-existing-header-identity','path':str(source.resolve()),'partial':False}}}
            with patch.object(a,'header_identity',return_value=record['message_id']):
                first=a.backup(record,root/'recovery1',account_cache_root=cache)
                prior=Path(first['manifest']);manifest=json.loads(prior.read_text())
                part=root/'recovery1'/'M001'/'cached-parts'/'part.bin';part.parent.mkdir();part.write_bytes(b'part')
                manifest['files'].append({'path':str(part),'sha256':__import__('hashlib').sha256(part.read_bytes()).hexdigest()})
                prior.write_text(json.dumps(manifest))
                record['email_context']['local_source']['path']=str(root/'recovery1'/'M001'/'original.emlx.bin')
                manifest['files'][-1]['path']=str(root/'outside.bin')
                prior.write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError,'outside|confine|manifest'):
                    a.backup(record,root/'recovery2',recovery_root=root/'recovery1')
                manifest['files'][-1]['path']=str(part);manifest['files'][-1]['sha256']='0'*64
                prior.write_text(json.dumps(manifest))
                with self.assertRaisesRegex(ValueError,'digest|hash|manifest'):
                    a.backup(record,root/'recovery3',recovery_root=root/'recovery1')

    def test_rebackup_rejects_symlinked_manifest_part(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();cache=root/'cache';mail=cache/'Messages';mail.mkdir(parents=True)
            source=mail/'9.emlx';source.write_bytes(b'opaque emlx')
            record={**self.source['records'][0],'item':'M001','email_context':{'local_source':{'availability':'verified-existing-header-identity','path':str(source.resolve()),'partial':False}}}
            outside=root/'outside.part';outside.write_bytes(b'outside')
            with patch.object(a,'header_identity',return_value=record['message_id']):
                first=a.backup(record,root/'recovery1',account_cache_root=cache)
                prior=Path(first['manifest']);manifest=json.loads(prior.read_text())
                link=root/'recovery1'/'M001'/'cached-parts'/'part.bin';link.parent.mkdir();link.symlink_to(outside)
                manifest['files'].append({'path':str(link),'sha256':__import__('hashlib').sha256(outside.read_bytes()).hexdigest()})
                prior.write_text(json.dumps(manifest))
                record['email_context']['local_source']['path']=str(root/'recovery1'/'M001'/'original.emlx.bin')
                with self.assertRaisesRegex(ValueError,'noncanonical|symlink|Symlink'):
                    a.backup(record,root/'recovery2',recovery_root=root/'recovery1')
