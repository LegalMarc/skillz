#!/usr/bin/env python3
"""Export reviewed generic skill source for GitHub, or build an optional archive."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import zipfile


MANIFEST_PATH = "package-files.json"
PUBLISH_DIRS = ("scripts", "assets", "references")
RULE_SOURCE = "references/generic-rules.md"
RULE_TARGET = "rules.md"


def _safe_name(name):
    path = PurePosixPath(name)
    if not isinstance(name, str) or not name or path.is_absolute() or ".." in path.parts or "\\" in name or "\x00" in name:
        raise ValueError("Unsafe package path: " + repr(name))
    return name


def load_manifest(root):
    path = root / MANIFEST_PATH
    if path.is_symlink() or not path.is_file():
        raise ValueError("Reviewed package manifest is missing or is a symlink")
    value = json.loads(path.read_text(encoding="utf-8"))
    files = value.get("files") if isinstance(value, dict) else None
    if not isinstance(files, list) or not files or any(not isinstance(name, str) for name in files):
        raise ValueError("package-files.json must contain a nonempty files list")
    files = [_safe_name(name) for name in files]
    if len(files) != len(set(files)):
        raise ValueError("Duplicate paths in package manifest")
    if RULE_TARGET not in files or RULE_SOURCE not in files:
        raise ValueError("Manifest must include generic rules as rules.md and the generic rule source")
    return files


def _check_unlisted(root, listed):
    expected = set(listed) - {RULE_TARGET}
    expected.add(RULE_SOURCE)
    found = set()
    for name in ("SKILL.md", MANIFEST_PATH):
        path = root / name
        if path.is_symlink():
            raise ValueError("Symlink found in package source tree: " + name)
        if path.is_file():
            found.add(name)
    for directory in PUBLISH_DIRS:
        base = root / directory
        if base.is_symlink():
            raise ValueError("Symlink found in package source tree: " + directory)
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_symlink():
                raise ValueError("Symlink found in package source tree: " + str(path.relative_to(root)))
            if path.is_file() and "__pycache__" not in path.parts and path.name != ".DS_Store":
                found.add(path.relative_to(root).as_posix())
    unlisted = found - expected
    missing_sources = expected - found
    if unlisted:
        raise ValueError("Unlisted package source file(s): " + ", ".join(sorted(unlisted)))
    if missing_sources:
        raise ValueError("Manifest source file(s) missing: " + ", ".join(sorted(missing_sources)))


def _source_for(root, target):
    return root / (RULE_SOURCE if target == RULE_TARGET else target)


def _validate_payload(payload):
    path_pattern = re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+/")
    uuid_pattern = re.compile(r"imap://[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}/")
    for name, data in payload.items():
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("Package files must be UTF-8 text: " + name) from None
        if path_pattern.search(content) or uuid_pattern.search(content):
            raise ValueError("Personal installation detail in shared file: " + name)


def _verify_archive(archive_path, expected):
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Archive contains duplicate paths")
        expected_names = {"email-triage/" + name for name in expected}
        if set(names) != expected_names | {"email-triage/manifest.json"}:
            raise ValueError("Archive file set does not match reviewed manifest")
        for name in names:
            _safe_name(name)
        manifest = json.loads(archive.read("email-triage/manifest.json"))
        if set(manifest) != set(expected):
            raise ValueError("Archive hash manifest does not match packaged files")
        for name in expected:
            data = archive.read("email-triage/" + name)
            if hashlib.sha256(data).hexdigest() != manifest[name]:
                raise ValueError("Archive hash verification failed: " + name)
        # Force a safe extraction pass and validate the extracted bytes too.
        with tempfile.TemporaryDirectory() as temp:
            for info in archive.infolist():
                name = info.filename
                _safe_name(name)
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise ValueError("Archive contains a symlink: " + name)
                destination = Path(temp).joinpath(*PurePosixPath(name).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(archive.read(info))
            for name in expected:
                data = (Path(temp) / "email-triage" / name).read_bytes()
                if hashlib.sha256(data).hexdigest() != manifest[name]:
                    raise ValueError("Extracted archive hash verification failed: " + name)


def public_payload(root):
    root = Path(root)
    files = load_manifest(root)
    _check_unlisted(root, files)
    payload = {}
    for name in files:
        source = _source_for(root, name)
        if source.is_symlink() or not source.is_file():
            raise ValueError("Manifest source missing or is a symlink: " + str(source.relative_to(root)))
        payload[name] = source.read_bytes()
    _validate_payload(payload)
    return payload


def export_directory(output):
    """Export reviewed generic source and synthetic tests into a public checkout."""
    root = Path(__file__).resolve().parents[1]
    payload = public_payload(root)
    extras = json.loads((root / MANIFEST_PATH).read_text()).get('public_files', [])
    if not isinstance(extras, list) or any(not isinstance(n, str) for n in extras):
        raise ValueError('public_files must be a list of reviewed relative paths')
    if len(extras) != len(set(extras)) or set(extras) & set(payload):
        raise ValueError('Duplicate public export paths')
    for name in extras:
        _safe_name(name)
        if name != '.gitignore' and not name.startswith('tests/'):
            raise ValueError('Additional public files must be reviewed synthetic tests or .gitignore: ' + name)
        source = root / name
        if source.is_symlink() or not source.is_file():
            raise ValueError('Public export requires the complete source checkout: ' + name)
        payload[name] = source.read_bytes()
    _validate_payload(payload)
    requested = Path(output).expanduser().absolute()
    if requested.is_symlink():
        raise ValueError('Public export destination may not be a symlink')
    output = requested.resolve()
    if output == root or (output.exists() and output.samefile(root)):
        raise ValueError('Public export must use a separate checkout directory')
    if (output / 'local-config.json').exists():
        raise ValueError('Move the legacy local profile to ignored-resources before public export')
    # Check every destination before updating any public source file.
    for name in payload:
        destination = output / name
        for ancestor in (destination, *destination.parents):
            if ancestor.is_symlink():
                raise ValueError('Symlink in public export destination: ' + str(ancestor))
        if destination.exists() and not destination.is_file():
            raise ValueError('Public export destination is not a file: ' + name)
    for name, data in sorted(payload.items()):
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    print(f'Exported {len(payload)} reviewed public files: {output}')


def package(output):
    root = Path(__file__).resolve().parents[1]
    payload = public_payload(root)
    files = list(payload)
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(payload.items())}
    output = Path(output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=".email-triage-", suffix=".zip", dir=output.parent, delete=False) as temp:
        temp_path = Path(temp.name)
    try:
        with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(payload.items()):
                archive.writestr("email-triage/" + name, data)
            archive.writestr("email-triage/manifest.json", json.dumps(hashes, indent=2, sort_keys=True) + "\n")
        _verify_archive(temp_path, files)
        temp_path.replace(output)
        output.chmod(0o600)
    finally:
        temp_path.unlink(missing_ok=True)
    print(f"Packaged and verified {len(payload)} generic files: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', help='export reviewed generic source and synthetic tests into a public checkout')
    parser.add_argument('archive', nargs='?', help='optional ZIP archive destination')
    args = parser.parse_args()
    if bool(args.directory) == bool(args.archive):
        parser.error('choose either --directory PUBLIC_CHECKOUT/email-triage or OUTPUT.zip')
    if args.directory:
        export_directory(args.directory)
    else:
        package(args.archive)
