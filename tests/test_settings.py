import shutil
import tempfile
import unittest

from qscli.qssettings import run

class TestQssettings(unittest.TestCase):
    def setUp(self):
        self.direc = tempfile.mkdtemp()
        self.prompter = FakePrompter()

    def tearDown(self):
        shutil.rmtree(self.direc)

    def run_cli(self, *args):
        new_args = ('--config-dir', self.direc) + tuple(args)
        return run(self.prompter, new_args)

    def test_prefix(self):
        self.run_cli('--prefix', 'prefix', 'update', '--name', 'test', '--value', '1.1')
        self.run_cli('update', '--name', 'test', '--value', '2.0')
        self.assertEquals(self.run_cli('show', '--name', 'test'), '2.0')
        self.assertEquals(self.run_cli('--prefix', 'prefix', 'show', '--name', 'test'), '1.1')

    def test_basic(self):
        self.run_cli('update', '--name', 'test', '--value', '1.1')
        self.assertEquals(self.run_cli('show', '--name', 'test'), '1.1')
        self.run_cli('update', '--name', 'test', '--value', '1.2')
        self.assertEquals(self.run_cli('show', '--name', 'test'), '1.2')

    def test_prompter(self):
        self.prompter.set_value('Which setting:', 'setting1')
        self.run_cli('update', '--value', '1.1')
        self.prompter.set_value('Which setting:', 'setting1')
        self.assertEquals(self.run_cli('show'), '1.1')
        self.prompter.set_value('Value:', 2.0)
        self.run_cli('update')
        self.assertEquals(self.run_cli('show'), '2.0')


    def test_prompter_empty(self):
        self.prompter.set_value('Value:', 2.0)
        self.prompter.set_value('Which setting:', 'setting1')
        self.run_cli('update')
        self.assertEquals(self.run_cli('show'), '2.0')

class FakePrompter(object):
    def __init__(self):
        self._values = {}

    def set_value(self, prompt, value):
        self._values[prompt] = value

    def float_prompt(self, prompt, default=None):
        del default
        return self._values[prompt]

    def combo_prompt(self, prompt, choices):
        del choices
        return self._values[prompt]

if __name__ == '__main__':
    unittest.main()
