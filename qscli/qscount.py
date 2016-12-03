#!/usr/bin/python
"""
Very feature complete utility to count things.

Usage:

qscount # Count some things
qscount show
qscount clear
qscount incr hops
qscount list # list the things that you are counting

"""

import argparse
import contextlib
import datetime
import json
import logging
import os
import pdb
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

import fasteners

from . import ipc

CURRENT = 'CURRENT'

def get_set_id(string):
    if string == 'CURRENT':
        return CURRENT
    else:
        return int(string)

def counter_arg(parser):
    return parser.add_argument('counter', type=str, default='DEFAULT', help='What are you counter', nargs='?')

DEFAULT_DATA_DIR = os.path.join(os.environ['HOME'], '.config', 'qscount')

PARSER = argparse.ArgumentParser(description='')
PARSER.add_argument('--config-dir', '-D', type=str, help='Use this directory to store data', default=DEFAULT_DATA_DIR)

PARSERS = PARSER.add_subparsers(dest='command')

new_set = PARSERS.add_parser('new-set', help='Count in a new set')
new_set.add_argument('counter', type=str, help='What are you counting')

incr = PARSERS.add_parser('incr', help='Increment a counter')
counter_arg(incr)

log = PARSERS.add_parser('log', help='Show when each event occurred')
counter_arg(log)
log.add_argument('--set', type=get_set_id, help='Show the count for a particular set (CURRENT for the current set)')
log.add_argument('--json', action='store_true', help='Output in machine readable json')

move = PARSERS.add_parser('move', help='Rename a counter')
move.add_argument('before', type=str)
move.add_argument('after', type=str)

merge = PARSERS.add_parser('merge', help='Merge together two counters')
merge.add_argument('target', type=str)
merge.add_argument('merged', type=str)

PARSERS.add_parser('daemon')

note = PARSERS.add_parser('note', help='Record a note about a counter')
counter_arg(note)
note.add_argument('note', type=str, help='A note to record')

def days_ago(string):
    return datetime.date.today() - datetime.timedelta(days=int(string))

def backticks(command):
    process = subprocess.Popen(command, stdout=subprocess.PIPE)
    result, _ = process.communicate(command)
    if process.returncode != 0:
        raise Exception('{!r} returned non-zero return code {!r}'.format(command, process.returncode))
    return result

def fuzzy_date(string):
    if string in ('today', 'yesterday') or string.endswith('day ago') or string.endswith('days ago'):
        # reset dayish things to midnight
        day = fuzzy_date_raw(string)
        return datetime.datetime(day.year, day.month, day.day)
    else:
        return fuzzy_date_raw(string)

def fuzzy_date_raw(string):
    return datetime.datetime.fromtimestamp(float(backticks(['date', '-d', string, '+%s'])))


def rel_or_fuzzy_date(string):
    unit_durations = dict(s=1, m=60, h=3600, d=3600 * 24)
    match = re.search(r'\+(\d+)([dhms])', string)
    if match:
        period, unit = match.groups()
        return datetime.timedelta(seconds=unit_durations[unit] * int(period))
    else:
        return fuzzy_date(string)

def compare_sort_method(name):
    if name == 'name':
        return compare_sort_name
    elif name == 'shortfall':
        return compare_sort_shortfall
    else:
        raise ValueError(name)

def days_ago_argument(parser):
    parser.add_argument('--days-ago', '-A', type=days_ago, dest='date', help='Summary events on this day')

def json_argument(parser):
    parser.add_argument('--json', action='store_true', help='Output results in machine-readable json')

summary = PARSERS.add_parser('summary', help='Summarize counts')
days_ago_argument(summary)
json_argument(summary)
summary.add_argument('--regexp', '-x', type=re.compile, help='Only show counters matching this regular expression')
summary.add_argument('--zeros', '-0', action='store_true', help='Display counts even if no events happened during *this* period')

# This feature might not belong in this program
compare = PARSERS.add_parser('compare', help='Compare what happened in two periods')
compare.add_argument('start1', type=fuzzy_date, help='When the first period starts (format suitable for `date -d`)')
compare.add_argument('end1', type=rel_or_fuzzy_date, help='When the first period starts a relative date (e.g. +1d) or something suitable for date -d ')
compare.add_argument('start2', type=fuzzy_date)
compare.add_argument('end2', type=rel_or_fuzzy_date)
compare.add_argument('--sort', choices=('name', 'shortfall'), default='name', type=str)
compare.add_argument('--json', dest='is_json', action='store_true', help='Output results as json')
compare.add_argument('--regex', '-x', type=re.compile, help='Only display counters matching this regular expression')


delete_parser = PARSERS.add_parser('delete', help='List counters')
delete_parser.add_argument('counter', type=str, help='What are you counter')

list_parser = PARSERS.add_parser('list', help='List counters')
days_ago_argument(list_parser)

count_parser = PARSERS.add_parser('count', help='Show the count')
counter_arg(count_parser)
count_parser.add_argument('--set', type=get_set_id, help='Show the count for a particular set (CURRENT) for the current set)')

