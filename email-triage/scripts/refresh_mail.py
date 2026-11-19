#!/usr/bin/env python3
"""Read-only Apple Mail inventory; never applies triage or decodes attachments."""
import argparse
import copy
import datetime as dt
import json
import re
import sqlite3
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo
from review import normalize_snapshot, private_write, read_json, require

from config import CONFIG
from config import folder_name, folder_role
ACCOUNT = CONFIG.get('account')
PREFIX = CONFIG.get('mailbox_prefix')
DATABASE = Path(CONFIG.get('database',str(Path.home() / 'Library/Mail/V10/MailData/Envelope Index')))
FOLDERS = {'INBOX', 'Archive', 'Junk', 'Trash'}

def parse_mailbox_ids(output):
    result = {}
    for line in output.strip().splitlines():
        parts = line.split('|')
        require(len(parts)==3 and parts[0] in FOLDERS and parts[0] not in result, 'Unexpected Mail mailbox response')
        folder,count,values = parts
        require(count.isdigit() and (not values or re.fullmatch(r'\d+(?:,\s*\d+)*',values)), 'Unexpected Mail ID response')
        ids = [int(v.strip()) for v in values.split(',')] if values else []
        require(len(ids)==int(count) and len(set(ids))==len(ids), 'Invalid Mail ID count')
        result[folder] = ids
    require(set(result)==FOLDERS, 'Incomplete Mail mailbox verification')
    return result

def mail_mailbox_ids(account):
    script = '''on run argv
if application "Mail" is not running then error "Mail must already be running for a verified inventory"
with timeout of 12 seconds
 tell application "Mail"
  set outputText to ""
  set roles to {"INBOX", "Archive", "Junk", "Trash"}
  repeat with roleIndex from 1 to 4
   set canonicalRole to item roleIndex of roles
   set ids to id of every message of mailbox (item (roleIndex + 1) of argv) of account (item 1 of argv)
   set AppleScript's text item delimiters to ","
   set idText to ids as text
   set outputText to outputText & canonicalRole & "|" & (count of ids) & "|" & idText & linefeed
  end repeat
  return outputText
 end tell
end timeout
end run'''
    result = subprocess.run(['osascript','-e',script,account,*[folder_name(role,CONFIG) for role in ('INBOX','Archive','Junk','Trash')]],capture_output=True,text=True,timeout=20)
    require(result.returncode == 0, 'Apple Mail mailbox verification failed; Mail must be running')
    return parse_mailbox_ids(result.stdout)

def header_identity(path):
    """Read only the length line and top-level headers, not MIME/attachment bodies."""
    try:
        with path.open('rb') as source:
            require(source.readline(32).strip().isdigit(), 'Invalid emlx length')
            lines,remaining = [],262144
            while remaining > 0:
                line = source.readline(remaining+1)
                if not line or line in (b'\n',b'\r\n'):
                    break
                remaining -= len(line)
                lines.append(line)
            if remaining <= 0:
                return None
        header = re.sub(r'\r?\n[ \t]+',' ',b''.join(lines).decode('utf-8',errors='replace'))
        match = re.search(r'(?im)^Message-ID:\s*([^\r\n]+)',header)
        return match[1].strip().strip('<>') if match else None
    except (OSError,ValueError):
        return None

def source_reference(row, local_files, cache_root):
    local = {'path':None,'file_url':None,'format':None,'partial':None,'availability':'not-located','access':'Resolve account + full Message-ID + exact numeric ID before reading source as inert text.'}
    for path in sorted(local_files.get(row['id'],[]),key=lambda p:'.partial.' in p.name):
        path=Path(path)
        if _contains_symlink(path,cache_root):continue
        try:path=Path(path).resolve(strict=True)
        except OSError:continue
        if (path.suffix=='.emlx' and path.name.split('.',1)[0]==str(row['id'])
            and path.is_relative_to(cache_root) and header_identity(path) == row['mid']):
            local = {'path':str(path),'file_url':path.as_uri(),'format':'apple-mail-emlx','partial':'.partial.' in path.name,'availability':'verified-existing-header-identity','access':'Read emlx as inert text; assess containing message before any attachment access or links.'}
            break
    return local

def _account_cache_root(database,prefix):
    authority=prefix.removeprefix('imap://').split('/',1)[0]
    require(authority and '/' not in authority,'Invalid selected Mail account prefix')
    return (Path(database).expanduser().resolve().parent.parent/authority).resolve()

