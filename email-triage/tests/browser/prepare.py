"""Build synthetic browser fixtures only. Never reads real mail."""
import copy
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]))
from test_review import ReviewTests,r
x=ReviewTests();x.setUp()
# Fixture paths are intentionally unavailable; the browser never accesses source mail.
for record in x.source['records']:record['email_context']['local_source'].update(path=None,file_url=None,format=None,partial=None,availability='not-located')
extra=copy.deepcopy(x.source['records'][0]);extra.update(item='M002',message_id='second@example.test',current_id=8,observed_mailbox='Junk',size_bytes=None,subject='Synthetic note to alice@example.test '+str(Path('/').joinpath('Users','example','private','123456'))+' Example Person');x.source['records'].append(extra)
extra=copy.deepcopy(extra);extra.update(item='M003',message_id='third@example.test',current_id=9,observed_mailbox='Trash',received='20261115T120000Z',size_bytes=2000000);x.source['records'].append(extra)
x.source['refreshed_at']='2026-11-16T15:00:00Z'
x.source['refresh_evidence']={'source':'Synthetic verified inventory','read_started_at':'2026-11-16T14:59:59Z','read_completed_at':x.source['refreshed_at'],'mail_api_verified':True,'verified_folders':sorted(r.FOLDERS),'inbox_count':0,'added_unreviewed':0,'prior_snapshot_id':'0'*64,'server_sync':'Local view only'}
for name,text in [('fixture.html',r.render_html(x.source)[0]),('source.json',json.dumps(x.source))]:
    r.private_write(Path(__file__).parent/name,text)
legacy=copy.deepcopy(x.source);legacy.pop('refresh_evidence',None);legacy.pop('refreshed_at',None)
r.private_write(Path(__file__).parent/'legacy-fixture.html',r.render_html(legacy)[0])

# Deterministic larger fixtures for measurement-only browser runs.
prototype=x.source['records'][0]
for size in (100,1000,10000):
    large=copy.deepcopy(x.source);records=[]
    for index in range(size):
        row=copy.deepcopy(prototype)
        row.update(item=f'M{index+1:05}',message_id=f'synthetic-{index+1}@example.test',current_id=index+100,observed_mailbox='INBOX',subject=f'Synthetic message {index+1}',gist=f'Synthetic immutable summary for record {index+1}')
        records.append(row)
    large['records']=records
    if 'refresh_evidence' in large:large['refresh_evidence']['inbox_count']=len(records)
    r.private_write(Path(__file__).parent/f'benchmark-{size}.html',r.render_html(large)[0])

# Separate synthetic history fixture: no real Mail or user selections.
history=[{'run_id':'test','at':'2026-11-15T15:00:00Z','reviewed_at':'2026-11-16T15:00:00Z','review_url':'file:///synthetic/older.html','counts':{},'actions':[{'item':'M001','account':'test','message_id':'odd:message@example.test','old_id':6,'new_id':7,'status':'verified-completed','attempt_id':'synthetic-attempt-1','receipt_new_id':7,'old_mailbox':'INBOX','destination':'Archive','subject':'<img src=x onerror=alert(1)>','reason':'Synthetic receipt-backed completed action'},{'item':'M002','account':'test','message_id':'second@example.test','old_id':7,'new_id':8,'status':'verified-completed','attempt_id':'synthetic-attempt-2','receipt_new_id':9,'old_mailbox':'INBOX','destination':'Junk','subject':'Invalid receipt synthetic row','reason':'Must remain unverified'}], 'tasks':[{'item':'M001','account':'test','message_id':'odd:message@example.test','current_id':7,'status':'waiting_vendor','next_action':'Check vendor response'}], 'assessments':[{'item':'M001','account':'test','message_id':'odd:message@example.test','current_id':7,'assessed_at':'2026-11-15T14:00:00Z','result':{'status':'reviewed'},'invalidated_at':None}],'assessment_readiness':[{'item':'M001','account':'test','message_id':'odd:message@example.test','current_id':7,'status':'awaiting_assessment','reason':'Synthetic cache miss'}]},{'run_id':'latest-run','at':'2026-11-16T15:00:00Z','reviewed_at':None,'review_url':'file:///synthetic/latest.html','counts':{},'actions':[]}]
history_source=copy.deepcopy(x.source);history_source.pop('refresh_evidence',None);history_source.pop('refreshed_at',None)
r.private_write(Path(__file__).parent/'history-fixture.html',r.render_html(history_source,history=history)[0])
