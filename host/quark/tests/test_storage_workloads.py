import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('storage_workloads', Path(__file__).parents[1] / 'storage_workloads.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.config = {'storage': [{'mount': '/mnt/tank', 'fstype': 'btrfs', 'uuid': 'mirror', 'serials': ['first', 'second']}]}
        self.tree = {'blockdevices': [{'serial': s, 'children': [{'uuid': 'mirror'}]} for s in ['first', 'second']]}
        self.mount = {'target': '/mnt/tank', 'fstype': 'btrfs', 'uuid': 'mirror', 'options': 'rw,relatime'}
        self.layout = 'Total devices 2\n devid 1 /dev/sdb1\n devid 2 /dev/sdc1'
        self.usage = 'Data,RAID1: Size: 1\nMetadata,RAID1: Size: 1\nSystem,RAID1: Size: 1'
        self.device_error = False

    def run_command(self, args, **kwargs):
        if args[0] == 'lsblk': return json.dumps(self.tree)
        if args[0] == 'findmnt': return json.dumps({'filesystems': [self.mount]})
        if args[1:3] == ['filesystem', 'show']: return self.layout
        if args[1:3] == ['filesystem', 'usage']: return self.usage
        if self.device_error: raise RuntimeError('device errors')
        return 'errors 0'

    def ready(self): return MODULE.mounted_storage(self.config, run=self.run_command)

    def test_verified_mirror(self): self.assertTrue(self.ready())

    def test_parent_filesystem_fallback_is_not_a_mount(self):
        self.mount['target'] = '/'
        self.assertFalse(self.ready())

    def test_wrong_filesystem_uuid(self):
        self.mount['uuid'] = 'other'
        self.assertFalse(self.ready())

    def test_missing_member_even_if_mount_persists(self):
        self.tree['blockdevices'].pop()
        self.assertFalse(self.ready())

    def test_wrong_hardware_with_same_uuid(self):
        self.tree['blockdevices'][1]['serial'] = 'backup'
        self.assertFalse(self.ready())

    def test_read_only_after_io_error(self):
        self.mount['options'] = 'ro,relatime'
        self.assertFalse(self.ready())

    def test_missing_btrfs_device(self):
        self.layout += '\n*** Some devices missing'
        self.assertFalse(self.ready())

    def test_non_mirrored_metadata(self):
        self.usage = self.usage.replace('Metadata,RAID1', 'Metadata,DUP')
        self.assertFalse(self.ready())

    def test_device_errors_fail_closed(self):
        self.device_error = True
        with self.assertRaises(RuntimeError): self.ready()


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.marker = Path(self.temp.name) / 'enabled'
        self.marker.touch()
        self.config = {'enabled_file': str(self.marker), 'environment': 1,
                       'start_order': [{'name': 'server', 'healthy_dependencies': ['database']}],
                       'stop_order': ['server', 'database']}
        self.guard = MODULE.Guard(self.config)
        self.records = [{'name': 'server', 'id': 'server-id', 'state': 'exited'},
                        {'name': 'database', 'id': 'db-id', 'state': 'running', 'health': 'healthy'}]
        self.posts = []
        self.guard.api = self.api

    def api(self, path, method='GET', **kwargs):
        if method == 'GET': return self.records
        self.posts.append(path)
        return {'success': True}

    def test_verified_start_through_dockhand_only(self):
        with patch.object(MODULE, 'mounted_storage', return_value=True): self.guard.step()
        self.assertEqual(self.posts, ['/api/containers/server-id/start?env=1'])

    def test_storage_loss_between_listing_and_start(self):
        with patch.object(MODULE, 'mounted_storage', side_effect=[True, False]): self.guard.step()
        self.assertEqual(self.posts, ['/api/containers/db-id/stop?env=1'])

    def test_unhealthy_database_blocks_server(self):
        self.records[1]['health'] = 'starting'
        with patch.object(MODULE, 'mounted_storage', return_value=True): self.guard.step()
        self.assertEqual(self.posts, [])

    def test_vpn_restart_stops_namespace_dependents_before_start(self):
        self.config['start_order'] = [{'name': 'vpn', 'stop_before_start': ['download']}]
        self.records = [{'name': 'vpn', 'id': 'vpn-id', 'state': 'exited'},
                        {'name': 'download', 'id': 'download-id', 'state': 'running'}]
        with patch.object(MODULE, 'mounted_storage', return_value=True): self.guard.step()
        self.assertEqual(self.posts, ['/api/containers/download-id/stop?env=1', '/api/containers/vpn-id/start?env=1'])

    def test_disabled_marker_stops_even_with_storage(self):
        self.marker.unlink()
        with patch.object(MODULE, 'mounted_storage') as check: self.guard.step()
        check.assert_not_called()
        self.assertEqual(self.posts, ['/api/containers/db-id/stop?env=1'])

    def test_stop_failure_does_not_skip_other_workloads(self):
        self.records[0]['state'] = 'running'
        def fail_first(path, method='GET', **kwargs):
            if method == 'GET': return self.records
            self.posts.append(path)
            if 'server-id' in path: raise TimeoutError()
            return {'success': True}
        self.guard.api = fail_first
        with self.assertRaises(RuntimeError): self.guard.stop_workloads()
        self.assertEqual(self.posts, ['/api/containers/server-id/stop?env=1', '/api/containers/db-id/stop?env=1'])


if __name__ == '__main__': unittest.main()
