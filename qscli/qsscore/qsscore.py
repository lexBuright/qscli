#!/usr/bin/python
"""Stupidly feature-complete command-line tool to keep track of scores;
Quickly gameify any activity.

Designed to be useable programmatically, though you might prefer to use something like a
database of ELK (elasticsearch logstash kibana) if you are being serious.
"""

import argparse
import contextlib
import datetime
import json
import logging
import os
import sys

import jsdb
import jsdb.leveldict
import jsdb.python_copy

from .. import ipc
from ..symbol import Symbol

from . import store
from . import config
from . import statistics
from . import parse_utils
from . import native_store

LOGGER = logging.getLogger()

UNKNOWN = Symbol('unknown')

DATA_DIR = os.path.join(os.environ['HOME'], '.config', 'qsscore')


def days_ago_option(parser):
    parser.add_argument('--days-ago', '-A', type=int, help='Returns scores recorded this many days ago')

UNIT_SIZE = {'h': datetime.timedelta(seconds=3600), 'm': datetime.timedelta(seconds=60), 's': datetime.timedelta(seconds=1), 'd': datetime.timedelta(days=1)}

def build_parser():
    PARSER = argparse.ArgumentParser(description=__doc__)
    PARSER.add_argument('--debug', action='store_true', help='Print debug output')

    PARSER.add_argument('--config-dir', '-d', default=DATA_DIR, help='Read and store data in this directory')
    parsers = PARSER.add_subparsers(dest='command')

    store.add_parsers(parsers)

    parsers.add_parser('daemon', help='Run a daemon')

    records_command = parsers.add_parser('records', help='Display when all time bests were obtained')
    records_command.add_argument('--json', action='store_true', help='Output results in machine readable json', default=False)
    days_ago_option(records_command)
    parse_utils.regexp_option(records_command)

    delete_command = parsers.add_parser('delete', help='Delete a metric')
    delete_command.add_argument('metric', type=str)

    move_command = parsers.add_parser('move', help='Rename a metric')
    move_command.add_argument('old_name', type=str)
    move_command.add_argument('new_name', type=str)

    parsers.add_parser('backup', help='Dump out all data to standard out')
    parsers.add_parser('restore', help='Restore a previous data dump')

    config_command = parsers.add_parser('config', help='Change the configuration for a series')
    config_command.add_argument('--id-type', type=str, choices=('isodate', 'isohour', 'isominute'), help='Automatically create IDs. iosdate means ids of the form YYYY-MM-DD every number of days, isohour and isominute means ids taking the form of timestamps', dest='ident_type')
    config_command.add_argument('--id-period', type=int, help='How many id-type units per reading', dest='ident_period')
    config_command.add_argument('metric', type=str)

    def metric_command(p, name, help_string=''):
        command = p.add_parser(name, help=help_string)
        command.add_argument('metric', type=str)
        return command

    metric_command(parsers, 'best')
    metric_command(parsers, 'mean')
    metric_command(parsers, 'run-length')

    summary_parser = metric_command(parsers, 'summary', help_string='Summarise a result (defaults to the last value)')
    summary_parser.add_argument('--update', action='store_true', help='Assume last value is still changing')
    summary_parser.add_argument('--json', action='store_true', help='Output as machine readable testing')

    ident_mx = summary_parser.add_mutually_exclusive_group()
    ident_mx.add_argument('--id', type=str, help='Show summary for the result with this id')
    ident_mx.add_argument('--index', type=int, help='Show the nth most recent value', default=0)

    parsers.add_parser('list', help='List the things that we have scores for')
    return PARSER


def main():
    options = build_parser().parse_args(sys.argv[1:])
    if options.debug:
        logging.basicConfig(level=logging.DEBUG)

    LOGGER.debug('Running')
    result = run(options, sys.stdin)
    LOGGER.debug('Finished running')

    if result is not None:
        formatted = unicode(result).encode('utf8')
        print(formatted)

@contextlib.contextmanager
def with_jsdb_data(data_file):
    LOGGER.debug('Opening db')
    db = jsdb.Jsdb(data_file, storage_class=jsdb.leveldict.LevelDict)
    LOGGER.debug('Db open')
    with db:
        try:
            yield db
        except:
            db.rollback()
            raise
        else:
            LOGGER.debug('Committing')
            db.commit()
            LOGGER.debug('Committed')

with_data = with_jsdb_data

DATA_VERSION = 1

def run(options, stdin):
    if not os.path.isdir(options.config_dir):
        os.mkdir(options.config_dir)

    if options.command == 'daemon':
        return ipc.run_server(build_parser(), lambda more_options: run(more_options, stdin))

    data_file = os.path.join(options.config_dir, 'data.jsdb')

    with with_data(data_file) as data:
        # new_data = migrate_data(data, DATA_VERSION)
        # data.clear()
        # data.update(**new_data)
        if options.command == 'list':
            metric_names = sorted(data.get('metrics', dict()))
            return '\n'.join(metric_names)
        elif options.command == 'log':
            return store.log_action(data, options, delete=options.delete)
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
        elif options.command == 'records':
            if options.days_ago is not None:
                start, end = store.days_ago_bounds(options.days_ago)
            else:
                start = end = None
            return records(data, options.json, options.regex, start=start, end=end)

        metric_data = config.get_metric_data(data, options.metric)
        if options.command == 'store':
            return store.store(metric_data, options.value)
        elif options.command == 'store-csv':
            return store.store_csv(metric_data, stdin.read())
        elif options.command == 'update':
            return store.update(metric_data, options.value, options.id)
        elif options.command == 'best':
            return statistics.best(metric_data)
        elif options.command == 'mean':
            return statistics.mean(metric_data)
        elif options.command == 'run-length':
            return statistics.run_length(metric_data)
        elif options.command == 'summary':
            return statistics.summary(
                metric_data,
                options.update,
                ident=options.id,
                index=options.index,
                is_json=options.json)
        elif options.command == 'config':
            return config.config(
                metric_data,
                options.ident_type,
                options.ident_period)
        elif options.command == 'command-update':
            store.command_update(metric_data, command=options.update_command, refresh=options.refresh, first_id=options.first_id)
        else:
            raise ValueError(options.command)

def backup(data):
    data = jsdb.python_copy.copy(data)
    data['version'] = DATA_VERSION
    backup_string = json.dumps(data)
    return backup_string

def restore(data, backup_filename):
    data.clear()
    backup_data = json.loads(backup_filename)
    data.update(**backup_data)

def records(data, json_output, regex, start=None, end=None):
    result = {}
    for metric_name, metric_data in data['metrics'].items():
        timeseries = native_store.get_timeseries(metric_data)

        if regex is not None:
            if not regex.search(metric_name):
                continue

        if native_store.num_values(metric_data) == 0:
            continue

        sort_key = lambda v: (v.value, -v.time)
        record_entry = max(timeseries, key=sort_key)

        previous_entries = list(v for v in timeseries if v.time < record_entry.time)
        beaten_entry = max(previous_entries, key=sort_key) if previous_entries else None

        if start and record_entry.time < start:
            continue
        if end and record_entry.time >= end:
            continue

        if beaten_entry:
            improvement = record_entry.value - beaten_entry.value
        else:
            improvement = None

        result[metric_name] = dict(value=record_entry.value, time=record_entry.value, improvement=improvement)

    if not json_output:
        output = []
        for key in sorted(result.keys()):
            output.append('{} {} {} {}'.format(key, result[key]['value'], improvement, datetime.datetime.fromtimestamp(result[key]['time']).isoformat()))
        return '\n'.join(output)
    else:
        return json.dumps(dict(records=result))
