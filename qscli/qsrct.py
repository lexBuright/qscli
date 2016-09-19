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

This tool represents represents a convenience wrapper, you might be better coding your own tests in R or python.

Lots of things can break independence assumptions when experimenting on yourself...
"""

import argparse
import collections
import contextlib
import csv
import datetime
import json
import logging
import math
import os
import random
import shutil
import StringIO
import subprocess
import sys
import tempfile
import threading
import time
import unittest

import fasteners

LOGGER = logging.getLogger()

def parse_csv_line(line):
    result, = tuple(csv.reader(StringIO.StringIO(line)))
    return result

def run(qsrct, argv):
    options = build_parser().parse_args(argv)
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

Result = collections.namedtuple('Result', 'returncode output')


def main():
    if '--debug' in sys.argv:
        logging.basicConfig(level=logging.DEBUG)

    if '--test' in sys.argv:
        sys.argv.remove('--test')
        unittest.main()
    else:
        # Double-parse to get config_dir
        #    while using run for testing
        options = build_parser().parse_args()
        result = (run(QsRct(random, options.config_dir), sys.argv[1:]))

        if not isinstance(result, Result):
            result = Result(output=result, returncode=0)

        if result.output:
            sys.stdout.write(result.output)
            sys.stdout.write('\n')
            sys.stdout.flush()
        sys.exit(result.returncode)

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

        if options.command == 'edit' or options.command == 'new':
            return self.edit(options.name, description=options.description, options=options.options, assign_period=options.assign_period, data_source=options.data_source)
        elif options.command == 'assign':
            return self.assign(options.name, check=options.check)
        elif options.command == 'assignments':
            result = self.assignments(options.name)
            return result
        elif options.command == 'trials':
            return self.trials()
        elif options.command == 'delete':
            return self.delete(options.name)
        elif options.command == 'show':
            return self.show(options.name)
        elif options.command == 'test':
            return self.test(options.name)
        elif options.command == 'data':
            return self.data(options.name)
        elif options.command == 'timeseries':
            return self.timeseries(options.timeseries_command)
        else:
            raise ValueError(options.command)

    def timeseries(self, command):
        return self._timeseries_run(command)

    def _assign(self, name):
        with self._with_experiment_data(name) as experiment_data:
            options = experiment_data['options']
            if not options:
                raise Exception('No options to choose from')
            assignment = self._random.choice(list(options))

            if experiment_data['assign_period'] is not None:
                ident = datetime.datetime.utcfromtimestamp(int(time.time()) // experiment_data['assign_period'] * experiment_data['assign_period']).isoformat()
            else:
                ident = None

            if ident:
                result = json.loads(self._timeseries_run([
                    'show',
                    '--series', 'assignments.{}'.format(name),
                    '--id', str(ident),
                    '--json'
                ]))

                if result:
                    LOGGER.debug('Reusing assignment')
                    return result[0]['value']

            LOGGER.debug('Creating a new assignment')
            command = ['append', 'assignments.{}'.format(name), '--string', assignment]
            if ident:
                command += ['--id', str(ident)]

            self._timeseries_run(command)

    def assign(self, name, check=None):
        assignment = self._assign(name)
        if check is not None :
            if assignment != check:
                return Result(returncode=1, output=assignment)
            else:
                return assignment
        else:
            return assignment


    def assignments(self, name):
        return self._timeseries_run(['show', '--series', 'assignments.{}'.format(name)])

    @contextlib.contextmanager
    def _with_experiment_data(self, name, create=True):
        with with_data(self._data_file) as data:
            experiments = data.setdefault('experiments', dict())
            if create:
                yield experiments.setdefault(name, dict())
            else:
                yield experiments[name]

    def edit(self, name, description, options, assign_period, data_source):
        with self._with_experiment_data(name) as experiment_data:
            if 'description' not in experiment_data:
                experiment_data['description'] = ''
            if 'options' not in experiment_data:
                experiment_data['options'] = []
            if 'assign_period' not in experiment_data:
                experiment_data['assign_period'] = None
            if 'data_source' not in experiment_data:
                experiment_data['data_source'] = None

            if data_source is not None:
                experiment_data['data_source'] = data_source
            if description is not None:
                experiment_data['description'] = description
            if options is not None:
                experiment_data['options'] = options
            if assign_period is not None:
                experiment_data['assign_period'] = assign_period

    def trials(self):
        with with_data(self._data_file) as data:
            return '\n'.join(data['experiments'])

    def test(self, name):
        LOGGER.debug('Testing')
        from scipy import stats
        with self._with_experiment_data(name) as experiment_data:
            options = experiment_data['options']

        if len(options) == 2:
            return self._ttest(experiment_data, name)
        else:
            raise ValueError(options)

    def _ttest(self, experiment_data, name):
        from scipy import stats
        LOGGER.debug('Running t-test')
        option1, option2 = experiment_data['options']

        num_tests = experiment_data.setdefault('num_tests', 1)

        data_points = self.get_data(name)
        sample1 = [x.value for x in data_points if x.assignment == option1]
        sample2 = [x.value for x in data_points if x.assignment == option2]
        result = stats.ttest_ind(sample1, sample2, equal_var=True)
        if math.isnan(result.pvalue):
            return 'Not enough data for test'
        else:
            # Work out the exact p-value rather
            #   than use approximation (more accurate)

            corrected_pvalue = (1 - (1 - result.pvalue)) ** (float(1) / num_tests)

            experiment_data.setdefault('num_tests', num_tests + 1)

            interval = stats.t.interval()

            result = []
            result.append('Corrected p-value: {}'.format(corrected_pvalue))
            result.append('Number of tests: {}'.format(num_tests))
            result.append('Cheat p-value: {}'.format(result.pvalue))


    def get_data(self, name):
        with self._with_experiment_data(name) as experiment_data:
            if experiment_data['data_source']:
                command = str(experiment_data['data_source']).split(' ')
                LOGGER.debug('command %r', command)
                raw_result = subprocess.check_output(command)
                results = list(csv.reader(raw_result.splitlines()))
            else:
                raise NotImplementedError('Getting results')

            assignments = self.get_assignments(name)
            data_points = []
            data_idents = set()
            for ident, value in results:
                if ident in assignments:
                    data_points.append(DataPoint(ident=ident, value=float(value), assignment=assignments[ident]))
                    data_idents.add(ident)

            for ident in assignments:
                if ident not in data_idents:
                    data_points.append(DataPoint(ident=ident, value=None, assignment=assignments[ident]))

            return data_points

    def get_assignments(self, name):
        data = json.loads(self._timeseries_run(['show', '--series', 'assignments.{}'.format(name), '--json']))
        result = {}
        for assignment in data:
            result[assignment['id']] = assignment['value']

        return result

    def delete(self, name):
        with with_data(self._data_file) as data:
            del data['experiments'][name]

    def data(self, name):
        data_points = self.get_data(name)
        for point in data_points:
            print point.ident, point.assignment, point.value

    def show(self, name):
        result = []
        with self._with_experiment_data(name) as experiment_data:
            result.append('options: ' + ' '.join(sorted(experiment_data['options'])))
            result.append('description: ' + experiment_data['description'])
            result.append('data_source:' + experiment_data['data_source'])

        return '\n'.join(result)

    def _timeseries_run(self, command):
        return backticks([
            'qstimeseries',
            '--config-dir',
            self._timeseries_data_dir] + command)

DataPoint = collections.namedtuple('DataPoint', 'ident value assignment')


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
    parser = argparse.ArgumentParser(description='Convenience tool to run randomized controlled trial ')
    parser.add_argument('--config-dir', type=str, help='Where to store configuration', default=DEFAULT_DATA_DIR)
    parser.add_argument('--debug', action='store_true', help='Include debug output')
    parsers = parser.add_subparsers(dest='command')

    def new_or_edit(parsers, name):
        new = parsers.add_parser(name, help='Create a new experiment')
        new.add_argument('name', type=str)
        new.add_argument('--options', type=parse_csv_line, help='Possible values for the experiment')
        new.add_argument('--description', type=str, help='Description of the experiment')
        new.add_argument('--every', type=parse_period, help='Only assign every period (e.g. 1d, 2h)', dest='assign_period')
        new.add_argument('--no-period', action='store_const', const=None, dest='assign_period', help='Give a new assignment every time assign is called')
        new.add_argument('--data-source', type=str, help='Command run to fetch data')

    new_or_edit(parsers, 'new')
    new_or_edit(parsers, 'edit')

    timeseries = parsers.add_parser('timeseries', help='Interact with underlying timeseries (see qstimeseries). LIABLE TO CHANGE')
    timeseries.add_argument('timeseries_command', nargs='+')

    assign = parsers.add_parser('assign', help='Randomly assign a subject to a particular experiment')
    assign.add_argument('name', type=str)
    assign.add_argument('--check', type=str, metavar='VALUE', help='Exit with a non-zero return code if VALUE is not returned')

    result = parsers.add_parser('result', help='Record a result for this assignment (not necessary if using another source for storage)')
    result.add_argument('name', type=str)
    result.add_argument('value', type=float, help='Value of experiment')

    data = parsers.add_parser('data', help='Display the data collected for an experiment')
    data.add_argument('name', type=str)

    assignment = parsers.add_parser('assignments', help='Show the assignments for an experiment')
    assignment.add_argument('name', type=str)

    test = parsers.add_parser('test', help='Run a test of the experiment')
    test.add_argument('name', type=str)

    delete = parsers.add_parser('delete', help='Delete an experiment')
    delete.add_argument('name', type=str)

    show = parsers.add_parser('show', help='Show information about an experiment')
    show.add_argument('name', type=str)

    trials = parsers.add_parser('trials', help='List all trials')
    return parser

UNITS = {
    's': 1,
    'd': 86400,
    'm': 60,
    'h': 3600,
             }

def parse_period(string):
    unit = string[-1]
    number = int(string[:-1])
    return number * UNITS[unit]



if __name__ == '__main__':
    main()
