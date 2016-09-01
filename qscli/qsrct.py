"""
Command line tools to carry out randomized controlled trial.
Prevents you from P-value fishing with bonferroni correction

qsrct new jumping --options witharms,without-arms # define the options for an experiment
qsrct assign jumping # assign the choice for an experiment
qsrct result jumping 1.9 # score the result for the assignment
qsrct test jumping # runs an appropriate test on the experiment

qsrct assign jumping --id ID # Get an assignment for id id
qsrct assign jumping --every 1d # return a new assignment every day
qsrct assign jumping --every 1h # return a new assignment every hour
qsrct assign jumping --every 10m # return a new assignment every ten minutes

# Run a test with an external source of data
#  Data should consist of a csv of _ID,value_ or _timestamp,value_ as appropriate
qsrct test jumping --data <(qstimeseries show jumping)

qsrct test jumping --data <(qstimeseries show jumping) --method alternative # use a different method of fitting

# Caveats

Bon ferroni is overly aggressive, there are alternative approaches for
calculating the significance loss for repeatedly looking at results.

This tool represents represents a convenience wrapper, you might be
better off using R for certain things.

Lots of things can break independence assumptions when experimenting on yourself...
"""

import argparse
import contextlib
import csv
import json
import os
import random
import shutil
import StringIO
import subprocess
import sys
import tempfile
import threading
import unittest

import fasteners


def parse_csv_line(line):
    result, = tuple(csv.reader(StringIO.StringIO(line)))
    return result

def run(qsrct, argv):
    options = PARSER.parse_args(argv)
    return qsrct.run(options)

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

def main():
    if '--test' in sys.argv:
        sys.argv.remove('--test')
        unittest.main()
    else:
        # Double-parse to get config_dir
        #    while using run for testing
        options = PARSER.parse_args()
        sys.stdout.write(run(QsRct(random, options.config_dir), sys.argv[1:]))
        sys.stdout.flush()

class QsRct(object):
    def __init__(self, random, config_dir):
        self._random = random
        self._config_dir = config_dir
        self._data_file = os.path.join(self._config_dir, 'data.json')
        self._timeseries_data_dir = os.path.join(self._config_dir, 'timeseries')

    def ensure_config(self):
        if not os.path.isdir(self._config_dir):
            os.mkdir(self._config_dir)

        if not os.path.isdir(self._timeseries_data_dir):
            os.mkdir(self._timeseries_data_dir)

    def run(self, options):
        self.ensure_config()

        if options.command == 'new':
            return self.new(options.name, options.options)
        elif options.command == 'assign':
            return self.assign(options.name)
        elif options.command == 'assignments':
            result = self.assignments(options.name)
            print 'Assignments results', result
            return result
        else:
            raise ValueError(options.command)

    def assign(self, name):
        with self._with_experiment_data(name) as experiment_data:
            options = experiment_data['options']
            assignment = self._random.choice(list(options))
            self._timeseries_run(['append', 'assignments.{}'.format(name), '--string', assignment])
            return assignment

    def assignments(self, name):
        return self._timeseries_run(['show', 'assignments.{}'.format(name)])

    @contextlib.contextmanager
    def _with_experiment_data(self, name):
        with with_data(self._data_file) as data:
            experiments = data.setdefault('experiments', dict())
            yield experiments.setdefault(name, dict())

    def new(self, name, options):
        with self._with_experiment_data(name) as experiment_data:
            experiment_data['options'] = options

    def _timeseries_run(self, command):
        return backticks([
            'qstimeseries',
            '--config-dir',
            self._timeseries_data_dir] + command)



def backticks(command, stdin=None, shell=False):
    stdin = subprocess.PIPE if stdin is not None else None
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stdin=stdin, shell=shell)
    result, _ = process.communicate(stdin)
    if process.returncode != 0:
        raise Exception('{!r} ({!r}) returned non-zero return code {!r}'.format(command, " ".join(command), process.returncode))
    return result

DEFAULT_DATA_DIR = os.path.join(os.environ['HOME'], '.config', 'qsrct')

def read_json(filename):
    if os.path.exists(filename):
        with open(filename) as stream:
            return json.loads(stream.read())
    else:
        return dict()

# IMPROVEMENT: isolate this
DATA_LOCK = threading.Lock()
@contextlib.contextmanager
def with_data(data_file):
    "Read from a json file, write back to it when we are finished"
    with fasteners.InterProcessLock(data_file + '.lck'):
        with DATA_LOCK:
            data = read_json(data_file)
            yield data

            output = json.dumps(data)
            with open(data_file, 'w') as stream:
                stream.write(output)


class TestQsrct(unittest.TestCase):
    def setUp(self):
        self.direc = tempfile.mkdtemp()
        self.random = FakeRandom()
        self.qsrct = QsRct(self.random, self.direc)

    def tearDown(self):
        shutil.rmtree(self.direc)

    def run_cli(self, args):
        new_args = tuple(args) + ('--config-dir', self.direc)
        return run(self.qsrct, args)

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


    def test_basic(self):
        self.run_cli(['new', 'test', '--options', 'good,bad'])

        self.destine('good')
        self.run_cli(['assign', 'test'])

        while True:
            print blah

        self.run_cli(['result', 'test', '1'])

        self.destine('good')
        self.run_cli(['assign', 'test'])
        self.run_cli(['result', 'test', '2'])

        self.destine('bad')
        self.run_cli(['assign', 'test'])
        self.run_cli(['result', 'test', '-10000000000000'])

        print self.run_cli(['test', 'test']) # Two sample t-test

def build_parser():
    PARSER = argparse.ArgumentParser(description='Convenience tool to run randomized controlled trial ')
    PARSER.add_argument('--debug', action='store_true', help='Include debug output')
    parsers = PARSER.add_subparsers(dest='command')

    new = parsers.add_parser('new', help='Create a new experiment')
    new.add_argument('name', type=str)
    new.add_argument('--options', type=parse_csv_line, help='Possible values for the experiment')

    assign = parsers.add_parser('assign', help='Randomly assign a subject to a particular experiment')
    assign.add_argument('name', type=str)

    result = parsers.add_parser('result', help='Record a result for this assignment (not necessary if using another source for storage)')
    result.add_argument('name', type=str)
    result.add_argument('value', type=float, help='Value of experiment')

    assignment = parsers.add_parser('assignments', help='Show the assignments for an experiment')
    assignment.add_argument('name', type=str)

    test = parsers.add_parser('test', help='Run a test of the experiment')
    test.add_argument('name', type=str)
    return PARSER

PARSER = build_parser()



if __name__ == '__main__':
    main()
