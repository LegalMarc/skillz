import json
from contextlib import closing
from pathlib import Path
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import config
import setup


class ConfigurationPathsTests(unittest.TestCase):
    def test_private_config_is_default_with_legacy_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);skill=root/'email-triage';skill.mkdir()
            private=root/'ignored-resources/email-triage/local-config.json'
            self.assertEqual(config.default_config_path(skill),private)
            legacy=skill/'local-config.json';legacy.write_text('{}')
            self.assertEqual(config.default_config_path(skill),legacy)
            private.parent.mkdir(parents=True);private.write_text('{}')
            self.assertEqual(config.default_config_path(skill),private)

    def test_personal_rules_are_selected_without_replacing_shared_rules(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);skill=root/'email-triage';skill.mkdir()
            shared=skill/'rules.md';shared.write_text('Generic')
            profile=root/'ignored-resources/email-triage';profile.mkdir(parents=True)
            settings=profile/'local-config.json';personal=profile/'rules.md';personal.write_text('Personal')
            self.assertEqual(config.resolve_rules_path({},settings,skill),shared)
            settings.write_text('{}')
            self.assertEqual(config.resolve_rules_path({},settings,skill),personal)
            self.assertEqual(config.resolve_rules_path({'rules_path':'custom.md'},settings,skill),profile/'custom.md')
            self.assertEqual(config.resolve_rules_path({},skill/'local-config.json',skill),shared)
            self.assertEqual(shared.read_text(),'Generic')


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.index = self.root / "Envelope Index"
        with closing(sqlite3.connect(self.index)) as db:
            db.execute("CREATE TABLE mailboxes (url TEXT)")
            db.commit()
        self.map = {"INBOX": "Inbox", "Archive": "All Mail", "Junk": "Spam", "Trash": "Deleted"}
        with closing(sqlite3.connect(self.index)) as db:
            db.executemany("INSERT INTO mailboxes VALUES (?)", [("imap://synthetic-account/" + n,) for n in self.map.values()])
            db.execute("CREATE TABLE messages (rowid INTEGER PRIMARY KEY, mailbox INTEGER, deleted INTEGER)")
            db.execute("CREATE TABLE mailbox_ids (id INTEGER PRIMARY KEY, url TEXT)")
            db.executemany("INSERT INTO mailbox_ids VALUES (?,?)", [(i, "imap://synthetic-account/" + name) for i, name in enumerate(self.map.values(), 1)])
            db.executemany("INSERT INTO messages(mailbox, deleted) VALUES (?,0)", [(i,) for i in range(1, 5)])
            db.commit()
        self.metadata = {"accounts": [{"name": "Synthetic", "mailboxes": list(self.map.values()),
            "mailbox_prefix": "imap://synthetic-account/", "database": str(self.index),
            "capabilities": {"read_only_inventory": True, "exact_identity": True, "recoverable_moves": True, "move_verification": True}}]}
        self.verify = lambda account, mapping: {role: [i] for i, role in enumerate(mapping, 1)}

    def test_ambiguous_accounts_and_missing_nonstandard_folders_fail_closed(self):
        second = json.loads(json.dumps(self.metadata["accounts"][0]))
        second["name"] = "Synthetic 2"
        ambiguous = {"accounts": self.metadata["accounts"] + [second]}
        with self.assertRaisesRegex(ValueError, "Account selection required"):
            setup.doctor(ambiguous)
        with self.assertRaisesRegex(ValueError, "does not match"):
            setup.doctor(self.metadata, "Synthetic", {**self.map, "Trash": "Missing"}, verify_adapter=self.verify)

    def test_explicit_nonstandard_folder_roles_validate_index_and_timezone(self):
        result = setup.doctor(self.metadata, "Synthetic", self.map, verify_adapter=self.verify)
        self.assertEqual(result["folder_map"], self.map)
        value = {"account": "Synthetic", "mailbox_prefix": "imap://synthetic-account/", "database": str(self.index),
                 "folder_map": self.map, "timezone": "America/New_York"}
        self.assertEqual(config.validate_config(value)["timezone"], "America/New_York")
        with self.assertRaisesRegex(ValueError, "IANA"):
            config.validate_config({**value, "timezone": "Mars/Olympus"})

    def test_missing_index_mailbox_and_capability_fail_closed(self):
        broken = self.root / "broken.sqlite"
        with closing(sqlite3.connect(broken)) as db:
            db.execute("CREATE TABLE mailboxes (url TEXT)")
            db.execute("INSERT INTO mailboxes VALUES (?)", ("imap://synthetic-account/INBOX",))
            db.commit()
        metadata = json.loads(json.dumps(self.metadata))
        metadata["accounts"][0]["database"] = str(broken)
        with self.assertRaisesRegex(ValueError, "missing configured mailbox"):
            setup.doctor(metadata, "Synthetic", self.map, verify_adapter=self.verify)
        metadata["accounts"][0]["database"] = str(self.index)
        metadata["accounts"][0]["capabilities"]["recoverable_moves"] = False
        with self.assertRaisesRegex(ValueError, "lacks required"):
            setup.doctor(metadata, "Synthetic", self.map, verify_adapter=self.verify)

    def test_owner_only_atomic_config_creation_never_overwrites(self):
        target = self.root / "settings.json"
        settings = {"account": "Synthetic", "mailbox_prefix": "imap://synthetic-account/", "database": str(self.index),
                    "state_root": str(self.root / "state"), "timezone": "UTC", "folder_map": self.map}
        with self.assertRaisesRegex(ValueError, "explicit IANA timezone"):
            setup.write_config_atomic(target, {key: value for key, value in settings.items() if key != "timezone"})
        setup.write_config_atomic(target, settings)
        before = target.read_bytes()
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
            setup.write_config_atomic(target, {**settings, "account": "Changed"})
        self.assertEqual(target.read_bytes(), before)

    def test_folder_map_rejects_duplicates_empty_and_controls(self):
        for bad in ({**self.map, "Trash": "Spam"}, {**self.map, "Junk": ""}, {**self.map, "Junk": "Spam\n"}):
            with self.assertRaises(ValueError):
                config.validate_folder_map(bad)

    def test_mailbox_names_are_argv_data_and_script_compiles(self):
        mapping={'INBOX':'Inbox\\','Archive':'Archive "All"','Junk':'Spam 📨','Trash':'Deleted Messages'}
        captured=[]
        def fake_run(args,**kwargs):
            captured.append((args,kwargs))
            return SimpleNamespace(returncode=0,stdout='INBOX|0|\nArchive|0|\nJunk|0|\nTrash|0|\n',stderr='')
        with patch.object(setup.subprocess,'run',side_effect=fake_run):
            self.assertEqual(setup.verify_mail_ids('Synthetic',mapping),{'INBOX':[],'Archive':[],'Junk':[],'Trash':[]})
        args,kwargs=captured[0]
        script=args[2]
        self.assertEqual(args[3:],['Synthetic',*mapping.values()])
        for physical in mapping.values():self.assertNotIn(physical,script)
        compiler=shutil.which('osacompile')
        if not compiler:self.skipTest('osacompile unavailable; AppleScript source/argv separation was checked')
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'setup-bridge.scpt'
            result=subprocess.run([compiler,'-o',str(target),'-'],input=script,text=True,capture_output=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertTrue(target.is_file())

    def test_private_state_path_requires_private_owned_directory_and_rejects_tmp(self):
        state = self.root / "private-state"
        state.mkdir(mode=0o700)
        self.assertEqual(setup.validate_private_path(state), state.resolve())
        broad = self.root / "broad-state"
        broad.mkdir(mode=0o755)
        with self.assertRaisesRegex(ValueError, "owner-only"):
            setup.validate_private_path(broad)
        with self.assertRaisesRegex(ValueError, "temporary"):
            setup.validate_private_path(Path("/tmp") / "email-triage-state")
        link = self.root / "state-link"
        link.symlink_to(state, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            setup.validate_private_path(link)

    def test_legacy_timezone_uses_explicit_snapshot_timezone_but_explicit_config_must_match(self):
        legacy_path = Path(__file__).parent / "fixtures" / "legacy-config-no-timezone.json"
        settings, timezone_explicit = config.load_config(legacy_path, with_metadata=True)
        self.assertFalse(timezone_explicit)
        self.assertEqual(settings["timezone"], "UTC")
        self.assertEqual(config.resolve_snapshot_timezone("America/New_York", settings, explicit=timezone_explicit), "America/New_York")
        with self.assertRaisesRegex(ValueError, "explicitly selected configuration"):
            config.resolve_snapshot_timezone("America/New_York", {"timezone": "UTC"})
        self.assertEqual(config.resolve_snapshot_timezone("America/New_York", {"timezone": "America/New_York"}), "America/New_York")
        with self.assertRaisesRegex(ValueError, "IANA"):
            config.resolve_snapshot_timezone("Local/Unknown", settings, explicit=timezone_explicit)


if __name__ == "__main__":
    unittest.main()
