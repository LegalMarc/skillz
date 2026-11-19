#!/usr/bin/env python3
"""Supported coordinator for a frozen triage snapshot, verified actions and offline review."""
import argparse
import datetime as dt
import html
import json
import os
from pathlib import Path
import sys
import uuid

HERE=Path(__file__).resolve().parent
if str(HERE) not in sys.path:sys.path.insert(0,str(HERE))
from apply_mail import apply, validate_plan
from execution import _reconcile_locked, account_locks, account_transaction, append_event, create_or_validate_manifest, reconcile, rules_digest, validate_existing_manifest
from history import acknowledge, export_history, get_export_receipt, get_registered_snapshot, journal_attempt_state, record_comment, register, upsert_followup
from review import normalize_snapshot, private_write, read_json, render_html, require, validate_review_bundle


def _read_journal(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()] if Path(path).exists() else []


def _attempt_state(events,snapshot_id):
    return journal_attempt_state(events,snapshot_id)


def _plan_from_bundle(snapshot,bundle,raw_bundle=None,raw_snapshot=None):
    validate_review_bundle(snapshot,bundle)
    require(bundle.get('refresh_request') is None,'Read-only refresh bundle cannot authorize moves; create a new action-only export from the refreshed review')
    raw=raw_bundle if raw_bundle is not None else json.dumps(bundle,sort_keys=True,separators=(',',':')).encode('utf-8')
    snapshot_raw=raw_snapshot if raw_snapshot is not None else json.dumps(snapshot,sort_keys=True,separators=(',',':')).encode('utf-8')
    evidence={'bundle_json':raw.decode('utf-8'),'export_sha256':__import__('hashlib').sha256(raw).hexdigest(),
      'snapshot_json':snapshot_raw.decode('utf-8'),'snapshot_sha256':__import__('hashlib').sha256(snapshot_raw).hexdigest()}
    actions=[];rows={r['item']:r for r in snapshot['records']}
    for request in bundle['moves']:
        action={'item':request['item'],'destination':{'inbox':'INBOX','archive':'Archive'}[request['destination']],'reason':'User-requested move from validated review bundle'}
        row=rows[request['item']]
        if action['destination']!='INBOX':
            action['age_override']={'source':'validated-user-review','export_sha256':evidence['export_sha256'],'item':request['item'],'account':request['account'],'message_id':request['message_id'],'numeric_id':request['snapshot_numeric_id']}
        actions.append(action)
    return {'snapshot_id':snapshot['snapshot_id'],'started_at':bundle['exported_at'],'authorization':'Validated exact-snapshot user review bundle.',
      'actions':actions,'user_review_evidence':evidence}


def _apply_bundle_annotations(database,snapshot,bundle,actions=(),verified_snapshot=None):
    from history import alias_item_identity
    now=(bundle or {}).get('exported_at') or __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat();rows={r['item']:r for r in snapshot['records']}
    current_rows={r['item']:r for r in verified_snapshot['records']} if verified_snapshot else rows
    target_run_id=verified_snapshot['run_id'] if verified_snapshot else snapshot['run_id']
    for event in actions:
        if event.get('status') in ('verified-moved','verified-retained','verified-completed'):
            for run_id in {snapshot['run_id'],target_run_id}:
                alias_item_identity(database,run_id,event['item'],{'account':event['account'],'message_id':event['message_id'],'current_id':event['new_id']},now)
                old_id=event.get('old_id')
                if old_id!=event.get('new_id'):
                    alias_item_identity(database,run_id,event['item'],{'account':event['account'],'message_id':event['message_id'],'current_id':old_id},now)
    if not bundle:return
    for task in bundle['tasks']:
        row=rows[task['item']];current=current_rows.get(task['item'],row);key=json.dumps([snapshot['run_id'],task['item'],task['account'],task['message_id'],task['instruction']],sort_keys=True)
        task_id='task-'+__import__('hashlib').sha256(key.encode()).hexdigest()[:24]
        upsert_followup(database,{'task_id':task_id,'run_id':target_run_id,'item':task['item'],'account':task['account'],'message_id':task['message_id'],'current_id':current['current_id'],
          'summary':row['gist'],'next_action':task['instruction'],'status':'ready','deadline':None,'waiting_on':None,'evidence_refs':[f"item:{task['item']}",f"message-id:{task['message_id']}"],
          'result_link':None,'created_at':now,'updated_at':now,'result_confirmed_at':None},preserve_progress=True)
    for entry in bundle.get('opt_outs',[]):
        row=rows[entry['item']];current=current_rows.get(entry['item'],row);key=json.dumps([snapshot['run_id'],entry['item'],entry['account'],entry['message_id'],'opt-out-review'],sort_keys=True)
        task_id='optout-'+__import__('hashlib').sha256(key.encode()).hexdigest()[:24]
        upsert_followup(database,{'task_id':task_id,'run_id':target_run_id,'item':entry['item'],'account':entry['account'],'message_id':entry['message_id'],'current_id':current['current_id'],
          'summary':row['gist'],'next_action':'Pending safety review: assess whether a verified list-specific opt-out flow is safe. Do not unsubscribe or contact the sender from this selection alone.',
          'status':'ready','deadline':None,'waiting_on':None,'evidence_refs':[f"item:{entry['item']}",f"message-id:{entry['message_id']}"],
          'result_link':None,'created_at':now,'updated_at':now,'result_confirmed_at':None},preserve_progress=True)
    for comment in bundle['comments']:
        row=rows[comment['item']];identity={'account':row['account'],'message_id':row['message_id'],'current_id':row['current_id']}
        record_comment(database,target_run_id,row['item'],identity,comment['original_summary'],comment['comment'],now)
        # Comments do not rewrite a summary; a changed assessment needs fresh evidence.
        from history import invalidate_assessments
        invalidate_assessments(database,snapshot['run_id'],identity,'user_correction',now)


