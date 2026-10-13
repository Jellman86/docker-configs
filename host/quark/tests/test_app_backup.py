import importlib.util
from pathlib import Path
import sqlite3
import tempfile
from contextlib import closing
import unittest

spec = importlib.util.spec_from_file_location('app_backup', Path(__file__).parents[1] / 'app_backup.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BackupTests(unittest.TestCase):
    def test_sqlite_backup_includes_committed_wal(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'live.db'
            target = Path(directory) / 'recovery.db'
            with closing(sqlite3.connect(source)) as conn:
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('CREATE TABLE important(value TEXT)')
                conn.execute("INSERT INTO important VALUES ('committed in WAL')")
                conn.commit()
                module.sqlite_copy(source, target)
                with closing(sqlite3.connect(target)) as recovered:
                    self.assertEqual(recovered.execute('SELECT value FROM important').fetchone(), ('committed in WAL',))

    def test_rebuildable_data_and_database_sidecars_are_excluded(self):
        for name in ['cache/blob.bin','models/model.bin','recordings/video.mp4','MediaCover/1/image.jpg','app.db-wal','app.db-shm','state.db.malformed-backup-20260101','speciesid.pre-migration-20261013-abc.db']:
            self.assertFalse(module.included(Path(name)), name)
        for name in ['.encryption_key','secrets.yaml','.storage/auth','config.xml','app.db']:
            self.assertTrue(module.included(Path(name)), name)
        self.assertTrue(module.included(Path('letsencrypt/archive/npm-1/privkey1.pem')))

    def test_retention_recognizes_only_its_own_archives(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ['apps-20261013T031000Z.tar.gz','fixed-migration-recovery.tar.gz','.candidate-20261013T031000Z.tar.gz']:
                (root/name).touch()
            self.assertEqual([p.name for p in module.retained_archives(root)], ['apps-20261013T031000Z.tar.gz'])

    def test_total_data_bound_is_below_allowance(self):
        self.assertLessEqual((3+1+1)*module.MAX_GENERATION, 20*module.GIB)


if __name__ == '__main__':
    unittest.main()
