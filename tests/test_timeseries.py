import json
import shutil
import tempfile
import unittest

from qscli import qstimeseries


class TimeseriesTest(unittest.TestCase):
    def setUp(self):
        self.direc = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.direc)

    def run_cli(self, *args):
        new_args = ('--config-dir', self.direc) + tuple(args)
        return qstimeseries.run(new_args)

    def test_basic(self):
        self.run_cli('append', 'metric', '1')
        self.run_cli('append', 'other-metric', '2')
        value, = json.loads(self.run_cli('show', '--series', 'metric', '--json'))
        self.assertEquals(value['value'], 1)
        self.assertEquals(value['id'], 'internal--1')

    def test_append_at_time(self):
        self.run_cli('append', 'metric', '1', '--time', '1000')
        value, = json.loads(self.run_cli('show', '--series', 'metric', '--json'))
        self.assertEquals(value['time'], 1000)
        self.assertEquals(value['value'], 1)



    def test_delete_internal(self):
        self.run_cli('append', 'metric', '1')
        self.run_cli('append', 'metric', '2')

        self.run_cli('delete', 'metric', '--id', 'internal--1')
        value, = json.loads(self.run_cli('show', '--series', 'metric', '--json'))
        self.assertEquals(value['value'], 2)

    def test_show_internal(self):
        self.run_cli('append', 'metric', '1')
        self.run_cli('append', 'metric', '2')
        result, = json.loads(self.run_cli('show', '--id', 'internal--2', '--json'))
        self.assertEquals(result['value'], 2)

    def test_show(self):
        self.run_cli('append', 'metric', '1')
        self.run_cli('append', 'metric', '2', '--id', 'two')
        result, = json.loads(self.run_cli('show', '--id', 'two', '--json'))
        self.assertEquals(result['value'], 2)

    def test_delete_given(self):
        self.run_cli('append', 'metric', '1')
        self.run_cli('append', 'metric', '2', '--id', 'uniq')

        self.run_cli('delete', 'metric', '--id', 'uniq')
        value, = json.loads(self.run_cli('show', '--series', 'metric', '--json'))
        self.assertEquals(value['value'], 1)

    def test_show_indexes(self):
        self.run_cli('append', 'metric', '1')
        self.run_cli('append', 'metric', '2')
        self.run_cli('append', 'metric', '3')

        entry1, entry2 = json.loads(self.run_cli('show', '--series', 'metric', '--index', '0', '--index', '2', '--json'))
        self.assertEquals(entry1['value'], 1)
        self.assertEquals(entry2['value'], 3)

        entry1, entry2 = json.loads(self.run_cli('show', '--series', 'metric', '--index', '-1', '--index', '0', '--json'))
        self.assertEquals(entry1['value'], 3)
        self.assertEquals(entry2['value'], 1)









if __name__ == '__main__':
    unittest.main()
