#!/usr/bin/python3
"""Stupidly feature-complete command line tool to keep track of scores;
Quickly gameify any activity.

Designed to be useable programmatically, though you might  prefer to use something like a
database of ELK (elasticsearch logstash kibana). If you being serious

Example usage:
   cli-score.py store game 8
   cli-score.py store game 9
   cli-score.py best game
"""

import argparse
import contextlib
import copy
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
PARSER.add_argument('--config-dir', '-d', default=DATA_DIR, help='Read and store data in this directory')
parsers = PARSER.add_subparsers(dest='command')

store_command = parsers.add_parser('store', help='', aliases=['s'])
store_command.add_argument('metric', type=str)
store_command.add_argument('value', type=float)

update_command = parsers.add_parser('update', help='', aliases=['u'])
update_command.add_argument('metric', type=str)
update_command.add_argument('value', type=float)
update_command.add_argument('--id', type=str, help='Update the score with this id (or create a value)')

def metric_command(parsers, name):
    command = parsers.add_parser(name, help='', aliases=[name[0]])
    command.add_argument('metric', type=str)
    return command

metric_command(parsers, 'best')
metric_command(parsers, 'mean')
metric_command(parsers, 'run-length')

summary_parser = metric_command(parsers, 'summary')
summary_parser.add_argument('--update', action='store_true', help='Assume last value is still changing')

parsers.add_parser('list', help='List the things that we have scores for')

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
        return dict(version=1)

@contextlib.contextmanager
def with_data(data_file):
    "Read from a json file, write back to it when we are finished"
    with fasteners.InterProcessLock(data_file + '.lck'):
        data = read_json(data_file)

        yield data

        output_data = json.dumps(data)
        with open(data_file, 'w') as stream:
            stream.write(output_data)


DATA_VERSION = 1

def migrate_data(data, to_version):
    while True:
        if get_version(data) == to_version:
            return data

        old_version = get_version(data)
        new_data = up_migrate_data(data)
        new_version = get_version(new_data)
        if not down_migrate_data(new_data) == data:
            raise Exception('Rounding tripping: {} -> {} -> {} failed'.format(old_version, new_version, old_version))

        data = new_data

def get_version(data):
    return data.get('version')

def up_migrate_data(data):
    new_data = copy.copy(data)
    version = get_version(new_data)

    if version == None:
        metrics = new_data.get('metrics', dict())
        for metric_name in metrics:
            metric = get_metric_data(new_data, metric_name)
            metric['values'] = [dict(time=time, value=value) for (time, value) in metric['values']]

        new_data['version'] = 1
        return new_data
    else:
    	raise ValueError(version)

def down_migrate_data(data):
    new_data = copy.copy(data)
    version = get_version(new_data)
    if version == 1:
        metrics = new_data.get('metrics', dict())
        for metric_name in metrics:
            metric = get_metric_data(new_data, metric_name)
            metric['values'] = [(value['time'], value['value']) for value in metric['values']]

        del new_data['version']
    return new_data

def run(arguments):
    options = PARSER.parse_args(arguments)
    if not os.path.isdir(options.config_dir):
        os.mkdir(options.config_dir)

    data_file = os.path.join(options.config_dir, 'data.json')
    with with_data(data_file) as data:
        # new_data = migrate_data(data, DATA_VERSION)
        # data.clear()
        # data.update(**new_data)

        if options.command == 'list':
            metric_names = sorted(data.get('metrics', dict()))
            return '\n'.join(metric_names)

        metric_data = get_metric_data(data, options.metric)
        if options.command == 'store':
            return store(metric_data, options.value)
        elif options.command == 'update':
            return update(metric_data, options.value, options.id)
        elif options.command == 'best':
            return best(metric_data)
        elif options.command == 'mean':
            return mean(metric_data)
        elif options.command == 'run-length':
            return run_length(metric_data)
        elif options.command == 'summary':
            return summary(metric_data, options.update)
        else:
            raise ValueError(options.command)

def get_metric_data(data, metric):
    metrics = data.setdefault('metrics', dict())
    metric_data = metrics.setdefault(metric, dict() )
    metric_data.setdefault('values', [])
    return metric_data

def store(metric_data, value):
    metric_values = metric_data.setdefault('values', [])
    metric_values.append(dict(time=time.time(), value=value))
    return ''

def update(metric_data, value, ident):
    metric_values = metric_data.setdefault('values', [])
    entry = dict(time=time.time(), value=value)
    if ident is not None:
        entry['id'] = ident

    if not metric_values:
        metric_values.append(entry)

    if ident is not None:
        ident_entries = [x for x in metric_values if x.get('id') == ident]
        if ident_entries:
            ident_entry, = ident_entries
            ident_entry['value'] = value
        else:
            metric_values.append(entry)
    else:
        metric_values[-1] = entry

    return ''

def rank(metric_data):
    result = 0
    last = get_last(metric_data)
    for entry in metric_data['values']:
        if entry['value'] > last:
            result += 1
    return result

def best(metric_data):
    best_pair = max(metric_data['values'], key=lambda pair: pair['value'])
    return best_pair['value']

def mean(metric_data):
    value = sum([pair[1] for pair in metric_data['values']]) / len(metric_data['values'])
    return value

def run_length(metric_data):
    rev_values = [entry['value'] for entry in metric_data['values']][::-1]

    pairs = zip(rev_values,rev_values[1:])
    result = len(list(itertools.takewhile(lambda x: x[0] > x[1], pairs))) + 1
    return result

def quantile(metric_data):
    # don't pull in numpy / scipy dependnecies
    values = [d['value'] for d in metric_data['values']]
    if not values:
        return None

    last = get_last(metric_data)
    lower = len([x for x in values if x <= last])
    upper = len(values) - len([x for x in values if x > last])
    return float(lower + upper) / 2 / len(values)

def best_ratio(metric_data):
    if len(metric_data['values']) < 1:
        return None
    else:
        last = get_last(metric_data)
        rest = [x['value'] for x in metric_data['values'][:-1]]
        if not rest or max(rest) == 0:
            return None
        else:
            return last / max(rest)

def get_last(metric_data):
    has_ids = any(entry.get('id') for entry in metric_data['values'])
    if has_ids:
        return sorted(metric_data['values'], key=lambda x: x.get('id'))[-1]['value']
    else:
        return metric_data['values'][-1]['value']

def summary(metric_data, update=False):
    last = get_last(metric_data)
    messages = [str(last)]
    last_rank = rank(metric_data)
    if last_rank == 0 and len(metric_data['values']) > 1:
        messages.append('New best')

    if len(metric_data['values']) == 1:
        messages.append('First time')

    runl = run_length(metric_data)
    if runl > 1:
        messages.append('Run of {}'.format(runl))
    elif len(metric_data['values']) > 1:
        if not update:
            messages.append('Broken run :(')

    if len(metric_data['values']) > 1:
        messages.append('{} best'.format(ordinal(last_rank + 1)))
        messages.append('Quantile: {:.2f}'.format(quantile(metric_data)))
        ratio = best_ratio(metric_data)
        if ratio is not None:
            messages.append('Ratio of best: {:.2f}'.format(ratio))

    return '{}'.format('\n'.join(messages))

def ordinal(number):
    return str(number) + {
        '0': 'th',
        '1': 'st',
        '2': 'nd',
        '3': 'rd',
        '4': 'th',
        '5': 'th',
        '6': 'th',
        '7': 'th',
        '8': 'th',
        '9': 'th',
    }[str(number)[-1]]

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