PARSERS.add_parser('shell')

def main():
    if '--test' in sys.argv[1:]:
        sys.argv.remove('--test')
        unittest.main()
    else:
        options = PARSER.parse_args(sys.argv[1:] or ['incr'])
        print run(options)

DATA_FILE = 'data'

def run(options):
    if options.command == 'daemon':
        return ipc.run_server(PARSER, run)

    with with_data(os.path.join(options.config_dir, DATA_FILE)) as data:
        counter = Counter(data)
        if options.command == 'shell':
            return str(counter.shell())
        if options.command == 'new-set':
            return str(counter.new_set(options.counter))
        elif options.command == 'move':
            return str(counter.move(options.before, options.after))
        elif options.command == 'merge':
            return str(counter.merge(options.target, options.merged))
        elif options.command == 'delete':
            return str(counter.delete(options.counter))
        elif options.command == 'incr':
            return str(counter.incr(options.counter))
        elif options.command == 'count':
            return str(counter.count(options.counter, options.set))
        elif options.command == 'log':
            return str(counter.log(options.counter, options.set, options.json))
        elif options.command == 'summary':
            return str(counter.summary(options.date, options.regexp, options.zeros, options.json))
        elif options.command == 'compare':
            end1 = options.start1 + options.end1 if isinstance(options.end1, datetime.timedelta) else options.end1
            end2 = options.start2 + options.end2 if isinstance(options.end2, datetime.timedelta) else options.end2
            sort_func = compare_sort_method(options.sort)
            return str(counter.compare(options.start1, end1, options.start2, end2, sort_func=sort_func, is_json=options.is_json, regex=options.regex))
        elif options.command == 'note':
            return str(counter.note(options.counter, options.note))
        elif options.command == 'list':
            return str(counter.list(options.date))
        else:
            raise ValueError(options.command)

def compare_sort_name((name, _count1, _count2)):
    return name

def compare_sort_shortfall((_name, count1, count2)):
    if not count1:
        return (1.0, count1)
    else:
        result = (float(min(count2, count1)) / (count1 or 1), count1)
    return result

class Counter(object):
    def __init__(self, data):
        self._data = data

    @contextlib.contextmanager
    def with_counter(self, name):
        if '\n' in name:
            raise ValueError(name)
        counters = self._data.setdefault('counters', dict())
        counter = counters.setdefault(name, dict())
        counter.setdefault('events', [])
        counter.setdefault('notes', [])
        counter.setdefault('set', 0)
        yield counter

    def new_set(self, name):
        with self.with_counter(name) as counter:
            counter['set'] += 1

    def shell(self):
        pdb.set_trace()

    def incr(self, name):
        with self.with_counter(name) as counter:
            event = dict(time=time.time(), set=counter['set'])
            counter['events'].append(event)

        return self.count(name)

    def count(self, name, set_id=None):
        with self.with_counter(name) as counter:
            if set_id == CURRENT:
                set_id = counter['set']

            events = counter['events']
            events = [event for event in events if set_id is None or event.get('set', None) == set_id]

            return len(events)

    def log(self, name, set_id, is_json):
        with self.with_counter(name) as counter:
            if set_id == CURRENT:
                set_id = counter['set']

            events = counter['events']
            events = [event for event in events if set_id is None or event.get('set', None) == set_id]

            if not is_json:
                string_result = '\n'.join(datetime.datetime.fromtimestamp(event['time']).isoformat() + ' ' + str(event['set']) for event in events)
                return string_result
            else:
                return json.dumps(dict(events=events))

    def delete(self, name):
        del self._data['counters'][name]
        return ''

    def list(self, date=None):
        counters = sorted(self._data['counters'])
        if days_ago is not None:
            new_counters = []
            for c in counters:
                counter_events = self._data['counters'][c]['events']
                if filter_events(counter_events, date=date):
                    new_counters.append(c)
            counters = new_counters

        return '\n'.join(counters)

    def note(self, name, note):
        with self.with_counter(name) as counter:
            counter['notes'].append(dict(time=time.time(), note=note))
        return ''

    def move(self, before, after):
        self._data['counters'][after] = self._data['counters'][before]
        del self._data['counters'][before]

    def merge(self, target, merged):
        with self.with_counter(target) as target_counter:
            with self.with_counter(merged) as merged_counter:

                is_simple_counter = target_counter['set'] == merged_counter['set'] == 0

                merged_set_offset = target_counter.get('set', 1)

                if not is_simple_counter:
                    for event in merged_counter['events']:
                        event['set'] = merged_set_offset + event.get('set', 0)

                new_events = target_counter['events'] + merged_counter['events']
                new_events.sort(key=lambda x: x['time'])

                if not is_simple_counter:
                    set_id = 0
                    for event in new_events:
                        set_id = max(event.get('set', 0), set_id)
                        if event.get('set', 0) < set_id:
                            raise Exception('Overlapping sets')

                target_counter['events'] = 'events'
                target_counter['notes'] = sorted(target_counter['notes'] + merged_counter['notes'], key=lambda x: x['time'])
                target_counter['set'] = max([event['set'] for event in target_counter['events']]) + 1


    def summary(self, date, regexp, show_zeros, json_format):
        counts = []
        for name, counter in sorted(self._data['counters'].items()):
            if regexp and not regexp.search(name):
                continue

            events = counter['events']
            events = filter_events(events, date=date)

            count = len(events)

            if count == 0 and not show_zeros:
                continue
            else:
                counts.append((name, count))

        if json_format:
            json_counts = [dict(name=name, count=count) for (name, count) in counts]
            return json.dumps(dict(counts=json_counts, indent=4))
        else:
            return '\n'.join('{}: {}'.format(action, count) for action, count in sorted(counts))

    def compare(self, period1_start, period1_end, period2_start, period2_end, sort_func=compare_sort_name, is_json=False, regex=None):
        results = []
        for name, counter in sorted(self._data['counters'].items()):
            if regex and not regex.search(name):
                continue

            events = counter['events']

            period1_events = [event for event in events if
                                  period1_start <= datetime.datetime.fromtimestamp(event['time']) <= period1_end]

            period2_events = [event for event in events if
                                  period2_start <= datetime.datetime.fromtimestamp(event['time']) <= period2_end]

            if period1_events or period2_events:
                results.append((name, len(period1_events), len(period2_events)))

        results.sort(key=sort_func)
        if is_json:
            return json.dumps(results)
        else:
            return '\n'.join('{} {} {}'.format(*result) for result in results)