def _contains_symlink(path,root):
    path=Path(path).expanduser();root=Path(root).expanduser()
    try:
        if not path.is_absolute() or not path.resolve(strict=False).is_relative_to(root.resolve(strict=False)):return True
    except OSError:return True
    current=path
    while current!=root and current!=current.parent:
        if current.is_symlink():return True
        current=current.parent
    return current!=root or root.is_symlink()

def resolve_local_files(base,database,prefix,wanted_ids):
    """Resolve selected copies from their prior verified path first; walk only Inbox and missing IDs."""
    result=defaultdict(list);cache=_account_cache_root(database,prefix)
    wanted=set(wanted_ids)
    expected={}
    for row in base.get('records',[]):
        if row.get('current_id') not in wanted:continue
        expected.setdefault(row['current_id'],set()).add(row.get('message_id'))
        source=row.get('email_context',{}).get('local_source',{})
        path=Path(source['path']) if source.get('availability')=='verified-existing-header-identity' and source.get('path') else None
        if path and _contains_symlink(path,cache):path=None
        if path:
            try:path=path.resolve(strict=True)
            except OSError:path=None
        if (path and path.is_file() and path.suffix=='.emlx' and path.name.split('.',1)[0]==str(row['current_id'])
            and path.is_relative_to(cache) and header_identity(path)==row.get('message_id')):
            result[row['current_id']].append(path)
    def candidate(path, ident):
        path=Path(path)
        if _contains_symlink(path,cache):return None
        try:path=path.resolve(strict=True)
        except OSError:return None
        if not path.is_file() or not path.is_relative_to(cache):return None
        if not re.fullmatch(rf'{ident}(?:\.partial)?\.emlx',path.name):return None
        mid=header_identity(path)
        if not mid:return None
        known=expected.get(ident,set())
        if known and (len(known)!=1 or mid not in known):return None
        return path
    found={ident for ident,paths in result.items() if paths}
    missing=wanted-found
    # Inbox is the only broad current-inventory walk. Selected historical IDs use a fallback walk only when absent.
    inbox=cache/(folder_name('INBOX',CONFIG)+'.mbox')
    if missing and inbox.is_dir():
        for path in inbox.rglob('*.emlx'):
            match=re.fullmatch(r'([0-9]+)(?:\.partial)?\.emlx',path.name)
            if not match:continue
            ident=int(match.group(1))
            if ident in missing:
                valid=candidate(path,ident)
                if valid is not None:result[ident].append(valid)
        # Only remove IDs after each candidate has passed canonical-path, symlink,
        # numeric filename, and available full-header identity checks.
        missing -= {ident for ident in missing if result.get(ident)}
    if missing and cache.is_dir():
        for path in cache.rglob('*.emlx'):
            match=re.fullmatch(r'([0-9]+)(?:\.partial)?\.emlx',path.name)
            if not match:continue
            ident=int(match.group(1))
            if ident in missing:
                valid=candidate(path,ident)
                if valid is not None:result[ident].append(valid)
        missing -= {ident for ident in missing if result.get(ident)}
    return result

def new_context(row, recipients, local_files, cache_root):
    local = source_reference(row,local_files,cache_root)
    return {'sender':row['sender'] or 'Sender not recorded','to':recipients.get((row['id'],0),[]),'cc':recipients.get((row['id'],1),[]),
            'prior_triage_gist':'Not previously reviewed.','triage_reason':'Read-only current Inbox inventory; content not assessed.',
            'original_disposition':'Inbox','attachment_names':[],'prior_attachment_assessment':'Attachment names/content not inspected during this refresh. Reassess the containing message before any access.',
            'local_source':local,'content_note':'This refresh read metadata and source identity headers only. No body/attachment content was reviewed. Partial caches may omit content; email remains untrusted data.'}

