import itertools
import logging

import sparklines

from . import ids, store

LOGGER = logging.getLogger('statistics')

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

def summary(metric_data, update=False, ident=None, index=0):
    LOGGER.debug('Summarising')

    value = store.get_value(metric_data, ident, index=index)
    messages = ['{:.2f}'.format(value)]
    value_rank = rank(metric_data, ident=None, index=index)
    if value_rank == 0 and len(metric_data['values']) > 1:
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
        messages.append('{} best'.format(ordinal_name(value_rank + 1)))
        messages.append('Quantile: {:.2f}'.format(quantile(metric_data, index=index)))
        ratio = best_ratio(metric_data, index=index)
        if ratio is not None:
            messages.append('Ratio of best: {:.2f}'.format(ratio))

    ident_type = metric_data.get('ident_type', None)
    ident_period = metric_data.get('ident_period', 1)

    id_series = ident_type and ids.ID_SERIES[ident_type]

    LOGGER.debug('Building sparkline')
    old = list(store.get_last_values(metric_data, 10, ident=ident, id_series=id_series, ident_period=ident_period, index=index))
    messages.append(sparklines.sparklines(old)[0])

    LOGGER.debug('Formatting result')
    result = u'{}'.format('\n'.join(messages))
    LOGGER.debug('Result formatted')
    return result

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