def filter_events(events, date=None):
    events = events[:]
    if date:
        events = [event for event in events if datetime.datetime.fromtimestamp(event['time']).date() == date]
    return events

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

class TestCounter(unittest.TestCase):
    def setUp(self):
        self.direc = tempfile.mkdtemp()
        self.config_dir = os.path.join(self.direc, 'config')
        self.fake_time = FakeTime()

    def tearDown(self):
        shutil.rmtree(self.direc)

    def run_cli(self, *args):
        args = list(args)
        args = ['--config-dir', self.config_dir] + args
        return run(args)

    def test_basic(self):
        self.assertEquals(self.run_cli('count'), '0')
        self.assertEquals(self.run_cli('incr'), '1')
        self.assertEquals(self.run_cli('incr'), '2')
        self.assertEquals(self.run_cli('count'), '2')

    def test_names(self):
        self.assertEquals(self.run_cli('incr', 'first'), '1')
        self.assertEquals(self.run_cli('incr', 'second'), '1')

        self.assertEquals(self.run_cli('incr', 'first'), '2')
        self.assertEquals(self.run_cli('count', 'first'), '2')
        self.assertEquals(self.run_cli('count', 'second'), '1')

    def test_summary(self):
        self.run_cli('incr', 'first')
        self.run_cli('incr', 'second')
        self.run_cli('incr', 'second')

        self.assertEquals(self.run_cli('summary'), 'first: 1\nsecond: 2\n')

    def test_note(self):
        self.set_time(0)
        self.set_time(1)
        self.assertEquals(self.run_cli('incr', 'first'), '1')
        self.set_time(2)
        self.assertEquals(self.run_cli('note', 'first', 'mild pain'), '')
        self.set_time(2)
        self.assertEquals(self.run_cli('log', 'first'), '')

    def test_sets(self):
        self.run_cli('incr', 'first')
        self.assertEquals(self.run_cli('count', 'first', '--set', 'CURRENT'), '1')
        self.run_cli('new-set', 'first')
        self.assertEquals(self.run_cli('count', 'first'),  '1')
        self.assertEquals(self.run_cli('count', 'first', '--set', 'CURRENT'), '0')
        self.run_cli('incr', 'first')
        self.assertEquals(self.run_cli('count', 'first'), '2')
        self.assertEquals(self.run_cli('count', 'first', '--set', 'CURRENT'), '1')

    def set_time(self, value):
        self.fake_time.set_time(value)

# Utility functions
class FakeTime(object):
    def __init__(self):
        self._time = 0.0
        self._lock = threading.RLock()
        self._tick_events = []
        self._logger = logging.getLogger('FakeTime')

    def time(self):
        return self._time

    def set_time(self, value):
        with self._lock:
            self._time = value
            self._logger.debug('Set time to %r', value)
            self._tick()

    def incr_time(self, incr):
        with self._lock:
            self.set_time(self._time + incr)

    def _tick(self):
        for expiry, event in self._tick_events[:]:
            if self._time > expiry:
                self._logger.debug('Expiring %r', self._time)
                self._tick_events.remove((expiry, event))
                event.set()

    def sleep(self, delay):
        self._logger.debug('Sleeping for %r at %r', delay, self._time)
        event = threading.Event()
        with self._lock:
            start_time = self._time
            expiry = self._time + delay
            self._tick_events.append((expiry, event))
        event.wait()
        self._logger.debug('Sleep started at %r for %r expired', start_time, delay)

if __name__ == '__main__':
	main()