def _refresh_after_apply(snapshot,journal,database,refresh_adapter=None):
    events=[e for e in _attempt_state(_read_journal(journal),snapshot['snapshot_id'])['verified']
        if e.get('status') in ('verified-moved','verified-completed','verified-retained')]
    base=json.loads(json.dumps(snapshot));rows={r['item']:r for r in base['records']}
    frozen_rows=json.loads(json.dumps(rows))
    for event in events:
        row=rows[event['item']]
        require((row['account'],row['message_id'],row['current_id'],row['observed_mailbox'])==(event['account'],event['message_id'],event['old_id'],event['old_mailbox']),'Journal source identity differs from frozen snapshot')
        row['current_id']=event['new_id'];row['observed_mailbox']=event['destination']
    base.pop('refreshed_at',None);base.pop('refresh_evidence',None)
    if refresh_adapter:return refresh_adapter(base)
    from refresh_mail import refresh_snapshot, DATABASE, ACCOUNT, PREFIX, resolve_local_files
    from history import allocate_item_id, reserve_snapshot_items
    reserve_snapshot_items(database,base)
    completed_items={event['item'] for event in events if event['status'] in ('verified-moved','verified-completed')}
    inbox_base=json.loads(json.dumps(base));inbox_base['records']=[r for r in base['records'] if r['item'] not in completed_items and r['observed_mailbox']=='INBOX']
    local=resolve_local_files(inbox_base,DATABASE,PREFIX,{r['current_id'] for r in inbox_base['records']})
    source=refresh_snapshot(inbox_base,DATABASE,account=ACCOUNT,prefix=PREFIX,verify_mail=True,local_files=local,include_prior=False,
      item_allocator=lambda identity:allocate_item_id(database,base['run_id'],identity))
    # A receipt proves the earlier action, not continued placement after a later
    # manual move. Check the exact current copies before adding them to this
    # freshly inventoried report; never publish the receipt as current state.
    from apply_mail import lookup_many
    from config import CONFIG
    outcome_items={event['item'] for event in events}
    outcome_rows=[row for row in base['records'] if row['item'] in outcome_items]
    current_checks=lookup_many(outcome_rows,CONFIG['folder_map'])
    for row in outcome_rows:
        checked=current_checks.get((row['account'],row['message_id'],row['current_id']))
        require(type(checked) is bool and checked==(row['observed_mailbox']=='Junk'),
            'Post-action exact-copy placement or Junk state changed; refresh not published')
    fresh_rows={r['item']:r for r in source['records']}
    for event in events:
        original=frozen_rows[event['item']]
        if event['status']=='verified-retained':
            require((original['account'],original['message_id'],event['old_id'],event['old_mailbox'],event['new_id'],event['destination'])==
                (event['account'],event['message_id'],original['current_id'],original['observed_mailbox'],original['current_id'],original['observed_mailbox']),
                'Retained action differs from the frozen exact-copy identity')
            if event['destination']!='INBOX':
                old=fresh_rows.get(event['item']);require(old is None or (old['account'],old['message_id'],old['current_id'])==(original['account'],original['message_id'],original['current_id']),
                    'Refreshed inventory conflicts with the retained exact copy')
                fresh_rows[event['item']]=json.loads(json.dumps(original))
            continue
        if event['status'] not in ('verified-moved','verified-completed'):continue
        require((original['account'],original['message_id'],event['old_id'],event['old_mailbox'])==(event['account'],event['message_id'],original['current_id'],original['observed_mailbox']),
            'Verified move differs from the frozen exact-copy identity')
        moved=json.loads(json.dumps(original));moved['current_id']=event['new_id'];moved['observed_mailbox']=event['destination']
        old=fresh_rows.get(event['item']);require(old is None or (old['account'],old['message_id'],old['current_id'])==(moved['account'],moved['message_id'],moved['current_id']),
            'Refreshed inventory conflicts with the receipt-backed destination copy')
        fresh_rows[event['item']]=moved
    source['records']=list(fresh_rows.values())
    source=normalize_snapshot(source)
    current={r['item'] for r in source['records']}
    from history import tombstone_item
    for row in base['records']:
        if row['item'] not in current:
            try:tombstone_item(database,base['run_id'],row['item'])
            except ValueError:pass
    return source


def run_pipeline(snapshot_path,plan_path,rules_path,manifest_path,journal_path,recovery_root,verified_snapshot_path,review_path,database,*,bundle_path=None,assessment_evidence_path=None,apply_adapter=None,refresh_adapter=None,authorized=False,expected_plan_digest=None):
    if not authorized:
        return _run_pipeline_impl(snapshot_path,plan_path,rules_path,manifest_path,journal_path,recovery_root,verified_snapshot_path,review_path,database,
            bundle_path=bundle_path,assessment_evidence_path=assessment_evidence_path,apply_adapter=apply_adapter,refresh_adapter=refresh_adapter,
            authorized=False,expected_plan_digest=expected_plan_digest)
    snapshot=normalize_snapshot(read_json(snapshot_path))
    import config
    selected_account=config.CONFIG.get('account')
    require(selected_account and snapshot.get('account_scope')==[selected_account]
        and all(row.get('account')==selected_account for row in snapshot['records']),
        'Snapshot must name exactly the single selected Mail account; no actions applied')
    config.resolve_snapshot_timezone(snapshot.get('timezone'))
    from apply_mail import configured_history_database
    configured_database=Path(configured_history_database()).resolve()
    require(Path(database).resolve()==configured_database,'Coordinator history database must be the configured private history database')
    # The core performs registered-baseline checks; acquire the account lock
    # before it opens/migrates history SQLite, then retain it through publication.
    with account_transaction([selected_account]):
        return _run_pipeline_impl(snapshot_path,plan_path,rules_path,manifest_path,journal_path,recovery_root,verified_snapshot_path,review_path,database,
            bundle_path=bundle_path,assessment_evidence_path=assessment_evidence_path,apply_adapter=apply_adapter,refresh_adapter=refresh_adapter,
            authorized=True,expected_plan_digest=expected_plan_digest)


