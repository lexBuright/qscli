"Functions that perform summary statistics on data"

import itertools
import json
import logging

import sparklines

from . import ids, store, native_store

LOGGER = logging.getLogger('statistics')

def best(metric_data):
    if not native_store.check_if_empty(metric_data):
        return None
    else:
        best_record = max(native_store.get_raw_values(metric_data))
        return best_record

def mean(metric_data):
    if not native_store.check_if_empty(metric_data):
        return None
    else:
        value = sum(native_store.get_raw_values(metric_data)) / native_store.num_values(metric_data)
        return value

def run_length(metric_data):
    rev_values = native_store.get_raw_values(metric_data)[::-1]

    records = zip(rev_values,rev_values[1:])
    result = len(list(itertools.takewhile(lambda x: x[0] > x[1], records))) + 1
    return result

def quantile(metric_data, index=0):
    # don't pull in numpy / scipy dependnecies
    LOGGER.debug('Quantile')

    values = native_store.get_raw_values(metric_data)
    if not values:
        return None

    last = native_store.get_value(metric_data, index=index)
    lower = len([x for x in values if x <= last])
    upper = len(values) - len([x for x in values if x > last])
    return float(lower + upper) / 2 / len(values)

def best_ratio(metric_data, index=0):
    if native_store.num_values(metric_data) < 1:
        return None
    else:
        last = native_store.get_value(metric_data, index=index)
        rest = native_store.get_raw_values(metric_data)[:-1]
        if not rest or max(rest) == 0:
            return None
        else:
            return last / max(rest)

def get_summary_data(metric_data, ident, index):
    value_rank = rank(metric_data, ident=None, index=index)
    is_best = value_rank == 0
    is_first = native_store.num_values(metric_data) == 1
    runl = run_length(metric_data)
    is_broken_run = not is_first and runl < 2
    quantile_value = quantile(metric_data, index=index)

    timeseries = get_timeseries(metric_data, ident, index, 10)
    sparkline = sparklines.sparklines(timeseries)[0]
    mean_value = mean(metric_data)
    num_values = native_store.num_values(metric_data)

    return dict(
        mean=mean_value,
        best=best(metric_data),
        is_best=is_best,
        is_first=is_first,
        num_values=num_values,
        run_length=runl,
        rank=value_rank,
        is_broken_run=is_broken_run,
        quantile=quantile_value,
        sparkline=sparkline,
        timeseries=timeseries,
        best_ratio=best_ratio(metric_data, index=index),
        value = native_store.get_value(metric_data, ident, index=index)
    )

def get_timeseries(metric_data, ident, index, num_values):
    ident_type = metric_data.get('ident_type', None)
    ident_period = metric_data.get('ident_period', 1)
    id_series = ident_type and ids.ID_SERIES[ident_type]
    return list(native_store.get_last_values(
        metric_data,
        num_values,
        ident=ident,
        id_series=id_series,
        ident_period=ident_period,
        index=index))

def summary_format(data, update):
    messages = ['{:.2f}'.format(data['value'])]

    if data['is_best']:
        messages.append('New best')

    if data['is_first']:
        messages.append('First time')

    if data['run_length'] > 1:
        messages.append('Run of {}'.format(data['run_length']))

    if data['is_broken_run'] and not update:
        messages.append('Broken run :(')

    if not data['is_first']:
        messages.append('{} best'.format(ordinal_name(data['rank'] + 1)))
        messages.append('Quantile: {:.2f}'.format(data['quantile']))
        messages.append('Ratio of best: {:.2f}'.format(data['best_ratio']))

    messages.append(data['sparkline'])
    result = u'{}'.format('\n'.join(messages))
    return result

def summary(metric_data, update=False, ident=None, index=0, is_json=False):
    data = get_summary_data(metric_data, ident, index)
    if is_json:
        return json.dumps(data)
    else:
        if data['num_values'] >= 1:
            return summary_format(data, update)
        else:
            return 'No data'

def rank(metric_data, ident=None, index=0):
    LOGGER.debug('Rank')
    result = 0
    last = native_store.get_value(metric_data, ident, index=index)
    for value in native_store.get_raw_values(metric_data):
        if value > last:
            result += 1
    return result

def ordinal_name(number):
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
