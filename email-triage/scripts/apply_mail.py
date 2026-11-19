#!/usr/bin/env python3
"""Apply an explicitly authorized disposition plan through Apple Mail's scripting API.

Never sends mail or expunges. Each copy is resolved by account, full Message-ID,
mailbox and numeric ID immediately before a move. Immutable intents/results allow
safe inspection after interruption; unfinished intents are never replayed blindly.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid
from review import FOLDERS, normalize_snapshot, read_json, private_write, require, validate_review_bundle
from refresh_mail import header_identity
from execution import account_locks, account_lock_root, append_event, create_or_validate_manifest, rules_digest, validate_existing_manifest


class MailAPIError(RuntimeError):
    """Systemic Mail bridge or response failure; stop the run and reconcile intents."""


class ActionConflict(ValueError):
    """A selected copy or action-specific postcondition no longer matches."""


def protected(received, started_at):
    if received is None:
        return True
    stamp = dt.datetime.fromisoformat(received.replace('Z', '+00:00'))
    start = dt.datetime.fromisoformat(started_at.replace('Z', '+00:00'))
    require(stamp.tzinfo is not None and start.tzinfo is not None, 'Explicit timezone required')
    return stamp < start - dt.timedelta(days=30)


def validate_plan(source, plan, trusted_started_at=None):
    snapshot = normalize_snapshot(source)
    allowed_plan_fields = {'snapshot_id', 'started_at', 'authorization', 'actions', 'user_review_evidence'}
    require(isinstance(plan, dict) and set(plan) <= allowed_plan_fields and {'snapshot_id', 'started_at', 'authorization', 'actions'} <= set(plan), 'Unexpected plan fields')
    require(plan['snapshot_id'] == snapshot['snapshot_id'], 'Plan snapshot mismatch')
    start = dt.datetime.fromisoformat(plan['started_at'].replace('Z', '+00:00'))
    require(start.tzinfo is not None, 'Plan start needs timezone')
    policy_start = dt.datetime.fromisoformat((trusted_started_at or dt.datetime.now(dt.timezone.utc).isoformat()).replace('Z', '+00:00'))
    require(policy_start.tzinfo is not None, 'Trusted policy start needs timezone')
    require(isinstance(plan['authorization'], str) and plan['authorization'].strip(), 'Authorization evidence required')
    require(isinstance(plan['actions'], list), 'Invalid plan actions')
    evidence = plan.get('user_review_evidence')
    review_moves = {}
    evidence_digest = None
    if evidence is not None:
        require(isinstance(evidence, dict) and set(evidence) == {'bundle_json', 'export_sha256', 'snapshot_json', 'snapshot_sha256'}, 'Invalid user-review override evidence')
        require(all(isinstance(evidence[k], str) for k in evidence), 'Invalid user-review evidence values')
        bundle_bytes = evidence['bundle_json'].encode('utf-8')
        source_bytes = evidence['snapshot_json'].encode('utf-8')
        evidence_digest = hashlib.sha256(bundle_bytes).hexdigest()
        require(evidence_digest == evidence['export_sha256'] and re.fullmatch(r'[0-9a-f]{64}', evidence['export_sha256']), 'User-review export digest mismatch')
        require(hashlib.sha256(source_bytes).hexdigest() == evidence['snapshot_sha256'] and re.fullmatch(r'[0-9a-f]{64}', evidence['snapshot_sha256']), 'User-review source snapshot digest mismatch')
        try:
            evidence_snapshot = normalize_snapshot(json.loads(source_bytes))
            evidence_bundle = json.loads(bundle_bytes)
        except (ValueError, TypeError, UnicodeDecodeError) as error:
            raise ValueError('Invalid user-review evidence JSON') from error
        validate_review_bundle(evidence_snapshot, evidence_bundle)
        review_moves = {move['item']: move for move in evidence_bundle['moves']}
    records = {r['item']: r for r in snapshot['records']}
    seen = set()
    for action in plan['actions']:
        require(isinstance(action, dict) and set(action) in ({'item', 'destination', 'reason'}, {'item', 'destination', 'reason', 'age_override'}), 'Unexpected action fields')
        item = action['item']
        require(item in records and item not in seen, 'Unknown or duplicate action')
        require(action['destination'] in FOLDERS, 'Unsupported destination')
        require(isinstance(action['reason'], str) and action['reason'].strip(), 'Reason required')
        row = records[item]
        old_protected = protected(row['received'], policy_start.isoformat()) and action['destination'] != 'INBOX'
        override = action.get('age_override')
        if old_protected:
            require(isinstance(override, dict), 'Older/unknown-date mail is protected: '+item)
        if override is not None:
            common = {'item':item,'account':row['account'],'message_id':row['message_id'],'numeric_id':row['current_id'],'destination':action['destination']}
            if override.get('source') == 'validated-user-review':
                expected = {'source':'validated-user-review','export_sha256':evidence_digest,**{k:v for k,v in common.items() if k != 'destination'}}
                require(evidence is not None and set(override) == set(expected) and type(override.get('numeric_id')) is int and override == expected, 'Invalid item-specific user-review override')
                move = review_moves.get(item)
                require(move is not None, 'User-review override needs an exact selected move: '+item)
                require((move['account'],move['message_id'],move['snapshot_numeric_id'],move['destination']) == (row['account'],row['message_id'],row['current_id'],{'INBOX':'inbox','Archive':'archive'}.get(action['destination'])), 'User-review override does not match exact selected move: '+item)
                evidence_row = {r['item']:r for r in normalize_snapshot(json.loads(evidence['snapshot_json']))['records']}[item]
                require((evidence_row['account'],evidence_row['message_id'],evidence_row['current_id']) == (row['account'],row['message_id'],row['current_id']), 'User-review override source copy changed: '+item)
            elif override.get('source') == 'direct-user-instruction':
                expected={'source':'direct-user-instruction','attestation':'caller-attested-not-cryptographically-verified',**common}
                require(set(override) == set(expected) | {'instruction'} and type(override.get('numeric_id')) is int and all(override.get(k)==v for k,v in expected.items()), 'Direct user override must match the exact item and destination')
                require(isinstance(override['instruction'],str) and override['instruction'].strip() and len(override['instruction'])<=2000, 'Direct user override needs a specific bounded instruction')
            else:
                raise ValueError('Age override source must be a validated user review or caller-attested exact user instruction')
        seen.add(item)
    require(evidence is not None or not any(a.get('age_override',{}).get('source')=='validated-user-review' for a in plan['actions']), 'User-review override evidence is required')
    return snapshot


def configured_history_database():
    """Return the only authoritative history DB path for this installation."""
    import config
    state_root = Path(config.CONFIG.get('state_root', str(config.STATE_ROOT))).expanduser().resolve()
    return state_root / 'history.sqlite3'


def _validate_registered_baseline(snapshot, history_database=None):
    """Reject stale snapshots whenever this run already has an immutable registration."""
    configured = configured_history_database()
    supplied = configured if history_database is None else Path(history_database).expanduser()
    require(not supplied.is_symlink(), 'History database may not be a symlink')
    require(supplied.resolve() == configured, 'History database must be the configured authoritative baseline')
    if configured.exists():
        require(not configured.is_symlink() and configured.is_file(), 'Configured history database must be a regular file')
        if configured.stat().st_size:
            import sqlite3
            try:
                connection = sqlite3.connect(configured.resolve().as_uri() + '?mode=ro', uri=True)
                try:
                    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                finally:
                    connection.close()
            except sqlite3.DatabaseError as error:
                raise ValueError('Configured history database cannot be safely inspected') from error
            require('runs' in tables, 'Configured history database has no authoritative run registry')
    import history
    baseline = history.get_registered_snapshot(configured, snapshot['run_id'])
    if baseline is not None:
        require(baseline['snapshot_id'] == snapshot['snapshot_id'], 'Snapshot differs from the registered history baseline')
    return configured


def api(script, *args):
    result = subprocess.run(['osascript', '-e', 'on run argv\nwith timeout of 20 seconds\ntell application "Mail"\n'+script+'\nend tell\nend timeout\nend run', *map(str, args)], capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        detail=result.stderr.strip()
        item_errors=('Exact source copy missing','Message-ID changed','Source identity changed','Copy identity changed during action','Destination copy missing or ambiguous','Destination prestate changed','Junk marking missing','Junk status not cleared','Source copy still exists')
        if any(marker in detail for marker in item_errors): raise ActionConflict('Mail item conflict: '+detail)
        raise MailAPIError('Mail API error: '+detail)
    return result.stdout.strip()


def _folder(role, folder_map):
    return (folder_map or {}).get(role, role)


def lookup(record, folder_map=None):
    result = api('''set a to account (item 1 of argv)
set b to mailbox (item 2 of argv) of a
set found to (every message of b whose id is (item 3 of argv as integer))
if count of found is not 1 then error "Exact source copy missing"
set m to item 1 of found
if message id of m is not (item 4 of argv) then error "Message-ID changed"
return (id of m as text) & tab & (junk mail status of m as text)''', record['account'], _folder(record['observed_mailbox'], folder_map), record['current_id'], record['message_id'])
    ident, junk = result.split('\t')
    try: found_id=int(ident)
    except ValueError as error: raise MailAPIError('Malformed Mail lookup response') from error
    require(found_id == record['current_id'], 'Mail ID mismatch')
    return junk == 'true'


def lookup_many(records, folder_map=None):
    """Batch read-only exact-copy checks; each row has an independent outcome."""
    grouped = {}
    for record in records:
        grouped.setdefault((record['account'], _folder(record['observed_mailbox'], folder_map)), []).append(record)
    results = {}
    for (account, mailbox), account_records in grouped.items():
      for offset in range(0, len(account_records), 50):
        group = account_records[offset:offset+50]
        args = [account, mailbox]
        args.extend(value for record in group for value in (record['current_id'], record['message_id']))
        output = api('''set a to account (item 1 of argv)
set b to mailbox (item 2 of argv) of a
set lines to {}
set i to 3
repeat while i <= (count of argv)
 try
  set wantedID to (item i of argv) as integer
  set wantedMID to item (i + 1) of argv
  set found to every message of b whose id is wantedID
  if count of found is not 1 then error "copy count"
  set m to item 1 of found
  if message id of m is not wantedMID then error "identity"
  set end of lines to (wantedID as text) & tab & (junk mail status of m as text) & tab & "OK"
 on error
  set end of lines to "0" & tab & "false" & tab & "ERROR"
 end try
 set i to i + 2
end repeat
set AppleScript's text item delimiters to linefeed
return lines as text''', *args)
        rows = output.splitlines()
        require(len(rows) == len(group), 'Batched Mail lookup returned incomplete results')
        for record, row in zip(group, rows):
            ident, junk, status = row.split('\t')
            key = (record['account'], record['message_id'], record['current_id'])
            if status != 'OK' or int(ident) != record['current_id']:
                results[key] = ValueError('Exact source copy identity missing in batched lookup')
            else:
                results[key] = junk == 'true'
    return results


def _has_symlink_component(path, stop=None):
    current = Path(path)
    while True:
        if current.is_symlink():
            return True
        if stop is not None and current == Path(stop):
            return False
        if current.parent == current:
            return False
        current = current.parent


def cache_root_from_config(settings):
    database=settings.get('database');prefix=settings.get('mailbox_prefix')
    require(isinstance(database,str) and isinstance(prefix,str) and prefix.startswith('imap://') and prefix.endswith('/'), 'Exact account Mail cache configuration is required for recovery')
    account_partition=prefix.split('://',1)[1].split('/',1)[0]
    require(account_partition and account_partition not in ('.','..'), 'Invalid configured Mail account cache partition')
    return Path(database).expanduser().parent.parent/account_partition


def _verified_recovery_files(record, source, root):
    """Validate every manifest-listed recovery file before allowing reuse or rebackup."""
    requested_root = Path(root).expanduser().absolute()
    require(not _has_symlink_component(requested_root), 'Recovery root may not contain symlinks')
    root = Path(root).resolve(strict=True)
    item_dir = root / record['item']
    require(item_dir.is_dir() and not _has_symlink_component(item_dir), 'Recovery item directory is unavailable or symlinked')
    item_dir = item_dir.resolve(strict=True)
    require(source.parent == item_dir, 'Recovery original must be in the exact authorized item directory')
    manifest_path = item_dir / 'manifest.json'
    require(manifest_path.is_file() and not _has_symlink_component(manifest_path, item_dir), 'Recovery source manifest is unavailable or symlinked')
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError) as error:
        raise ValueError('Recovery source manifest is invalid') from error
    require(isinstance(manifest, dict) and (manifest.get('account'), manifest.get('message_id'), manifest.get('numeric_id'), manifest.get('item')) ==
        (record['account'], record['message_id'], record['current_id'], record['item']), 'Recovery source lineage identity mismatch')
    require(isinstance(manifest.get('files'), list) and manifest['files'], 'Recovery source manifest has no file inventory')
    paths = {}
    source_found = False
    for entry in manifest['files']:
        require(isinstance(entry, dict) and set(entry) == {'path', 'sha256'}, 'Recovery manifest file entry is invalid')
        raw_path = entry['path']; digest = entry['sha256']
        require(isinstance(raw_path, str) and isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest), 'Recovery manifest path or digest is invalid')
        path = Path(raw_path)
        try: resolved_path = path.resolve(strict=True)
        except OSError as error: raise ValueError('Recovery manifest file is missing or unreadable') from error
        require(path.is_absolute() and str(path) == str(resolved_path), 'Recovery manifest path is noncanonical or missing')
        require(not _has_symlink_component(path, item_dir), 'Symlink in recovery manifest file path')
        require(path.is_file() and path.is_relative_to(item_dir), 'Recovery manifest file escapes the authorized item directory')
        relative = path.relative_to(item_dir)
        require(relative.parts and all(part not in ('', '.', '..') for part in relative.parts) and relative.as_posix() != 'manifest.json', 'Recovery manifest contains an invalid relative path')
        require(relative not in paths, 'Recovery manifest contains duplicate file paths')
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        require(actual == digest, 'Recovery manifest file digest mismatch')
        paths[relative] = path
        if path == source:
            source_found = True
    require(source_found, 'Recovery source manifest does not inventory original copy')
    completeness = manifest.get('completeness')
    require(isinstance(completeness, dict) and completeness.get('provider_attachment_completeness') == 'unknown'
        and type(completeness.get('cached_parts_directory_present')) is bool
        and type(completeness.get('discovered_cached_files_copied')) is bool, 'Recovery manifest completeness is invalid')
    require(completeness['cached_parts_directory_present'] or not any(path.parts[0] == 'cached-parts' for path in paths), 'Recovery manifest completeness omits listed cached parts')
    return manifest, paths


def verify_source_copy(record, source, account_cache_root=None, recovery_root=None):
    """Bind an emlx path to its account cache + numeric filename, or a verified recovery manifest."""
    source=Path(source)
    require(source.is_absolute() and str(source)==str(source.resolve(strict=True)), 'Recovery source path must be canonical and contain no symlink')
    require(source.is_file() and not _has_symlink_component(source), 'Recovery source must be a regular non-symlink file')
    match=re.fullmatch(r'([0-9]+)(?:\.partial)?\.emlx',source.name)
    if match:
        require(int(match.group(1)) == record['current_id'], 'Recovery filename numeric ID differs from selected Mail copy')
        require(account_cache_root is not None, 'Configured account cache root is required to verify recovery source')
        root=Path(account_cache_root).resolve(strict=True)
        require(root.is_dir() and source.is_relative_to(root) and not _has_symlink_component(source, root), 'Recovery source is outside the selected account cache')
    elif source.name == 'original.emlx.bin':
        require(recovery_root is not None, 'Verified recovery root is required for a recovery source')
        require(not _has_symlink_component(Path(recovery_root).expanduser().absolute()), 'Recovery root may not contain symlinks')
        root=Path(recovery_root).resolve(strict=True)
        require(source.is_relative_to(root) and not _has_symlink_component(source, root), 'Recovery source is outside the authorized recovery root')
        _verified_recovery_files(record, source, root)
    else:
        raise ValueError('Recovery source must be a numeric Mail emlx or verified recovery copy')
    require(header_identity(source) == record['message_id'], 'Recovery source full Message-ID mismatch')
    return source


def backup(record, root, account_cache_root=None, recovery_root=None):
    require(re.fullmatch(r'M[0-9]{1,8}', record['item']) is not None and int(record['item'][1:]) > 0, 'Invalid recovery item identifier')
    local = record.get('email_context', {}).get('local_source', {})
    require(local.get('availability') == 'verified-existing-header-identity', 'Recovery source unavailable')
    source = verify_source_copy(record, Path(local['path']), account_cache_root, recovery_root)
    root = Path(root).expanduser()
    require(not _has_symlink_component(root.absolute()), 'Recovery root path may not contain symlinks')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root = root.resolve(strict=True)
    require(root.is_dir(), 'Recovery root must be a directory')
    target = root / record['item']
    require(not target.is_symlink(), 'Recovery target may not be a symlink')
    require(target.resolve().parent == root, 'Recovery target escapes authorized root')
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    prior_manifest = None
    prior_files = None
    if source.name == 'original.emlx.bin':
        prior_manifest, prior_files = _verified_recovery_files(record, source, recovery_root)
        require(local.get('partial') == prior_manifest.get('partial'), 'Recovery source partial-content status changed')
        paths = [(original, target/relative) for relative, original in sorted(prior_files.items(), key=lambda pair: pair[0].as_posix())]
    else:
        paths = [(source, target/'original.emlx.bin')]
    # Opaque copies only. Never decode, render or execute attachment bytes.
    parts = source.parent.parent/'Attachments'/str(record['current_id'])
    parts_present = bool(prior_manifest and prior_manifest['completeness'].get('cached_parts_directory_present')) if prior_manifest else parts.exists() or parts.is_symlink()
    if prior_manifest is None and parts_present:
        require(not _has_symlink_component(parts), 'Symlink in cached attachment path')
        for current, directories, filenames in os.walk(parts, followlinks=False):
            current_path=Path(current)
            for name in directories+filenames:
                candidate=current_path/name
                require(not candidate.is_symlink(), 'Symlink encountered in cached attachment tree')
            directories[:] = sorted(directories)
            for filename in sorted(filenames):
                part=current_path/filename
                if part.is_file():
                    paths.append((part,target/'cached-parts'/(str(part.relative_to(parts))+'.bin')))
    manifest = {'item':record['item'],'account':record['account'],'message_id':record['message_id'],'numeric_id':record['current_id'],
      'partial': prior_manifest['partial'] if prior_manifest else local['partial'], 'server_retention': 'Not established',
      'completeness':dict(prior_manifest['completeness']) if prior_manifest else {'cached_parts_directory_present':parts_present,'discovered_cached_files_copied':True,'provider_attachment_completeness':'unknown'},'files': []}
    for original, destination in paths:
        parent = destination.parent
        while parent != target.parent:
            require(not parent.is_symlink(), 'Symlink in recovery destination path')
            parent = parent.parent
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        require(not destination.is_symlink() and destination.resolve().is_relative_to(target.resolve()), 'Recovery file escapes item directory')
        digest = hashlib.sha256(original.read_bytes()).hexdigest()
        if not destination.exists():
            shutil.copyfile(original, destination)
        destination.chmod(0o600)
        with destination.open('rb') as recovered:
            os.fsync(recovered.fileno())
        require(hashlib.sha256(destination.read_bytes()).hexdigest() == digest, 'Recovery hash mismatch')
        manifest['files'].append({'path': str(destination), 'sha256': digest})
    if prior_manifest is None:
        manifest['completeness']['discovered_cached_files_copied'] = True
    private_write(target/'manifest.json', json.dumps(manifest, indent=2)+'\n')
    return {'manifest': str(target/'manifest.json'), 'partial': local['partial']}


def move(record, destination, folder_map=None, pre_destination_ids=None):
    # All parameters are argv, not interpolated AppleScript or shell code.
    output = api('''set a to account (item 1 of argv)
set src to mailbox (item 2 of argv) of a
set dest to mailbox (item 3 of argv) of a
set wantedID to item 4 of argv as integer
set wantedMID to item 5 of argv
set found to (every message of src whose id is wantedID)
if count of found is not 1 then error "Exact source copy missing"
set m to item 1 of found
if message id of m is not wantedMID then error "Source identity changed"
set beforeIDs to id of every message of dest whose message id is wantedMID
set expectedText to item 7 of argv
set expectedIDs to {}
if expectedText is not "" then
 set oldDelimiters to AppleScript's text item delimiters
 set AppleScript's text item delimiters to tab
 set expectedIDs to text items of expectedText
 set AppleScript's text item delimiters to oldDelimiters
end if
if count of beforeIDs is not count of expectedIDs then error "Destination prestate changed"
repeat with candidate in beforeIDs
 if (candidate as text) is not in expectedIDs then error "Destination prestate changed"
end repeat
if (item 6 of argv) is "Junk" then set junk mail status of m to true
if (item 6 of argv) is not "Junk" then set junk mail status of m to false
set remaining to (every message of src whose id is wantedID)
if count of remaining is 1 then
 set m to item 1 of remaining
 if message id of m is not wantedMID then error "Copy identity changed during action"
 move m to dest
end if
set afterCopies to (every message of dest whose message id is wantedMID)
set added to {}
repeat with candidate in afterCopies
 if (id of candidate) is not in beforeIDs then set end of added to candidate
end repeat
if count of added is not 1 then error "Destination copy missing or ambiguous"
set verified to item 1 of added
if (item 6 of argv) is "Junk" and junk mail status of verified is false then error "Junk marking missing"
if (item 6 of argv) is not "Junk" and junk mail status of verified is true then error "Junk status not cleared"
if exists (first message of src whose id is wantedID) then error "Source copy still exists"
return (id of verified as text) & tab & (junk mail status of verified as text)''', record['account'], _folder(record['observed_mailbox'], folder_map), _folder(destination, folder_map), record['current_id'], record['message_id'], destination, '\t'.join(str(v) for v in (pre_destination_ids or [])))
    try:
        ident, junk = output.split('\t')
        numeric_id=int(ident)
    except ValueError as error:
        raise MailAPIError('Malformed Mail move response') from error
    expected_junk=destination=='Junk'
    if (junk=='true') is not expected_junk:
        raise MailAPIError('Mail move response did not satisfy destination Junk postcondition')
    return {'mailbox': destination, 'numeric_id': numeric_id, 'junk': junk == 'true'}


def destination_ids(record, destination, folder_map=None):
    output = api('''set a to account (item 1 of argv)
set dest to mailbox (item 2 of argv) of a
set found to every message of dest whose message id is (item 3 of argv)
set values to {}
repeat with m in found
 set end of values to id of m as text
end repeat
set AppleScript's text item delimiters to tab
return values as text''', record['account'], _folder(destination, folder_map), record['message_id'])
    try: return [int(v) for v in output.split('\t') if v]
    except ValueError as error: raise MailAPIError('Malformed destination-copy lookup response') from error


def apply(source, plan, journal, recovery, manifest_path=None, rules_path=None, folder_map=None, *, history_database=None):
    import config
    configured_account = config.CONFIG.get('account')
    selected_scope = [configured_account] if configured_account else None
    require(isinstance(selected_scope, (list, tuple, set)) and len(selected_scope) > 0, 'Mutation requires an explicitly configured selected account')
    selected_scope = sorted(set(selected_scope))
    require(all(isinstance(a, str) and a for a in selected_scope), 'Invalid selected account scope')
    if configured_account:
        require(selected_scope == [configured_account], 'Mutation scope differs from configured selected account')
    snapshot = normalize_snapshot(source)
    require(all(r['account'] in selected_scope for r in snapshot['records']), 'Snapshot exceeds trusted selected account scope')
    _validate_registered_baseline(snapshot, history_database)
    journal = Path(journal)
    if journal.exists() and journal.read_text().strip():
        raise ValueError('Journal already contains an attempt: reconcile it before generating a new plan; no blind replay')
    records = {r['item']: r for r in snapshot['records']}
    accounts = {records[a['item']]['account'] for a in plan['actions']}
    require(accounts <= set(selected_scope), 'Plan action exceeds trusted selected account scope')
    if folder_map is None:
        folder_map = config.CONFIG.get('folder_map') or {name: name for name in FOLDERS}
    require(set(folder_map) == set(FOLDERS) and all(isinstance(v, str) and v.strip() and len(v) <= 4000 and not any(ord(c) < 32 or ord(c) == 127 for c in v) for v in folder_map.values()), 'Invalid Mail folder-role mapping')
    require(len(set(folder_map.values())) == len(FOLDERS), 'Mail folder roles must map to distinct physical mailboxes')
    rules_path = Path(rules_path) if rules_path else config.resolve_rules_path()
    manifest_path = Path(manifest_path) if manifest_path else journal.with_suffix('.manifest.json')
    rules_hash = rules_digest(rules_path)
    if manifest_path.exists():
        manifest = validate_existing_manifest(manifest_path, snapshot, plan, rules_hash, authorized_accounts=selected_scope)
        validate_plan(snapshot, plan, trusted_started_at=manifest['started_at'])
    else:
        validate_plan(snapshot, plan)
        manifest = create_or_validate_manifest(manifest_path, snapshot, plan, rules_hash, authorized_accounts=selected_scope)
    validate_plan(snapshot, plan, trusted_started_at=manifest['started_at'])
    cache_root = cache_root_from_config(config.CONFIG) if config.CONFIG.get('database') and config.CONFIG.get('mailbox_prefix') else None
    outcomes = []
    for account in sorted(accounts):
        with account_locks([account]):
            current_actions = [a for a in plan['actions'] if records[a['item']]['account'] == account]
            current_items = {a['item'] for a in current_actions}
            if journal.exists():
                prior = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
                require(not any(e.get('item') in current_items and e.get('snapshot_id') == snapshot['snapshot_id'] for e in prior), 'Journal changed while waiting for account lock; reconcile before retry')
            policies = None
            if any(a['destination'] in ('Junk', 'Trash') for a in current_actions):
                policies = api('''set a to account (item 1 of argv)
return (empty junk messages frequency of a as text) & tab & (empty trash frequency of a as text) & tab & (empty junk messages on quit of a as text) & tab & (empty trash on quit of a as text)''', account)
            retained = [records[a['item']] for a in current_actions if records[a['item']]['observed_mailbox'] == a['destination']]
            retained_checks = lookup_many(retained, folder_map) if retained else {}
            for action in current_actions:
                record = records[action['item']]
                event = {'item': record['item'], 'account': record['account'], 'message_id': record['message_id'], 'old_id': record['current_id'], 'old_mailbox': record['observed_mailbox'], 'destination': action['destination'], 'reason': action['reason'], 'snapshot_id': snapshot['snapshot_id'], 'at': dt.datetime.now(dt.timezone.utc).isoformat()}
                intent_written = False
                try:
                    if record['observed_mailbox'] == action['destination']:
                        checked = retained_checks[(record['account'], record['message_id'], record['current_id'])]
                        if isinstance(checked, Exception): raise checked
                        junk = checked
                        require((action['destination'] == 'Junk' and junk) or (action['destination'] != 'Junk' and not junk), 'Retained message destination/Junk postcondition failed')
                        event.update(status='verified-retained', new_id=record['current_id'], junk=junk)
                    else:
                        event['pre_source_junk'] = lookup(record, folder_map)
                        if action['destination'] in ('Junk', 'Trash'):
                            event['deletion_policy'] = policies
                            event['recovery'] = backup(record, recovery, cache_root, config.STATE_ROOT/'recovery')
                        event['pre_destination_ids'] = destination_ids(record, action['destination'], folder_map)
                        event['attempt_id'] = uuid.uuid4().hex
                        append_event(journal, {**event, 'status': 'intent'}); intent_written = True
                        result = move(record, action['destination'], folder_map, event['pre_destination_ids'])
                        receipt = {k:event[k] for k in ('item','account','message_id','old_id','old_mailbox','destination','snapshot_id','attempt_id','pre_destination_ids','pre_source_junk')}
                        receipt.update(status='move-receipt', new_id=result['numeric_id'], junk=result['junk'], completed_at=dt.datetime.now(dt.timezone.utc).isoformat())
                        append_event(journal, receipt)
                        event.update(status='verified-moved', new_id=result['numeric_id'], junk=result['junk'], completed_at=receipt['completed_at'])
                    append_event(journal, event); outcomes.append(event)
                    print(record['item'], event['status'], action['destination'], flush=True)
                except ValueError as error:
                    if intent_written and not isinstance(error,ActionConflict): raise
                    conflict = {**event, 'status':'conflict-or-failed', 'error':str(error)}
                    append_event(journal, conflict); outcomes.append(conflict)
                    print(record['item'], conflict['status'], action['destination'], str(error), flush=True)
    return outcomes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', required=True);parser.add_argument('--plan', required=True)
    parser.add_argument('--journal');parser.add_argument('--recovery');parser.add_argument('--manifest');parser.add_argument('--apply', action='store_true');parser.add_argument('--sha256')
    args = parser.parse_args()
    raw = Path(args.plan).read_bytes();plan = json.loads(raw);source = read_json(args.snapshot)
    digest = hashlib.sha256(raw).hexdigest()
    print('Plan SHA-256:', digest)
    if not args.apply:
        manifest_path=Path(args.manifest) if args.manifest else None
        if manifest_path and manifest_path.exists():
            import config
            selected=config.CONFIG.get('account')
            require(selected,'A persisted manifest needs a configured selected account')
            manifest=validate_existing_manifest(manifest_path,normalize_snapshot(source),plan,rules_digest(config.resolve_rules_path()),authorized_accounts=[selected])
            validate_plan(source,plan,trusted_started_at=manifest['started_at'])
        else:
            validate_plan(source, plan)
        print('Validated', len(plan['actions']), 'actions; Mail unchanged.');return
    require(args.sha256 == digest and args.journal and args.recovery, 'Exact plan hash, journal and recovery path required')
    apply(source, plan, Path(args.journal), Path(args.recovery), Path(args.manifest) if args.manifest else None)

if __name__ == '__main__':
    os.umask(0o077)
    main()