def _run_pipeline_impl(snapshot_path,plan_path,rules_path,manifest_path,journal_path,recovery_root,verified_snapshot_path,review_path,database,*,bundle_path=None,assessment_evidence_path=None,apply_adapter=None,refresh_adapter=None,authorized=False,expected_plan_digest=None):
    snapshot=normalize_snapshot(read_json(snapshot_path))
    bundle_raw=Path(bundle_path).read_bytes() if bundle_path else None
    snapshot_raw=Path(snapshot_path).read_bytes()
    bundle=read_json(bundle_path) if bundle_path else None
    if authorized and bundle:
        require(bundle.get('refresh_request') is None,'Read-only refresh bundle cannot authorize a mutating run; create a new action-only export from the refreshed review')
    plan=_plan_from_bundle(snapshot,bundle,bundle_raw,snapshot_raw) if bundle else read_json(plan_path)
    manifest_candidate=Path(manifest_path)
    existing_manifest=None
    if manifest_candidate.is_file():
        existing_manifest=validate_existing_manifest(manifest_candidate,snapshot,plan,rules_digest(rules_path),
          authorized_accounts=snapshot.get('account_scope') or [])
    validate_plan(snapshot,plan,trusted_started_at=(existing_manifest or {}).get('started_at'))
    plan_bytes=Path(plan_path).read_bytes() if plan_path else Path(bundle_path).read_bytes()
    actual_digest=__import__('hashlib').sha256(plan_bytes).hexdigest()
    if not authorized:return {'validated':True,'snapshot_id':snapshot['snapshot_id'],'plan_sha256':actual_digest,'actions':len(plan['actions']),'mail_changed':False}
    require(expected_plan_digest==actual_digest,'Exact plan SHA-256 required before applying')
    import config
    from apply_mail import configured_history_database
    configured_database=Path(configured_history_database()).resolve()
    require(Path(database).resolve()==configured_database,'Coordinator history database must be the configured private history database')
    selected_account=config.CONFIG.get('account')
    configured_scope=set(snapshot.get('account_scope') or [])
    require(selected_account and snapshot.get('account_scope')==[selected_account] and configured_scope=={selected_account} and all(r['account']==selected_account for r in snapshot['records']),'Snapshot must name exactly the single selected Mail account; no actions applied')
    resolved_timezone=config.resolve_snapshot_timezone(snapshot.get('timezone'))
    require(resolved_timezone==snapshot.get('timezone'),'Snapshot timezone differs from selected configuration; no actions applied')
    action_accounts={next(r['account'] for r in snapshot['records'] if r['item']==a['item']) for a in plan['actions']}
    require(action_accounts <= {selected_account},'Plan action exceeds the selected Mail account; no actions applied')
    if bundle:
        prior_receipt=get_export_receipt(database,actual_digest,operation='apply')
        if prior_receipt:
            outcome=prior_receipt['outcome']
            return {'already_processed':True,'export_sha256':actual_digest,'received_at':prior_receipt['received_at'],**outcome}
    if apply_adapter is None:
        require(verified_snapshot_path is None,'A live Mail action cannot trust an externally supplied post-action snapshot')
        from refresh_mail import ACCOUNT, PREFIX, DATABASE
        require(ACCOUNT==selected_account and PREFIX and Path(DATABASE).is_file(),'Selected Mail inventory is not available for safe apply-and-refresh; no actions applied')
    baseline=get_registered_snapshot(database,snapshot['run_id'])
    checkpoint=Path(manifest_path).with_suffix('.verified-snapshot.json')
    if baseline and baseline['snapshot_id']!=snapshot['snapshot_id'] and checkpoint.is_file():
        prior_checkpoint=normalize_snapshot(read_json(checkpoint))
        prior_events=_read_journal(journal_path)
        prior_state=_attempt_state(prior_events,snapshot['snapshot_id'])
        prior_verified={e.get('item') for e in prior_state['verified']}
        if (prior_checkpoint['run_id']==snapshot['run_id'] and prior_verified=={a['item'] for a in plan['actions']}
            and not prior_state['unresolved'] and not prior_state['not_started'] and not prior_state['ambiguous']):
            baseline=None  # This immutable checkpoint belongs to the current run's own completed pipeline.
    if baseline:
        require(baseline['snapshot_id']==snapshot['snapshot_id'],'Saved review bundle does not match the immutable registered baseline')
        app_digest=__import__('hashlib').sha256((actual_digest+snapshot['snapshot_id']).encode()).hexdigest()[:20]
        app_run_id=f"{snapshot['run_id'][:70]}.apply-{app_digest}"
        original_review=Path(review_path)
        require(original_review.parent.name==snapshot['run_id'] and original_review.name=='review.html','Registered baseline review path must stay in runs/<baseline-run>/review.html')
        output_review=original_review.parent.parent/app_run_id/'review.html'
    else:
        app_run_id=snapshot['run_id'];output_review=Path(review_path)
    output_review.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    rules_hash=rules_digest(rules_path);manifest=create_or_validate_manifest(manifest_path,snapshot,plan,rules_hash,authorized_accounts=sorted(configured_scope))
    validate_plan(snapshot,plan,trusted_started_at=manifest['started_at'])
    # apply_mail owns account locks and rechecks the journal after acquiring them.
    apply_fn=apply_adapter or apply
    journal_events=_read_journal(journal_path)
    attempt_state=_attempt_state(journal_events,snapshot['snapshot_id'])
    if journal_events:
        completed={e['item'] for e in attempt_state['verified']}
        require(not attempt_state['unresolved'] and not attempt_state['not_started'] and not attempt_state['ambiguous'],
            'Existing journal has unresolved attempts; reconcile and prepare a remaining plan before continuing')
        require(completed <= {a['item'] for a in plan['actions']},'Existing journal contains outcomes outside this authorization')
        missing={a['item'] for a in plan['actions']}-completed
        conflict_items={e.get('item') for e in attempt_state['conflicts']}
        require(missing <= conflict_items,'Existing journal is incomplete; reconcile and prepare a remaining plan before continuing')
        outcomes=[]
    elif plan['actions']:
        outcomes=apply_fn(snapshot,plan,Path(journal_path),Path(recovery_root),manifest_path=manifest_path,rules_path=rules_path,folder_map=config.CONFIG['folder_map'],history_database=database)
    else:outcomes=[]
    journal_events=_read_journal(journal_path);attempt_state=_attempt_state(journal_events,snapshot['snapshot_id'])
    if attempt_state['unresolved'] or attempt_state['ambiguous']:
        confirmed_change=any(event.get('status') in ('verified-moved','verified-completed') for event in attempt_state['verified'])
        mail_changed=True if confirmed_change else None
        append_event(Path(manifest_path).with_suffix('.stages.jsonl'),{'stage':'partial-actions-awaiting-reconciliation','snapshot_id':snapshot['snapshot_id'],
            'verified_items':sorted({event['item'] for event in attempt_state['verified']}),'unresolved_items':sorted({event['item'] for event in attempt_state['unresolved']}),
            'ambiguous_items':sorted({event.get('item') for event in attempt_state['ambiguous']} )})
        return {'status':'partial','snapshot_id':snapshot['snapshot_id'],'manifest':str(manifest_path),'journal':str(journal_path),
            'verified_items':sorted({event['item'] for event in attempt_state['verified']}),
            'unresolved_items':sorted({event['item'] for event in attempt_state['unresolved']}),
            'ambiguous_items':sorted({event.get('item') for event in attempt_state['ambiguous']}),
            'conflicts':[{'item':event.get('item'),'status':event.get('status'),'error':event.get('error')} for event in attempt_state['conflicts']],
            'refresh_published':False,'history_registered':False,'mail_changed':mail_changed,
            'mail_change_status':'confirmed-changed' if confirmed_change else 'unknown-awaiting-reconciliation'}
    completed_by_attempt={event.get('attempt_id'):event for event in attempt_state['verified'] if event.get('attempt_id')}
    intent_by_attempt={event.get('attempt_id'):event for event in attempt_state['intents'].values()}
    registered=[]
    for event in attempt_state['verified']:
        if event.get('status')=='verified-completed':
            intent=intent_by_attempt.get(event.get('attempt_id'),{})
            receipt=next((e for e in journal_events if e.get('status')=='move-receipt' and e.get('attempt_id')==event.get('attempt_id')), {})
            event={**intent,**receipt,**event,'status':'verified-completed','receipt_new_id':receipt.get('new_id'),
                'at':event.get('at') or receipt.get('completed_at') or intent.get('at')}
        if event.get('status') in ('verified-moved','verified-retained','verified-completed') and event.get('snapshot_id')==snapshot['snapshot_id']:
            registered.append(event)
    if checkpoint.exists():
        verified=normalize_snapshot(read_json(checkpoint))
    elif verified_snapshot_path:
        verified=normalize_snapshot(read_json(verified_snapshot_path))
    else:
        verified=normalize_snapshot(_refresh_after_apply(snapshot,journal_path,database,refresh_adapter))
    if baseline:
        verified['run_id']=app_run_id
        verified=normalize_snapshot(verified)
    if not checkpoint.exists():
        private_write(checkpoint,json.dumps(verified,indent=2)+'\n')
        append_event(Path(manifest_path).with_suffix('.stages.jsonl'),{'stage':'post-action-refresh-checkpointed','snapshot_id':verified['snapshot_id'],'refreshed_at':verified.get('refreshed_at')})
    require(verified['run_id']==app_run_id,'Verified post-action snapshot belongs to another run')
    require(verified.get('account_scope')==[selected_account],'Verified refresh scope differs from the configured selected account')
    lineage_file=Path(manifest_path).with_name('lineage.json')
    if lineage_file.is_file():
        lineage_data=json.loads(lineage_file.read_text())
        verified_rows={row['item']:row for row in verified['records']}
        registered_items={event['item'] for event in registered}
        for prior in lineage_data.get('completed_actions',[]):
            if prior['item'] in registered_items:continue
            row=verified_rows.get(prior['item'])
            require(row is not None and (row['account'],row['message_id'],row['observed_mailbox'])==(prior['account'],prior['message_id'],prior['destination']),
                'Completed lineage does not match the verified continuation snapshot')
            registered.append({**prior,'status':'verified-completed','new_id':row['current_id'],'receipt_new_id':prior.get('new_id'),
                'lineage_source_attempt_id':prior.get('attempt_id'),'attempt_id':prior.get('attempt_id')})
    register(database,verified,output_review,registered)
    _apply_bundle_annotations(database,snapshot,bundle,registered,verified)
    append_event(Path(manifest_path).with_suffix('.stages.jsonl'),{'stage':'history-and-followups-persisted','snapshot_id':verified['snapshot_id'],'actions':len(registered)})
    history_window=export_history(database)
    from assessments import readiness
    current_evidence=read_json(assessment_evidence_path) if assessment_evidence_path else {}
    assessment_source=baseline['run_id'] if baseline else verified['run_id']
    assessment_snapshot={**verified,'run_id':assessment_source}
    assessment_readiness=readiness(database,assessment_snapshot,rules_hash,current_evidence)
    for run in history_window:
        if run['run_id']==verified['run_id']:run['assessment_readiness']=assessment_readiness
    html,_=render_html(verified,history=history_window)
    private_write(output_review,html)
    refresh_request_path=None
    if bundle and bundle['refresh_request'] is not None:
        refresh_request_path=output_review.with_suffix('.refresh-request.json')
        private_write(refresh_request_path,json.dumps(bundle['refresh_request'],indent=2)+'\n')
    lineage_path=None
    if baseline:
        lineage_path=output_review.with_name('lineage.json')
        private_write(lineage_path,json.dumps({'schema':1,'application_run_id':app_run_id,'baseline_run_id':baseline['run_id'],'baseline_snapshot_id':baseline['snapshot_id'],'bundle_sha256':actual_digest,'application_snapshot_id':verified['snapshot_id'],'rules_digest':rules_hash,'account_scope':sorted(configured_scope)},indent=2,sort_keys=True)+'\n')
    append_event(Path(manifest_path).with_suffix('.stages.jsonl'),{'stage':'verified-actions-and-review-rendered','snapshot_id':snapshot['snapshot_id'],'actions':len(registered)})
    result={'run_id':app_run_id,'baseline_run_id':baseline['run_id'] if baseline else None,'snapshot_id':snapshot['snapshot_id'],'verified_snapshot_id':verified['snapshot_id'],'manifest':str(manifest_path),'journal':str(journal_path),'review':str(output_review),'lineage':str(lineage_path) if lineage_path else None,'refresh_request':str(refresh_request_path) if refresh_request_path else None,'verified_actions':len(registered),'followups':len(bundle['tasks']) if bundle else 0,'pending_opt_out_reviews':len(bundle.get('opt_outs',[])) if bundle else 0,'comments':len(bundle['comments']) if bundle else 0,'assessment_readiness':{'reusable':sum(x['status']=='reusable' for x in assessment_readiness),'awaiting_assessment':sum(x['status']=='awaiting_assessment' for x in assessment_readiness)},'accounts':manifest['accounts']}
    action_by_item={event['item']:event for event in registered}
    conflict_by_item={event.get('item'):event for event in attempt_state['conflicts']}
    moved_items={action['item'] for action in plan['actions']}
    item_ids=set(moved_items)
    if bundle:item_ids.update(entry['item'] for key in ('opt_outs','tasks','comments') for entry in bundle.get(key,[]))
    result['item_outcomes']=[{'item':item,
        'action':action_by_item[item]['status'] if item in action_by_item else ('conflict-or-failed' if item in conflict_by_item else 'not-applied'),
        'error':conflict_by_item[item].get('error') if item in conflict_by_item else None,
        'annotations':'persisted' if bundle and any(entry['item']==item for key in ('opt_outs','tasks','comments') for entry in bundle.get(key,[])) else None}
        for item in sorted(item_ids)]
    if bundle:
        receipt_run=baseline['run_id'] if baseline else app_run_id
        acknowledge(database,receipt_run,bundle['exported_at'],actual_digest,result,operation='apply')
    return result


