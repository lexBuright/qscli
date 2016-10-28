"Functions that perform summary statistics on data"

import itertools
import json
import logging

import sparklines

from . import ids, store

LOGGER = logging.getLogger('statistics')

def best(metric_data):
    if not metric_data['values']:
        return None
    else:
        best_record = max(metric_data['values'], key=lambda record: record['value'])
        return best_record['value']

def mean(metric_data):
    if len(metric_data['values']) == 0:
        return None
    else:
        value = sum([record['value'] for record in metric_data['values']]) / len(metric_data['values'])
        return value

def run_length(metric_data):
    rev_values = [entry['value'] for entry in metric_data['values']][::-1]

    records = zip(rev_values,rev_values[1:])
    result = len(list(itertools.takewhile(lambda x: x[0] > x[1], records))) + 1
    return result

def quantile(metric_data, index=0):
    # don't pull in numpy / scipy dependnecies
    LOGGER.debug('Quantile')

    values = [d['value'] for d in metric_data['values']]
    if not values:
        return None

    last = store.get_value(metric_data, index=index)
    lower = len([x for x in values if x <= last])
    upper = len(values) - len([x for x in values if x > last])
    return float(lower + upper) / 2 / len(values)

def best_ratio(metric_data, index=0):
    if len(metric_data['values']) < 1:
        return None
    else:
        last = store.get_value(metric_data, index=index)
        rest = [x['value'] for x in metric_data['values'][:-1]]
        if not rest or max(rest) == 0:
            return None
        else:
            return last / max(rest)

def get_summary_data(metric_data, ident, index):
    value_rank = rank(metric_data, ident=None, index=index)
    is_best = value_rank == 0
    is_first = len(metric_data['values']) == 1
    runl = run_length(metric_data)
    is_broken_run = not is_first and runl < 2
    quantile_value = quantile(metric_data, index=index)

    timeseries = get_timeseries(metric_data, ident, index, 10)
    sparkline = sparklines.sparklines(timeseries)[0]
    mean_value = mean(metric_data)
    num_values = len(metric_data['values'])

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
        value = store.get_value(metric_data, ident, index=index)
    )

def get_timeseries(metric_data, ident, index, num_values):
    ident_type = metric_data.get('ident_type', None)
    ident_period = metric_data.get('ident_period', 1)
    id_series = ident_type and ids.ID_SERIES[ident_type]
    return list(store.get_last_values(
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
    last = store.get_value(metric_data, ident, index=index)
    for entry in metric_data['values']:
        if entry['value'] > last:
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
