import copy
import datetime as dt
import json
import sqlite3
from contextlib import closing
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import history as h
import review as r
import assessments as assessment_helpers
import execution

class HistoryTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.db=self.root/'history.sqlite3';self.path=self.root/'runs/test/review.html'
        self.source={'run_id':'test','scope':'Synthetic','snapshot_as_of':'2026-11-17','refreshed_at':'2026-11-17T12:00:00+00:00','records':[{'item':'M1','account':'test','message_id':'odd:mid@example.test','current_id':42,'observed_mailbox':'Archive','to_display':'test@example.test','subject':'<script>unsafe</script>','received':None,'size_bytes':None,'gist':'Synthetic'}]}
        original=h.review_path
        patcher=patch.object(h,'review_path',side_effect=lambda value:original(value,self.root));patcher.start();self.addCleanup(patcher.stop)
        self.action={'item':'M1','account':'test','message_id':'odd:mid@example.test','old_id':41,'old_mailbox':'INBOX','destination':'Archive','new_id':42,'reason':'Synthetic','status':'verified-moved','at':'2026-11-17T11:59:59+00:00'}
    def test_append_idempotence_acknowledgment_and_immutable_runs(self):
        h.register(self.db,self.source,self.path,[self.action]);h.register(self.db,self.source,self.path,[self.action])
        out=h.export_history(self.db);self.assertEqual(len(out),1);self.assertEqual(len(out[0]['actions']),1);self.assertIsNone(out[0]['reviewed_at'])
        h.acknowledge(self.db,'test','2026-11-17T13:00:00+00:00','a'*64,{'status':'applied'})
        self.assertIsNotNone(h.export_history(self.db)[0]['reviewed_at'])
        changed=copy.deepcopy(self.source);changed['records'][0]['gist']='Changed'
        with self.assertRaisesRegex(ValueError,'immutable'):h.register(self.db,changed,self.path)
        self.assertEqual(self.db.stat().st_mode&0o777,0o600)

    def test_export_receipts_are_operation_scoped_and_legacy_schema_migrates(self):
        h.register(self.db,self.source,self.path)
        digest='c'*64
        h.acknowledge(self.db,'test','2026-11-17T13:00:00+00:00',digest,{'status':'refreshed'},operation='refresh')
        h.acknowledge(self.db,'test','2026-11-17T13:01:00+00:00',digest,{'status':'applied'},operation='apply')
        self.assertEqual(h.get_export_receipt(self.db,digest,operation='refresh')['outcome']['status'],'refreshed')
        self.assertEqual(h.get_export_receipt(self.db,digest,operation='apply')['outcome']['status'],'applied')

        legacy=self.root/'legacy-history.sqlite3';refresh_digest='d'*64;apply_digest='e'*64;ambiguous_digest='f'*64
        with closing(sqlite3.connect(legacy)) as connection:
            connection.executescript('''CREATE TABLE runs(run_id TEXT PRIMARY KEY,snapshot_id TEXT NOT NULL,as_of TEXT NOT NULL,review_path TEXT NOT NULL,reviewed_at TEXT,snapshot_json TEXT NOT NULL,as_of_utc TEXT);
              CREATE TABLE exports(sha256 TEXT PRIMARY KEY,run_id TEXT NOT NULL REFERENCES runs(run_id),received_at TEXT NOT NULL,outcome_json TEXT NOT NULL);
              INSERT INTO runs VALUES('legacy','s','2026-11-17T12:00:00+00:00','/tmp/review.html',NULL,'{}','2026-11-17T12:00:00+00:00');''')
            refresh_outcome={'status':'read-only-refresh-complete','snapshot':'/tmp/refreshed.json','pending_review_bundle':'/tmp/pending.json',
                'bundle_sha256':refresh_digest,'source_snapshot_id':'source','refreshed_snapshot_id':'fresh','item_outcomes':[],'mail_changed':False}
            apply_outcome={'run_id':'legacy','snapshot_id':'source','verified_snapshot_id':'after','verified_actions':1,'review':'/tmp/review.html'}
            connection.executemany('INSERT INTO exports VALUES(?,?,?,?)',[
                (refresh_digest,'legacy','2026-11-17T13:00:00+00:00',json.dumps(refresh_outcome)),
                (apply_digest,'legacy','2026-11-17T13:01:00+00:00',json.dumps(apply_outcome)),
                (ambiguous_digest,'legacy','2026-11-17T13:02:00+00:00','{"status":"read-only-refresh-complete"}')])
            connection.commit()
        self.assertEqual(h.get_export_receipt(legacy,refresh_digest,operation='refresh')['outcome']['status'],'read-only-refresh-complete')
        self.assertIsNone(h.get_export_receipt(legacy,refresh_digest,operation='apply'))
        self.assertEqual(h.get_export_receipt(legacy,apply_digest,operation='apply')['outcome']['verified_actions'],1)
        self.assertIsNone(h.get_export_receipt(legacy,apply_digest,operation='refresh'))
        # A global-schema refresh receipt can no longer poison a later explicit
        # action receipt for the same digest after the precise migration.
        h.acknowledge(legacy,'legacy','2026-11-17T13:03:00+00:00',refresh_digest,apply_outcome,operation='apply')
        self.assertEqual(h.get_export_receipt(legacy,refresh_digest,operation='apply')['outcome']['verified_snapshot_id'],'after')
        with self.assertRaisesRegex(ValueError,'ambiguous'):
            h.get_export_receipt(legacy,ambiguous_digest,operation='apply')
        with self.assertRaisesRegex(ValueError,'ambiguous'):
            h.acknowledge(legacy,'legacy','2026-11-17T13:04:00+00:00',ambiguous_digest,apply_outcome,operation='apply')

    def test_inclusive_date_window_uses_configured_zone_and_offset_chronology(self):
        first=copy.deepcopy(self.source);first['run_id']='first';first['refreshed_at']='2026-11-18T01:00:00-05:00'
        second=copy.deepcopy(self.source);second['run_id']='second';second['refreshed_at']='2026-11-18T06:30:00+01:00'
        outside=copy.deepcopy(self.source);outside['run_id']='outside';outside['refreshed_at']='2026-11-19T00:30:00-05:00'
        for source in (first,second,outside):h.register(self.db,source,self.path)
        result=h.export_history(self.db,since='2026-11-18',until='2026-11-18',timezone_name='America/New_York')
        self.assertEqual([run['run_id'] for run in result],['first','second'])
        with self.assertRaisesRegex(ValueError,'include an offset'):
            h.export_history(self.db,since='2026-11-18T00:00:00',timezone_name='UTC')

    def test_inclusive_date_window_respects_dst_day_length(self):
        before=copy.deepcopy(self.source);before['run_id']='dst-before';before['refreshed_at']='2026-03-08T04:30:00+00:00'
        last=copy.deepcopy(self.source);last['run_id']='dst-last';last['refreshed_at']='2026-03-09T03:30:00+00:00'
        after=copy.deepcopy(self.source);after['run_id']='dst-after';after['refreshed_at']='2026-03-09T04:30:00+00:00'
        for source in (before,last,after):h.register(self.db,source,self.path)
        result=h.export_history(self.db,since='2026-03-08',until='2026-03-08',timezone_name='America/New_York')
        self.assertEqual([row['run_id'] for row in result],['dst-last'])

    def test_legacy_history_requires_explicit_zone_for_date_only_bounds(self):
        eastern=copy.deepcopy(self.source);eastern['run_id']='legacy-east';eastern['timezone']='America/New_York';eastern['refreshed_at']='2026-11-19T04:30:00+00:00'
        h.register(self.db,eastern,self.path)
        from config import CONFIG
        with patch('config.CONFIG_TIMEZONE_EXPLICIT',False),patch.dict(CONFIG,{'timezone':'UTC'}):
            with self.assertRaisesRegex(ValueError,'explicit IANA timezone'):
                h.export_history(self.db,since='2026-11-18',until='2026-11-18')
            selected=h.export_history(self.db,since='2026-11-18',until='2026-11-18',timezone_name='America/New_York')
        self.assertEqual([row['run_id'] for row in selected],['legacy-east'])
    def test_only_verified_matching_actions_and_confined_links(self):
        bad={**self.action,'status':'intent'}
        with self.assertRaises(ValueError):h.register(self.db,self.source,self.path,[bad])
        with self.assertRaises(ValueError):h.register(self.db,self.source,self.root/'outside.html')
        bad={**self.action,'destination':'Junk'}
        with self.assertRaises(ValueError):h.register(self.db,self.source,self.path,[bad])
    def test_honest_provenance_duration_and_legacy_identity(self):
        old=r.normalize_snapshot(self.source)['snapshot_id']
        self.assertEqual(r.normalize_snapshot(r.normalize_snapshot(self.source))['snapshot_id'],old)
        self.source['execution']={'provider':'OpenAI','model':'synthetic-model','effort':'medium','kind':'review-application','started_at':'2026-11-17T11:59:00+00:00','completed_at':'2026-11-17T12:00:00+00:00'}
        html,snapshot=r.render_html(self.source);self.assertIn('60.0 seconds',html);self.assertNotEqual(snapshot['snapshot_id'],old)
        self.source['execution']['completed_at']='2026-11-17T11:58:00+00:00'
        with self.assertRaises(ValueError):r.normalize_snapshot(self.source)

    def test_identity_registry_counter_tombstones_and_aliases(self):
        ident={'account':'test','message_id':'copy@example.test','current_id':8}
        first=h.allocate_item_id(self.db,'test',ident)
        self.assertEqual(first,'M001')
        h.tombstone_item(self.db,'test',first)
        self.assertEqual(h.allocate_item_id(self.db,'test',ident),first)
        self.assertEqual(h.allocate_item_id(self.db,'test',{'account':'test','message_id':'next@example.test','current_id':9}),'M002')
        h.alias_item_identity(self.db,'test',first,{'account':'test','message_id':'copy@example.test','current_id':80})
        self.assertEqual(h.allocate_item_id(self.db,'test',{'account':'test','message_id':'copy@example.test','current_id':80}),'M001')

    def test_action_full_identity_is_required(self):
        for key,value in [('account','wrong'),('message_id','wrong'),('new_id',41)]:
            bad={**self.action,key:value}
            with self.assertRaises(ValueError):h.register(self.db,self.source,self.path,[bad])

    def test_retained_journal_requires_positive_identity_and_consistent_junk_flag(self):
        valid={'status':'verified-retained','item':'M1','account':'test','message_id':'odd:mid@example.test',
          'old_id':42,'new_id':42,'old_mailbox':'Archive','destination':'Archive','junk':False,'snapshot_id':'snapshot'}
        self.assertEqual(h.journal_attempt_state([valid],'snapshot')['verified'],[valid])
        for changed in ({'old_id':0},{'new_id':0},{'junk':'false'},{'junk':True},{'destination':'Junk','old_mailbox':'Junk','junk':False}):
            event={**valid,**changed};state=h.journal_attempt_state([event],'snapshot')
            with self.subTest(event=event):
                self.assertEqual(state['verified'],[])
                self.assertIn(event,state['ambiguous'])

    def test_history_journal_cli_records_reconciled_receipt_and_renders_undo(self):
        source=copy.deepcopy(self.source);source['run_id']='journal-cli'
        source['records'][0].update(current_id=41,observed_mailbox='INBOX')
        source['records'].append(dict(source['records'][0],item='M002',message_id='not-started@example.test',current_id=43,subject='Not started'))
        source=r.normalize_snapshot(source)
        final=copy.deepcopy(source);final['records'][0].update(current_id=42,observed_mailbox='Archive')
        final['refreshed_at']='2026-11-17T12:10:00+00:00'
        journal=self.root/'reconciled.jsonl'
        first={'item':'M1','account':'test','message_id':'odd:mid@example.test','old_id':41,'old_mailbox':'INBOX',
          'destination':'Archive','reason':'Synthetic verified filing','snapshot_id':source['snapshot_id'],'attempt_id':'attempt-completed',
          'pre_destination_ids':[],'pre_source_junk':False,'at':'2026-11-17T12:01:00+00:00'}
        receipt={key:first[key] for key in ('item','account','message_id','old_id','old_mailbox','destination','snapshot_id','attempt_id','pre_destination_ids','pre_source_junk')}
        receipt.update(status='move-receipt',new_id=42,junk=False,completed_at='2026-11-17T12:02:00+00:00')
        second={**first,'item':'M002','message_id':'not-started@example.test','old_id':43,'attempt_id':'attempt-not-started'}
        for event in ({**first,'status':'intent'},receipt,{**second,'status':'intent'}):execution.append_event(journal,event)
        lock_root=self.root.resolve()/'locks';lock_root.mkdir()
        with patch.object(execution,'account_lock_root',return_value=lock_root):
            classified=execution.reconcile(journal,lambda intent:({'destination_ids':[42],
              'destination_copies':[{'numeric_id':42,'message_id':intent['message_id'],'junk':False}],
              'source_present':False,'source_exact':False,'source_junk':False,'identity_matches':True}
              if intent['item']=='M1' else {'destination_ids':[],'destination_copies':[],
              'source_present':True,'source_exact':True,'source_junk':False,'identity_matches':True}))
        self.assertEqual([event['status'] for event in classified],['verified-completed','verified-not-started'])
        snapshot_path=self.root/'post-action.json';snapshot_path.write_text(json.dumps(final))
        review_path=self.root/'runs'/'journal-cli'/'review.html';review_path.parent.mkdir(parents=True)
        with patch.object(sys,'argv',['history.py','--database',str(self.db),'--snapshot',str(snapshot_path),
            '--review-html',str(review_path),'--journal',str(journal)]):h.main()
        action=h.export_history(self.db)[0]['actions'][0]
        self.assertEqual((action['status'],action['attempt_id'],action['receipt_new_id'],action['new_id']),
            ('verified-completed','attempt-completed',42,42))
        rendered,_=r.render_html(final,history=h.export_history(self.db))
        self.assertIn('verified-completed',rendered);self.assertIn('"receipt_new_id": 42',rendered)
        self.assertIn('verified moves',rendered);self.assertIn('Request undo',rendered)

    def test_assessment_invalidation_deadline_and_followup_lifecycle(self):
        identity={'account':'test','message_id':'odd:mid@example.test','current_id':42}
        h.record_assessment(self.db,'test',identity,fingerprint='fp',assessed_at='2026-11-17T12:00:00+00:00',rules_digest='r',content_digest='c',thread_digest='t',deadline='2026-11-20T00:00:00+00:00',evidence=[{'source':'header','ref':'message-id'}],result={'status':'review'})
        self.assertEqual(h.get_cached_assessment(self.db,'test',identity,fingerprint='fp',rules_digest='r',content_digest='c',thread_digest='t')['result']['status'],'review')
        h.invalidate_assessments(self.db,'test',identity,'thread_reply','2026-11-18T00:00:00+00:00')
        self.assertIsNone(h.get_cached_assessment(self.db,'test',identity,fingerprint='fp',rules_digest='r',content_digest='c',thread_digest='t'))
        task={'task_id':'task-1','run_id':'test','item':'M1','account':'test','message_id':'odd:mid@example.test','current_id':42,'summary':'Follow up','next_action':'Check response','status':'waiting_vendor','deadline':None,'waiting_on':'vendor','evidence_refs':['M1'],'result_link':None,'created_at':'2026-11-17T12:00:00+00:00','updated_at':'2026-11-17T12:00:00+00:00','result_confirmed_at':None}
        h.upsert_followup(self.db,task);self.assertEqual(h.list_followups(self.db)[0]['status'],'waiting_vendor')
        task.update(status='completed',updated_at='2026-11-18T12:00:00+00:00',result_confirmed_at='2026-11-18T12:00:00+00:00')
        h.upsert_followup(self.db,task);self.assertEqual(h.list_followups(self.db)[0]['status'],'completed')

    def test_assessment_cache_follows_verified_move_alias_and_explains_invalidations(self):
        old={'account':'test','message_id':'odd:mid@example.test','current_id':42}
        new={'account':'test','message_id':'odd:mid@example.test','current_id':99}
        item=h.allocate_item_id(self.db,'test',old,preferred='M42')
        fp=assessment_helpers.fingerprint('c','r','t','4')
        h.record_assessment(self.db,'test',old,fingerprint=fp,assessed_at='2026-11-17T12:00:00+00:00',rules_digest='r',content_digest='c',thread_digest='t',correction_version='4',evidence=[{'source':'body','ref':'paragraph-1'}],result={'status':'uncertain'})
        h.alias_item_identity(self.db,'test',item,new)
        decision=h.assessment_cache_decision(self.db,'test',new,rules_digest='r',content_digest='c',thread_digest='t',correction_version='4',now='2026-11-18T00:00:00+00:00')
        self.assertEqual(decision['status'],'reusable')
        self.assertEqual(h.assessment_cache_decision(self.db,'test',new,rules_digest='changed',content_digest='c',thread_digest='t',correction_version='4')['reason'],'rules_changed')
        h.invalidate_assessments(self.db,'test',old,'user_correction','2026-11-18T01:00:00+00:00')
        self.assertEqual(h.assessment_cache_decision(self.db,'test',new,rules_digest='r',content_digest='c',thread_digest='t',correction_version='4')['reason'],'user_correction')

    def test_legacy_followup_migration_only_backfills_exact_snapshot_identity(self):
        legacy=self.root/'legacy.sqlite3';connection=sqlite3.connect(legacy)
        connection.executescript('''CREATE TABLE runs(run_id TEXT PRIMARY KEY,snapshot_id TEXT NOT NULL,as_of TEXT NOT NULL,review_path TEXT NOT NULL,reviewed_at TEXT,snapshot_json TEXT NOT NULL);
        CREATE TABLE followups(task_id TEXT PRIMARY KEY,run_id TEXT NOT NULL,item TEXT NOT NULL,account TEXT NOT NULL,message_id TEXT NOT NULL,summary TEXT NOT NULL,next_action TEXT NOT NULL,status TEXT NOT NULL,deadline TEXT,waiting_on TEXT,evidence_refs_json TEXT NOT NULL,result_link TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,result_confirmed_at TEXT);''')
        normalized=r.normalize_snapshot(self.source)
        connection.execute('INSERT INTO runs VALUES(?,?,?,?,?,?)',('test',normalized['snapshot_id'],'2026-11-17T12:00:00+00:00',str(self.path),None,json.dumps(normalized)))
        connection.execute('INSERT INTO followups VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',('legacy-task','test','M1','test','odd:mid@example.test','Synthetic','Check','ready',None,None,'[]',None,'2026-11-17T12:00:00+00:00','2026-11-17T12:00:00+00:00',None));connection.commit();connection.close()
        with h.connect(legacy):pass
        task=h.list_followups(legacy)[0];self.assertEqual(task['current_id'],42)