def inspect_action(intent):
    """Fresh, read-only exact-copy check for reconciliation; never issues a Mail mutation."""
    from apply_mail import api
    import config
    folder_name=getattr(config,'folder_name',lambda role,settings=None:role)
    source=folder_name(intent['old_mailbox']);destination=folder_name(intent['destination'])
    output=api('''set a to account (item 1 of argv)
set src to mailbox (item 2 of argv) of a
set dst to mailbox (item 3 of argv) of a
set wantedID to item 4 of argv as integer
set wantedMID to item 5 of argv
set sourcePresent to false
set sourceExact to false
set sourceJunk to false
set srcMatches to (every message of src whose id is wantedID)
if count of srcMatches is 1 then
 set sourcePresent to true
 set sourceExact to (message id of item 1 of srcMatches is wantedMID)
 set sourceJunk to junk mail status of item 1 of srcMatches
end if
set destinationCopies to every message of dst whose message id is wantedMID
set destinationText to ""
repeat with candidate in destinationCopies
 if destinationText is not "" then set destinationText to destinationText & linefeed
 set destinationText to destinationText & (id of candidate as text) & "|" & (message id of candidate as text) & "|" & (junk mail status of candidate as text)
end repeat
return (sourcePresent as text) & tab & (sourceExact as text) & tab & (sourceJunk as text) & tab & destinationText''',intent['account'],source,destination,intent['old_id'],intent['message_id'])
    parts=output.split('\t',3)
    require(len(parts)==4,'Malformed exact-copy reconciliation response')
    source_present,source_exact,source_junk,copy_text=parts
    copies=[]
    for line in copy_text.splitlines():
        values=line.split('|',2)
        require(len(values)==3 and values[0].isdigit() and values[1],'Malformed destination copy identity')
        copies.append({'numeric_id':int(values[0]),'message_id':values[1],'junk':values[2]=='true'})
    destination_ids=[copy['numeric_id'] for copy in copies]
    return {'destination_ids':destination_ids,'destination_copies':copies,'source_present':source_present=='true',
        'source_exact':source_exact=='true','source_junk':source_junk=='true','identity_matches':all(copy['message_id']==intent['message_id'] for copy in copies)}


