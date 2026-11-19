"""Durable authorization, per-account serialization and interrupted-action checks."""
import fcntl
import hashlib
import json
import os
import re
import datetime as dt
import stat
import threading
from contextlib import ExitStack
from contextlib import contextmanager
from pathlib import Path

from review import private_write, require


_transaction_state = threading.local()


def account_lock_root():
    """One account-global root independent of journals, runs, and configured state roots."""
    return Path.home().resolve(strict=True)/'Library/Application Support/Email Triage/account-locks'


@contextmanager
def account_locks(accounts):
    requested = _validated_accounts(accounts, allow_empty=True)
    state = _current_transaction_state()
    if state is not None:
        require(requested <= state['accounts'], 'Nested account lock may not expand the active transaction scope')
        yield
        return
    with _acquire_account_locks(requested):
        yield


def _validated_accounts(accounts, allow_empty=False):
    require(not isinstance(accounts, str), 'Account lock scope must be a collection of account names')
    try:requested = set(accounts)
    except TypeError as error:raise ValueError('Account lock scope must be a collection of account names') from error
    require((allow_empty or requested) and all(isinstance(account, str) and account.strip() for account in requested), 'Account lock requires nonempty account names')
    return requested


def _current_transaction_state():
    state = getattr(_transaction_state, 'active', None)
    if state is None:return None
    if state['pid'] != os.getpid() or state['thread_id'] != threading.get_ident():
        # In particular, forked children must open and contend on their own lock.
        return None
    return state


@contextmanager
def _acquire_account_locks(accounts):
    with ExitStack() as stack:
        root = account_lock_root()
        for account in sorted(set(accounts)):
            stack.enter_context(account_lock(root, account))
        yield


@contextmanager
def account_transaction(accounts):
    """Hold each account's fixed global lock across one complete coordinator run.

    Nested calls may reuse only a subset of this real lock scope. Ownership is
    process and thread bound; forked processes and other threads must contend.
    """
    requested = _validated_accounts(accounts)
    state = _current_transaction_state()
    if state is not None:
        require(requested <= state['accounts'], 'Nested account transaction may not expand its active scope')
        state['depth'] += 1
        try:yield
        finally:state['depth'] -= 1
        return
    with _acquire_account_locks(requested):
        active = {'accounts': requested, 'pid': os.getpid(), 'thread_id': threading.get_ident(), 'depth': 1}
        _transaction_state.active = active
        try:yield
        finally:
            if getattr(_transaction_state, 'active', None) is active:
                del _transaction_state.active


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def rules_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _manifest_payload(snapshot, plan, rules_hash, accounts, trusted_start, parent_manifest_sha256=None):
    require(isinstance(trusted_start, str), 'Manifest has no trusted start time')
    start = dt.datetime.fromisoformat(trusted_start.replace('Z', '+00:00'))
    require(start.tzinfo is not None, 'Manifest start needs an explicit timezone')
    trusted_start = start.astimezone(dt.timezone.utc).isoformat()
    payload = {
        'schema': 2, 'snapshot_id': snapshot['snapshot_id'],
        'plan_digest': _digest(plan), 'accounts': accounts,
        'started_at': trusted_start, 'claimed_started_at': plan.get('started_at'),
        'cutoff_at': (dt.datetime.fromisoformat(trusted_start.replace('Z', '+00:00'))-dt.timedelta(days=30)).isoformat(),
        'permitted_actions': [dict(a) for a in plan['actions']],
        'rules_digest': rules_hash, 'authorization': plan['authorization'],
        'user_review_export_sha256': (plan.get('user_review_evidence') or {}).get('export_sha256'),
        'age_overrides': [dict(a['age_override']) for a in plan['actions'] if 'age_override' in a],
    }
    if parent_manifest_sha256 is not None:
        require(re.fullmatch(r'[0-9a-f]{64}', parent_manifest_sha256), 'Invalid parent manifest digest')
        payload['parent_manifest_sha256'] = parent_manifest_sha256
    return payload


