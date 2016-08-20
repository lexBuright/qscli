#!/usr/bin/python
"""Stupidly feature-complete command-line tool to keep track of scores;
Quickly gameify any activity.

Designed to be useable programmatically, though you might prefer to use something like a
database of ELK (elasticsearch logstash kibana) if you are being serious.
"""

import argparse
import contextlib
import copy
import datetime
import itertools
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unittest
from io import StringIO

import fasteners

import jsdb

from . import ipc

DATA_DIR = os.path.join(os.environ['HOME'], '.config', 'qsscore')
PARSER = argparse.ArgumentParser(description=__doc__)
PARSER.add_argument('--config-dir', '-d', default=DATA_DIR, help='Read and store data in this directory')
parsers = PARSER.add_subparsers(dest='command')

store_command = parsers.add_parser('store', help='Store a score')
store_command.add_argument('metric', type=str)
store_command.add_argument('value', type=float)

parsers.add_parser('daemon', help='Run a daemon')

log_command = parsers.add_parser('log', help='Show all the scores for a period of time')
log_command.add_argument('--regex', '-x', type=re.compile, help='Only return scores whose names match this regexp')
log_command.add_argument('--days-ago', '-A', type=int, help='Returns scores recorded this many days ago')
log_command.add_argument('--json', action='store_true', help='Output results in machine readable json')

update_command = parsers.add_parser('update', help='Update the last entered score (or the score with a particular id)')
update_command.add_argument('metric', type=str)
update_command.add_argument('value', type=float)
update_command.add_argument('--id', type=str, help='Update the score with this id (or create a value)')

delete_command = parsers.add_parser('delete', help='Delete a metric')
delete_command.add_argument('metric', type=str)

move_command = parsers.add_parser('move', help='Rename a metric')
move_command.add_argument('old_name', type=str)
move_command.add_argument('new_name', type=str)

backup_command = parsers.add_parser('backup', help='Dump out all data to standard out')

restore_command = parsers.add_parser('restore', help='Dump out all data to standard out')

def metric_command(parsers, name):
    command = parsers.add_parser(name, help='')
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
        options = PARSER.parse_args(sys.argv[1:])
        print(str(run(options, sys.stdin)))

def read_json(filename):
    if os.path.exists(filename):
        with open(filename) as stream:
            return json.loads(stream.read())
    else:
        return dict(version=1)

@contextlib.contextmanager
def with_json_data(data_file):
    "Read from a json file, write back to it when we are finished"
    with fasteners.InterProcessLock(data_file + '.lck'):
        data = read_json(data_file)

        yield data

        output_data = json.dumps(data)
        with open(data_file, 'w') as stream:
            stream.write(output_data)

@contextlib.contextmanager
def with_jsdb_data(data_file):
    db = jsdb.Jsdb(data_file)
    with db:
        try:
            yield db
        except:
            db.rollback()
            raise
        else:
            db.commit()

with_data = with_jsdb_data

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

def run(options, stdin):
    if not os.path.isdir(options.config_dir):
        os.mkdir(options.config_dir)

    if options.command == 'daemon':
        return ipc.run_server(PARSER, lambda more_options: run(more_options, stdin))

    data_file = os.path.join(options.config_dir, 'data.jsdb')
    with with_data(data_file) as data:
        # new_data = migrate_data(data, DATA_VERSION)
        # data.clear()
        # data.update(**new_data)

        if options.command == 'list':
            metric_names = sorted(data.get('metrics', dict()))
            return '\n'.join(metric_names)
        elif options.command == 'log':
            if options.days_ago is not None:
                start_time, end_time = days_ago_bounds(options.days_ago)
            else:
                start_time = end_time = None
            return log(data, json_output=options.json, name_regexp=options.regex, start_time=start_time, end_time=end_time)
        elif options.command == 'delete':
            metrics = data.get('metrics', dict())
            metrics.pop(options.metric)
            return ''
        elif options.command == 'move':
            metrics = data.get('metrics', dict())
            metrics[options.new_name] = metrics[options.old_name]
            del metrics[options.old_name]
            return ''
        elif options.command == 'backup':
            return backup(data)
        elif options.command == 'restore':
            restore(data, stdin.read())
            return ''

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

