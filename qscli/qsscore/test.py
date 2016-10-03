import os
import shutil
import StringIO
import tempfile
import unittest

from .qsscore import run

class TestCli(unittest.TestCase):
    def cli(self, command, input_data=''):
        stdin = StringIO.StringIO(input_data)
        try:
            return str(run(['--config-dir', self._config_dir] + command, stdin))
        except SystemExit:
            raise Exception('Exitted out')

    def setUp(self):
        self._config_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._config_dir)

    def test_basic(self):
        self.cli(['store', 'metric', '8'])
        self.cli(['store', 'metric', '10'])

        self.assertEqual(self.cli(['best', 'metric']), '10.0')
        self.assertEqual(self.cli(['mean', 'metric']), '9.0')

    def test_run_length(self):
        self.cli(['store', 'metric', '2'])
        self.cli(['store', 'metric', '1'])
        self.cli(['store', 'metric', '2'])
        self.cli(['store', 'metric', '30'])
        self.assertEqual(self.cli(['run-length', 'metric']), '3')

    def test_delete(self):
        self.cli(['store', 'first-metric', '1'])
        self.cli(['store', 'other-metric', '2'])
        first_list = self.cli(['list'])

        self.assertTrue('first-metric' in first_list)
        self.assertTrue('other-metric' in first_list)

        self.cli(['delete', 'first-metric'])

        second_list = self.cli(['list'])
        self.assertFalse('first-metric' in second_list)
        self.assertTrue('other-metric' in second_list)

    def test_move(self):
        self.cli(['store', 'first-metric', '1'])
        self.cli(['store', 'first-metric', '2'])
        self.cli(['move', 'first-metric', 'second-metric'])
        lst = self.cli(['list'])
        self.assertTrue('first-metric' not in lst)
        self.assertTrue('second-metric' in lst)
        self.assertEqual(self.cli(['best', 'second-metric']), '2.0')

    def test_backup(self):
        self.cli(['store', 'first-metric', '1'])
        self.cli(['store', 'other-metric', '2'])

        backup_string = self.cli(['backup'])

        for filename in os.listdir(self._config_dir):
            os.unlink(os.path.join(self._config_dir, filename))

        self.assertEqual(self.cli(['list']), '')

        for filename in os.listdir(self._config_dir):
            os.unlink(os.path.join(self._config_dir, filename))

        self.cli(['restore'], input=backup_string)

        lst = self.cli(['list'])
        self.assertTrue('other-metric' in lst)
        self.assertTrue('first-metric' in lst)

    def test_backup_compatible(self):
        BACKUP_STRING = '{"metrics": {"first-metric": {"values": [{"time": 1470877073.3021483, "value": 1.0}]}, "other-metric": {"values": [{"time": 1470877073.302729, "value": 2.0}]}}, "version": 1}'

        self.cli(['restore'], input=BACKUP_STRING)
        lst = self.cli(['list'])
        self.assertTrue('other-metric' in lst)
        self.assertTrue('first-metric' in lst)

if __name__ == '__main__':
    unittest.main()
