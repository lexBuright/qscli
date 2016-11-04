# Interfaces to timeseries data (in preference to multiple backenda

import collections
import itertools
import time

DataPoint = collections.namedtuple('DataPoint', 'time value id')

def init(metric_data):
    metric_data.setdefault('values', [])

def get_timeseries(metric_data):
    return [DataPoint(time=value['time'], value=value['value'], id=i) for i, value in enumerate(metric_data['values'])]

def _get_values(metric_data):
    return metric_data['values']

def get_raw_values(metric_data):
    return [entry['value'] for entry in metric_data['values']]

def delete_ids(metric_data, ids):
    for index in sorted(ids, reverse=True):
        metric_data['values'].pop(index) # unnecessary O(n**2)

def get_ids_values(metric_data):
    return [entry['id'] for entry in metric_data['values'] if entry['id'] is not None]

def num_values(metric_data):
    return len(metric_data['values'])

def get_has_ids(metric_data):
    return any(entry.get('id') for entry in metric_data['values'])

def check_if_empty(metric_data):
    return metric_data['values']

def get_value(metric_data, ident=None, index=0):
    values = get_last_values(metric_data, 1, ident, index=index)
    return values[0] if values else None

def get_last_values(metric_data, num, ident=None, id_series=None, ident_period=1, index=0):
    """If ids_before_func use it to generate a set of ids
    before the last value (of the one specified by ident
    """
    if index < 0:
        raise ValueError(index)

    has_ids = get_has_ids(metric_data)

    negative_index = -1 - index

    if has_ids:
        if ident is None:
            id_entries = sorted(_get_values(metric_data), key=lambda x: x.get('id'))
            entries = id_entries[negative_index:negative_index - num:-1]
        else:
            before_id_entries = sorted([x for x in _get_values(metric_data) if x.get('id') <= ident], key=lambda x: x.get('id'))
            entries = before_id_entries[negative_index:negative_index - num:-1]
    else:
        if ident is not None:
            raise ValueError(ident)
        else:
            entries = _get_values(metric_data)[negative_index:negative_index - num:-1]

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

def store(metric_data, time, value):
    metric_data['values'].append(dict(time=time, value=value))

def update_ids(metric_data, value_by_id):
    "Upsert values by id"
    updated = set()
    for entry in metric_data['values']:
        entry_id = entry.get('id')
        if entry_id is not None:
            if entry_id in value_by_id:
                entry['value'] = float(value_by_id[entry_id])
                entry['time'] = time.time()
                updated.add(entry_id)

    for ident, value in value_by_id.items():
        if ident in updated:
            continue
        else:
            metric_data['values'].append(dict(time=time.time(), id=ident, value=float(value)))
    return ''

def update(metric_data, value, ident):
    init(metric_data)

    entry = dict(time=time.time(), value=value)
    if ident is not None:
        entry['id'] = ident

    metric_values = metric_data['values']

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
