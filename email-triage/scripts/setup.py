#!/usr/bin/env python3
"""Guided, read-only account discovery and explicit local configuration."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import stat

from config import CONFIG_PATH, ROLES, validate_config, validate_folder_map


def discover_accounts(database=None):
    """Read account names from Mail and candidate index profiles, without pairing them."""
    script = '''tell application "Mail"
set outputText to ""
repeat with a in accounts
 set accountName to name of a
 repeat with m in mailboxes of a
  set outputText to outputText & accountName & tab & (name of m) & linefeed
 end repeat
end repeat
return outputText
end tell'''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise ValueError("Could not read account metadata from Apple Mail: " + result.stderr.strip())
    accounts = {}
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 2 or not all(parts):
            raise ValueError("Apple Mail returned malformed account metadata")
        accounts.setdefault(parts[0], set()).add(parts[1])
    dbpath = Path(database or Path.home() / "Library/Mail/V10/MailData/Envelope Index").expanduser()
    profiles = {}
    if dbpath.is_file():
        connection = sqlite3.connect(dbpath.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            for (url,) in connection.execute("SELECT url FROM mailboxes"):
                if not isinstance(url, str) or not url.startswith("imap://"):
                    continue
                authority, sep, mailbox = url[7:].partition("/")
                if sep and authority and mailbox:
                    prefix = "imap://" + authority + "/"
                    profiles.setdefault(prefix, set()).add(mailbox)
        finally:
            connection.close()
    return {"accounts": [{"name": name, "mailboxes": sorted(names)} for name, names in sorted(accounts.items())],
            "index_profiles": [{"mailbox_prefix": p, "mailboxes": sorted(names)} for p, names in sorted(profiles.items())],
            "database": str(dbpath)}


def metadata_accounts(metadata):
    if not isinstance(metadata, dict) or not isinstance(metadata.get("accounts"), list):
        raise ValueError("Metadata must contain an accounts list")
    result = []
    for entry in metadata["accounts"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str) or not entry["name"].strip():
            raise ValueError("Each account needs an exact nonempty name")
        mailboxes = entry.get("mailboxes")
        if isinstance(mailboxes, dict):
            physical = list(mailboxes.values())
            folder_map = validate_folder_map(mailboxes)
        elif isinstance(mailboxes, list) and all(isinstance(x, str) and x.strip() for x in mailboxes):
            physical, folder_map = mailboxes, None
        else:
            raise ValueError("Each account needs mailbox names or a canonical mailbox map")
        if len(set(physical)) != len(physical):
            raise ValueError("Duplicate mailbox names in account metadata")
        result.append({**entry, "physical_mailboxes": physical, "folder_map": folder_map})
    if len({a["name"] for a in result}) != len(result):
        raise ValueError("Duplicate account names in metadata")
    return result


def doctor(metadata, account=None, folder_map=None, mailbox_prefix=None, verify_adapter=None):
    accounts = metadata_accounts(metadata)
    if not accounts:
        raise ValueError("No Mail accounts were discovered")
    if account is None:
        if len(accounts) != 1:
            raise ValueError("Account selection required: multiple accounts are available")
        selected = accounts[0]
    else:
        matches = [a for a in accounts if a["name"] == account]
        if len(matches) != 1:
            raise ValueError("Selected account is not present exactly once in Mail metadata")
        selected = matches[0]
    mapping = validate_folder_map(folder_map or selected.get("folder_map") or None)
    missing = [name for name in mapping.values() if name not in selected["physical_mailboxes"]]
    if missing:
        raise ValueError("Mailbox mapping does not match selected account: " + ", ".join(missing))
    prefix = mailbox_prefix or selected.get("mailbox_prefix")
    database = Path(selected.get("database", metadata.get("database", ""))).expanduser()
    if not isinstance(prefix, str) or not prefix.strip():
        raise ValueError("Exact Mail index mailbox_prefix must be selected explicitly")
    if not str(database):
        raise ValueError("Local Mail index path is missing")
    if not prefix.startswith("imap://") or not prefix.endswith("/"):
        raise ValueError("Account metadata has an invalid mailbox_prefix")
    if not database.is_file():
        raise ValueError("Configured local Mail index does not exist: " + str(database))
    try:
        connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            rows = connection.execute("SELECT url FROM mailboxes WHERE substr(url,1,?)=?", (len(prefix), prefix)).fetchall()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise ValueError("Local Mail index cannot be read consistently: " + str(exc)) from None
    indexed = {row[0][len(prefix):] for row in rows if row[0].startswith(prefix)}
    missing_index = [name for name in mapping.values() if name not in indexed]
    if missing_index:
        raise ValueError("Mail index is missing configured mailbox(es): " + ", ".join(missing_index))
    adapter_verify = verify_adapter or verify_mail_ids
    api_ids = adapter_verify(selected["name"], mapping)
    if not isinstance(api_ids, dict) or set(api_ids) != set(ROLES):
        raise ValueError("Mail adapter did not verify all canonical mailbox roles")
    indexed_ids = {role: sorted(_index_ids(database, prefix, physical)) for role, physical in mapping.items()}
    if any(sorted(api_ids[role]) != indexed_ids[role] for role in ROLES):
        raise ValueError("Mail API and local Mail index message IDs differ")
    capabilities = selected.get("capabilities", {"read_only_inventory": True, "exact_identity": True, "recoverable_moves": True, "move_verification": True})
    if not isinstance(capabilities, dict) or any(capabilities.get(k) is not True for k in ("read_only_inventory", "exact_identity", "recoverable_moves", "move_verification")):
        raise ValueError("Adapter lacks required read-only inventory, exact identity, recoverable move, or verification capability")
    return {"account": selected["name"], "mailbox_prefix": prefix, "database": str(database),
            "folder_map": mapping, "capabilities": capabilities, "indexed_mailboxes": sorted(indexed), "verified_counts": {r: len(api_ids[r]) for r in ROLES}}


def _index_ids(database, prefix, physical):
    connection = sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        return [row[0] for row in connection.execute("SELECT m.rowid FROM messages m JOIN mailboxes b ON b.rowid=m.mailbox WHERE b.url=? AND m.deleted=0", (prefix + physical,))]
    finally:
        connection.close()


def verify_mail_ids(account, folder_map):
    """Read exact visible message IDs from Mail; no body or attachment access."""
    script = '''on run argv
set roleNames to {"INBOX", "Archive", "Junk", "Trash"}
set outputText to ""
with timeout of 20 seconds
 tell application "Mail"
  repeat with roleIndex from 1 to 4
   set physicalName to item (roleIndex + 1) of argv
   set roleName to item roleIndex of roleNames
   set ids to id of every message of mailbox physicalName of account (item 1 of argv)
   set AppleScript's text item delimiters to ","
   set idText to ids as text
   set outputText to outputText & roleName & "|" & (count of ids) & "|" & idText & linefeed
  end repeat
 end tell
end timeout
return outputText
end run'''
    result = subprocess.run(["osascript", "-e", script, account, *[folder_map[role] for role in ROLES]], capture_output=True, text=True, timeout=25)
    if result.returncode:
        raise ValueError("Apple Mail ID verification failed: " + result.stderr.strip())
    values = {}
    for line in result.stdout.strip().splitlines():
        role, count, ids = line.split("|", 2)
        if role not in ROLES or role in values or not count.isdigit():
            raise ValueError("Apple Mail returned malformed verification IDs")
        parsed = [int(x.strip()) for x in ids.split(",") if x.strip()]
        if len(parsed) != int(count) or len(set(parsed)) != len(parsed):
            raise ValueError("Apple Mail returned an invalid ID count")
        values[role] = parsed
    if set(values) != set(ROLES):
        raise ValueError("Apple Mail did not verify all mailbox roles")
    return values


def write_config_atomic(path, value):
    if not isinstance(value, dict) or "timezone" not in value:
        raise ValueError("New configuration requires an explicit IANA timezone")
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = (json.dumps(validate_config(value), indent=2, sort_keys=True) + "\n").encode()
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        # A hard link gives atomic create-if-absent semantics. Never replace a profile.
        try:
            os.link(temporary, path)
        except FileExistsError:
            raise ValueError("Configuration already exists; refusing to overwrite: " + str(path)) from None
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return path


def validate_private_path(path):
    """Require an existing private directory or a safely creatable user path."""
    original = Path(path).expanduser()
    if not original.is_absolute():
        raise ValueError("state_root must be an absolute path")
    if original.is_symlink():
        raise ValueError("state_root may not be a symlink")
    target = original
    target = target.resolve(strict=False)
    if target == Path("/tmp") or Path("/tmp") in target.parents or target == Path("/private/tmp") or Path("/private/tmp") in target.parents:
        raise ValueError("state_root may not be in a temporary directory")
    if target.exists():
        info = target.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError("Existing state_root must be a user-owned directory with owner-only permissions")
    else:
        parent = target.parent
        while not parent.exists() and parent != parent.parent:
            parent = parent.parent
        info = parent.stat()
        if info.st_uid != os.geteuid() or not os.access(parent, os.W_OK | os.X_OK):
            raise ValueError("state_root parent must be user-owned and writable")
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("accounts", help="read available account and mailbox names only")
    check = sub.add_parser("doctor", help="validate metadata, index, folders, and adapter capability")
    check.add_argument("--metadata", help="synthetic metadata JSON; omitting reads Apple Mail account names")
    check.add_argument("--account")
    check.add_argument("--folders", help="JSON object mapping canonical roles to physical names")
    check.add_argument("--mailbox-prefix", help="explicit exact account URL prefix from the local index")
    configure = sub.add_parser("configure", help="write a new owner-only config without overwriting an existing profile")
    configure.add_argument("--metadata")
    configure.add_argument("--account", required=True)
    configure.add_argument("--mailbox-prefix", required=True, help="explicit exact account URL prefix from the local index")
    configure.add_argument("--folders", required=True, help="JSON object mapping canonical roles to physical names")
    configure.add_argument("--timezone", required=True, help="IANA timezone name")
    configure.add_argument("--state-root", required=True)
    configure.add_argument("--output", help="private config path; defaults to EMAIL_TRIAGE_CONFIG or ignored-resources/email-triage/local-config.json")
    args = parser.parse_args(argv)
    if args.command == "accounts":
        print(json.dumps(discover_accounts(), indent=2))
        return 0
    metadata = json.loads(Path(args.metadata).read_text(encoding="utf-8")) if args.metadata else discover_accounts()
    folder_map = json.loads(args.folders) if getattr(args, "folders", None) else None
    if args.command == "doctor":
        print(json.dumps(doctor(metadata, args.account, folder_map, args.mailbox_prefix), indent=2))
        return 0
    checked = doctor(metadata, args.account, folder_map, args.mailbox_prefix)
    state_root = validate_private_path(args.state_root)
    settings = {k: checked[k] for k in ("account", "mailbox_prefix", "database", "folder_map", "capabilities")}
    settings.update(timezone=args.timezone, state_root=str(state_root))
    path = write_config_atomic(args.output or CONFIG_PATH, settings)
    print("Configured owner-only settings: " + str(path))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit("Setup failed: " + str(exc))