def continue_run(journal_path,inspect_destination=inspect_action):
    """Reconcile unfinished actions. Returns exact classifications and never resumes moves."""
    return reconcile(journal_path,inspect_destination)


def prepare_resume(snapshot_path,plan_path,manifest_path,rules_path,journal_path,resume_root,inspect_destination=inspect_action):
    source=normalize_snapshot(read_json(snapshot_path))
    with account_locks(source.get('account_scope') or []):
        return _prepare_resume_locked(snapshot_path,plan_path,manifest_path,rules_path,journal_path,resume_root,inspect_destination)


def _prepare_resume_locked(snapshot_path,plan_path,manifest_path,rules_path,journal_path,resume_root,inspect_destination):
    """Create a new lineage-bound plan for only verified-not-started and never-attempted actions."""
    source=normalize_snapshot(read_json(snapshot_path));original_plan=read_json(plan_path)
    manifest_file=Path(manifest_path);require(manifest_file.is_file(),'Original authorization manifest is required')
    rules_hash=rules_digest(rules_path)
    # The persisted clock is usable only after its entire authorization envelope
    # has been verified against the exact source snapshot, plan, rules and scope.
    original_manifest=validate_existing_manifest(manifest_file,source,original_plan,rules_hash,
      authorized_accounts=source.get('account_scope') or [])
    validate_plan(source,original_plan,trusted_started_at=original_manifest['started_at'])
    expected=create_or_validate_manifest(manifest_file,source,original_plan,rules_hash,
      authorized_accounts=source.get('account_scope') or [])
    require(original_manifest==expected,'Original manifest does not match the frozen snapshot, plan and rules')
    classifications=_reconcile_locked(journal_path,inspect_destination) if Path(journal_path).exists() else []
    events=[e for e in _read_journal(journal_path) if e.get('snapshot_id')==source['snapshot_id']]
    by_item={r['item']:r for r in source['records']};allowed={a['item']:a for a in original_plan['actions']}
    terminal={}
    # A pre-intent conflict proves no mutation was launched; recheck exact source
    # identity under the account lock before authorizing it in the continuation.
    for conflict in [e for e in events if e.get('status')=='conflict-or-failed' and not e.get('attempt_id')]:
        item=conflict.get('item')
        if item not in allowed:continue
        probe={k:conflict[k] for k in ('item','account','message_id','old_id','old_mailbox','destination','snapshot_id') if k in conflict}
        probe['pre_destination_ids']=[]
        state=inspect_destination(probe)
        if state.get('source_present') is True and state.get('source_exact') is True and state.get('identity_matches') is True:
            classified={**probe,'pre_destination_ids':state.get('destination_ids',[]),'status':'verified-not-started','reason':conflict.get('reason','Retry after pre-intent conflict was verified safe'),'at':conflict.get('at') or dt.datetime.now(dt.timezone.utc).isoformat()}
            append_event(journal_path,classified);classifications.append(classified)
        else:
            classified={**probe,'status':'ambiguous','reason':'pre-intent conflict source identity could not be verified'}
            append_event(journal_path,classified);classifications.append(classified)
    events=[e for e in _read_journal(journal_path) if e.get('snapshot_id')==source['snapshot_id']]
    attempt_state=_attempt_state(events,source['snapshot_id'])
    if attempt_state['unresolved']:
        return {'status':'blocked','reason':'unmatched_intent','classifications':classifications,'remaining_plan':None}
    if attempt_state['ambiguous']:
        return {'status':'blocked','reason':'ambiguous_action_outcome','classifications':classifications,'remaining_plan':None}
    for event in attempt_state['verified']:
        item=event.get('item')
        if item not in allowed:continue
        if event.get('status') in ('verified-moved','verified-retained','verified-completed'):
            row=by_item[item]
            require(event.get('account')==row['account'] and event.get('message_id')==row['message_id'],'Journal outcome identity differs from authorized item')
            if event['status'] in ('verified-moved','verified-completed'):
                row['current_id']=event['new_id'];row['observed_mailbox']=event['destination']
            terminal[item]=event['status']
    remaining=[]
    for action in original_plan['actions']:
        if terminal.get(action['item']) in ('verified-moved','verified-retained','verified-completed'):continue
        remaining.append(action)
    require(all(a['item'] in by_item for a in remaining),'Resume includes unknown item')
    resume_snapshot={**source,'scope':source['scope']+' Continuation candidate; placements updated only from exact journal reconciliation.','records':list(by_item.values())}
    resume_snapshot.pop('refreshed_at',None);resume_snapshot.pop('refresh_evidence',None)
    resume_snapshot=normalize_snapshot(resume_snapshot)
    resume_plan={'snapshot_id':resume_snapshot['snapshot_id'],'started_at':original_plan['started_at'],
      'authorization':original_plan['authorization']+' Continuation of original run '+source['snapshot_id']+'; actions restricted to frozen authorization.',
      'actions':[dict(a) for a in remaining]}
    if 'user_review_evidence' in original_plan:resume_plan['user_review_evidence']=original_plan['user_review_evidence']
    validate_plan(resume_snapshot,resume_plan,trusted_started_at=original_manifest['started_at'])
    root=Path(resume_root);root.mkdir(parents=True,exist_ok=True,mode=0o700)
    index=1
    while (root/f'resume-{index}').exists():index+=1
    target=root/f'resume-{index}';target.mkdir(mode=0o700)
    resume_snapshot['run_id']=f"{source['run_id']}.r{index}"
    resume_snapshot=normalize_snapshot(resume_snapshot)
    resume_plan['snapshot_id']=resume_snapshot['snapshot_id']
    validate_plan(resume_snapshot,resume_plan,trusted_started_at=original_manifest['started_at'])
    snapshot_out=target/'snapshot.json';plan_out=target/'plan.json';manifest_out=target/'manifest.json'
    private_write(snapshot_out,json.dumps(resume_snapshot,indent=2)+'\n');private_write(plan_out,json.dumps(resume_plan,indent=2)+'\n')
    parent_manifest_sha256=__import__('hashlib').sha256(manifest_file.read_bytes()).hexdigest()
    resume_manifest=create_or_validate_manifest(manifest_out,resume_snapshot,resume_plan,rules_hash,
      authorized_accounts=original_manifest['accounts'],inherited_manifest=original_manifest,
      parent_manifest_sha256=parent_manifest_sha256)
    completed_actions=[]
    intent_by_attempt={e.get('attempt_id'):e for e in events if e.get('status')=='intent' and e.get('attempt_id')}
    receipts_by_attempt={e.get('attempt_id'):e for e in events if e.get('status')=='move-receipt' and e.get('attempt_id')}
    for outcome in attempt_state['verified']:
        if outcome.get('status')=='verified-not-started':continue
        attempt=outcome.get('attempt_id')
        intent=intent_by_attempt.get(attempt,{})
        receipt=receipts_by_attempt.get(attempt,{})
        merged={**intent,**receipt,**outcome}
        if merged.get('item') in allowed:
            completed_actions.append({key:merged.get(key) for key in ('item','account','message_id','old_id','old_mailbox','destination','new_id','reason','status','at','completed_at','attempt_id') if merged.get(key) is not None})
    for outcome in [e for e in events if e.get('status')=='verified-retained' and e.get('item') in allowed]:
        if not any(a['item']==outcome['item'] for a in completed_actions):completed_actions.append({key:outcome[key] for key in ('item','account','message_id','old_id','old_mailbox','destination','new_id','reason','status','at') if key in outcome})
    lineage={'schema':1,'source_manifest_sha256':__import__('hashlib').sha256(manifest_file.read_bytes()).hexdigest(),
      'source_run_id':source['run_id'],'source_snapshot_id':source['snapshot_id'],'source_plan_digest':original_manifest['plan_digest'],'resume_run_id':resume_snapshot['run_id'],'resume_snapshot_id':resume_snapshot['snapshot_id'],
      'completed_items':sorted(terminal),'completed_actions':completed_actions,'remaining_items':[a['item'] for a in remaining],'classifications':classifications,
      'started_at':original_manifest['started_at'],'cutoff_at':original_manifest['cutoff_at'],'rules_digest':rules_hash}
    lineage_out=target/'lineage.json';private_write(lineage_out,json.dumps(lineage,indent=2,sort_keys=True)+'\n')
    return {'status':'ready' if remaining else 'complete','snapshot':str(snapshot_out),'plan':str(plan_out),'manifest':str(manifest_out),'lineage':str(lineage_out),
      'plan_sha256':__import__('hashlib').sha256(plan_out.read_bytes()).hexdigest(),'remaining_actions':len(remaining),'accounts':resume_manifest['accounts'],'classifications':classifications}


