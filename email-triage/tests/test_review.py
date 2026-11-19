import copy
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import hashlib
import base64
import os
import unittest
import datetime as dt
import subprocess
from unittest import mock
import sys

sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))

spec=importlib.util.spec_from_file_location('review',Path(__file__).parents[1]/'scripts/review.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

class ReviewTests(unittest.TestCase):
    def setUp(self):
        fixture=tempfile.TemporaryDirectory();self.addCleanup(fixture.cleanup)
        self.fixture_root=Path(fixture.name).resolve()
        self.mail_root=self.fixture_root/'Mail';self.mail_root.mkdir()
        self.recovery_root=self.fixture_root/'recovery';self.recovery_root.mkdir()
        roots=mock.patch.object(r,'SOURCE_ROOTS',(self.mail_root,self.recovery_root));roots.start();self.addCleanup(roots.stop)
        self.source={'run_id':'test','scope':'Synthetic only','snapshot_as_of':'2026-11-15','timezone':'America/New_York','records':[{'item':'M001','account':'test','message_id':'odd:message@example.test','current_id':7,'observed_mailbox':'Archive','to_display':'test@example.test','subject':'</script><img src=x onerror=alert(1)>','received':'2026-11-14T01:00:00+00:00','size_bytes':42600,'gist':'@@JS@@ <b>text</b>'}]}
        self.source['account_scope']=['test','empty-account']
        self.source['records'][0]['email_context']={'sender':'sender@example.test','to':['test@example.test'],'cc':[],'prior_triage_gist':self.source['records'][0]['gist'],'triage_reason':'Synthetic test','original_disposition':'Archived','attachment_names':[],'prior_attachment_assessment':'Metadata only; reassess before attachment access.','local_source':{'path':str(self.mail_root/'synthetic/message.emlx'),'file_url':(self.mail_root/'synthetic/message.emlx').as_uri(),'format':'apple-mail-emlx','partial':True,'availability':'verified-existing-header-identity','access':'Synthetic fixture only. Read inert text.'},'content_note':'Synthetic fixture; body not embedded.'}
        self.snap=r.normalize_snapshot(self.source)
        row=self.source['records'][0]
        self.edit={'version':1,'run_id':'test','snapshot_id':self.snap['snapshot_id'],'exported_at':'2026-11-15T12:00:00.000Z','changes':[{'item':row['item'],'account':row['account'],'message_id':row['message_id'],'snapshot_mailbox':'Archive','snapshot_numeric_id':7,'original_gist':row['gist'],'gist':'Corrected','requested_move':'inbox','opt_out':True}]}
    def test_roundtrip_and_normalized_snapshot(self):
        self.assertEqual(r.validate_edits(self.snap,self.edit),self.edit)
        self.assertEqual(r.normalize_snapshot(self.snap)['snapshot_id'],self.snap['snapshot_id'])
    def test_dates_and_size(self):
        self.assertEqual(self.snap['records'][0]['received_label'],'2026-11-13 (42.6 KB)')
        self.assertEqual(r.received_label(None,None,'America/New_York'),'Unknown date (size unknown)')
    def test_inert_text_and_single_template_pass(self):
        text,_=r.render_html(self.source)
        self.assertNotIn('</script><img',text)
        self.assertIn(r'\u003c/script\u003e',text)
        self.assertIn('@@JS@@',text)
        self.assertEqual(text.count('<script>'),1)
        self.assertIn("connect-src &#x27;none&#x27;",text)
    def test_reject_tampered_exports(self):
        for field,value in [('snapshot_id','bad'),('version',True),('exported_at','2026-11-15'),('unknown',1)]:
            c=copy.deepcopy(self.edit);c[field]=value
            with self.subTest(field=field),self.assertRaises((ValueError,TypeError)):r.validate_edits(self.source,c)
        for field,value in [('message_id','other'),('snapshot_numeric_id',True),('requested_move','delete'),('opt_out','yes'),('gist','x'*4001),('unknown',1)]:
            c=copy.deepcopy(self.edit);c['changes'][0][field]=value
            with self.subTest(field=field),self.assertRaises((ValueError,TypeError)):r.validate_edits(self.source,c)
        c=copy.deepcopy(self.edit);c['changes']*=2
        with self.assertRaises(ValueError):r.validate_edits(self.source,c)
    def test_reject_empty_and_missing_fields(self):
        c=copy.deepcopy(self.edit);c['changes'][0].update(gist=self.source['records'][0]['gist'],requested_move=None,opt_out=False)
        with self.assertRaises(ValueError):r.validate_edits(self.source,c)
        del self.edit['exported_at']
        with self.assertRaises(ValueError):r.validate_edits(self.source,self.edit)
    def test_reject_duplicate_snapshot_and_bad_metadata(self):
        c=copy.deepcopy(self.source);c['records']*=2
        with self.assertRaises(ValueError):r.normalize_snapshot(c)
        for key,val in [('received','2026-11-15'),('size_bytes',True),('current_id',0)]:
            c=copy.deepcopy(self.source);c['records'][0][key]=val
            with self.subTest(key=key),self.assertRaises(ValueError):r.normalize_snapshot(c)

    def test_unicode_newlines_empty_and_private_write(self):
        c=copy.deepcopy(self.source);c['records'][0]['gist']='😀'*4000+'\r\n'
        with self.assertRaises(ValueError):r.normalize_snapshot(c)
        c['records'][0]['gist']='😀'*3999+'\r\n'
        self.assertTrue(r.normalize_snapshot(c)['records'][0]['gist'].endswith('\n'))
        c['records']=[]
        self.assertEqual(r.normalize_snapshot(c)['records'],[])
        with tempfile.TemporaryDirectory() as d:
            target=Path(d)/'target';target.write_text('original')
            link=Path(d)/'link';link.symlink_to(target)
            r.private_write(link,'private')
            self.assertEqual(target.read_text(),'original')
            self.assertEqual(link.read_text(),'private')
            self.assertEqual(link.stat().st_mode & 0o777,0o600)
    def test_csp_hashes_and_markdown_links(self):
        text,_=r.render_html(self.source)
        for tag,directive in [('script','script-src'),('style','style-src')]:
            content=re.search(f'<{tag}>(.*?)</{tag}>',text,re.S)[1]
            digest=base64.b64encode(hashlib.sha256(content.encode()).digest()).decode()
            self.assertIn(f"{directive} &#x27;sha256-{digest}&#x27;",text)
        c=copy.deepcopy(self.source);c['records'][0]['subject']='https://bad.test user@example.test www.bad.test'
        c['scope']='</script><img src=x> www.bad.test user@example.test WWW.Example.com'
        markdown=r.render_markdown(c)
        self.assertNotIn('<img',markdown)
        self.assertIn('WWW&#46;Example.com',markdown)
        self.assertNotIn('www.bad.test',markdown)
        self.assertIn('https&#58;//bad.test user&#64;example.test www&#46;bad.test',markdown)
    def test_disallowed_disposition_actions(self):
        c=copy.deepcopy(self.edit);c['changes'][0]['requested_move']='archive'
        with self.assertRaises(ValueError):r.validate_edits(self.source,c)
        c=copy.deepcopy(self.source);c['records'][0]['observed_mailbox']='Junk'
        e=copy.deepcopy(self.edit);e['snapshot_id']=r.normalize_snapshot(c)['snapshot_id'];e['changes'][0]['snapshot_mailbox']='Junk'
        self.assertEqual(r.validate_edits(c,e),e)

    def test_v2_assignments_with_source_context(self):
        c=copy.deepcopy(self.source);c['records'][0]['email_context']['sender']='other@example.test'
        e=copy.deepcopy(self.edit);e['version']=2;e['snapshot_id']=r.normalize_snapshot(c)['snapshot_id'];e['changes'][0]['assign_to_llm']=True
        a=r.assignment_payload(c,e)
        self.assertEqual(r.validate_assignments(c,a),a)
        self.assertEqual(a['assignments'][0]['user_instruction'],'Corrected')
        self.assertEqual(a['assignments'][0]['email']['email_context'],c['records'][0]['email_context'])
        a['assignments'][0]['email']['email_context']['sender']='changed'
        with self.assertRaises(ValueError):r.validate_assignments(c,a)
    def test_v2_assignment_instruction_is_independent_from_immutable_summary(self):
        row=self.snap['records'][0]
        assignment={'version':2,'kind':'email-triage-assignments','run_id':'test','snapshot_id':self.snap['snapshot_id'],
                    'exported_at':'2026-11-15T12:00:00.000Z','policy':r.ASSIGNMENT_POLICY,
                    'assignments':[{'item':row['item'],'assigned_to':None,'user_instruction':row['gist'],
                                   'requested_move':None,'opt_out':False,'email':row}]}
        self.assertEqual(r.validate_assignments(self.source,assignment),assignment)
        legacy=dict(assignment,version=1)
        with self.assertRaisesRegex(ValueError,'Edit gist/action'):
            r.validate_assignments(self.source,legacy)
    def test_typed_review_bundle_binds_each_action_to_exact_copy(self):
        row=self.snap['records'][0]
        identity={'item':row['item'],'account':row['account'],'message_id':row['message_id'],'snapshot_mailbox':row['observed_mailbox'],'snapshot_numeric_id':row['current_id']}
        bundle={'version':1,'kind':'email-triage-review-bundle','run_id':'test','snapshot_id':self.snap['snapshot_id'],'exported_at':'2026-11-15T12:00:00.000Z',
                'moves':[{**identity,'destination':'inbox'}], 'opt_outs':[identity.copy()],
                'tasks':[{**identity,'instruction':'Review this message locally and draft a response.'}],
                'comments':[{**identity,'original_summary':row['gist'],'comment':'Corrected account of the result.'}],
                'refresh_request':None}
        self.assertEqual(r.validate_review_bundle(self.source,bundle),bundle)
        pending={'version':2,'run_id':'test','snapshot_id':self.snap['snapshot_id'],'exported_at':'2026-11-15T12:00:00.000Z','changes':[{'item':row['item'],'account':row['account'],'message_id':row['message_id'],'snapshot_mailbox':row['observed_mailbox'],'snapshot_numeric_id':row['current_id'],'original_gist':row['gist'],'gist':bundle['comments'][0]['comment'],'requested_move':'inbox','opt_out':True,'assign_to_llm':False}]}
        bundle['refresh_request']={'version':1,'kind':'email-triage-refresh-request','mode':'read-only','run_id':'test','snapshot_id':self.snap['snapshot_id'],'requested_at':'2026-11-15T12:00:00.000Z','account_scope':['test','empty-account'],'request':r.REFRESH_REQUEST_TEXT,'pending_review':pending}
        self.assertEqual(r.validate_review_bundle(self.source,bundle),bundle)
        tampered=copy.deepcopy(bundle);tampered['refresh_request']['pending_review']['changes'][0]['opt_out']=False
        with self.assertRaises(ValueError):r.validate_review_bundle(self.source,tampered)
        for mutate in [lambda x:x['moves'][0].update(snapshot_numeric_id=8),lambda x:x['tasks'][0].update(instruction='  '),lambda x:x['comments'][0].update(original_summary='tampered'),lambda x:x.update(snapshot_id='other'),lambda x:x.update(extra=True)]:
            bad=copy.deepcopy(bundle);mutate(bad)
            with self.subTest(bundle=bad),self.assertRaises((ValueError,TypeError)):r.validate_review_bundle(self.source,bad)
    def test_assign_only_and_any_folder_opt_out(self):
        for folder in r.FOLDERS:
            c=copy.deepcopy(self.source);c['records'][0]['observed_mailbox']=folder
            e=copy.deepcopy(self.edit);e.update(version=2,snapshot_id=r.normalize_snapshot(c)['snapshot_id']);e['changes'][0].update(snapshot_mailbox=folder,gist=c['records'][0]['gist'],requested_move=None,opt_out=True,assign_to_llm=False)
            self.assertEqual(r.validate_edits(c,e),e)
            e['changes'][0].update(opt_out=False,assign_to_llm=True,gist='Review this source locally and draft a note.')
            self.assertEqual(len(r.assignment_payload(c,e)['assignments']),1)
            e['changes'][0]['assign_to_llm']='yes'
            with self.assertRaises(ValueError):r.validate_edits(c,e)

    def test_read_only_refresh_scope_and_pending_edits(self):
        request={'version':1,'kind':'email-triage-refresh-request','mode':'read-only','run_id':'test','snapshot_id':self.snap['snapshot_id'],'requested_at':self.edit['exported_at'],'account_scope':['test','empty-account'],'request':r.REFRESH_REQUEST_TEXT,'pending_review':self.edit}
        self.assertEqual(r.validate_refresh(self.source,request),request)
        for key,val in [('mode','apply'),('account_scope',['other']),('snapshot_id','other'),('request','move everything')]:
            bad=copy.deepcopy(request);bad[key]=val
            with self.subTest(key=key),self.assertRaises(ValueError):r.validate_refresh(self.source,bad)

    def test_assignment_validation_boundaries_and_versions(self):
        e=copy.deepcopy(self.edit);e['version']=2;e['changes'][0]['assign_to_llm']=True
        a=r.assignment_payload(self.source,e)
        for mutate in [lambda x:x['policy'].update(execution='unsafe'), lambda x:x['assignments'][0].update(assigned_to='an-agent'), lambda x:x['assignments'][0].update(requested_move='delete')]:
            bad=copy.deepcopy(a);mutate(bad)
            with self.assertRaises(ValueError):r.validate_assignments(self.source,bad)
        for version, include in [(1,True),(2,False)]:
            bad=copy.deepcopy(self.edit);bad['version']=version
            if include:bad['changes'][0]['assign_to_llm']=True
            with self.assertRaises(ValueError):r.validate_edits(self.source,bad)
        e['changes'][0]['gist']=self.source['records'][0]['gist']
        with self.assertRaises(ValueError):r.validate_edits(self.source,e)
    def test_context_schema_and_runtime_snapshot_separation(self):
        for mutate in [lambda x:x.pop('sender'),lambda x:x['local_source'].update(file_url='https://bad.test'),lambda x:x['local_source'].update(path='relative.emlx'),lambda x:x['local_source'].update(partial='unknown')]:
            c=copy.deepcopy(self.source);mutate(c['records'][0]['email_context'])
            with self.assertRaises(ValueError):r.normalize_snapshot(c)
        text,snap=r.render_html(self.source)
        self.assertNotIn('assignment_policy',snap)
        self.assertNotIn('refresh_request_text',snap)
        self.assertIn('received_timestamps',text)
    def test_refresh_pending_tamper_and_empty_accounts(self):
        request={'version':1,'kind':'email-triage-refresh-request','mode':'read-only','run_id':'test','snapshot_id':self.snap['snapshot_id'],'requested_at':self.edit['exported_at'],'account_scope':['test','empty-account'],'request':r.REFRESH_REQUEST_TEXT,'pending_review':copy.deepcopy(self.edit)}
        request['pending_review']['changes'][0]['message_id']='tampered'
        with self.assertRaises(ValueError):r.validate_refresh(self.source,request)
        c=copy.deepcopy(self.source);c['records']=[]
        request.update(snapshot_id=r.normalize_snapshot(c)['snapshot_id'])
        request['pending_review'].update(snapshot_id=request['snapshot_id'],changes=[])
        self.assertEqual(r.validate_refresh(c,request),request)
    def test_cli_validation_subcommands(self):
        source=copy.deepcopy(self.source);source['records'][0]['email_context']['local_source'].update(path=None,file_url=None,format=None,partial=None,availability='not-located')
        e=copy.deepcopy(self.edit);e.update(version=2,snapshot_id=r.normalize_snapshot(source)['snapshot_id']);e['changes'][0]['assign_to_llm']=True
        a=r.assignment_payload(source,e)
        refresh={'version':1,'kind':'email-triage-refresh-request','mode':'read-only','run_id':'test','snapshot_id':e['snapshot_id'],'requested_at':e['exported_at'],'account_scope':['test','empty-account'],'request':r.REFRESH_REQUEST_TEXT,'pending_review':e}
        row=source['records'][0];identity={'item':row['item'],'account':row['account'],'message_id':row['message_id'],'snapshot_mailbox':row['observed_mailbox'],'snapshot_numeric_id':row['current_id']}
        bundle={'version':1,'kind':'email-triage-review-bundle','run_id':'test','snapshot_id':e['snapshot_id'],'exported_at':e['exported_at'],'moves':[],'opt_outs':[identity],'tasks':[],'comments':[],'refresh_request':None}
        typed_assignment=copy.deepcopy(a);typed_assignment['version']=2;typed_assignment['assignments'][0]['user_instruction']=source['records'][0]['gist']
        with tempfile.TemporaryDirectory() as directory:
            d=Path(directory);(d/'source.json').write_text(json.dumps(source))
            for command,payload in [('validate-edits',e),('validate-assignments',a),('validate-assignments',typed_assignment),('validate-refresh',refresh),('validate-bundle',bundle)]:
                (d/'export.json').write_text(json.dumps(payload))
                result=subprocess.run([sys.executable,str(Path(r.__file__)),command,str(d/'source.json'),str(d/'export.json')],capture_output=True,text=True,timeout=10)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertIn('Export SHA-256:',result.stdout)
                self.assertIn('No Mail actions performed',result.stdout)

    def test_missing_source_and_legacy_scope(self):
        c=copy.deepcopy(self.source);local=c['records'][0]['email_context']['local_source'];local.update(path=None,file_url=None,format=None,partial=None,availability='not-located')
        r.normalize_snapshot(c)
        local['availability']='unsupported'
        with self.assertRaises(ValueError):r.normalize_snapshot(c)
        c=copy.deepcopy(self.source);c['account_scope']=['empty-account']
        with self.assertRaises(ValueError):r.normalize_snapshot(c)
        c=copy.deepcopy(self.source);del c['account_scope']
        text,snap=r.render_html(c)
        self.assertNotIn('account_scope',snap)
        request={'version':1,'kind':'email-triage-refresh-request','mode':'read-only','run_id':'test','snapshot_id':snap['snapshot_id'],'requested_at':self.edit['exported_at'],'account_scope':['test'],'request':r.REFRESH_REQUEST_TEXT,'pending_review':self.edit}
        with self.assertRaisesRegex(ValueError,'explicit account scope'):r.validate_refresh(c,request)
    def test_source_boundaries_and_whitespace(self):
        for path in ['/etc/passwd',str(self.mail_root/'../../etc/passwd')]:
            c=copy.deepcopy(self.source);local=c['records'][0]['email_context']['local_source'];local.update(path=path,file_url=Path(path).as_uri())
            with self.assertRaises(ValueError):r.normalize_snapshot(c)
        c=copy.deepcopy(self.source);c['records'][0]['email_context']['content_note']='x'*4001
        with self.assertRaises(ValueError):r.normalize_snapshot(c)
        for whitespace in ['\ufeff','\x85']:
            e=copy.deepcopy(self.edit);e['version']=2;e['changes'][0].update(assign_to_llm=True,gist=self.source['records'][0]['gist']+whitespace)
            with self.assertRaises(ValueError):r.validate_edits(self.source,e)

    def test_strict_source_file_paths_and_format(self):
        base=str(self.mail_root)
        for path in [base,base+'/Envelope Index',base+'/./real.emlx',base+'//real.emlx',base+'/real.emlx/',base+'/bad\x7f.emlx']:
            c=copy.deepcopy(self.source);local=c['records'][0]['email_context']['local_source'];local.update(path=path,file_url=Path(path).as_uri())
            with self.subTest(path=path),self.assertRaises(ValueError):r.normalize_snapshot(c)
        c=copy.deepcopy(self.source);c['records'][0]['email_context']['local_source']['format']='pdf'
        with self.assertRaises(ValueError):r.normalize_snapshot(c)
        c=copy.deepcopy(self.source);local=c['records'][0]['email_context']['local_source'];local.update(availability='not-located')
        with self.assertRaises(ValueError):r.normalize_snapshot(c)
        with tempfile.TemporaryDirectory() as directory:
            d=Path(directory).resolve();mail=d/'mail';mail.mkdir();outside=d/'outside.emlx';outside.write_text('synthetic');link=mail/'escape.emlx';link.symlink_to(outside)
            c=copy.deepcopy(self.source);c['records'][0]['email_context']['local_source'].update(path=str(link),file_url=link.as_uri())
            with mock.patch.object(r,'SOURCE_ROOTS',(mail,)),self.assertRaises(ValueError):r.normalize_snapshot(c)
    def test_record_limits_and_python_wrong_export_type(self):
        c=copy.deepcopy(self.source);c['records'][0]['subject']='x'*4001
        with self.assertRaises(ValueError):r.normalize_snapshot(c)
        for kind in ['email-triage-assignments','email-triage-refresh-request']:
            with self.assertRaisesRegex(ValueError,'Expected a Mail review export'):r.validate_edits(self.source,{'kind':kind})

    def test_recovery_extensions_directories_and_metadata_caps(self):
        for root,accepted in [(self.mail_root,False),(self.recovery_root,True)]:
            c=copy.deepcopy(self.source);path=root/'original.emlx.bin';c['records'][0]['email_context']['local_source'].update(path=str(path),file_url=path.as_uri())
            if accepted:r.normalize_snapshot(c)
            else:
                with self.assertRaises(ValueError):r.normalize_snapshot(c)
        for name in ['folder.emlx','.emlx','.emlx.bin']:
            path=self.mail_root/name
            if name=='folder.emlx':path.mkdir()
            c=copy.deepcopy(self.source);c['records'][0]['email_context']['local_source'].update(path=str(path),file_url=path.as_uri())
            with self.assertRaises(ValueError):r.normalize_snapshot(c)
        for key,value in [('scope','x'*8001)]:
            c=copy.deepcopy(self.source);c[key]=value
            with self.assertRaises(ValueError):r.normalize_snapshot(c)
        c=copy.deepcopy(self.source);c['records'][0]['received']='2026-11-15T12:00:00.'+'0'*110+'+00:00'
        with self.assertRaisesRegex(ValueError,'Invalid received timestamp'):r.normalize_snapshot(c)
        for accounts in [['test','x'*4001],['test']+[str(i) for i in range(100)]]:
            c=copy.deepcopy(self.source);c['account_scope']=accounts
            with self.assertRaisesRegex(ValueError,'Invalid explicit account scope'):r.normalize_snapshot(c)

    def test_separate_received_size_display_preserves_identity(self):
        before=r.normalize_snapshot(self.source)
        text,snapshot=r.render_html(self.source)
        self.assertEqual(snapshot['snapshot_id'],before['snapshot_id'])
        self.assertEqual(r.display_metadata(snapshot['records'][0]),{'received_date':'2026-11-13','size_label':'42.6 KB'})
        c=copy.deepcopy(self.source);c['records'][0].update(received=None,size_bytes=None)
        self.assertEqual(r.display_metadata(r.normalize_snapshot(c)['records'][0]),{'received_date':'Unknown date','size_label':'Size unknown'})
        markdown=r.render_markdown(self.source)
        self.assertIn('| Item | Received | Size | To address |',markdown)
        self.assertIn('| 2026-11-13 | 42.6 KB |',markdown)
        self.assertIn('data-sort="size_bytes"',text)

    def test_legacy_snapshot_id_from_de6cf29(self):
        source=json.loads((Path(__file__).parent/'fixtures/legacy-snapshot.json').read_text())
        expected='f91dfce00fc66ca0dbab012a55738441109aa3dd1ef157306f292fe26f3fd998'
        self.assertEqual(r.normalize_snapshot(source)['snapshot_id'],expected)
        self.assertEqual(r.render_html(source)[1]['snapshot_id'],expected)

    def test_report_time_format_and_snapshot_identity(self):
        cases=[('2026-11-16T15:00:00+00:00','11.16.26 @ 10am EST'),('2026-07-16T14:05:00+00:00','07.16.26 @ 10:05am EDT'),('2026-11-16T17:00:00+00:00','11.16.26 @ 12pm EST'),('2026-11-16T05:00:00+00:00','11.16.26 @ 12am EST')]
        for timestamp,expected in cases:
            self.assertEqual(r.refreshed_label(dt.datetime.fromisoformat(timestamp),'America/New_York'),expected)
        with self.assertRaises(ValueError):r.refreshed_label(dt.datetime(2026,11,16,10),'America/New_York')
        html,baseline=r.render_html(self.source,dt.datetime.fromisoformat(cases[0][0]))
        self.assertIn(cases[0][1],html)
        self.assertIn('Not recorded',html)
        self.assertEqual(baseline['snapshot_id'],self.snap['snapshot_id'])
        self.assertNotIn('generated_at',baseline)

    def test_mail_refresh_time_survives_layout_rebuild(self):
        source=copy.deepcopy(self.source);source['refreshed_at']='2026-11-16T15:00:00Z'
        source['refresh_evidence']={'source':'Synthetic verified inventory','read_started_at':'2026-11-16T14:59:59Z','read_completed_at':source['refreshed_at'],'mail_api_verified':True,'verified_folders':sorted(r.FOLDERS),'inbox_count':0,'added_unreviewed':0,'prior_snapshot_id':self.snap['snapshot_id'],'server_sync':'Local view only'}
        first,snapshot=r.render_html(source,dt.datetime.fromisoformat('2026-11-16T18:00:00Z'))
        second,later=r.render_html(source,dt.datetime.fromisoformat('2026-11-17T18:00:00Z'))
        for output in [first,second]:
            self.assertIn('"last_refreshed_label": "11.16.26 @ 10am EST"',output)
        self.assertEqual(snapshot['snapshot_id'],later['snapshot_id'])
        self.assertNotEqual(snapshot['snapshot_id'],self.snap['snapshot_id'])
        source['refreshed_at']='2026-11-16T10:00:00'
        with self.assertRaises(ValueError):r.normalize_snapshot(source)
    def test_distinct_copies_share_message_id_without_identity_loss(self):
        source=copy.deepcopy(self.source);other=copy.deepcopy(source['records'][0]);other.update(item='M002',current_id=8);source['records'].append(other)
        self.assertEqual(len(r.normalize_snapshot(source)['records']),2)
        source['records'][1]['current_id']=source['records'][0]['current_id']
        with self.assertRaises(ValueError):r.normalize_snapshot(source)

    def test_timestamp_without_verified_evidence_is_not_fresh(self):
        source=copy.deepcopy(self.source);source['refreshed_at']='2026-11-16T15:00:00Z'
        html,_=r.render_html(source,dt.datetime.fromisoformat('2026-11-17T18:00:00Z'))
        self.assertIn('"last_refreshed_label": "Not recorded"',html)
        self.assertIn('"generated_label": "11.17.26 @ 1pm EST"',html)
        self.assertIn('"status": "unverified"',html)
        self.assertIn('Placement not verified',html)
        self.assertNotIn('Verified disposition',html)

    def test_verified_placement_badge_requires_saved_mail_evidence_without_hash_change(self):
        source=copy.deepcopy(self.source);source['refreshed_at']='2026-11-16T15:00:00Z'
        source['refresh_evidence']={'source':'Synthetic verified inventory','read_started_at':'2026-11-16T14:59:59Z','read_completed_at':source['refreshed_at'],'mail_api_verified':True,'verified_folders':sorted(r.FOLDERS),'inbox_count':0,'added_unreviewed':0,'prior_snapshot_id':self.snap['snapshot_id'],'server_sync':'Synthetic'}
        expected=r.normalize_snapshot(source)['snapshot_id']
        html,snapshot=r.render_html(source)
        self.assertIn('"status": "verified"',html)
        self.assertIn('Placement verified',html)
        self.assertEqual(snapshot['snapshot_id'],expected)

    def test_completed_action_requires_matching_receipt_for_placement_verification(self):
        action={'item':'M001','account':'test','message_id':'odd:message@example.test','old_id':6,'new_id':7,
            'status':'verified-completed','attempt_id':'synthetic-attempt','receipt_new_id':7,'old_mailbox':'INBOX','destination':'Archive'}
        history=[{'run_id':'test','actions':[action]}]
        html,_=r.render_html(self.source,history=history)
        self.assertIn('Placement verified',html)
        action['receipt_new_id']=8
        html,_=r.render_html(self.source,history=history)
        self.assertIn('Placement not verified',html)

if __name__=='__main__':unittest.main()
