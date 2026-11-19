import json
import shutil
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
from package_skill import package
import package_skill

class PackageTests(unittest.TestCase):
    def test_shared_copy_has_no_owner_config_and_cannot_inventory_without_setup(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive=Path(tmp)/'skill.zip'
            # Build from a fabricated local installation with private sentinels.
            source=Path(tmp)/'source';source.mkdir()
            root=Path(package_skill.__file__).resolve().parents[1]
            for name in package_skill.load_manifest(root):
                origin=root/('references/generic-rules.md' if name=='rules.md' else name)
                dest=source/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(origin,dest)
            (source/'rules.md').write_text('PRIVATE-PROFILE-SENTINEL')
            (source/'local-config.json').write_text('{"account":"PRIVATE-CONFIG-SENTINEL"}')
            result=subprocess.run([sys.executable,str(source/'scripts/package_skill.py'),str(archive)],text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            with zipfile.ZipFile(archive) as z:
                names=z.namelist()
                self.assertFalse(any('local-config' in name or 'recovery/' in name or 'history.sqlite' in name or '/tests/' in name for name in names))
                packaged={name.removeprefix('email-triage/') for name in names if name.startswith('email-triage/') and name!='email-triage/manifest.json'}
                self.assertTrue({'package-files.json','references/generic-rules.md','references/workflow.md','references/quality.md','scripts/workflow.py','scripts/execution.py','scripts/assessments.py','scripts/evaluate.py','scripts/rules_preview.py','references/evaluation-cases.json'} <= packaged)
                # Check the complete shared archive, including Help, references and scripts.
                for name in names:
                    text=z.read(name).decode('utf-8').casefold()
                    for personal in ('private-profile-sentinel','private-config-sentinel'):
                        self.assertNotIn(personal,text,name)
                rules=z.read('email-triage/rules.md').decode()
                self.assertNotIn('autopay. All',rules)
                self.assertNotIn('PRIVATE-PROFILE-SENTINEL',rules)
                z.extractall(tmp)
            env={**os.environ,'EMAIL_TRIAGE_CONFIG':str(Path(tmp)/'missing-config.json')}
            second=Path(tmp)/'repackaged.zip'
            result=subprocess.run([sys.executable,str(Path(tmp)/'email-triage/scripts/package_skill.py'),str(second)],env=env,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            with zipfile.ZipFile(second) as z:
                self.assertEqual(set(z.namelist()),{f'email-triage/{name}' for name in packaged}|{'email-triage/manifest.json'})
                manifest=json.loads(z.read('email-triage/manifest.json'))
                for name,digest in manifest.items():
                    self.assertEqual(hashlib.sha256(z.read('email-triage/'+name)).hexdigest(),digest,name)
            result=subprocess.run([sys.executable,str(Path(tmp)/'email-triage/scripts/refresh_mail.py'),'--base','nonexistent','--output',str(Path(tmp)/'out.json')],env=env,text=True,capture_output=True)
            self.assertEqual(result.returncode,2)
            self.assertIn('No Apple Mail account configured',result.stderr)
            self.assertFalse((Path(tmp)/'out.json').exists())

    def test_public_directory_export_is_repeatable_and_contains_only_reviewed_files(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'email-triage'
            package_skill.export_directory(target)
            manifest=json.loads((target/'package-files.json').read_text())
            expected=set(manifest['files'])|set(manifest['public_files'])
            actual={p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()}
            self.assertEqual(actual,expected)
            self.assertFalse((target/'local-config.json').exists())
            self.assertEqual((target/'rules.md').read_bytes(),(target/'references/generic-rules.md').read_bytes())
            before={name:(target/name).read_bytes() for name in expected}
            package_skill.export_directory(target)
            self.assertEqual(before,{name:(target/name).read_bytes() for name in expected})
            self.assertTrue((target/'tests/test_workflow.py').is_file())
            (target/'local-config.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'legacy local profile'):
                package_skill.export_directory(target)
            self.assertEqual((target/'rules.md').read_bytes(),before['rules.md'])

    def test_help_and_missing_directory_argument_do_not_create_an_archive(self):
        script=Path(package_skill.__file__).resolve()
        with tempfile.TemporaryDirectory() as folder:
            for args,expected in [(['--help'],0),(['--directory'],2)]:
                result=subprocess.run([sys.executable,str(script),*args],cwd=folder,text=True,capture_output=True)
                self.assertEqual(result.returncode,expected)
                self.assertEqual(list(Path(folder).iterdir()),[])

    def test_manifest_rejects_duplicate_and_symlink_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'package-files.json').write_text('{"files":["SKILL.md","SKILL.md","rules.md"]}')
            with self.assertRaisesRegex(ValueError,'Duplicate'):
                package_skill.load_manifest(root)
            (root/'package-files.json').write_text('{"files":["../private","rules.md","references/generic-rules.md"]}')
            with self.assertRaisesRegex(ValueError,'Unsafe'):
                package_skill.load_manifest(root)
        root=Path(package_skill.__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            extra=root/'scripts'/'_package_unlisted_test.py'
            extra.write_text('# synthetic')
            try:
                with self.assertRaisesRegex(ValueError,'Unlisted'):
                    package(root.parent/'does-not-matter.zip')
            finally:
                extra.unlink()
            linked=root/'scripts'/'_package_symlink_test.py'
            linked.symlink_to(Path(tmp)/'target')
            try:
                with self.assertRaisesRegex(ValueError,'Symlink'):
                    package(Path(tmp)/'should-not-exist.zip')
            finally:
                linked.unlink()
