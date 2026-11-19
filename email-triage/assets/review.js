'use strict';
(() => {
  const data = JSON.parse(document.getElementById('review-data').textContent);
  const base = new Map(data.records.map(r => [r.item, Object.freeze(r)]));
  const edits = new Map(data.records.map(r => [r.item, {comment:'', task_instruction:'', requested_move:null, opt_out:false, assign_to_llm:false, assignment_touched:false}]));
  const dirty = new Set(), assignedItems = new Set(), rowCache = new Map();
  const currentHistory=data.history.find(run=>run.run_id===data.run_id);
  const receiptBackedCompleted=action=>action?.status==='verified-completed'&&typeof action.attempt_id==='string'&&action.attempt_id.length>0&&Number.isInteger(action.new_id)&&Number.isInteger(action.receipt_new_id)&&action.receipt_new_id===action.new_id;
  const verifiedMove=action=>action?.status==='verified-moved'||receiptBackedCompleted(action);
  const verifiedRetained=action=>action?.status==='verified-retained';
  const recordKey=r=>`${r.item}\u0000${r.account}\u0000${r.message_id}\u0000${r.current_id}`;
  const taskIndex=new Map(), assessmentIndex=new Map(), readinessIndex=new Map();
  for(const r of data.records)if(Array.isArray(r.tasks))taskIndex.set(recordKey(r),r.tasks.slice());
  for(const [rows,keyName] of [[currentHistory?.tasks||[], 'tasks'],[currentHistory?.assessments||[],'assessments'],[currentHistory?.assessment_readiness||[],'readiness']]){
    const index=keyName==='tasks'?taskIndex:keyName==='assessments'?assessmentIndex:readinessIndex;
    for(const entry of rows){const key=recordKey(entry),list=index.get(key)||[];list.push(entry);index.set(key,list);}
  }
  const $ = id => document.getElementById(id);
  const rows = $('rows');
  let lastFullSave = '';
  let sortKey='received', sortDirection=-1;
  function instructionText(value){let start=0,end=value.length;while(start<end && data.instruction_whitespace.includes(value[start]))start++;while(end>start && data.instruction_whitespace.includes(value[end-1]))end--;return value.slice(start,end);}
  const changed = item => dirty.has(item);
  function changes() {
    return data.records.filter(r => changed(r.item)).map(r => ({item:r.item,account:r.account,message_id:r.message_id,snapshot_mailbox:r.observed_mailbox,snapshot_numeric_id:r.current_id,original_gist:r.gist,gist:edits.get(r.item).comment || r.gist,requested_move:edits.get(r.item).requested_move,opt_out:edits.get(r.item).opt_out,assign_to_llm:edits.get(r.item).assign_to_llm}));
  }
  function stateForSignature(includeDrafts) {
    const result=[];
    for(const r of data.records){
      if(!changed(r.item))continue;
      const s=edits.get(r.item),hasComment=!!s.comment.trim(),hasTask=s.assign_to_llm&&!!instructionText(s.task_instruction);
      const hasExportable=hasComment||hasTask||!!s.requested_move||s.opt_out;
      const hasDraft=!!((s.comment&&!hasComment)||(s.task_instruction&&!hasTask));
      if(!hasExportable&&!(includeDrafts&&hasDraft))continue;
      const state={item:r.item,comment:hasComment?s.comment:'',task_instruction:hasTask?s.task_instruction:'',
        requested_move:s.requested_move,opt_out:s.opt_out,assign_to_llm:hasTask};
      state.draft_comment=includeDrafts&&s.comment&&!hasComment?s.comment:'';
      state.draft_task_instruction=includeDrafts&&s.task_instruction&&!hasTask?s.task_instruction:'';
      result.push(state);
    }
    return result;
  }
  const pendingSignature=()=>JSON.stringify(stateForSignature(true));
  const resumableSignature=()=>JSON.stringify(stateForSignature(false));
  function unexportedDrafts(){return data.records.filter(r=>{const s=edits.get(r.item);return (s.comment&&!s.comment.trim())||(s.task_instruction&&!(s.assign_to_llm&&instructionText(s.task_instruction)));});}
  function exportableCount(){return data.records.filter(r=>{const s=edits.get(r.item);return !!s.requested_move||s.opt_out||!!s.comment.trim()||(s.assign_to_llm&&!!instructionText(s.task_instruction));}).length;}
  function markDirty(item){const s=edits.get(item);if(s.comment||s.task_instruction||s.requested_move||s.opt_out||s.assign_to_llm)dirty.add(item);else dirty.delete(item);if(s.assign_to_llm)assignedItems.add(item);else assignedItems.delete(item);}
  function exactIdentity(r){return {item:r.item,account:r.account,message_id:r.message_id,snapshot_mailbox:r.observed_mailbox,snapshot_numeric_id:r.current_id};}
  function reviewBundle(){
    const timestamp=new Date().toISOString();
    return {version:1,kind:'email-triage-review-bundle',run_id:data.run_id,snapshot_id:data.snapshot_id,exported_at:timestamp,
      moves:data.records.filter(r=>edits.get(r.item).requested_move).map(r=>({...exactIdentity(r),destination:edits.get(r.item).requested_move})),
      opt_outs:data.records.filter(r=>edits.get(r.item).opt_out).map(r=>exactIdentity(r)),
      tasks:data.records.filter(r=>edits.get(r.item).assign_to_llm).map(r=>({...exactIdentity(r),instruction:edits.get(r.item).task_instruction})),
      comments:data.records.filter(r=>edits.get(r.item).comment.trim()).map(r=>({...exactIdentity(r),original_summary:r.gist,comment:edits.get(r.item).comment})),refresh_request:null};
  }
  function maskCommonPatterns(value){return String(value).replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi,'[email]').replace(/https?:\/\/[^\s]+/gi,'[link]').replace(/\/(?:Users|home)\/[^\s]+/g,'[local path]').replace(/\b\d{6,}\b/g,'[number]').replace(/\b[A-F0-9]{16,}\b/gi,'[identifier]');}
  function minimalReview(){return {version:1,kind:'email-triage-limited-review',created_at:new Date().toISOString(),privacy_notice:'LIMITED-DATA: pattern masking is partial, not anonymization. Subject, summary, comments and dates can still identify people or contain sensitive information. Inspect before sharing.',records:data.records.map((r,index)=>({number:index+1,received:data.received_dates[r.item],subject:maskCommonPatterns(r.subject),observed_placement:r.disposition,placement_status:data.placement_labels[r.item],summary:maskCommonPatterns(r.gist),comment:edits.get(r.item).comment?maskCommonPatterns(edits.get(r.item).comment):null}))};}
  function updatePreview(){const mode=$('export-profile').value;$('included-preview').textContent=mode==='minimal-review'?'LIMITED-DATA preview: received date, subject, observed placement, immutable summary and comments. Omits account, Message-ID, numeric Mail ID, source path, task instruction and queued Mail actions. Common pattern masking is partial; sensitive or identifying free text may remain. This file cannot request an action. Inspect before sharing.':'Local handoff preview: exact snapshot identity and separately typed move, comment and task requests. Save assignments separately to include allowed local source references. No message body or attachment bytes are included.';}
  const taskStatuses=new Set(['ready','waiting_user_authentication','waiting_vendor','blocked_by_terms','completed','cancelled']);
  function tasksFor(record){return taskIndex.get(recordKey(record))||[];}
  function assessmentsFor(record){return assessmentIndex.get(recordKey(record))||[];}
  function readinessFor(record){return readinessIndex.get(recordKey(record))||[];}
  function needsMe(record){return tasksFor(record).some(task=>taskStatuses.has(task.status)&&task.status!=='completed'&&task.status!=='cancelled')||readinessFor(record).some(a=>a.status==='awaiting_assessment');}
  function status() {
    const n=dirty.size, resumable=exportableCount(), draftItems=unexportedDrafts(), invalidAssignment=[...assignedItems].some(item=>!instructionText(edits.get(item).task_instruction));
    $('export').disabled=resumable===0 || invalidAssignment;$('refresh').disabled=invalidAssignment || !data.account_scope?.length;$('refresh').title=!data.account_scope?.length?'Refresh unavailable: rebuild this older review with explicit account scope. See Help.':invalidAssignment?'Complete each selected task instruction or clear it before refreshing.':'Download a read-only refresh request'; $('clear').disabled=n===0;
    const assigned=assignedItems.size;$('assignments').disabled=assigned===0 || invalidAssignment;$('assignments').textContent=assigned?`Save ${assigned} assignment${assigned===1?'':'s'}`:'Save assignments';
    $('export').textContent=resumable ? `Export ${resumable} changed item${resumable===1?'':'s'}` : 'No exportable changes';
    const draftNote=draftItems.length?` Draft text in ${draftItems.map(r=>r.item).join(', ')} is not included in review exports; select it as a task or clear it before closing.`:'';
    $('status').textContent=invalidAssignment?'Complete each selected task instruction before saving, exporting or refreshing.':n ? `${resumable} exportable request${resumable===1?'':'s'} across ${n} changed row${n===1?'':'s'}. Mail has not changed.${draftNote}` : 'No review requests are queued. Placement verification is shown only where saved evidence supports it; it does not establish content assessment. This file makes no Mail changes.';
  }
  function node(tag, cls, text) {
    const n=document.createElement(tag); if(cls)n.className=cls; if(text!==undefined)n.textContent=text; return n;
  }
  function row(record) {
    const tr=node('tr');tr.setAttribute('role','row'); tr.dataset.item=record.item;
    const state=edits.get(record.item);
    tr.append(node('td','item',record.item),node('td','date',data.received_dates[record.item]),node('td','size',data.size_labels[record.item]),node('td','to',record.to_display),node('td','subject',record.subject));
    const disposition=node('td','disposition'); disposition.append(node('span',`badge ${record.disposition.toLowerCase()}`,record.disposition));
    const placement=data.placement_labels[record.item];const placementBadge=node('span',`badge placement-${placement.status}`,placement.label);placementBadge.title=placement.status==='verified'?'Saved Mail placement evidence matches this exact snapshot identity. This does not mean the message content was assessed.':'No saved placement evidence verifies this exact snapshot identity.';disposition.append(placementBadge);
    for(const taskRecord of tasksFor(record)){if(taskStatuses.has(taskRecord.status)){const badge=node('span',`badge task-${taskRecord.status}`,taskRecord.status.replaceAll('_',' '));badge.title=`Stored follow-up task status: ${taskRecord.status}`;disposition.append(badge);}}
    for(const assessment of assessmentsFor(record)){const state=assessment.invalidated_at?'Assessment invalidated':assessment.result?.status;if(typeof state==='string'&&state){const badge=node('span',`badge assessment`,state);badge.title=assessment.invalidated_at?`Stored assessment invalidated: ${assessment.invalidation_reason||'reason not recorded'}`:`Stored assessment status; assessed ${assessment.assessed_at}`;disposition.append(badge);}}
    for(const readiness of readinessFor(record)){if(['reusable','awaiting_assessment'].includes(readiness.status)){const badge=node('span',`badge readiness-${readiness.status}`,readiness.status.replaceAll('_',' '));badge.title=`Stored assessment cache status: ${readiness.status}${readiness.reason?` · ${readiness.reason}`:''}`;disposition.append(badge);}}
    tr.append(disposition);
    const gist=node('td','gist'), summary=node('p','summary-text',record.gist);summary.setAttribute('aria-label',`Immutable triage summary for ${record.item}`);const input=node('textarea'); input.value=state.comment;input.placeholder='Add a correction or comment';input.setAttribute('aria-label',`Correction or comment for ${record.item}`);gist.append(summary,input);tr.append(gist);
    const assigned=node('td','assignment'),includeLabel=node('label','assignment-toggle'),include=node('input');include.type='checkbox';include.checked=state.assign_to_llm;include.disabled=!record.email_context||!instructionText(state.task_instruction);include.setAttribute('aria-label',`Include task instruction for ${record.item} in assignment`);includeLabel.append(include,document.createTextNode(' Include as task'));const task=node('textarea');task.value=state.task_instruction;task.placeholder='Write a separate follow-up task';task.setAttribute('aria-label',`Task instruction for ${record.item}`);if(!record.email_context){task.disabled=true;task.title='Rebuild this review with local source context to enable assignments.';include.title=task.title;}assigned.append(includeLabel,task);tr.append(assigned);
    const actions=node('td','actions'), buttons=node('div','action-buttons'), description=node('p','row-state'); description.setAttribute('aria-live','polite');
    const opt=node('button','', 'Opt Out'), inbox=node('button','','Move to Inbox'), archive=node('button','','Archive'), reset=node('button','reset-row','Reset row');
    for(const b of [opt,inbox,archive,reset])b.type='button';
    inbox.disabled=record.disposition==='Inbox';archive.disabled=record.disposition==='Archived';
    opt.title='Queue an opt-out request for safety review in any folder. No sender is contacted.';
    opt.setAttribute('aria-label',`Opt Out ${record.item}`); inbox.setAttribute('aria-label',`Move to Inbox ${record.item}`); archive.setAttribute('aria-label',`Archive ${record.item}`); reset.setAttribute('aria-label',`Reset row ${record.item}`);
    function paint(updateStatus=true) {
      markDirty(record.item);
      opt.setAttribute('aria-pressed',String(state.opt_out)); inbox.setAttribute('aria-pressed',String(state.requested_move==='inbox')); archive.setAttribute('aria-pressed',String(state.requested_move==='archive'));
      const pending=[]; if(state.opt_out)pending.push('Opt Out'); if(state.requested_move)pending.push(state.requested_move==='inbox'?'Move to Inbox':'Archive'); if(state.comment)pending.push('comment / correction'); if(state.assign_to_llm)pending.push(instructionText(state.task_instruction)?'follow-up task':'task needs an instruction');else if(state.task_instruction)pending.push('unselected task draft');
      description.textContent=pending.length ? `Queued: ${pending.join(' + ')}` : 'No requested change';
      tr.classList.toggle('edited',changed(record.item)); reset.disabled=!changed(record.item); if(updateStatus)status();
    }
    input.addEventListener('input',()=>{const chars=Array.from(input.value);if(chars.length>4000)input.value=chars.slice(0,4000).join('');state.comment=input.value;paint();});
    task.addEventListener('input',()=>{const chars=Array.from(task.value);if(chars.length>4000)task.value=chars.slice(0,4000).join('');state.task_instruction=task.value;const hasInstruction=!!instructionText(state.task_instruction);if(!hasInstruction){state.assign_to_llm=false;state.assignment_touched=false;}else if(!state.assignment_touched)state.assign_to_llm=true;include.checked=state.assign_to_llm;include.disabled=!record.email_context||!hasInstruction;paint();});
    include.addEventListener('change',()=>{state.assign_to_llm=include.checked;state.assignment_touched=true;paint();});
    opt.addEventListener('click',()=>{state.opt_out=!state.opt_out;paint();});
    inbox.addEventListener('click',()=>{state.requested_move=state.requested_move==='inbox'?null:'inbox';paint();});
    archive.addEventListener('click',()=>{state.requested_move=state.requested_move==='archive'?null:'archive';paint();});
    reset.addEventListener('click',()=>{state.comment='';state.task_instruction='';state.requested_move=null;state.opt_out=false;state.assign_to_llm=false;state.assignment_touched=false;input.value='';task.value='';include.checked=false;include.disabled=true;paint();});
    buttons.append(opt,inbox,archive); actions.append(buttons,description,reset);tr.append(actions);
    const labels=['Item','Received','Size','To address','Subject','Observed placement and verification','Summary and correction','Task instruction','Requested changes'];
    const columns=['item','received','size_bytes','to_display','subject','disposition','gist','assign_to_llm','requests'];
    [...tr.children].forEach((cell,index)=>{cell.dataset.label=labels[index];cell.setAttribute('role','cell');cell.setAttribute('headers','review-col-'+columns[index]);const label=node('span','mobile-label',labels[index]);label.setAttribute('aria-hidden','true');cell.prepend(label);});
    paint(false);rowCache.set(record.item,tr);return tr;
  }
  function render() {
    const needle=$('search').value.toLocaleLowerCase().trim(), filter=$('filter').value;
    const list=data.records.filter(r => (filter==='all'||filter===r.disposition||(filter==='changed'&&changed(r.item))||(filter==='assigned'&&edits.get(r.item).assign_to_llm)||(filter==='needs-me'&&needsMe(r))) && (!needle || `${r.item} ${r.received_label} ${r.to_display} ${r.subject} ${r.gist} ${edits.get(r.item).comment} ${edits.get(r.item).task_instruction}`.toLocaleLowerCase().includes(needle)));
    function value(r) {
      if(sortKey==='received')return data.received_timestamps[r.item];
      if(sortKey==='gist')return `${r.gist} ${edits.get(r.item).comment}`;
      if(sortKey==='assign_to_llm')return Number(edits.get(r.item).assign_to_llm);
      if(sortKey==='requests'){const e=edits.get(r.item);return `${e.opt_out?'Opt Out ':''}${e.requested_move||''}`;}
      return r[sortKey];
    }
    list.sort((a,b)=>{const x=value(a),y=value(b);if(x===null)return y===null?a.item.localeCompare(b.item):1;if(y===null)return -1;const c=typeof x==='number'?x-y:String(x).localeCompare(String(y),undefined,{numeric:true,sensitivity:'base'});return c*sortDirection||a.item.localeCompare(b.item,undefined,{numeric:true});});
    rows.replaceChildren();for(const r of list)rows.append(rowCache.get(r.item)||row(r));
    const shown=list.length;
    if(!shown){const tr=node('tr'),td=node('td','empty','No messages match this filter.');td.colSpan=9;td.setAttribute('role','cell');tr.setAttribute('role','row');tr.append(td);rows.append(tr);}
    for(const th of document.querySelectorAll('th[data-sort]')){
      const selected=th.dataset.sort===sortKey;th.setAttribute('aria-sort',selected?(sortDirection===1?'ascending':'descending'):'none');
      const button=th.querySelector('button');button.textContent=button.textContent.replace(/ [↕↑↓]$/,'')+' '+(selected?(sortDirection===1?'↑':'↓'):'↕');
    }
    $('summary').textContent=`${shown} of ${data.records.length} messages shown · `+['Inbox','Archived','Spam','Trash'].map(d=>`${data.records.filter(r=>r.disposition===d).length} ${d}`).join(' · ')+` · Last Refreshed: ${data.last_refreshed_label}`;
    const verifiedMoves=(currentHistory?.actions||[]).filter(verifiedMove).length;
    $('receipt').textContent=`${data.run_id} · ${data.records.length} messages · ${verifiedMoves} verified moves · ${data.records.filter(needsMe).length} explicit follow-up / assessment items · ${dirty.size} pending review requests`;status();
  }
  function payload() {return {version:2,run_id:data.run_id,snapshot_id:data.snapshot_id,exported_at:new Date().toISOString(),changes:changes()};}
  function refreshPendingReview(){const kept=changes().filter(c=>c.requested_move||c.opt_out||edits.get(c.item).comment.trim());return {version:2,run_id:data.run_id,snapshot_id:data.snapshot_id,exported_at:new Date().toISOString(),changes:kept.map(c=>({...c,assign_to_llm:false}))};}
  let searchTimer=null;$('search').addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(render,120);});$('filter').addEventListener('change',render);
  for(const button of document.querySelectorAll('button[data-sort]'))button.addEventListener('click',()=>{const key=button.dataset.sort;if(key===sortKey)sortDirection*=-1;else{sortKey=key;sortDirection=key==='received'?-1:1;}render();});
  function download(value, name) {
    const blob=new Blob([JSON.stringify(value,null,2)+'\n'],{type:'application/json'}),url=URL.createObjectURL(blob),a=node('a');
    a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function assignments() {
    return {version:2,kind:'email-triage-assignments',run_id:data.run_id,snapshot_id:data.snapshot_id,exported_at:new Date().toISOString(),policy:data.assignment_policy,
      assignments:data.records.filter(r=>edits.get(r.item).assign_to_llm).map(r=>({item:r.item,assigned_to:null,user_instruction:edits.get(r.item).task_instruction,requested_move:edits.get(r.item).requested_move,opt_out:edits.get(r.item).opt_out,email:r}))};
  }
  $('export').addEventListener('click',()=>{
    if(!changes().length)return;
    if($('export-profile').value==='minimal-review'){
      download(minimalReview(),'email-triage-limited-review.json');
      $('status').textContent='Limited-data review download requested. This digest cannot resume pending edits or request actions; your full review changes remain unsaved. Sensitive text may remain. Nothing changed in Mail.';
    } else {
      download(reviewBundle(),`email-triage-review-${data.snapshot_id.slice(0,12)}.json`);
      lastFullSave=resumableSignature();
      const drafts=unexportedDrafts();$('status').textContent=`Review bundle download requested. Moves, comments and selected follow-up tasks are separately typed and bound to this exact snapshot.${drafts.length?` Draft text in ${drafts.map(r=>r.item).join(', ')} was omitted and remains unsaved; select it as a task or clear it.`:' Changes in this full bundle are saved for this page session.'} Nothing changed in Mail.`;
    }
  });
  $('assignments').addEventListener('click',()=>{
    if(!assignments().assignments.length)return;download(assignments(),`email-triage-assignments-${data.snapshot_id.slice(0,12)}.json`);
    $('status').textContent='Assignment JSON download requested. No LLM has been started. Give this file to your chosen agent; it includes your edited instructions and local source references.';
  });
  $('refresh').addEventListener('click',()=>{
    const refresh_request={version:1,kind:'email-triage-refresh-request',mode:'read-only',run_id:data.run_id,snapshot_id:data.snapshot_id,requested_at:new Date().toISOString(),account_scope:data.account_scope,request:data.refresh_request_text,pending_review:refreshPendingReview()};
    download({...reviewBundle(),refresh_request},`email-triage-refresh-${data.snapshot_id.slice(0,12)}.json`);lastFullSave=resumableSignature();
    const drafts=unexportedDrafts();$('status').textContent=`Refresh request download requested. This offline file cannot wake an agent or read Mail. Ask an agent to process it and produce an updated review;${drafts.length?` draft text in ${drafts.map(r=>r.item).join(', ')} remains unsaved.`:' the selected review requests are saved in this file.'}`;
  });
  $('export-profile').addEventListener('change',updatePreview);updatePreview();
  function objectKeys(value, allowed) {return value && typeof value==='object' && !Array.isArray(value) && Object.keys(value).length===allowed.length && Object.keys(value).every(k=>allowed.includes(k));}
  function importReview(p) {
    if(p && ['email-triage-assignments','email-triage-refresh-request'].includes(p.kind))throw Error('Load saved edits accepts review exports. Give assignment or refresh JSON to an agent to process it.');
    if(p?.kind==='email-triage-review-bundle'){
      if(!objectKeys(p,['version','kind','run_id','snapshot_id','exported_at','moves','opt_outs','tasks','comments','refresh_request'])||p.version!==1||p.run_id!==data.run_id||p.snapshot_id!==data.snapshot_id||typeof p.exported_at!=='string'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(p.exported_at)||new Date(p.exported_at).toISOString()!==p.exported_at||!Array.isArray(p.moves)||!Array.isArray(p.opt_outs)||!Array.isArray(p.tasks)||!Array.isArray(p.comments))throw Error('Invalid review bundle. No edits loaded.');
      const approved=new Map(data.records.map(r=>[r.item,{comment:'',task_instruction:'',requested_move:null,opt_out:false,assign_to_llm:false,assignment_touched:false}]));
      const identityKeys=['item','account','message_id','snapshot_mailbox','snapshot_numeric_id'];
      const readIdentity=(x,suffix=[])=>{const r=base.get(x?.item);if(!objectKeys(x,[...identityKeys,...suffix]))throw Error('Invalid bundle entry fields. No edits loaded.');if(!r)throw Error('Unknown bundle item. No edits loaded.');if(x.account!==r.account||x.message_id!==r.message_id||x.snapshot_mailbox!==r.observed_mailbox||x.snapshot_numeric_id!==r.current_id)throw Error('Bundle identity does not match the exact snapshot. No edits loaded.');return r;};
      const seen={moves:new Set(),opt_outs:new Set(),tasks:new Set(),comments:new Set()};
      for(const x of p.moves){const r=readIdentity(x,['destination']);if(seen.moves.has(r.item)||!['inbox','archive'].includes(x.destination)||(x.destination==='inbox'&&r.disposition==='Inbox')||(x.destination==='archive'&&r.disposition==='Archived'))throw Error('Invalid or unavailable move. No edits loaded.');seen.moves.add(r.item);approved.get(r.item).requested_move=x.destination;}
      for(const x of p.opt_outs){const r=readIdentity(x);if(seen.opt_outs.has(r.item))throw Error('Duplicate opt-out request. No edits loaded.');seen.opt_outs.add(r.item);approved.get(r.item).opt_out=true;}
      for(const x of p.tasks){const r=readIdentity(x,['instruction']);if(seen.tasks.has(r.item)||typeof x.instruction!=='string'||!instructionText(x.instruction)||Array.from(x.instruction).length>4000||!r.email_context)throw Error('Invalid follow-up task. No edits loaded.');seen.tasks.add(r.item);Object.assign(approved.get(r.item),{task_instruction:x.instruction,assign_to_llm:true,assignment_touched:true});}
      for(const x of p.comments){const r=readIdentity(x,['original_summary','comment']);if(seen.comments.has(r.item)||x.original_summary!==r.gist||typeof x.comment!=='string'||!x.comment.trim()||Array.from(x.comment).length>4000)throw Error('Invalid comment or changed summary. No edits loaded.');seen.comments.add(r.item);approved.get(r.item).comment=x.comment;}
      if(p.refresh_request!==null){const q=p.refresh_request;if(!objectKeys(q,['version','kind','mode','run_id','snapshot_id','requested_at','account_scope','request','pending_review'])||q.version!==1||q.kind!=='email-triage-refresh-request'||q.mode!=='read-only'||q.run_id!==data.run_id||q.snapshot_id!==data.snapshot_id||q.request!==data.refresh_request_text||JSON.stringify([...q.account_scope].sort())!==JSON.stringify([...(data.account_scope||[])].sort())||!Number.isFinite(Date.parse(q.requested_at))||!objectKeys(q.pending_review,['version','run_id','snapshot_id','exported_at','changes'])||![1,2].includes(q.pending_review.version)||q.pending_review.run_id!==data.run_id||q.pending_review.snapshot_id!==data.snapshot_id||!Array.isArray(q.pending_review.changes)||q.pending_review.changes.length>data.records.length)throw Error('Invalid nested read-only refresh request. No edits loaded.');
        const moveMap=new Map(p.moves.map(x=>[x.item,x.destination])),outSet=new Set(p.opt_outs.map(x=>x.item)),commentMap=new Map(p.comments.map(x=>[x.item,x.comment])),pendingSeen=new Set();
        for(const c of q.pending_review.changes){const r=base.get(c.item);if(!objectKeys(c,['item','account','message_id','snapshot_mailbox','snapshot_numeric_id','original_gist','gist','requested_move','opt_out',...(q.pending_review.version===2?['assign_to_llm']:[])])||!r||pendingSeen.has(c.item)||c.account!==r.account||c.message_id!==r.message_id||c.snapshot_mailbox!==r.observed_mailbox||c.snapshot_numeric_id!==r.current_id||c.original_gist!==r.gist||typeof c.gist!=='string'||Array.from(c.gist).length>4000||!['inbox','archive',null].includes(c.requested_move)||typeof c.opt_out!=='boolean'||(q.pending_review.version===2&&c.assign_to_llm!==false))throw Error('Invalid refresh pending review identity. No edits loaded.');
          const expectedComment=commentMap.get(c.item);if(expectedComment?c.gist!==expectedComment:c.gist!==r.gist)throw Error('Refresh request differs from typed comments. No edits loaded.');
          if((c.requested_move||null)!==(moveMap.get(c.item)||null)||c.opt_out!==outSet.has(c.item))throw Error('Refresh request differs from typed move or opt-out requests. No edits loaded.');pendingSeen.add(c.item);}
        if([...moveMap.keys(),...outSet,...commentMap.keys()].some(item=>!pendingSeen.has(item)))throw Error('Refresh request omitted pending review edits. No edits loaded.');
      }
      if(changes().length&&pendingSignature()!==lastFullSave&&!confirm('Replace unsaved edits with this saved review?'))return;
      for(const r of data.records)edits.set(r.item,approved.get(r.item));dirty.clear();assignedItems.clear();for(const r of data.records)markDirty(r.item);rowCache.clear();lastFullSave=resumableSignature();render();$('error').hidden=true;$('status').textContent=`Loaded ${p.moves.length} moves, ${p.opt_outs.length} opt-out requests, ${p.tasks.length} tasks and ${p.comments.length} comments. Nothing applied to Mail.`;return;
    }
    if(!objectKeys(p,['version','run_id','snapshot_id','exported_at','changes']) || ![1,2].includes(p.version) || typeof p.exported_at!=='string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(p.exported_at) || !Number.isFinite(Date.parse(p.exported_at)) || new Date(p.exported_at).toISOString()!==p.exported_at || !Array.isArray(p.changes) || p.changes.length>data.records.length)throw Error('Invalid review format, version or timestamp. No edits loaded.');
    if(p.run_id!==data.run_id || p.snapshot_id!==data.snapshot_id)throw Error('This review does not match this exact snapshot. No edits loaded.');
    const seen=new Set(), approved=[];
    for(const c of p.changes) {
      if(!objectKeys(c,['item','account','message_id','snapshot_mailbox','snapshot_numeric_id','original_gist','gist','requested_move','opt_out',...(p.version===2?['assign_to_llm']:[])]))throw Error('Unsupported review fields. No edits loaded.');
      const r=base.get(c.item);
      if(!r || seen.has(c.item) || c.account!==r.account || c.message_id!==r.message_id || c.snapshot_mailbox!==r.observed_mailbox || c.snapshot_numeric_id!==r.current_id || c.original_gist!==r.gist || typeof c.gist!=='string' || Array.from(c.gist).length>4000 || ![null,'inbox','archive'].includes(c.requested_move) || typeof c.opt_out!=='boolean')throw Error('Invalid, duplicated or changed message identity. No edits loaded.');
      if((c.requested_move==='inbox' && r.disposition==='Inbox') || (c.requested_move==='archive' && r.disposition==='Archived'))throw Error('Unavailable action for this observed disposition. No edits loaded.');
      if(p.version===2 && typeof c.assign_to_llm!=='boolean')throw Error('Invalid assignment checkbox. No edits loaded.');
      if(c.assign_to_llm && (!r.email_context || !instructionText(c.gist) || instructionText(c.gist)===instructionText(r.gist)))throw Error('Assignments need source context and an explicit edited instruction. No edits loaded.');
      if(c.requested_move===null && !c.opt_out && c.gist===r.gist && !c.assign_to_llm)throw Error('Empty change row. No edits loaded.');
      seen.add(c.item);approved.push(c);
    }
    if(changes().length && pendingSignature()!==lastFullSave && !confirm('Replace unsaved edits with this saved review?'))return;
    for(const r of data.records)edits.set(r.item,{comment:'',task_instruction:'',requested_move:null,opt_out:false,assign_to_llm:false,assignment_touched:false});
    for(const c of approved)edits.set(c.item,{comment:c.gist===base.get(c.item).gist?'':c.gist,task_instruction:c.assign_to_llm?c.gist:'',requested_move:c.requested_move,opt_out:c.opt_out,assign_to_llm:c.assign_to_llm||false,assignment_touched:!!c.assign_to_llm});
    dirty.clear();assignedItems.clear();for(const r of data.records)markDirty(r.item);rowCache.clear();lastFullSave=resumableSignature();render();$('error').hidden=true;$('status').textContent=`Loaded ${approved.length} reviewed item${approved.length===1?'':'s'}. Nothing applied to Mail.`;
  }
  $('import').addEventListener('click',()=>$('import-file').click());
  $('import-file').addEventListener('change',async e=>{
    const file=e.target.files[0];if(!file)return;
    try {if(file.size>2_000_000)throw Error('Review file is too large. No edits loaded.');importReview(JSON.parse(await file.text()));}
    catch(error){$('error').textContent=String(error.message||error);$('error').hidden=false;}
    finally{e.target.value='';}
  });
  $('clear').addEventListener('click',()=>{if(!confirm('Reset every queued action, comment and task? Mail will not change.'))return;for(const r of data.records)edits.set(r.item,{comment:'',task_instruction:'',requested_move:null,opt_out:false,assign_to_llm:false,assignment_touched:false});dirty.clear();assignedItems.clear();rowCache.clear();lastFullSave='';render();});
  addEventListener('beforeunload',e=>{if(changes().length && pendingSignature()!==lastFullSave){e.preventDefault();e.returnValue='';}});
  const helpDialog=$('help-dialog');let helpOpener=null;
  $('help').addEventListener('click',()=>{helpOpener=document.activeElement;helpDialog.showModal();document.documentElement.classList.add('help-open');$('help-body').scrollTop=0;});
  helpDialog.addEventListener('close',()=>{document.documentElement.classList.remove('help-open');if(helpOpener?.isConnected)helpOpener.focus({preventScroll:true});});
  $('help-close').addEventListener('click',()=>helpDialog.close());
  helpDialog.addEventListener('keydown',event=>{
    if(event.key!=='Tab')return;
    const items=[...helpDialog.querySelectorAll('button,a[href],input,select,textarea,[tabindex]')].filter(e=>!e.disabled && e.tabIndex>=0 && e.getClientRects().length);
    const first=items[0],last=items[items.length-1];
    if(first && ((!event.shiftKey && document.activeElement===last) || (event.shiftKey && document.activeElement===first))){event.preventDefault();(event.shiftKey?last:first).focus();}
  });
  helpDialog.addEventListener('click',event=>{const box=helpDialog.getBoundingClientRect();if(event.target===helpDialog && (event.clientX<box.left || event.clientX>box.right || event.clientY<box.top || event.clientY>box.bottom))helpDialog.close();});
  $('execution').textContent=data.execution_label;
  const unreviewed=data.history.filter(run=>!run.reviewed_at).length;
  $('history').textContent=unreviewed?`Run history (${unreviewed} unreviewed)`:'Run history';
  function renderHistory(){
    const from=$('history-from').value,through=$('history-to').value;
    $('history-runs').replaceChildren();
    if(from && through && from>through){$('history-status').textContent='Choose a start date on or before the end date.';return;}
    const runs=data.history.filter(run=>{const day=new Intl.DateTimeFormat('en-CA',{timeZone:data.timezone,year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(run.at));return (!from||day>=from)&&(!through||day<=through);});
    $('history-status').textContent=`${runs.length} saved run${runs.length===1?'':'s'} in this time range. History reflects the export time, not live Mail.`;
    for(const run of runs){
      const card=node('article','history-run');
      card.append(node('h3','',run.run_id),node('p','',`${new Date(run.at).toLocaleString(undefined,{timeZone:data.timezone})} · ${run.reviewed_at?'Acknowledged':'Not yet reviewed'}`));
      const link=node('a','','Open original review / undo');link.href=run.review_url;link.target='_blank';link.rel='noopener';card.append(link);
      const actions=Array.isArray(run.actions)?run.actions:[];
      const moved=actions.filter(verifiedMove),retained=actions.filter(verifiedRetained);
      card.append(node('p','',`${moved.length} verified moves · ${retained.length} verified retained items`));
      const list=node('ul');
      for(const action of moved){const entry=node('li');entry.append(node('span','',`${action.item} · ${action.old_mailbox} → ${action.destination} · ${action.subject} · ${action.reason}`));
        const exact=base.get(action.item),canUndo=!!exact&&action.account===exact.account&&action.message_id===exact.message_id&&Number.isInteger(action.new_id)&&action.new_id===exact.current_id&&action.destination===exact.observed_mailbox&&(!receiptBackedCompleted(action)||action.receipt_new_id===exact.current_id);
        if(canUndo&&action.destination!=='INBOX'){const undo=node('button','request-undo','Request undo');undo.type='button';undo.setAttribute('aria-label',`Request undo for ${action.item}`);undo.addEventListener('click',()=>{const state=edits.get(exact.item);state.requested_move='inbox';markDirty(exact.item);rowCache.get(exact.item)?.classList.add('edited');status();$('status').textContent=`Undo request queued for ${exact.item}. The saved snapshot remains unchanged; Mail was not changed.`;});entry.append(document.createTextNode(' '),undo);}
        else {const unavailable=node('span','undo-unavailable',' Undo request unavailable: exact saved copy identity is incomplete.');entry.append(unavailable);}
        list.append(entry);}
      card.append(list);$('history-runs').append(card);
      for(const task of run.tasks||[]){const line=node('p','history-task',`${task.item||'Unlinked item'} · ${task.status.replaceAll('_',' ')} · ${task.next_action}`);card.append(line);}
      for(const assessment of run.assessments||[]){const label=assessment.invalidated_at?'invalidated':assessment.result?.status;if(typeof label==='string'&&label){const line=node('p','history-assessment',`${assessment.item||'Unlinked item'} · ${label} · assessed ${assessment.assessed_at}`);card.append(line);}}
    }
  }
  $('history').addEventListener('click',()=>{const panel=$('history-panel');panel.hidden=!panel.hidden;$('history').setAttribute('aria-expanded',String(!panel.hidden));if(!panel.hidden)renderHistory();});
  $('history-load').addEventListener('click',renderHistory);
  $('help-scope').textContent=data.scope;
  $('help-snapshot').textContent=data.snapshot_as_of;
  $('help-timezone').textContent=data.timezone;
  $('help-generated').textContent=data.generated_label;
  $('help-refreshed').textContent=data.last_refreshed_label;
  render();
})();
