import unittest

import shutil
import tempfile

from qscli.qsrct import QsRct, run

class TestQsrct(unittest.TestCase):
    def setUp(self):
        self.direc = tempfile.mkdtemp()
        self.random = FakeRandom()
        self.qsrct = QsRct(self.random, self.direc)

    def tearDown(self):
        shutil.rmtree(self.direc)

    def run_cli(self, args):
        new_args = ('--config-dir', self.direc) + tuple(args)
        return run(self.qsrct, new_args)

    def destine(self, value):
        # Tester does not play dice
        self.random.destine(value)

    def test_assign(self):
        self.run_cli(['new', 'experiment', '--options', 'good,bad'])
        self.destine('good')
        self.run_cli(['assign', 'experiment'])

        self.destine('bad')
        self.run_cli(['assign', 'experiment'])

        lines = self.run_cli(['assignments', 'experiment']).splitlines()
        self.assertTrue('good' in lines[0])
        self.assertTrue('bad' in lines[1])

    def test_trials(self):
        self.run_cli(['new', 'test', '--options', 'good,bad'])
        result = self.run_cli(['trials'])
        self.assertEquals(result, 'test')

    def test_delete(self):
        self.run_cli(['new', 'test', '--options', 'good,bad'])
        self.run_cli(['delete', 'test'])
        result = self.run_cli(['trials'])
        self.assertEquals(result, '')

    def test_show(self):
        self.run_cli(['new', 'boring-test'])

        self.run_cli(['new', 'test', '--options', 'good,bad'])
        result = self.run_cli(['show', 'test'])
        self.assertTrue('options: bad good' in result, result)

        result = self.run_cli(['show', 'boring-test'])
        self.assertTrue('options:' in result, result)

    def test_edit(self):
        self.run_cli(['new', 'test'])
        self.run_cli(['edit', 'test', '--description', 'some testing'])
        result = self.run_cli(['show', 'test'])
        self.assertTrue('description: some testing' in result, result)

    @unittest.skip('broken')
    def test_basic(self):
        self.run_cli(['new', 'test', '--options', 'good,bad'])

        self.destine('good')
        self.run_cli(['assign', 'test'])

        self.run_cli(['result', 'test', '1'])

        self.destine('good')
        self.run_cli(['assign', 'test'])
        self.run_cli(['result', 'test', '2'])

        self.destine('bad')
        self.run_cli(['assign', 'test'])
        self.run_cli(['result', 'test', '-10000000000000'])

        print self.run_cli(['test', 'test']) # Two sample t-test

class FakeRandom(object):
    def __init__(self):
        self.destined_values = []

    def destine(self, value):
        self.destined_values.append(value)

    def choice(self, values):
        destined_value = self.destined_values[0]
        if destined_value not in values:
            raise Exception('{!r} not in {!r}'.format(destined_value, values))

        return self.destined_values.pop(0)

if __name__ == '__main__':
    unittest.main()
