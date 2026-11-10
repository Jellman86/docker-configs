import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
DUMP='growlog-20261110T160057Z.dump'

class CroftviewBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.source=self.root/'source';self.source.mkdir()
        (self.source/DUMP).write_bytes(b'fixture')
        self.script=self.root/'guard.sh'
        self.script.write_text((ROOT/'croftview-guard.sh').read_text().replace('/source/croftview',str(self.source)))
        self.script.chmod(0o755)
        tool=self.root/'duplicati-backend-tool'
        tool.write_text('#!/bin/sh\nprintf "%s\\n" "$TEST_LISTING"\nexit "${TEST_EXIT:-0}"\n')
        tool.chmod(0o755)
        self.env=dict(os.environ,PATH=str(self.root)+':'+os.environ['PATH'],DUPLICATI__OPERATIONNAME='Backup',DUPLICATI__REMOTEURL='onedrivev2://QuarkBackups/croftview?authid=test-only',TEST_LISTING='Name\tDir/File\tLastChange\tSize\nduplicati-test\tFile\ttoday\t2.50 MiB')

    def run_guard(self):
        return subprocess.run([str(self.script)],env=self.env,capture_output=True,text=True)

    def test_current_usage_allowed(self):
        self.assertEqual(self.run_guard().returncode,0)

    def test_empty_new_destination_allowed(self):
        self.env['TEST_LISTING']='Name\tDir/File\tLastChange\tSize'
        self.assertEqual(self.run_guard().returncode,0)

    def test_allocation_with_headroom_enforced(self):
        self.env['TEST_LISTING']='Name\tDir/File\tLastChange\tSize\nduplicati-test\tFile\ttoday\t35.00 GiB'
        result=self.run_guard()
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Croftview allocation',result.stderr)

    def test_quark_destination_refused(self):
        self.env['DUPLICATI__REMOTEURL']='onedrivev2://QuarkBackups/app-recovery?authid=test-only'
        self.assertNotEqual(self.run_guard().returncode,0)

    def test_listing_failure_closed_and_secret_not_logged(self):
        self.env.update(TEST_EXIT='1',TEST_LISTING=self.env['DUPLICATI__REMOTEURL'])
        result=self.run_guard()
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn('test-only',result.stdout+result.stderr)

    def test_no_dumps_refused(self):
        (self.source/DUMP).unlink()
        self.assertNotEqual(self.run_guard().returncode,0)

    def test_oversized_dump_refused(self):
        with (self.source/DUMP).open('r+b') as stream:
            stream.truncate(1073741825)
        self.assertNotEqual(self.run_guard().returncode,0)

    def test_too_many_dumps_refused(self):
        for hour in range(201):
            (self.source/f'growlog-20261101T{hour:06d}Z.dump').write_bytes(b'x')
        self.assertNotEqual(self.run_guard().returncode,0)

    def test_restore_is_not_blocked(self):
        self.env.update(DUPLICATI__OPERATIONNAME='Restore',TEST_EXIT='1')
        self.assertEqual(self.run_guard().returncode,0)

if __name__=='__main__': unittest.main()