def plan_undo(bundle,snapshot,raw_bundle=None,raw_snapshot=None):
    """Turn exact-item undo requests into a plan only after snapshot identity validation."""
    snapshot=normalize_snapshot(snapshot)
    return _plan_from_bundle(snapshot,bundle,raw_bundle,raw_snapshot)


def _selection_key(entry):
    return (entry['item'],entry['account'],entry['message_id'],entry.get('snapshot_mailbox'),entry['snapshot_numeric_id'])


def _selected_review_edits(bundle):
    """Union typed selections independently of the legacy changes envelope."""
    selections={}
    for kind in ('moves','opt_outs','tasks','comments'):
        for entry in bundle.get(kind,[]):
            key=_selection_key(entry)
            record=selections.setdefault(key,{'item':entry['item'],'account':entry['account'],'message_id':entry['message_id'],
                'snapshot_mailbox':entry.get('snapshot_mailbox'),'snapshot_numeric_id':entry['snapshot_numeric_id'],'labels':[]})
            if kind=='moves':record['labels'].append('requested move: '+entry['destination'])
            elif kind=='opt_outs':record['labels'].append('opt-out review requested')
            elif kind=='tasks':record['labels'].append('task: '+entry['instruction'])
            else:record['labels'].append('comment: '+entry['comment'])
    for change in (bundle.get('refresh_request') or {}).get('pending_review',{}).get('changes',[]):
        key=_selection_key(change)
        selections.setdefault(key,{'item':change['item'],'account':change['account'],'message_id':change['message_id'],
            'snapshot_mailbox':change.get('snapshot_mailbox'),'snapshot_numeric_id':change['snapshot_numeric_id'],'labels':[]})
    return list(selections.values())


