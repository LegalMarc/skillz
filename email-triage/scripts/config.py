"""Validated local settings. Shared installations do not select an account."""
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROLES = ("INBOX", "Archive", "Junk", "Trash")
DEFAULT_FOLDER_MAP = {role: role for role in ROLES}
SKILL_ROOT = Path(__file__).resolve().parents[1]


def default_config_path(skill_root=SKILL_ROOT):
    skill_root = Path(skill_root)
    private = skill_root.parent / 'ignored-resources' / 'email-triage' / 'local-config.json'
    legacy = skill_root / 'local-config.json'
    return private if private.exists() or not legacy.exists() else legacy


CONFIG_PATH = Path(os.environ.get(
    "EMAIL_TRIAGE_CONFIG",
    str(default_config_path()),
)).expanduser()


def validate_folder_map(value):
    if value is None:
        return dict(DEFAULT_FOLDER_MAP)
    if not isinstance(value, dict) or set(value) != set(ROLES):
        raise ValueError("folder_map must map exactly INBOX, Archive, Junk, and Trash")
    names = []
    for role in ROLES:
        name = value[role]
        if not isinstance(name, str) or not name.strip() or len(name) > 512 or any(ord(c) < 32 or ord(c) == 127 for c in name):
            raise ValueError("folder_map values must be nonempty physical mailbox names without control characters")
        if name != name.strip():
            raise ValueError("folder_map values may not have surrounding whitespace")
        names.append(name)
    if len(set(names)) != len(ROLES):
        raise ValueError("folder_map values must be distinct physical mailboxes")
    return dict(value)


def folder_name(role, settings=None):
    if role not in ROLES:
        raise ValueError("Unknown canonical mailbox role: " + str(role))
    settings = CONFIG if settings is None else settings
    return validate_folder_map(settings.get("folder_map"))[role]


def folder_role(physical_name, settings=None):
    settings = CONFIG if settings is None else settings
    mapping = validate_folder_map(settings.get("folder_map"))
    matches = [role for role, name in mapping.items() if name == physical_name]
    if len(matches) != 1:
        raise ValueError("Physical mailbox does not identify one configured canonical role")
    return matches[0]


def validate_config(value):
    if not isinstance(value, dict):
        raise ValueError("Email triage configuration must be an object")
    for key in ("account", "mailbox_prefix", "database", "state_root", "rules_path"):
        if key in value and (not isinstance(value[key], str) or not value[key].strip()):
            raise ValueError("Invalid email triage setting: " + key)
    if "account" in value and ("\n" in value["account"] or "\r" in value["account"]):
        raise ValueError("Invalid email triage setting: account")
    if "mailbox_prefix" in value and not (value["mailbox_prefix"].startswith("imap://") and value["mailbox_prefix"].endswith("/")):
        raise ValueError("mailbox_prefix must be an exact imap:// account URL prefix ending in /")
    value = dict(value)
    value["folder_map"] = validate_folder_map(value.get("folder_map"))
    timezone = value.get("timezone", "UTC")
    if not isinstance(timezone, str) or not timezone.strip():
        raise ValueError("timezone must be an IANA timezone name")
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("timezone must be a valid IANA timezone name") from None
    value["timezone"] = timezone
    return value


def _validate_timezone(timezone):
    if not isinstance(timezone, str) or not timezone.strip():
        raise ValueError("timezone must be an IANA timezone name")
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("timezone must be a valid IANA timezone name") from None
    return timezone


def resolve_snapshot_timezone(snapshot_timezone, settings=None, *, explicit=None):
    """Keep legacy run snapshots in their recorded zone; enforce new explicit settings."""
    snapshot_timezone = _validate_timezone(snapshot_timezone)
    if settings is None:
        settings = CONFIG
        explicit = CONFIG_TIMEZONE_EXPLICIT if explicit is None else explicit
    elif explicit is None:
        # A plain supplied settings mapping represents exactly what it contains.
        explicit = "timezone" in settings
    if explicit:
        configured = _validate_timezone(settings.get("timezone"))
        if configured != snapshot_timezone:
            raise ValueError("Snapshot timezone differs from explicitly selected configuration")
        return configured
    return snapshot_timezone


def load_config(path=None, *, with_metadata=False):
    path = CONFIG_PATH if path is None else Path(path).expanduser()
    if not path.exists():
        raw = {}
    else:
        raw = json.loads(path.read_text(encoding="utf-8"))
    explicit = isinstance(raw, dict) and "timezone" in raw
    value = validate_config(raw)
    return (value, explicit) if with_metadata else value


CONFIG, CONFIG_TIMEZONE_EXPLICIT = load_config(with_metadata=True)
STATE_ROOT = Path(CONFIG.get("state_root", str(Path.home() / ".local/share/email-triage"))).expanduser()


def resolve_rules_path(settings=None, config_path=None, skill_root=SKILL_ROOT):
    settings = CONFIG if settings is None else settings
    config_path = CONFIG_PATH if config_path is None else Path(config_path).expanduser()
    configured = settings.get('rules_path')
    if configured:
        path = Path(configured).expanduser()
        return path if path.is_absolute() else config_path.parent / path
    private = config_path.parent / 'rules.md'
    if config_path.is_file() and config_path.parent.resolve() != Path(skill_root).resolve() and private.is_file():
        return private
    return Path(skill_root) / 'rules.md'


RULES_PATH = resolve_rules_path()


if __name__ == '__main__':
    print(json.dumps({'config_path':str(CONFIG_PATH), 'rules_path':str(RULES_PATH),
                      'state_root':str(STATE_ROOT)},indent=2))