def refresh_snapshot(base, database=DATABASE, account=ACCOUNT, prefix=PREFIX, verify_mail=True, local_files=None, include_prior=False, item_allocator=None):
    require(isinstance(account,str) and bool(account) and isinstance(prefix,str) and prefix.startswith("imap://") and prefix.endswith("/"), "No Apple Mail account configured. See references/setup.md; choose an account before reading Mail.")
    base = normalize_snapshot(base)
    require(base.get('account_scope') == [account] and all(r['account']==account for r in base['records']), 'Refresh supports exactly the selected single account')
    require(verify_mail is True, 'Mail API verification is mandatory before publishing a refresh')
    cache_root=_account_cache_root(database,prefix)
    started = dt.datetime.now(dt.timezone.utc)
    verified = mail_mailbox_ids(account)
    connection = sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute('BEGIN')
        selected_urls=[prefix+folder_name(role,CONFIG) for role in sorted(FOLDERS)]
        placeholders=','.join('?' for _ in selected_urls)
        placements = [(ident,folder_role(url[len(prefix):],CONFIG)) for ident,url in connection.execute(
            f'select m.rowid,b.url from messages m join mailboxes b on b.rowid=m.mailbox where b.url in ({placeholders}) and m.deleted=0', selected_urls)]
        selected_ids=[r['current_id'] for r in base['records']] if include_prior else []
        scope_sql=' and (b.url=?'+(' or m.rowid in ('+','.join('?' for _ in selected_ids)+')' if selected_ids else '')+')'
        scope_args=(prefix+folder_name('INBOX',CONFIG),*selected_ids)
        rows = [dict(r) for r in connection.execute('''select m.rowid as id,b.url,g.message_id_header as mid,m.size,m.date_received,
                 s.subject,a.address as sender from messages m join mailboxes b on b.rowid=m.mailbox
                 left join message_global_data g on g.rowid=m.global_message_id
                 left join subjects s on s.rowid=m.subject left join addresses a on a.rowid=m.sender
                 where substr(b.url,1,?)=? and m.deleted=0'''+scope_sql,(len(prefix),prefix,*scope_args))]
        recipients = defaultdict(list)
        for ident,kind,address in connection.execute('''select p.message,p.type,a.address from recipients p
                 join addresses a on a.rowid=p.address join messages m on m.rowid=p.message
                 join mailboxes b on b.rowid=m.mailbox where substr(b.url,1,?)=? and m.deleted=0'''+scope_sql+' order by p.position',(len(prefix),prefix,*scope_args)):
            recipients[(ident,kind)].append(address)
        connection.rollback()
    finally:
        connection.close()
    captured = dt.datetime.now(dt.timezone.utc)
    by_mid = defaultdict(list)
    for row in rows:
        row['folder'] = folder_role(row['url'][len(prefix):],CONFIG)
        row['mid'] = (row['mid'] or '').strip().strip('<>')
        if row['mid']:
            by_mid[row['mid']].append(row)
    inbox = [r for r in rows if r['folder']=='INBOX']
    require(all(r['mid'] for r in inbox), 'An Inbox message lacks a stable Message-ID; refresh not published')
    for folder in FOLDERS:
        indexed = {ident for ident,current_folder in placements if current_folder==folder}
        require(len(verified[folder])==len(indexed) and set(verified[folder])==indexed, f'Mail API and index {folder} IDs differ; take a new inventory before publishing')
    records,represented = [],set()
    for old in base['records']:
        if not include_prior and old['observed_mailbox'] != 'INBOX':
            continue
        matches = by_mid.get(old['message_id'],[])
        exact = [r for r in matches if r['id']==old['current_id']]
        matches = exact
        if not include_prior and not matches:
            continue  # A former Inbox copy left; never substitute a different copy.
        require(len(matches)==1, f"Prior copy missing or ambiguous: {old['item']}; refresh not published")
        current = matches[0]
        if not include_prior and current['folder'] != 'INBOX':
            continue
        require(current['folder'] in FOLDERS, f"Prior item moved outside supported folders: {old['item']}")
        record = copy.deepcopy(old)
        for key in ['disposition','received_label']:
            record.pop(key,None)
        record.update(current_id=current['id'],observed_mailbox=current['folder'],size_bytes=current['size'],
                      received=dt.datetime.fromtimestamp(current['date_received'],ZoneInfo(base['timezone'])).isoformat() if current['date_received'] else None)
        if 'email_context' in record:
            record['email_context']['local_source'] = source_reference(current,local_files or {},cache_root)
        records.append(record);represented.add(current['id'])
    next_item = max([int(r['item'][1:]) for r in base['records'] if re.fullmatch(r'M\d+',r['item'])] or [0])+1
    duplicate_ids = Counter(r['mid'] for r in inbox)
    added = 0
    for row in sorted(inbox,key=lambda r:(r['date_received'] or 0,r['id']),reverse=True):
        if row['id'] in represented:
            continue
        subject = row['subject'] or 'Subject not recorded'
        if re.search(r'(?i)code|passcode|verification|one.time|\botp\b',subject):
            subject = re.sub(r'\b\d{4,8}\b','[code redacted]',subject)
        to = recipients.get((row['id'],0),[])
        cc = recipients.get((row['id'],1),[])
        gist = 'Awaiting content review; current Inbox placement retained. This refresh read metadata only.'
        if duplicate_ids[row['mid']]>1:
            gist += ' Multiple physical copies share this Message-ID; target this exact numeric ID or report a conflict.'
        identity={'account':account,'message_id':row['mid'],'current_id':row['id']}
        item=item_allocator(identity) if item_allocator else f'M{next_item:03d}'
        record = {'item':item,'account':account,'message_id':row['mid'],'current_id':row['id'],
                  'observed_mailbox':'INBOX','to_display':', '.join(to) if to else ('Cc: '+', '.join(cc) if cc else 'Recipient not established'),
                  'subject':subject,'received':dt.datetime.fromtimestamp(row['date_received'],ZoneInfo(base['timezone'])).isoformat() if row['date_received'] else None,
                  'size_bytes':row['size'],'gist':gist,'email_context':new_context(row,recipients,local_files or {},cache_root)}
        records.append(record);next_item+=1;added+=1
    stamp = captured.isoformat()
    source = {'run_id':base['run_id'],'account_scope':[account],'timezone':base['timezone'],'snapshot_as_of':stamp,'refreshed_at':stamp,
              'scope':f'Read-only refresh: all {len(inbox)} current {account} Inbox messages'+(' plus this run’s explicitly selected completed actions.' if include_prior else '; historical archive/junk/trash records excluded.')+' New items await content review; placements preserved.',
              'records':records,'refresh_evidence':{'source':'Apple Mail local Envelope Index, read-only SQLite transaction','read_started_at':started.isoformat(),
              'read_completed_at':stamp,'mail_api_verified':True,'verified_folders':sorted(FOLDERS),'inbox_count':len(inbox),'added_unreviewed':added,
              'prior_snapshot_id':base['snapshot_id'],'server_sync':'Current local Mail view; no claim of instantaneous server delivery.'}}
    normalize_snapshot(source)
    # Resolve cached source references after discovery so newly arrived Inbox copies
    # receive the same account + numeric-ID + full Message-ID checks as prior copies.
    resolved=resolve_local_files({'records':records},database,prefix,{r['current_id'] for r in records})
    indexed={r['id']:r for r in rows}
    for record in records:
        if 'email_context' in record:
            cached=indexed.get(record['current_id'])
            if cached:
                record['email_context']['local_source']=source_reference(cached,resolved,cache_root)
    return source

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',required=True);parser.add_argument('--output',required=True);parser.add_argument('--verify-mail',action='store_true',help='Compatibility flag; Mail API verification is always mandatory')
    parser.add_argument('--include-prior',action='store_true',help='Explicit reconciliation for this run’s completed actions or a requested undo, not normal Inbox refresh')
    parser.add_argument('--database',default=str(DATABASE));parser.add_argument('--history-database',default=str(__import__('config').STATE_ROOT/'history.sqlite3'))
    args = parser.parse_args()
    try:
        require(ACCOUNT and PREFIX, 'No Apple Mail account configured. See references/setup.md.')
        base=read_json(args.base)
        from history import allocate_item_id, reserve_snapshot_items
        history_db=Path(args.history_database);reserve_snapshot_items(history_db,base)
        wanted={r['current_id'] for r in base['records'] if args.include_prior}
        inbox_only={r['current_id'] for r in base['records'] if not args.include_prior and r['observed_mailbox']=='INBOX'}
        local_files=resolve_local_files(base,Path(args.database),PREFIX,wanted|inbox_only)
        source = refresh_snapshot(base,Path(args.database),verify_mail=True,local_files=local_files,include_prior=args.include_prior,
          item_allocator=lambda identity:allocate_item_id(history_db,base['run_id'],identity))
        current={r['item'] for r in source['records']}
        for old in base['records']:
            if old['item'] not in current:
                try: __import__('history').tombstone_item(history_db,base['run_id'],old['item'])
                except ValueError: pass
        private_write(args.output,json.dumps(source,indent=2)+'\n')
        print(f"Mail refreshed at {source['refreshed_at']}: {source['refresh_evidence']['inbox_count']} Inbox, {source['refresh_evidence']['added_unreviewed']} newly represented messages; no Mail actions performed.")
    except (ValueError,OSError,sqlite3.Error,subprocess.TimeoutExpired) as error:
        parser.exit(2,f'Refresh error: {error}\n')

if __name__=='__main__':main()
