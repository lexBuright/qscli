import json
import os
import shutil
import StringIO
import tempfile
import unittest

from qscli.qsscore.qsscore import build_parser, run

class TestCli(unittest.TestCase):
    def cli(self, command, input_data=''):
        stdin = StringIO.StringIO(input_data)
        args = ['--config-dir', self._config_dir] + command
        options = build_parser().parse_args(args)
        try:
            return unicode(run(options, stdin))
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
        self.assertFalse('first-metric' not in second_list)
        self.assertTrue('other-metric' in second_list)

    def test_move(self):
        self.cli(['store', 'first-metric', '1'])
        self.cli(['store', 'first-metric', '2'])
        self.cli(['move', 'first-metric', 'second-metric'])
        lst = self.cli(['list'])
        self.assertTrue('first-metric' not in lst)
        self.assertTrue('second-metric' in lst)
        self.assertEqual(self.cli(['best', 'second-metric']), '2.0')

    def test_log(self):
        self.cli(['store', 'first-metric', '1'])
        self.cli(['store', 'first-metric', '2'])
        self.cli(['store', 'second-metric', '3'])

        log_lines = self.cli(['log']).splitlines()
        self.assertTrue('3' in log_lines[-1])
        self.assertEquals(len(log_lines), 3)

    def test_records(self):
        self.cli(['store', 'first-metric', '1'])
        self.cli(['store', 'first-metric', '2'])
        self.cli(['store', 'second-metric', '3'])
        lines = self.cli(['records']).splitlines()
        self.assertEquals(len(lines), 2)

        first_metric_line, = [l for l in lines if 'first-metric' in l]
        self.assertTrue('2.0' in first_metric_line)

        second_metric_line, = [l for l in lines if 'second-metric' in l]
        self.assertTrue('3.0' in second_metric_line)

    def test_store_csv(self):
        self.cli(['store', 'other-metric', '1337'])
        first_metric_csv = '1,11\n2,12\n'
        self.cli(['store-csv', 'first-metric'], first_metric_csv)
        self.assertTrue('12' in self.cli(['records']))
        self.assertTrue('1337' in self.cli(['records']))
        self.assertEquals(len(self.cli(['log']).splitlines()), 3)

    def test_store_csv_update(self):
        self.cli(['update', 'first-metric', '10', '--id', '2'])
        first_metric_csv = '1,11\n2,12\n'
        self.cli(['store-csv', 'first-metric'], first_metric_csv)

        # value is replaced
        self.assertEquals(len(self.cli(['log']).splitlines()), 2)
        self.assertTrue('12' in self.cli(['records']))

    def test_delete_record(self):
        self.cli(['store', 'first-metric', '121'])
        self.cli(['store', 'first-metric', '131'])

        self.assertEquals(len(self.cli(['log']).splitlines()), 2)
        self.cli(['log', '--index', '-1', '--delete'])
        self.assertEquals(len(self.cli(['log']).splitlines()), 1)
        self.assertTrue('121' in self.cli(['log']))
        self.assertTrue('131' not in self.cli(['log']))

    def test_multidelete(self):
        self.cli(['store', 'first-metric', '111'])
        self.cli(['store', 'first-metric', '222'])
        self.cli(['store', 'first-metric', '333'])
        self.cli(['log', '--index', '0', '--index', '-1', '--delete'])
        self.assertEquals(len(self.cli(['log']).splitlines()), 1)
        self.assertTrue('222' in self.cli(['log']))
        self.assertTrue('111' not in self.cli(['log']))
        self.assertTrue('333' not in self.cli(['log']))

    def test_statistics(self):
        self.cli(['store', 'metric', '1'])
        self.cli(['store', 'metric', '2'])
        self.cli(['store', 'metric', '3'])
        self.assertEquals(self.cli(['best', 'metric']), '3.0')

    def test_summary_small(self):
        self.cli(['store', 'metric', '1'])
        data = json.loads(self.cli(['summary', 'metric', '--json']))

        # consistentcy testing - this doesn't completely break
        self.cli(['summary', 'metric'])
        self.assertEquals(data['value'], 1.0)
        self.assertEquals(data['is_first'], True)
        self.assertEquals(data['is_best'], True)
        self.assertEquals(data['quantile'], 1.0)
        self.assertEquals(data['rank'], 0)

    def test_summary(self):
        self.cli(['store', 'metric', '1'])
        self.cli(['store', 'metric', '2'])
        self.cli(['store', 'metric', '3'])

        data = json.loads(self.cli(['summary', 'metric', '--json']))
        # consistentcy testing - this doesn't completely break
        self.cli(['summary', 'metric'])

        self.assertEquals(data['mean'], 2.0)
        self.assertEquals(data['best'], 3.0)
        self.assertEquals(data['run_length'], 3)

    def test_summary_modulation(self):
        for x in [1, 2, 3, 1, 2]:
            self.cli(['store', 'metric', str(x)])

        data = json.loads(self.cli(['summary', 'metric', '--json']))
        # consistentcy testing - this doesn't completely break
        self.cli(['summary', 'metric'])

        self.assertEquals(data['mean'], 1.8)
        self.assertEquals(data['best'], 3.0)
        self.assertEquals(data['run_length'], 2)
        self.assertEquals(data['quantile'], 0.8)

    def test_empty(self):
        self.cli(['config', 'empty'])
        self.cli(['summary', 'empty'])

    def test_summary_broken_run(self):
        for x in [1, 2, 3, 1]:
            self.cli(['store', 'metric', str(x)])
        summary = self.cli(['summary', 'metric'])
        self.assertTrue('Broken run' in summary)

    def test_backup(self):
        self.cli(['store', 'first-metric', '1'])
        self.cli(['store', 'other-metric', '2'])

        backup_string = self.cli(['backup'])

        for filename in os.listdir(self._config_dir):
            full_path = os.path.join(self._config_dir, filename)
            if os.path.isdir(full_path):
                shutil.rmtree(full_path)
            else:
                os.unlink(full_path)

        self.assertEqual(self.cli(['list']), '')

        for filename in os.listdir(self._config_dir):
            shutil.rmtree(os.path.join(self._config_dir, filename))

        self.cli(['restore'], input_data=backup_string)

        lst = self.cli(['list'])
        self.assertTrue('other-metric' in lst)
        self.assertTrue('first-metric' in lst)

    def test_backup_compatible(self):
        BACKUP_STRING = '{"metrics": {"first-metric": {"values": [{"time": 1470877073.3021483, "value": 1.0}]}, "other-metric": {"values": [{"time": 1470877073.302729, "value": 2.0}]}}, "version": 1}'

        self.cli(['restore'], input_data=BACKUP_STRING)
        lst = self.cli(['list'])
        self.assertTrue('other-metric' in lst)
        self.assertTrue('first-metric' in lst)

if __name__ == '__main__':
    unittest.main()
