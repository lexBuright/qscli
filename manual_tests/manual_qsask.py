#!/usr/bin/python


import shutil
import tempfile
import unittest

import qscli.qsask


class TestManualQsask(unittest.TestCase):
    "A manual test harness for qsask"
    def setUp(self):
        self.direc = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.direc)

    def run_cli(self, *args):
        new_args = ('--config-dir', self.direc) + tuple(args)
        return qscli.qsask.run(new_args)

    def test_confirmation(self):
        print 'Every 5 ish second warn that we are going to ask a question, wait ten seconds them ask it'
        self.run_cli('new', '--warning-period', '10', '--period', '5', 'test', '--prompt', 'Answer to question?')
        self.run_cli('daemon', '--exit-after', '10')


if __name__ == "__main__":
	unittest.main()
