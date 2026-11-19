import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
import shutil
from datetime import datetime, timezone
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]/'scripts'))
import execution


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.lock_root=Path(tempfile.mkdtemp(prefix='email-triage-account-global-lock-test-')).resolve()
        self.addCleanup(shutil.rmtree,self.lock_root,ignore_errors=True)
        self.lock_patch=patch.object(execution,'account_lock_root',return_value=self.lock_root/'shared-locks')
        self.lock_patch.start();self.addCleanup(self.lock_patch.stop)
        self.snapshot = {'snapshot_id':'s1','account_scope':['a'],'records':[{'item':'M1','account':'a','message_id':'<x>','current_id':7}]}
        self.plan = {'snapshot_id':'s1','started_at':'2026-11-01T12:00:00+00:00','authorization':'approved','actions':[{'item':'M1','destination':'Archive','reason':'test'}]}
        self.hash = 'a'*64

    def test_manifest_freezes_accounts_cutoff_actions_and_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'manifest.json'
            before=datetime.now(timezone.utc)
            got = execution.create_or_validate_manifest(path,self.snapshot,self.plan,self.hash)
            after=datetime.now(timezone.utc)
            self.assertEqual(got['accounts'],['a'])
            actual=datetime.fromisoformat(got['started_at'])
            self.assertGreaterEqual(actual,before);self.assertLessEqual(actual,after)
            self.assertEqual(got['claimed_started_at'],self.plan['started_at'])
            self.assertEqual(datetime.fromisoformat(got['cutoff_at']),actual.replace(tzinfo=timezone.utc)-__import__('datetime').timedelta(days=30))
            self.assertEqual(json.loads(path.read_text()),got)
            self.assertEqual(execution.create_or_validate_manifest(path,self.snapshot,self.plan,self.hash),got)
            altered = {**self.plan,'authorization':'different'}
            with self.assertRaisesRegex(ValueError,'manifest mismatch'):
                execution.create_or_validate_manifest(path,self.snapshot,altered,self.hash)

    def test_account_lock_excludes_second_writer_but_reuses_released_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal_a=Path(tmp)/'run-a'/'journal.jsonl';journal_b=Path(tmp)/'run-b'/'journal.jsonl'
            self.assertNotEqual(journal_a.parent,journal_b.parent)
            with execution.account_locks(['account']):
                with self.assertRaisesRegex(ValueError,'Another mutating run'):
                    with execution.account_locks(['account']): pass
            with execution.account_locks(['account']): pass

    def test_account_transaction_reuses_nested_lock_and_holds_through_publication(self):
        import multiprocessing
        if 'fork' not in multiprocessing.get_all_start_methods():self.skipTest('fork unavailable')
        context=multiprocessing.get_context('fork');receiver,sender=context.Pipe(duplex=False)
        def competing_process(connection):
            try:
                with execution.account_locks(['account']):connection.send('acquired')
            except ValueError:connection.send('blocked')
            finally:connection.close()
        with execution.account_transaction(['account']):
            with execution.account_locks(['account']):pass
            with self.assertRaisesRegex(ValueError,'may not expand'):
                with execution.account_locks(['other']):pass
            publication_stage='refresh-and-publication'
            process=context.Process(target=competing_process,args=(sender,));process.start();sender.close()
            self.assertTrue(receiver.poll(5),publication_stage+' failed to retain the transaction lock')
            self.assertEqual(receiver.recv(),'blocked')
            process.join(5)
            self.assertFalse(process.is_alive())
            self.assertEqual(process.exitcode,0)
        with execution.account_locks(['account']):pass

    def test_account_transaction_releases_lock_after_failure(self):
        with self.assertRaisesRegex(RuntimeError,'synthetic publication failure'):
            with execution.account_transaction(['account']):raise RuntimeError('synthetic publication failure')
        with execution.account_locks(['account']):pass

    def test_account_transaction_ownership_does_not_cross_threads(self):
        import threading
        observed=[];finished=threading.Event()
        def contender():
            try:
                with execution.account_locks(['account']):observed.append('acquired')
            except ValueError:observed.append('blocked')
            finally:finished.set()
        with execution.account_transaction(['account']):
            thread=threading.Thread(target=contender);thread.start()
            self.assertTrue(finished.wait(5),'other thread did not contend on the lock')
            thread.join(5);self.assertFalse(thread.is_alive())
            self.assertEqual(observed,['blocked'])

    def test_reconcile_classifies_without_replay_and_preserves_ambiguous(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = Path(tmp)/'journal.jsonl'
            base = {'item':'M1','account':'a','message_id':'<x>','old_id':7,'old_mailbox':'INBOX','destination':'Archive','snapshot_id':'s1','pre_destination_ids':[5],'pre_source_junk':False,'attempt_id':'a1','reason':'test','at':'2026-11-19T00:00:00+00:00'}
            m2={**base,'item':'M2','pre_destination_ids':[],'attempt_id':'a2'}
            journal.write_text('\n'.join(json.dumps(e) for e in [
                {**base,'status':'intent'},
                {**m2,'status':'intent'},
                {**m2,'status':'move-receipt','new_id':8,'junk':False},
                {**base,'item':'M3','pre_destination_ids':[1],'status':'intent'},
                {**base,'item':'M4','pre_destination_ids':[],'attempt_id':'a4','status':'intent'},
                {**base,'item':'M5','pre_destination_ids':[],'attempt_id':'a5','status':'intent'},
                {**base,'item':'M5','pre_destination_ids':[],'attempt_id':'a5','status':'move-receipt','new_id':15,'junk':True},
                {**base,'item':'M6','pre_destination_ids':[],'attempt_id':'a6','status':'intent'},
            ])+'\n')
            states = {
                'M1': {'destination_ids':[5],'destination_copies':[{'numeric_id':5,'message_id':'<x>','junk':False}],'source_present':True,'source_exact':True,'source_junk':False,'identity_matches':True},
                'M2': {'destination_ids':[8],'destination_copies':[{'numeric_id':8,'message_id':'<x>','junk':False}],'source_present':False,'source_exact':False,'source_junk':None,'identity_matches':True},
                'M3': {'destination_ids':[1,9],'destination_copies':[{'numeric_id':1,'message_id':'<x>','junk':False},{'numeric_id':9,'message_id':'<x>','junk':False}],'source_present':True,'source_exact':True,'source_junk':False,'identity_matches':True},
                'M4': {'destination_ids':[44],'destination_copies':[{'numeric_id':44,'message_id':'<x>','junk':False}],'source_present':False,'source_exact':False,'source_junk':None,'identity_matches':True},
                'M5': {'destination_ids':[15],'destination_copies':[{'numeric_id':15,'message_id':'<x>','junk':True}],'source_present':False,'source_exact':False,'source_junk':None,'identity_matches':True},
                'M6': {'destination_ids':[],'destination_copies':[],'source_present':True,'source_exact':True,'source_junk':True,'identity_matches':True},
            }
            out = execution.reconcile(journal,lambda event: states[event['item']])
            self.assertEqual([x['status'] for x in out],['verified-not-started','verified-completed','ambiguous','ambiguous','ambiguous','ambiguous'])
            self.assertEqual(len(execution.reconcile(journal,lambda _: self.fail('must not reclassify terminal action'))),0)
            self.assertEqual(len([x for x in journal.read_text().splitlines() if json.loads(x)['status']=='intent']),6)

    def test_bad_rules_digest_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(ValueError,'rules digest'):
            execution.create_or_validate_manifest(Path(tmp)/'m',self.snapshot,self.plan,'bad')

    def test_manifest_requires_explicit_authorized_account_scope(self):
        snapshot={**self.snapshot,'account_scope':['other']}
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(ValueError,'exceeds frozen manifest scope'):
            execution.create_or_validate_manifest(Path(tmp)/'m',snapshot,self.plan,self.hash)

    def test_legacy_manifest_cannot_supply_trusted_run_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'manifest.json';path.write_text(json.dumps({'schema':1,'started_at':'2000-01-01T00:00:00+00:00'}))
            with self.assertRaisesRegex(ValueError,'Legacy manifest'):
                execution.create_or_validate_manifest(path,self.snapshot,self.plan,self.hash)


if __name__ == '__main__':
    unittest.main()
