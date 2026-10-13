import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('app_backup', Path(__file__).parents[1] / 'app_backup.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BackupTests(unittest.TestCase):
    def test_online_sqlite_backup_contains_wal_commits(self):
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / 'live.db'
            dst = Path(directory) / 'recovery.db'
            with sqlite3.connect(src) as writer:
                writer.execute('PRAGMA journal_mode=WAL')
                writer.execute('CREATE TABLE important(value TEXT)')
                writer.execute("INSERT INTO important VALUES ('committed while WAL open')")
                writer.commit()
                self.assertTrue(src.with_name('live.db-wal').exists())
                module.sqlite_backup(src, dst)
                with sqlite3.connect(dst) as recovered:
                    self.assertEqual(recovered.execute('SELECT value FROM important').fetchone()[0], 'committed while WAL open')
                    self.assertEqual(recovered.execute('PRAGMA quick_check').fetchone(), ('ok',))

    def test_cold_checksum_failure_does_not_accept_changed_data(self):
        backup = module.Backup({'destination': '/mnt/tank/backups/quark-apps', 'state_file': '/tmp/state'})
        class Result:
            returncode = 0
            stdout = '>fc........ database.db\n'
            stderr = ''
        with patch.object(module.subprocess, 'run', return_value=Result()):
            with self.assertRaises(RuntimeError):
                backup.copy(Path('/source'), Path('/backup'), verify=True)

    def test_recovery_attempts_other_apps_after_one_start_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            backup = module.Backup({'destination': directory, 'state_file': directory + '/state',
                                   'extra_start_order': ['broken', 'working'], 'guard_enabled_file': directory + '/enabled'})
            backup.running = ['broken', 'working']
            backup.quiescing = True
            calls = []
            def lifecycle(name, _action):
                calls.append(name)
                if name == 'broken':
                    raise RuntimeError('Unavailable')
            backup.lifecycle = lifecycle
            backup.storage = lambda **kwargs: None
            with self.assertRaises(RuntimeError):
                backup.recover()
            self.assertEqual(calls, ['broken', 'working'])

    def test_live_pre_copy_allows_vanished_file_but_cold_copy_rejects_it(self):
        with tempfile.TemporaryDirectory() as directory:
            backup = module.Backup({'destination': directory, 'state_file': directory + '/state'})
            class Result:
                returncode = 24
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass
                def poll(self):
                    return self.returncode
            with patch.object(module.subprocess, 'Popen', return_value=Result()):
                backup.copy(Path('/source'), Path(directory) / 'copy', live=True)
                with self.assertRaises(RuntimeError):
                    backup.copy(Path('/source'), Path(directory) / 'copy')

    def test_example_excludes_management_from_cold_tree(self):
        config = json.loads((Path(__file__).parents[1] / 'app-backup.example.json').read_text())
        tree = next(s for s in config['sources'] if s['name'] == 'quark/docker')
        self.assertIn('/dockhand/***', tree['excludes'])
        self.assertIn('/nginx-proxy-manager/***', tree['excludes'])
        self.assertEqual(len(config['online_management']), 2)

    def test_failed_cold_copy_still_recovers_apps_and_creates_no_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            backup = module.Backup({'destination': directory, 'state_file': directory + '/state'})
            events = []
            commands = []
            backup.storage = lambda: None
            backup.run = lambda command, **kwargs: commands.append(command)
            backup.event = lambda stage, **kwargs: events.append(stage)
            backup.quiesce = lambda: events.append('apps-stopped')
            backup.recover = lambda: events.append('apps-recovered')
            def copies(verify=False, live=False):
                if not live:
                    raise RuntimeError('Disk copy failed')
            backup.copies = copies
            backup.budget = lambda: None
            class Response:
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    pass
                def read(self):
                    return b'{"runningJobs":0}'
            with patch.object(module.subprocess, 'check_output', return_value='Status: cancelled'), patch.object(module.urllib.request, 'urlopen', return_value=Response()):
                with self.assertRaises(RuntimeError):
                    backup.execute()
            self.assertIn('apps-stopped', events)
            self.assertIn('apps-recovered', events)
            self.assertFalse(any('snapshot' in command for command in commands))

    def test_retention_prunes_by_bytes_before_running_out_of_space(self):
        existing = [('oldest', 30), ('middle', 30), ('newest', 30)]
        self.assertEqual(module.retention_plan(existing, 90, 30, 130), ['oldest'])

    def test_retention_does_not_destroy_last_two_to_fit_oversized_backup(self):
        existing = [('older', 30), ('newer', 30)]
        with self.assertRaises(RuntimeError):
            module.retention_plan(existing, 60, 100, 200)

    def test_retention_has_count_limit_even_with_plentiful_space(self):
        existing = [(str(i), 1) for i in range(7)]
        self.assertEqual(module.retention_plan(existing, 7, 1, 1000), ['0'])


if __name__ == '__main__':
    unittest.main()