def _pending_review_html(bundle,outcomes,sidecar):
    """Add a visible, non-actionable record of edits retained from the old export."""
    outcome_by_key={_selection_key(entry):entry for entry in outcomes}
    entries=[]
    for selection in _selected_review_edits(bundle):
        key=_selection_key(selection);item=selection['item'];labels=selection['labels']
        outcome=outcome_by_key.get(key,{})
        status=outcome.get('status','conflict-unapplied')
        detail=outcome.get('reason','')
        entries.append('<li><strong>'+html.escape(item)+'</strong> — '+html.escape(status)+
            ((': '+html.escape(detail)) if detail else '')+'<br>'+html.escape('; '.join(labels))+'</li>')
    if not entries:return ''
    link=html.escape(Path(sidecar).as_uri(),quote=True)
    return ('<section class="pending-review-preserved" aria-labelledby="pending-review-preserved-title">'
        '<h2 id="pending-review-preserved-title">Pending edits preserved from the previous review (not applied)</h2>'
        '<p>These selections remain bound to their original snapshot and numeric copy IDs. Use the current review controls to reselect edits, or ask the agent to reconcile them against the current exact copy IDs and prepare a separate action-only export after you explicitly authorize application.</p>'
        '<ul>'+''.join(entries)+'</ul><p>Original export: <a href="'+link+'">saved pending review bundle</a>.</p></section>')


def _paths_alias(left,right):
    left=Path(left).expanduser();right=Path(right).expanduser()
    if left.resolve(strict=False)==right.resolve(strict=False):return True
    try:return left.exists() and right.exists() and os.path.samefile(left,right)
    except OSError:return False


def _preflight_refresh_paths(inputs,outputs):
    input_paths=[Path(path).expanduser().resolve(strict=False) for path in inputs]
    output_paths=[Path(path).expanduser().resolve(strict=False) for path in outputs]
    for index,left in enumerate(input_paths):
        for right in input_paths[index+1:]:
            require(not _paths_alias(left,right),f'Refresh input paths alias the same file: {left} and {right}')
    for output in output_paths:
        for source in input_paths:
            require(not _paths_alias(output,source),f'Refresh output path collides with an input or database side file: {output}')
    for index,left in enumerate(output_paths):
        for right in output_paths[index+1:]:
            require(not _paths_alias(left,right),f'Refresh output paths collide or alias each other: {left} and {right}')


def _require_new_refresh_outputs(outputs):
    for output in outputs:
        path=Path(output)
        require(not path.exists() and not path.is_symlink(),f'Refresh refuses to overwrite an existing artifact: {path}')


def refresh_review(snapshot_path,bundle_path,output_path,database,*,refresh_adapter=None):
    import config
    selected=config.CONFIG.get('account')
    require(selected,'Read-only refresh requires a configured selected account')
    with account_transaction([selected]):
        return _refresh_review_impl(snapshot_path,bundle_path,output_path,database,refresh_adapter=refresh_adapter)


