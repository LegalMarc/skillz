import copy
import datetime as dt
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import refresh_mail as m
import review as review_module

class RefreshMailTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.folder=Path(folder.name).resolve()
        self.account='refresh-tests@example.test'
        self.prefix='imap://refresh-tests@example.test/'
        self.folder_map={'INBOX':'INBOX','Archive':'Archive','Junk':'Junk','Trash':'Trash'}
        self.synthetic_config={'account':self.account,'mailbox_prefix':self.prefix,'timezone':'UTC','folder_map':self.folder_map}
        config=mock.patch.object(m,'CONFIG',self.synthetic_config);config.start();self.addCleanup(config.stop)
        roots=mock.patch.object(review_module,'SOURCE_ROOTS',(self.folder,));roots.start();self.addCleanup(roots.stop)
        self.database=self.folder/'MailData'/'Envelope Index'
        self.database.parent.mkdir(parents=True)
        self.connection=sqlite3.connect(self.database);self.addCleanup(self.connection.close)
        self.connection.executescript('''
        create table mailboxes(rowid integer primary key,url text);
        create table message_global_data(rowid integer primary key,message_id_header text);
        create table subjects(rowid integer primary key,subject text);
        create table addresses(rowid integer primary key,address text);
        create table messages(rowid integer primary key,mailbox integer,global_message_id integer,sender integer,subject integer,date_received integer,deleted integer,size integer);
        create table recipients(message integer,address integer,type integer,position integer);
        ''')
        self.connection.executemany('insert into mailboxes values (?,?)',[(1,self.prefix+'INBOX'),(2,self.prefix+'Archive'),(3,self.prefix+'Sent')])
        self.connection.executemany('insert into addresses values (?,?)',[(1,'sender@example.test'),(2,'recipient@example.test')])
        for ident,mid,box,subject in [(1,'prior@example.test',2,'Earlier note'),(2,'new@example.test',1,'Your verification code 123456'),(3,'shared@example.test',1,'Copy one'),(4,'shared@example.test',1,'Copy two')]:
            self.connection.execute('insert into message_global_data values (?,?)',(ident,'<'+mid+'>'))
            self.connection.execute('insert into subjects values (?,?)',(ident,subject))
            self.connection.execute('insert into messages values (?,?,?,?,?,?,?,?)',(ident,box,ident,1,ident,1794848000+ident,0,1000+ident))
            self.connection.execute('insert into recipients values (?,?,?,?)',(ident,2,0,0))
        self.connection.commit()
        self.verified={'INBOX':[2,3,4],'Archive':[1],'Junk':[],'Trash':[]}
        api=mock.patch.object(m,'mail_mailbox_ids',side_effect=lambda account:copy.deepcopy(self.verified));api.start();self.addCleanup(api.stop)
        self.base={'run_id':'test','scope':'Prior reviewed messages','snapshot_as_of':'2026-11-15','timezone':'UTC','account_scope':[self.account],
                   'records':[{'item':'M001','account':self.account,'message_id':'prior@example.test','current_id':1,'observed_mailbox':'INBOX','to_display':'recipient@example.test','subject':'Earlier note','received':'2026-11-15T12:00:00+00:00','size_bytes':1000,'gist':'Original content assessment.'}]}

    def refresh(self,**kwargs):
        return m.refresh_snapshot(self.base,self.database,account=self.account,prefix=self.prefix,**kwargs)
    def test_current_inbox_and_prior_placements_are_actual_and_read_only(self):
        before=self.connection.execute('select * from messages').fetchall();original=copy.deepcopy(self.base)
        with mock.patch.object(m,'mail_mailbox_ids',return_value=self.verified):
            source=self.refresh(verify_mail=True,include_prior=True)
        self.assertEqual(source['refresh_evidence']['inbox_count'],3)
        self.assertEqual(source['refresh_evidence']['added_unreviewed'],3)
        self.assertEqual(len(source['records']),4)
        self.assertEqual(source['records'][0]['item'],'M001')
        self.assertEqual(source['records'][0]['observed_mailbox'],'Archive')
        self.assertEqual(source['records'][0]['gist'],original['records'][0]['gist'])
        self.assertEqual(source['refreshed_at'],source['refresh_evidence']['read_completed_at'])
        self.assertIsNotNone(dt.datetime.fromisoformat(source['refreshed_at']).tzinfo)
        incoming=[r for r in source['records'] if r['observed_mailbox']=='INBOX']
        self.assertTrue(all('Awaiting content review' in r['gist'] for r in incoming))
        self.assertEqual(len([r for r in incoming if r['message_id']=='shared@example.test']),2)
        self.assertIn('[code redacted]',next(r['subject'] for r in incoming if r['message_id']=='new@example.test'))
        self.assertEqual(before,self.connection.execute('select * from messages').fetchall())
        self.assertEqual(self.base,original)
    def test_api_mismatch_and_missing_prior_copy_fail_closed(self):
        with mock.patch.object(m,'mail_mailbox_ids',return_value={**self.verified,'INBOX':[2]}):
            with self.assertRaisesRegex(ValueError,'IDs differ'):self.refresh(verify_mail=True,include_prior=True)
        self.connection.execute('delete from messages where rowid=1');self.connection.commit();self.verified['Archive']=[]
        with self.assertRaisesRegex(ValueError,'missing or ambiguous'):self.refresh(include_prior=True)
    def test_prior_duplicate_requires_the_exact_copy(self):
        self.connection.execute('insert into messages values (5,2,1,1,1,1794848005,0,1005)');self.connection.commit();self.verified['Archive']=[1,5]
        source=self.refresh(include_prior=True)
        self.assertEqual(source['records'][0]['current_id'],1)
        self.base['records'][0]['current_id']=99
        with self.assertRaisesRegex(ValueError,'missing or ambiguous'):self.refresh(include_prior=True)
    def test_default_refresh_only_keeps_current_inbox_and_reserves_old_ids(self):
        source=self.refresh(include_prior=False)
        self.assertEqual(len(source['records']),3)

    def test_unconfigured_physical_folders_are_ignored_for_role_verification(self):
        self.connection.execute('insert into message_global_data values (5,?)',('<sent@example.test>',))
        self.connection.execute('insert into subjects values (5,?)',('Sent message',))
        self.connection.execute('insert into messages values (5,3,5,1,5,1794848005,0,1005)')
        self.connection.commit()
        source=self.refresh()
        self.assertEqual(len(source['records']),3)
        self.assertEqual(source['refresh_evidence']['verified_folders'],sorted(m.FOLDERS))

    def test_new_inbox_copy_gets_exact_cache_source_after_inventory(self):
        account_cache=m._account_cache_root(self.database,self.prefix)
        inbox_cache=account_cache/'INBOX.mbox';inbox_cache.mkdir(parents=True,exist_ok=True)
        headers=b'Message-ID: <new@example.test>\r\nSubject: Verification\r\n\r\n'
        path=inbox_cache/'2.emlx';path.write_bytes(str(len(headers)).encode()+b'\n'+headers)
        source=self.refresh()
        record=next(row for row in source['records'] if row['current_id']==2)
        self.assertEqual(record['email_context']['local_source']['path'],str(path.resolve()))
        self.assertEqual(record['email_context']['local_source']['availability'],'verified-existing-header-identity')
        self.assertTrue(all(r['observed_mailbox']=='INBOX' for r in source['records']))
        self.assertNotIn('M001',[r['item'] for r in source['records']])
        self.assertEqual(source['refresh_evidence']['added_unreviewed'],3)
        self.connection.execute('delete from messages where rowid=1');self.connection.commit();self.verified['Archive']=[]
        source=self.refresh(include_prior=False)
        self.assertEqual(len(source['records']),3)

    def test_wrong_first_same_id_candidate_does_not_hide_later_exact_inbox_copy(self):
        cache=m._account_cache_root(self.database,self.prefix);inbox=cache/'INBOX.mbox'
        wrong=inbox/'a'/'Messages'/'42.emlx';wrong.parent.mkdir(parents=True);wrong.write_bytes(b'80\nMessage-ID: <wrong@example.test>\n\nsynthetic\n')
        valid=inbox/'b'/'Messages'/'42.emlx';valid.parent.mkdir(parents=True);valid.write_bytes(b'80\nMessage-ID: <right@example.test>\n\nsynthetic\n')
        original_rglob=Path.rglob
        def deterministic_walk(path,pattern):
            if path==inbox:return iter([wrong,valid])
            return original_rglob(path,pattern)
        with mock.patch.object(Path,'rglob',deterministic_walk):
            candidates=m.resolve_local_files({'records':[]},self.database,self.prefix,{42})
        selected=m.source_reference({'id':42,'mid':'right@example.test'},candidates,cache)
        self.assertEqual(selected['availability'],'verified-existing-header-identity')
        self.assertEqual(selected['path'],str(valid.resolve()))

    def test_invalid_inbox_candidate_keeps_account_fallback_available(self):
        cache=m._account_cache_root(self.database,self.prefix);inbox=cache/'INBOX.mbox'
        wrong=inbox/'a'/'Messages'/'1.emlx';wrong.parent.mkdir(parents=True);wrong.write_bytes(b'80\nMessage-ID: <wrong@example.test>\n\nsynthetic\n')
        valid=cache/'Archive.mbox'/'1.emlx';valid.parent.mkdir(parents=True);valid.write_bytes(b'80\nMessage-ID: <prior@example.test>\n\nsynthetic\n')
        candidates=m.resolve_local_files(self.base,self.database,self.prefix,{1})
        selected=m.source_reference({'id':1,'mid':'prior@example.test'},candidates,cache)
        self.assertEqual(selected['availability'],'verified-existing-header-identity')
        self.assertEqual(selected['path'],str(valid.resolve()))

    def test_header_lookup_stops_before_body_and_preserves_unusual_id(self):
        headers=b'Message-ID: <odd:message@example.test>\r\nSubject: Test\r\n\r\n'
        body=b'Attachment/body content must never be read'
        payload=str(len(headers)+len(body)).encode()+b'\n'+headers+body
        boundary=len(payload)-len(body)
        class HeadersOnly(io.BytesIO):
            def readline(self,size=-1):
                if self.tell()>=boundary:raise AssertionError('Read crossed into body')
                return super().readline(size)
        path=mock.Mock();path.open.return_value=HeadersOnly(payload)
        self.assertEqual(m.header_identity(path),'odd:message@example.test')

    def test_missing_copy_is_never_replaced_by_a_unique_other_copy(self):
        self.connection.execute('update messages set rowid=9 where rowid=1');self.connection.commit();self.verified['Archive']=[9]
        with self.assertRaisesRegex(ValueError,'Prior copy missing or ambiguous'):self.refresh(include_prior=True)
    def test_verification_scope_and_parser_are_mandatory(self):
        with self.assertRaisesRegex(ValueError,'mandatory'):self.refresh(verify_mail=False)
        del self.base['account_scope']
        with self.assertRaisesRegex(ValueError,'single account'):self.refresh(include_prior=True)
        valid='INBOX|2|1,2\nArchive|0|\nJunk|0|\nTrash|0|\n'
        self.assertEqual(m.parse_mailbox_ids(valid)['INBOX'],[1,2])
        for bad in ['INBOX|2|1,1','INBOX|3|1,2',valid.replace('Trash|0|',''),valid+'INBOX|0|']:
            with self.assertRaises(ValueError):m.parse_mailbox_ids(bad)
    def test_stale_prior_reference_is_not_republished_as_verified(self):
        headers=b'Message-ID: <prior@example.test>\r\nSubject: Synthetic\r\n\r\n'
        payload=str(len(headers)).encode()+b'\n'+headers
        account_cache=m._account_cache_root(self.database,self.prefix)
        account_cache.mkdir(parents=True,exist_ok=True)
        cache_roots=mock.patch.object(review_module,'SOURCE_ROOTS',(account_cache,));cache_roots.start();self.addCleanup(cache_roots.stop)
        stale=account_cache/'99.emlx';stale.write_bytes(payload)
        local={'path':str(stale),'file_url':stale.as_uri(),'format':'apple-mail-emlx','partial':False,'availability':'verified-existing-header-identity','access':'Earlier verified source'}
        self.base['records'][0]['email_context']={'sender':'sender@example.test','to':[],'cc':[],'prior_triage_gist':'Earlier','triage_reason':'Earlier','original_disposition':'Inbox','attachment_names':[],'prior_attachment_assessment':'Not assessed','local_source':local,'content_note':'Earlier snapshot'}
        source=self.refresh(include_prior=True)
        self.assertEqual(source['records'][0]['email_context']['local_source']['availability'],'not-located')
        inbox_cache=account_cache/'INBOX.mbox';inbox_cache.mkdir(parents=True,exist_ok=True)
        current=inbox_cache/'1.emlx';current.write_bytes(payload)
        source=self.refresh(local_files={1:[current]},include_prior=True)
        resolved=source['records'][0]['email_context']['local_source']
        self.assertEqual(resolved['availability'],'verified-existing-header-identity')
        self.assertEqual(resolved['path'],str(current))
        self.assertNotEqual(resolved['path'],str(stale))
        self.assertEqual(source['refresh_evidence']['verified_folders'],sorted(m.FOLDERS))

if __name__=='__main__':unittest.main()