def days_ago_bounds(days_ago):
    start = datetime.datetime.now().replace(hour=0, second=0, microsecond=0) - datetime.timedelta(days=days_ago)
    start_time = time.mktime(start.timetuple())
    end_time = start_time + 3600 * 24
    return start_time, end_time

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
    best_record = max(metric_data['values'], key=lambda record: record['value'])
    return best_record['value']

def mean(metric_data):
    value = sum([record['value'] for record in metric_data['values']]) / len(metric_data['values'])
    return value

def run_length(metric_data):
    rev_values = [entry['value'] for entry in metric_data['values']][::-1]

    records = zip(rev_values,rev_values[1:])
    result = len(list(itertools.takewhile(lambda x: x[0] > x[1], records))) + 1
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
    messages = ['{:.2f}'.format(last)]
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

def backup(data):
    data = copy.deepcopy(data)
    data['version'] = DATA_VERSION
    backup_string = json.dumps(data)
    return backup_string

def restore(data, backup):
    data.clear()
    backup_data = json.loads(backup)
    data.update(**backup_data)

def log(data, json_output, name_regexp, start_time, end_time):
    entries = []
    for metric_name, metric in data['metrics'].items():
        if name_regexp is not None and not name_regexp.search(metric_name):
            continue

        values = []
        for value in jsdb.python_copy.copy(metric['values']):
            if start_time and value['time'] < start_time:
                continue
            if end_time and value['time'] >= end_time:
                continue

            values.append(value)
        for value in values:
            value.update(metric=metric_name)
        entries.extend(values)

    entries.sort(key=lambda v: v['time'])

    if json_output:
        return json.dumps([dict(time=entry['time'], value=entry['value'], metric=entry['metric']) for entry in entries])
    else:
        output = []
        for entry in entries:
            output.append('{} {} {}'.format(datetime.datetime.fromtimestamp(entry['time']).isoformat(), entry['metric'], entry['value']))
        return '\n'.join(output)


class TestCli(unittest.TestCase):
    def cli(self, command, input=''):
        stdin = StringIO(input)
        try:
            return str(run(['--config-dir', self._config_dir] + command, stdin))
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
        self.assertFalse('first-metric' in second_list)
        self.assertTrue('other-metric' in second_list)

    def test_move(self):
        self.cli(['store', 'first-metric', '1'])
        self.cli(['store', 'first-metric', '2'])
        self.cli(['move', 'first-metric', 'second-metric'])
        lst = self.cli(['list'])
        self.assertTrue('first-metric' not in lst)
        self.assertTrue('second-metric' in lst)
        self.assertEqual(self.cli(['best', 'second-metric']), '2.0')

    def test_backup(self):
        self.cli(['store', 'first-metric', '1'])
        self.cli(['store', 'other-metric', '2'])

        backup_string = self.cli(['backup'])

        for filename in os.listdir(self._config_dir):
            os.unlink(os.path.join(self._config_dir, filename))

        self.assertEqual(self.cli(['list']), '')

        for filename in os.listdir(self._config_dir):
            os.unlink(os.path.join(self._config_dir, filename))

        self.cli(['restore'], input=backup_string)

        lst = self.cli(['list'])
        self.assertTrue('other-metric' in lst)
        self.assertTrue('first-metric' in lst)

    def test_backup_compatible(self):
        BACKUP_STRING = '{"metrics": {"first-metric": {"values": [{"time": 1470877073.3021483, "value": 1.0}]}, "other-metric": {"values": [{"time": 1470877073.302729, "value": 2.0}]}}, "version": 1}'

        self.cli(['restore'], input=BACKUP_STRING)
        lst = self.cli(['list'])
        self.assertTrue('other-metric' in lst)
        self.assertTrue('first-metric' in lst)

if __name__ == "__main__":
	main()