def _scope_and_plan(snapshot, plan, rules_hash, authorized_accounts):
    require(re.fullmatch(r'[0-9a-f]{64}', rules_hash or '') is not None, 'Invalid rules digest')
    by_item = {r['item']: r for r in snapshot['records']}
    accounts = sorted(set(authorized_accounts if authorized_accounts is not None else snapshot.get('account_scope', [])))
    require(accounts and all(isinstance(a, str) and a for a in accounts), 'Manifest requires an explicit authorized account scope')
    require(all(by_item[a['item']]['account'] in accounts for a in plan['actions']), 'Plan account exceeds frozen manifest scope')
    return accounts


def validate_existing_manifest(path, snapshot, plan, rules_hash, authorized_accounts=None, parent_manifest_sha256=None):
    """Read-only validation before trusting a persisted manifest clock for plan gates."""
    target = Path(path)
    require(target.is_file() and not target.is_symlink(), 'Persisted manifest is unavailable or may be a symlink')
    try:existing = json.loads(target.read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError) as error:raise ValueError('Persisted manifest is invalid') from error
    require(isinstance(existing, dict) and existing.get('schema') == 2, 'Legacy manifest cannot authorize current mutation')
    accounts = _scope_and_plan(snapshot, plan, rules_hash, authorized_accounts)
    recorded_parent = existing.get('parent_manifest_sha256')
    if parent_manifest_sha256 is not None:
        require(recorded_parent == parent_manifest_sha256, 'Continuation manifest parent digest mismatch')
    elif recorded_parent is not None:
        require(re.fullmatch(r'[0-9a-f]{64}', recorded_parent or '') is not None, 'Invalid parent manifest digest')
        parent_manifest_sha256 = recorded_parent
    expected = _manifest_payload(snapshot, plan, rules_hash, accounts, existing.get('started_at'), parent_manifest_sha256)
    require(existing == expected, 'Persisted run manifest mismatch; authorization is frozen')
    return existing


def create_or_validate_manifest(path, snapshot, plan, rules_hash, authorized_accounts=None, *, inherited_manifest=None, parent_manifest_sha256=None):
    """Persist authorization once; continuations inherit only a verified parent clock."""
    target = Path(path)
    accounts = _scope_and_plan(snapshot, plan, rules_hash, authorized_accounts)
    if inherited_manifest is not None:
        require(isinstance(inherited_manifest, dict) and inherited_manifest.get('schema') == 2, 'Continuation requires a verified current manifest')
        require(inherited_manifest.get('rules_digest') == rules_hash and inherited_manifest.get('accounts') == accounts, 'Continuation manifest policy differs from parent')
        start = dt.datetime.fromisoformat(inherited_manifest['started_at'].replace('Z', '+00:00'))
        require(start.tzinfo is not None and inherited_manifest.get('cutoff_at') == (start.astimezone(dt.timezone.utc)-dt.timedelta(days=30)).isoformat(), 'Parent manifest trusted cutoff is invalid')
        require(parent_manifest_sha256 is not None and re.fullmatch(r'[0-9a-f]{64}', parent_manifest_sha256), 'Continuation parent manifest digest is required')
        trusted_start = inherited_manifest['started_at']
    else:
        require(parent_manifest_sha256 is None, 'Parent digest requires an inherited manifest')
        trusted_start = dt.datetime.now(dt.timezone.utc).isoformat()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    require(not target.is_symlink(), 'Manifest may not be a symlink')
    if target.exists():
        manifest = validate_existing_manifest(target, snapshot, plan, rules_hash, accounts,
            parent_manifest_sha256=parent_manifest_sha256 if inherited_manifest is not None else None)
    else:
        manifest = _manifest_payload(snapshot, plan, rules_hash, accounts, trusted_start, parent_manifest_sha256)
        private_write(target, json.dumps(manifest, indent=2, sort_keys=True)+'\n')
    target.chmod(0o600)
    return manifest