def _refresh_review_impl(snapshot_path,bundle_path,output_path,database,*,refresh_adapter=None):
    """Refresh inventory from a review export without applying any pending edits."""
    source=normalize_snapshot(read_json(snapshot_path));bundle_raw=Path(bundle_path).read_bytes();bundle=read_json(bundle_path)
    validate_review_bundle(source,bundle)
    bundle_digest=__import__('hashlib').sha256(bundle_raw).hexdigest()
    import config
    from apply_mail import configured_history_database
    database=Path(database).expanduser().resolve(strict=False)
    require(database==Path(configured_history_database()).expanduser().resolve(strict=False),'Refresh history database must be the configured private history database')
    target=Path(output_path).expanduser().resolve(strict=False)
    sidecar=target.with_suffix('.pending-review.json')
    refresh_run_id='refresh-'+uuid.uuid4().hex
    review=Path(config.CONFIG['state_root']).expanduser().resolve(strict=False)/'runs'/refresh_run_id/'review.html'
    lineage=review.with_name('lineage.json')
    db_sidefiles=[Path(str(database)+suffix) for suffix in ('-wal','-shm','-journal')]
    outputs=[target,sidecar,review,lineage]
    _preflight_refresh_paths([snapshot_path,bundle_path,database,*db_sidefiles],outputs)
    prior_receipt=get_export_receipt(database,bundle_digest,operation='refresh')
    if prior_receipt:return {'already_processed':True,'export_sha256':bundle_digest,'received_at':prior_receipt['received_at'],**prior_receipt['outcome']}
    _require_new_refresh_outputs(outputs)
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    review.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    baseline=get_registered_snapshot(database,source['run_id'])
    require(baseline is not None and baseline['snapshot_id']==source['snapshot_id'],'Read-only refresh requires this exact registered source snapshot')
    request=bundle.get('refresh_request')
    require(isinstance(request,dict),'Review export does not contain a typed refresh request')
    require(request.get('mode')=='read-only' and request.get('snapshot_id')==source['snapshot_id'],'Refresh request is not bound to this read-only source snapshot')
    selected=config.CONFIG.get('account')
    require(selected and source.get('account_scope')==[selected] and request.get('account_scope')==[selected], 'Refresh request scope differs from configured selected account')
    require(config.resolve_snapshot_timezone(source.get('timezone'))==source.get('timezone'),'Snapshot timezone differs from selected configuration')
    if refresh_adapter:
        refreshed=refresh_adapter(source)
    else:
        from refresh_mail import refresh_snapshot, DATABASE, ACCOUNT, PREFIX, resolve_local_files
        from history import allocate_item_id, reserve_snapshot_items
        require(ACCOUNT==selected and PREFIX and Path(DATABASE).is_file(),'Selected Mail inventory is not available for read-only refresh')
        history_db=Path(database);reserve_snapshot_items(history_db,source)
        wanted={r['current_id'] for r in source['records'] if r['observed_mailbox']=='INBOX'}
        local=resolve_local_files(source,DATABASE,PREFIX,wanted)
        refreshed=refresh_snapshot(source,DATABASE,account=ACCOUNT,prefix=PREFIX,verify_mail=True,local_files=local,include_prior=False,
            item_allocator=lambda identity:allocate_item_id(history_db,source['run_id'],identity))
    refreshed=normalize_snapshot(refreshed)
    require(refreshed.get('account_scope')==[selected],'Read-only refresh returned an unexpected account scope')
    by_identity={(r['account'],r['message_id'],r['current_id'],r['observed_mailbox']):r for r in refreshed['records']}
    outcomes=[]
    for selection in _selected_review_edits(bundle):
        key=(selection['account'],selection['message_id'],selection['snapshot_numeric_id'],selection['snapshot_mailbox'])
        selected_exact=key in by_identity
        same_message=[r for r in refreshed['records'] if r['account']==selection['account'] and r['message_id']==selection['message_id']]
        outcomes.append({'item':selection['item'],'account':selection['account'],'message_id':selection['message_id'],
            'snapshot_mailbox':selection['snapshot_mailbox'],'snapshot_numeric_id':selection['snapshot_numeric_id'],
            'status':'preserved-unapplied' if selected_exact else 'conflict-unapplied',
            'reason':None if selected_exact else ('Exact saved numeric copy or mailbox changed; a matching Message-ID exists under another copy identity' if same_message else 'Exact saved copy is absent; no current matching Message-ID was found')})
    refreshed['run_id']=refresh_run_id
    refreshed=normalize_snapshot(refreshed)
    private_write(target,json.dumps(refreshed,indent=2)+'\n')
    private_write(sidecar,bundle_raw.decode('utf-8'))
    register(database,refreshed,review)
    html_text,_=render_html(refreshed,history=export_history(database))
    section=_pending_review_html(bundle,outcomes,sidecar)
    if section:
        require('<body>' in html_text,'Review renderer did not produce an HTML body')
        html_text=html_text.replace('<body>','<body>'+section,1)
    private_write(review,html_text)
    private_write(lineage,json.dumps({'schema':1,'kind':'read-only-refresh','source_run_id':source['run_id'],
        'source_snapshot_id':source['snapshot_id'],'refreshed_run_id':refreshed['run_id'],'refreshed_snapshot_id':refreshed['snapshot_id'],
        'bundle_sha256':bundle_digest,'pending_bundle':str(sidecar),'mail_changed':False},indent=2,sort_keys=True)+'\n')
    receipt={'status':'read-only-refresh-complete','snapshot':str(target),'pending_review_bundle':str(sidecar),
        'bundle_sha256':bundle_digest,'source_snapshot_id':source['snapshot_id'],
        'refreshed_snapshot_id':refreshed['snapshot_id'],'run_id':refreshed['run_id'],'review':str(review),'lineage':str(lineage),
        'item_outcomes':outcomes,'mail_changed':False}
    acknowledge(database,source['run_id'],bundle['exported_at'],bundle_digest,receipt,operation='refresh')
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    run=sub.add_parser('run',help='execute one frozen snapshot plan and publish its private review')
    run.add_argument('--snapshot',required=True);choice=run.add_mutually_exclusive_group(required=True);choice.add_argument('--plan');choice.add_argument('--bundle')
    for flag in ('rules','manifest','journal','recovery','review','database'):run.add_argument('--'+flag,required=True)
    run.add_argument('--verified-snapshot',help='Optional already verified post-action snapshot for offline orchestration')
    run.add_argument('--assessment-evidence',help='JSON map of current exact-copy content/thread/correction fingerprints; missing evidence remains awaiting assessment')
    run.add_argument('--apply',action='store_true',help='Authorize the validated frozen plan to run through Mail')
    run.add_argument('--sha256',help='Exact plan SHA-256 displayed by the read-only validation run')
    cont=sub.add_parser('continue',help='classify interrupted intents; never replays them');cont.add_argument('--journal',required=True)
    cont.add_argument('--resume',action='store_true',help='prepare a lineage-bound remaining plan after exact reconciliation')
    for flag in ('snapshot','plan','manifest','rules','resume-dir'):cont.add_argument('--'+flag)
    undo=sub.add_parser('undo-plan',help='validate a saved exact-item bundle and emit an inert plan');undo.add_argument('--bundle',required=True);undo.add_argument('--snapshot',required=True);undo.add_argument('--output',required=True)
    refresh=sub.add_parser('refresh-review',help='strictly read-only refresh; preserves typed edits in a bound sidecar');refresh.add_argument('--snapshot',required=True);refresh.add_argument('--bundle',required=True);refresh.add_argument('--output',required=True);refresh.add_argument('--database',required=True)
    args=p.parse_args()
    if args.command=='run':
        result=run_pipeline(args.snapshot,args.plan,args.rules,args.manifest,args.journal,args.recovery,args.verified_snapshot,args.review,args.database,
          bundle_path=args.bundle,assessment_evidence_path=args.assessment_evidence,authorized=args.apply,expected_plan_digest=args.sha256)
        print(json.dumps(result,indent=2))
    elif args.command=='continue':
        if args.resume:
            require(all((args.snapshot,args.plan,args.manifest,args.rules,args.resume_dir)),'--resume requires --snapshot, --plan, --manifest, --rules and --resume-dir')
            result=prepare_resume(args.snapshot,args.plan,args.manifest,args.rules,args.journal,args.resume_dir)
            print(json.dumps(result,indent=2))
        else:print(json.dumps(continue_run(args.journal),indent=2))
    elif args.command=='undo-plan':
        plan=plan_undo(read_json(args.bundle),read_json(args.snapshot),Path(args.bundle).read_bytes(),Path(args.snapshot).read_bytes());private_write(args.output,json.dumps(plan,indent=2)+'\n');print('Validated inert undo plan written; Mail unchanged.')
    else:
        print(json.dumps(refresh_review(args.snapshot,args.bundle,args.output,args.database),indent=2))

if __name__=='__main__':
    os.umask(0o077);main()
