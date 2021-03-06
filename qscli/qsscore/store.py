import collections
import copy
import csv
import datetime
import json
import logging
import StringIO
import subprocess
import time

from . import ids
from . import parse_utils

LOGGER = logging.getLogger('data')

class Store(object):
    def __init__(self, ts_store):
        self._ts_store = ts_store

    def update(self, metric_data, value, ident):
        if metric_data.get('ident_type') and ident is None:
            ident = ids.TIME_ID_FUNC[metric_data.get('ident_type')](datetime.datetime.now())
        self._ts_store.update(metric_data, value, ident)

    def up_migrate_data(self, data):
        new_data = copy.copy(data)
        version = self.get_version(new_data)
        raise ValueError(version)

    def down_migrate_data(self, data):
        new_data = copy.copy(data)
        version = self.get_version(new_data)
        del version
        return new_data

    def log_action(self, data, options, delete=False):
        if options.days_ago is not None:
            start_time, end_time = days_ago_bounds(options.days_ago)
        elif options.since:
            start_time = dt_to_unix(options.since)
            end_time = None
        else:
            start_time = end_time = None

        entries = self.find_entries(data, name_regex=options.regex, start_time=start_time, end_time=end_time, indexes=options.index, name=options.name)

        if delete:
            self.delete_entries(data, entries)
        else:
            return self.log_entries(entries, options.json, options.output)

    def store_csv(self, metric_data, csv_string):
        entries = list(csv.reader(StringIO.StringIO(csv_string)))
        value_by_id = dict(entries)
        LOGGER.debug('Updating %r', value_by_id)

        self._ts_store.initialize(metric_data)
        self._ts_store.update_ids(metric_data, value_by_id)

    def get_version(self, data):
        return data.get('version')

    def migrate_data(self, data, to_version):
        while True:
            if self.get_version(data) == to_version:
                return data

            old_version = self.get_version(data)
            new_data = self.up_migrate_data(data)
            new_version = self.get_version(new_data)
            if not self.down_migrate_data(new_data) == data:
                raise Exception('Rounding tripping: {} -> {} -> {} failed'.format(old_version, new_version, old_version))


    def find_entries(self, data, name_regex, start_time, end_time, indexes, name):
        if name_regex is not None and name is not None:
            raise Exception('Cannot use both a name and a regular expression')

        data.setdefault('metrics', {})
        entries = []
        for metric_name, metric_data in data['metrics'].items():
            if name_regex is not None and not name_regex.search(metric_name):
                continue

            if name is not None and metric_name != name:
                continue

            values = []
            for value in self._ts_store.get_timeseries(metric_data):
                if start_time and value.time < start_time:
                    continue
                if end_time and value.time >= end_time:
                    continue
                values.append(dict(metric=metric_name, value=value.value, time=value.time, id=value.id))
            entries.extend(values)

        entries.sort(key=lambda v: v['time'])

        if indexes:
            indexes = [(len(entries) + i if i < 0 else i ) for i in indexes]
            entries = [e for i, e in enumerate(entries) if i in indexes]

        return entries

    def delete_entries(self, data, entries):
        deleted_by_metric = collections.defaultdict(list)
        for entry in entries:
            deleted_by_metric[entry['metric']].append(entry['id'])

        for metric, lst in deleted_by_metric.items():
            self._ts_store.delete_ids(data['metrics'][metric], lst)

    def store(self, metric_data, value):
        self._ts_store.initialize(metric_data)
        self._ts_store.store(metric_data, time.time(), value)
        return ''

    def command_update(self, metric_data, command, refresh, first_id):
        if not metric_data.get('ident_type'):
            raise Exception('Must have an --id-type to use this options')

        if first_id is None:
            first_id = min(self._ts_store.get_ids_values(metric_data))

        last_id = ids.TIME_ID_FUNC[metric_data.get('ident_type')](metric_data.get('ident_period', 1), datetime.datetime.now())
        known_idents = set(self._ts_store.get_ids_values(metric_data))

        id_series = ids.ID_SERIES[metric_data['ident_type']]
        for ident in id_series(first_id, metric_data.get('ident_period', 1)):
            if ident > last_id:
                break

            if refresh or ident not in known_idents:
                LOGGER.debug('Updating %r', ident)
                LOGGER.debug('Running command %r', command + [ident])
                value = float(subprocess.check_output(command + [ident]))
                self.update(metric_data, value, ident)
            else:
                LOGGER.debug('Already a value for %r', ident)

    def log_entries(self, entries, json_output, output_fields):
        if json_output and output_fields:
            raise Exception('Cannot output specific fields and json')

        if json_output:
            return json.dumps([dict(time=entry['time'], value=entry['value'], metric=entry['metric'], id=entry.get('id')) for entry in entries])
        else:
            result = []
            for entry in entries:
                info = dict(
                    time = datetime.datetime.fromtimestamp(entry['time']).isoformat(),
                    metric = entry['metric'],
                    ident = entry.get('id', '-'),
                    value = entry['value'],
                )
                result.append(' '.join(str(info[field]) for field in output_fields))

            return '\n'.join(result)

def add_parsers(parsers):
    # Parsers for data related commands
    store_command = parsers.add_parser('store', help='Store a score')
    store_command.add_argument('metric', type=str)
    store_command.add_argument('value', type=float)

    store_csv_command = parsers.add_parser('store-csv', help='Read a csv of id-value pairs and store/update them')
    store_csv_command.add_argument('metric', type=str)

    log_command = parsers.add_parser('log', help='Show all the scores for a period of time')
    log_command.add_argument('--output', '-o', help='csv of fields to output', type=csv_split, default='time,metric,ident,value')
    def log_command_option(command):
        name_group = command.add_mutually_exclusive_group()
        parse_utils.regexp_option(name_group)
        name_group.add_argument('name', type=str, help='Name of metric', nargs='?')

        log_date = command.add_mutually_exclusive_group()
        log_date.add_argument('--days-ago', '-A', type=int, help='Returns scores recorded this many days ago')
        log_date.add_argument('--since', type=parse_utils.fuzzy_date, help='Log results since a given date. (10d for ten days ago, otherwise and iso8601 timestamp or date)')
        command.add_argument('--json', action='store_true', help='Output results in machine readable json', default=False)
        command.add_argument('--index', action='append', type=int, help='Only delete these indexes')
        command.add_argument('--delete', action='store_true', help='Delete the records found')
    log_command_option(log_command)

    update_command = parsers.add_parser('update', help='Update the last entered score (or the score with a particular id)')
    update_command.add_argument('metric', type=str)
    update_command.add_argument('value', type=float)
    update_command.add_argument('--id', type=str, help='Update the score with this id (or create a value)')

    command_update_p = parsers.add_parser('command-update', help='If an --id-type is specified then update values by running an external command with ID as an argument')
    command_update_p.add_argument('metric', type=str)
    command_update_p.add_argument('update_command', nargs='+', type=str, help='Command to run')
    command_update_p.add_argument('--refresh', action='store_true', default=False, help='Update pre-existing values')
    command_update_p.add_argument('--first-id', type=str, help='Start updating at this id. Defaults to minimum stored id')

def days_ago_bounds(days_ago):
    start = datetime.datetime.now().replace(hour=0, second=0, microsecond=0) - datetime.timedelta(days=days_ago)
    start_time = dt_to_unix(start)
    end_time = start_time + 3600 * 24
    return start_time, end_time

def dt_to_unix(dt):
    return time.mktime(dt.timetuple()) + dt.microsecond * 1.0e-6

def csv_split(string):
    return [x.strip() for x in string.split(',')]