@contextmanager
def account_lock(lock_root, account):
    """A kernel advisory lock serializes writers; old lock files are safe to reuse."""
    name = hashlib.sha256(account.encode()).hexdigest()+'.lock'
    root = Path(lock_root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    require(not root.is_symlink() and root.is_dir() and root.absolute()==root.resolve(strict=True), 'Account-global lock root path must be canonical and contain no symlinks')
    root.chmod(0o700)
    path = root/name
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        mode=os.fstat(fd).st_mode
        require(stat.S_ISREG(mode) and os.fstat(fd).st_nlink==1, 'Account lock must be a private regular file')
        os.fchmod(fd,0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            raise ValueError('Another mutating run owns this account lock') from e
        os.ftruncate(fd, 0)
        os.write(fd, json.dumps({'pid': os.getpid(), 'account_digest': hashlib.sha256(account.encode()).hexdigest()}).encode())
        os.fsync(fd)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def append_event(journal, value):
    journal = Path(journal)
    journal.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(journal, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        payload = memoryview((json.dumps(value, sort_keys=True)+'\n').encode())
        while payload:
            payload = payload[os.write(fd, payload):]
        os.fsync(fd)
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    journal.chmod(0o600)


def reconcile(journal, inspect_destination):
    """Public reconciliation always holds the fixed global lock for every journal account."""
    events = [json.loads(line) for line in Path(journal).read_text().splitlines() if line.strip()]
    accounts = {e.get('account') for e in events if e.get('account')}
    with account_locks(accounts):
        return _reconcile_locked(journal, inspect_destination)


def _reconcile_locked(journal, inspect_destination):
    """Internal reconciliation body; caller must already hold global locks for all accounts."""
    events = [json.loads(line) for line in Path(journal).read_text().splitlines() if line.strip()]
    receipts = {}
    for e in events:
        if e.get('status') == 'move-receipt':
            receipts.setdefault(e.get('attempt_id'), []).append(e)
    verified_attempts=set()
    for event in (e for e in events if e.get('status')=='verified-moved' and e.get('attempt_id')):
        matches=receipts.get(event['attempt_id'],[])
        if len(matches)==1 and all(matches[0].get(k)==event.get(k) for k in ('attempt_id','account','item','message_id','old_id','old_mailbox','destination','snapshot_id','new_id','junk','pre_destination_ids','pre_source_junk')):
            verified_attempts.add(event['attempt_id'])
    reconciled_attempts={e.get('attempt_id') for e in events if e.get('status') in ('verified-completed','verified-not-started','ambiguous') and e.get('attempt_id')}
    out = []
    for intent in (e for e in events if e.get('status') == 'intent'):
        attempt = intent.get('attempt_id')
        if attempt in verified_attempts or attempt in reconciled_attempts:
            continue
        receipt_list = receipts.get(attempt, []) if attempt else []
        before = intent.get('pre_destination_ids')
        state = inspect_destination(intent)
        ids = state.get('destination_ids')
        copies = state.get('destination_copies')
        source_present = state.get('source_present')
        source_exact = state.get('source_exact')
        source_junk = state.get('source_junk')
        status = 'ambiguous'; new_id = None
        if (isinstance(before, list) and len(before) == len(set(before)) and isinstance(ids, list)
                and len(ids) == len(set(ids)) and state.get('identity_matches') is True):
            if (not receipt_list and set(ids) == set(before) and source_present is True and source_exact is True
                    and type(source_junk) is bool and source_junk is intent.get('pre_source_junk')):
                status = 'verified-not-started'
            elif len(receipt_list) == 1 and source_present is False and source_exact is False:
                receipt = receipt_list[0]
                receipt_identity = all(receipt.get(k) == intent.get(k) for k in ('attempt_id','account','item','message_id','old_id','old_mailbox','destination','pre_destination_ids','pre_source_junk'))
                rid = receipt.get('new_id')
                expected_junk = intent.get('destination') == 'Junk'
                copy = next((c for c in copies or [] if c.get('numeric_id') == rid), None)
                complete_destination = set(ids) == set(before) | {rid} and copy is not None and copy.get('message_id') == intent.get('message_id') and copy.get('junk') is expected_junk
                receipt_valid = type(rid) is int and rid not in before and receipt.get('junk') is expected_junk
                receipt_valid = receipt_valid and type(receipt.get('pre_source_junk')) is bool
                if receipt_identity and receipt_valid and complete_destination:
                    status='verified-completed';new_id=rid
        result = {k:v for k,v in intent.items() if k != 'status'}
        result.update(status=status, new_id=new_id)
        if status == 'verified-completed':
            receipt = receipt_list[0]
            result.update(junk=receipt['junk'],completed_at=receipt.get('completed_at'),receipt_attempt_id=attempt)
        append_event(journal, result)
        out.append(result)
    return out
