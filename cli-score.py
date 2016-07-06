#!/usr/bin/python3
"""Stupidly feature-complete command line tool to keep track of scores.

Designed to be useable programmatically, though you might like to use something like a
database of ELK (elasticsearch logstash kibana).

Example usage:
   cli-score.py store game 8
   cli-score.py store game 9
   cli-score.py best game
"""

import argparse
import contextlib
import itertools
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

import fasteners

PARSER = argparse.ArgumentParser(description='')

DATA_DIR = os.path.join(os.environ['HOME'], '.config', 'cli-score')

PARSER = argparse.ArgumentParser(description='')
PARSER.add_argument('--config-dir', '-d', default=DATA_DIR, help='Reand and store data in this directory')
parsers = PARSER.add_subparsers(dest='command')

store_command = parsers.add_parser('store', help='', aliases=['s'])
store_command.add_argument('metric', type=str)
store_command.add_argument('value', type=float)

def metric_command(parser, name):
    command = parsers.add_parser(name, help='', aliases=['b'])
    command.add_argument('metric', type=str)

metric_command(PARSER, 'best')
metric_command(PARSER, 'mean')
metric_command(PARSER, 'run-length')
metric_command(PARSER, 'summary')

def main():
    if '--test' in sys.argv[1:]:
        sys.argv.remove('--test')
        unittest.main()
    else:
        print(str(run(sys.argv[1:])))

def read_json(filename):
    if os.path.exists(filename):
        with open(filename) as stream:
            return json.loads(stream.read())
    else:
        return dict()

@contextlib.contextmanager
def with_data(data_file):
    "Read from a json file, write back to it when we are finished"
    with fasteners.InterProcessLock(data_file + '.lck'):
        data = read_json(data_file)

        yield data

        output_data = json.dumps(data)
        with open(data_file, 'w') as stream:
            stream.write(output_data)

def run(arguments):
    options = PARSER.parse_args(arguments)
    if not os.path.isdir(options.config_dir):
        os.mkdir(options.config_dir)

    data_file = os.path.join(options.config_dir, 'data.json')


    with with_metric_data(data_file, options.metric) as metric_data:
        if options.command == 'store':
            return store(metric_data, options.value)
        elif options.command == 'best':
            return best(metric_data)
        elif options.command == 'mean':
            return mean(metric_data)
        elif options.command == 'run-length':
            return run_length(metric_data)
        elif options.command == 'summary':
            return summary(metric_data)
        else:
            raise ValueError(options.command)

@contextlib.contextmanager
def with_metric_data(data_file, metric):
    with with_data(data_file) as data:
        metrics = data.setdefault('metrics', dict())
        metric_data = metrics.setdefault(metric, dict() )
        metric_data.setdefault('values', [])
        yield metric_data

def store(metric_data, value):
    metric_values = metric_data.setdefault('values', [])
    metric_values.append((time.time(), value))
    return ''

def rank(metric_data):
    result = 0
    last = metric_data['values'][-1][1]
    for _time, value in metric_data['values']:
        if value > last:
            result += 1
    return result

def best(metric_data):
    best_pair = max(metric_data['values'], key=lambda pair: pair[1])
    return best_pair[1]

def mean(metric_data):
    value = sum([pair[1] for pair in metric_data['values']]) / len(metric_data['values'])
    return value

def run_length(metric_data):
    rev_values = [pair[1] for pair in metric_data['values']][::-1]

    pairs = zip(rev_values,rev_values[1:])
    result = len(list(itertools.takewhile(lambda x: x[0] > x[1], pairs))) + 1
    return result

def summary(metric_data):
    last = metric_data['values'][-1][1]
    messages = [str(last)]
    last_rank = rank(metric_data)
    if last_rank == 0:
        messages.append('New best')

    runl = run_length(metric_data)
    if runl > 1:
        messages.append('Run of {}'.format(runl))
    elif len(metric_data['values']) > 1:
        messages.append('Broken run')
        messages.append('{}st best'.format(last_rank + 1))

    return '{}'.format(' -- '.join(messages))


class TestCli(unittest.TestCase):
    def cli(self, command):
        try:
            return str(run(['--config-dir', self._config_dir] + command))
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

    def test_summary(self):
        self.cli(['store', 'metric', '1'])
        self.assertEqual(self.cli(['summary', 'metric']), '1.0 -- New best')
        self.cli(['store', 'metric', '2'])
        self.assertEqual(self.cli(['summary', 'metric']), '2.0 -- New best -- Run of 2')
        self.cli(['store', 'metric', '3'])
        self.assertEqual(self.cli(['summary', 'metric']), '3.0 -- New best -- Run of 3')
        self.cli(['store', 'metric', '2'])
        self.assertEqual(self.cli(['summary', 'metric']), '2.0 -- Broken run -- 2st best')
        self.cli(['store', 'metric', '4']);
        self.assertEqual(self.cli(['summary', 'metric']), '4.0 -- New best -- Run of 2')


if __name__ == "__main__":
	main()
