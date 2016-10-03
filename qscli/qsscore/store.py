import collections
import copy
import csv
import datetime
import itertools
import json
import logging
import StringIO
import subprocess
import time

import jsdb

from . import config, ids

LOGGER = logging.getLogger('data')

def update(metric_data, value, ident):
    if metric_data.get('ident_type') and ident is None:
        ident = ids.TIME_ID_FUNC[metric_data.get('ident_type')](datetime.datetime.now())

    metric_values = metric_data.setdefault('values', [])
    entry = dict(time=time.time(), value=value)
    if ident is not None:
        entry['id'] = ident

    if not metric_values:
        metric_values.append(entry)

    if ident is not None:
        LOGGER.debug('update: looking up old value')
        ident_entries = [x for x in metric_values if x.get('id') == ident]
        if ident_entries:
            ident_entry, = ident_entries
            ident_entry['value'] = value
        else:
            metric_values.append(entry)
    else:
        metric_values[-1] = entry
    return ''

def get_value(metric_data, ident=None, index=0):
    LOGGER.debug('Getting value')
    return get_last_values(metric_data, 1, ident, index=index)[0]

def get_last_values(metric_data, num, ident=None, id_series=None, ident_period=1, index=0):
    """If ids_before_func use it to generate a set of ids
    before the last value (of the one specified by ident
    """
    if index < 0:
        raise ValueError(index)

    has_ids = any(entry.get('id') for entry in metric_data['values'])

    negative_index = -1 - index


    if has_ids:
        if ident is None:
            id_entries = sorted(metric_data['values'], key=lambda x: x.get('id'))
            entries = id_entries[negative_index:negative_index - num:-1]
        else:
            before_id_entries = sorted([x for x in metric_data['values'] if x.get('id') <= ident], key=lambda x: x.get('id'))
            entries = before_id_entries[negative_index:negative_index - num:-1]
    else:
        if ident is not None:
            raise ValueError(ident)
        else:
            entries = metric_data['values'][negative_index:negative_index - num:-1]

    if not has_ids and id_series:
        raise Exception('Can only use an ids_before_func when we have ids')

    if id_series:
        series = id_series(ident or entries[0]['id'], -ident_period)
        idents = itertools.islice(series, num)
        values_by_id = {e['id']: e['value'] for e in entries}
        result = [values_by_id.get(ident, 0) for ident in idents]
        return result
    else:
        result = [e['value'] for e in entries]
        return result

def up_migrate_data(data):
    new_data = copy.copy(data)
    version = get_version(new_data)

    if version == None:
        metrics = new_data.get('metrics', dict())
        for metric_name in metrics:
            metric = config.get_metric_data(new_data, metric_name)
            metric['values'] = [dict(time=tm, value=value) for (tm, value) in metric['values']]

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
            metric = config.get_metric_data(new_data, metric_name)
            metric['values'] = [(value['time'], value['value']) for value in metric['values']]

        del new_data['version']
    return new_data

def log_action(data, options, delete=False):
    if options.days_ago is not None:
        start_time, end_time = days_ago_bounds(options.days_ago)
    elif options.since:
        start_time = dt_to_unix(options.since)
        end_time = None
    else:
        start_time = end_time = None

    entries = find_entries(data, name_regex=options.regex, start_time=start_time, end_time=end_time, indexes=options.index)

    if delete:
        delete_entries(data, entries)
    else:
        return log_entries(entries, options.json)

def store_csv(metric_data, csv_string):
    entries = list(csv.reader(StringIO.StringIO(csv_string)))

    value_by_id = dict(entries)
    updated = set()

    metric_values = metric_data.setdefault('values', [])
    for entry in metric_values:
        entry_id = entry.get('id')
        if entry_id is not None:
            if entry_id in value_by_id:
                entry['value'] = float(value_by_id[entry_id])
                entry['time'] = time.time()
                updated.add(entry_id)

    for ident, value in entries:
        if ident in updated:
            continue
        else:
            metric_values.append(dict(time=time.time(), id=ident, value=float(value)))

    return ''

def get_version(data):
    return data.get('version')

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

def days_ago_bounds(days_ago):
    start = datetime.datetime.now().replace(hour=0, second=0, microsecond=0) - datetime.timedelta(days=days_ago)
    start_time = dt_to_unix(start)
    end_time = start_time + 3600 * 24
    return start_time, end_time

def dt_to_unix(dt):
    return time.mktime(dt.timetuple()) + dt.microsecond * 1.0e-6

def find_entries(data, name_regex, start_time, end_time, indexes):
    data.setdefault('metrics', {})
    entries = []
    for metric_name, metric in data['metrics'].items():
        if name_regex is not None and not name_regex.search(metric_name):
            continue

        values = []
        for index, value in enumerate(jsdb.python_copy.copy(metric['values'])):
            if start_time and value['time'] < start_time:
                continue
            if end_time and value['time'] >= end_time:
                continue
            value.update(metric=metric_name)
            value.update(index=index)
            values.append(value)

        entries.extend(values)

    entries.sort(key=lambda v: v['time'])

    if indexes:
        indexes = [(len(entries) + i if i < 0 else i ) for i in indexes]
        entries = [e for i, e in enumerate(entries) if i in indexes]

    return entries

def delete_entries(data, entries):
    deleted_by_metric = collections.defaultdict(list)
    for entry in entries:
        deleted_by_metric[entry['metric']].append(entry['index'])

    for metric, lst in deleted_by_metric.items():
        for index in sorted(lst, reverse=True): # unnecessary O(n**2)
            data['metrics'][metric]['values'].pop(index)

def store(metric_data, value):
    metric_values = metric_data.setdefault('values', [])
    metric_values.append(dict(time=time.time(), value=value))
    return ''

def command_update(metric_data, command, refresh, first_id):
    if not metric_data.get('ident_type'):
        raise Exception('Must have an --id-type to use this options')

    if first_id is None:
        first_id = min(value['id'] for value in metric_data['values'] if value['id'] is not None)

    last_id = ids.TIME_ID_FUNC[metric_data.get('ident_type')](metric_data.get('ident_period', 1), datetime.datetime.now())
    known_idents = set(value['id'] for value in metric_data['values'] if value['id'] is not None)

    id_series = ids.ID_SERIES[metric_data['ident_type']]
    for ident in id_series(first_id, metric_data.get('ident_period', 1)):
        if ident > last_id:
            break

        if refresh or ident not in known_idents:
            LOGGER.debug('Updating %r', ident)
            LOGGER.debug('Running command %r', command + [ident])
            value = float(subprocess.check_output(command + [ident]))
            update(metric_data, value, ident)
        else:
            LOGGER.debug('Already a value for %r', ident)

def log_entries(entries, json_output):
    if json_output:
        return json.dumps([dict(time=entry['time'], value=entry['value'], metric=entry['metric'], id=entry.get('id')) for entry in entries])
    else:
        output = []
        for entry in entries:
            output.append('{} {} {} {}'.format(datetime.datetime.fromtimestamp(entry['time']).isoformat(), entry['metric'], entry.get('id', '-'), entry['value']))
        return '\n'.join(output)
