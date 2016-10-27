import unittest
import shutil
import tempfile

# This is difficult to test, and I feel as if the
#   code would turn into inside out reimplementation
#   asyncrhonous glueness

from qscli.qsask import run

class TestAsk(unittest.TestCase):
    def setUp(self):
        self.direc = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.direc)

    def run_cli(self, args):
        new_args = ('--config-dir', self.direc) + tuple(args)
        return run(new_args)

    def test_basic(self):
        self.run_cli(['new', 'test'])
        self.run_cli(['new', 'test2', '--period', '100'])

        result = self.run_cli(['list'])
        self.assertTrue('test\n' in result or 'test ' in result, result)
        self.assertTrue('test2\n' in result or 'test ' in result, result)

        self.run_cli(['delete', 'test2'])
        result = self.run_cli(['list'])
        self.assertTrue('test\n' in result or 'test ' in result, result)
        self.assertFalse('test2\n' in result or 'test2 ' in result, result)

    def test_prompt(self):
        self.run_cli(['new', 'test', '--prompt', 'This is a test'])
        result = self.run_cli(['show', 'test'])
        self.assertTrue('This is a test' in result, result)

if __name__ == '__main__':
    unittest.main()
