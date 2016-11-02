"""An easy to use command-line time-series storage interface.

For bigger projects you may prefer to use something like graphite, innodb, or elastic search

qstimeseries append series 1.0
qstimeseries append stringseries --string "this is a string value"

"""

import argparse
import collections
import datetime
import json
import logging
import os
import sqlite3
import time

LOGGER = logging.getLogger()

DEFAULT_CONFIG_DIR = os.path.join(os.environ['HOME'], '.config', 'qstimeseries')

def ensure_database(config_dir):
    data_file = os.path.join(config_dir, 'data.sqlite')
    if not os.path.exists(data_file):
        try:
            LOGGER.debug('Creating database')
            db = sqlite3.connect(data_file)
            cursor = db.cursor()
            cursor.execute('''
            CREATE TABLE timeseries(id INTEGER PRIMARY KEY, series TEXT NOT NULL, given_ident TEXT, time TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL, float_value REAL, string_value TEXT,

            CONSTRAINT unique_ident UNIQUE (series, given_ident)

            );
            ''')
            db.commit()
            return db
        except:
            os.unlink(data_file)
            raise
    else:
        LOGGER.debug('Database already exists')

    return sqlite3.connect(data_file)

def append(db, series, value_string, value_type, ident):
    value = value_type(value_string)
    cursor = db.cursor()
    value_field = {str: 'string_value', float: 'float_value'}[value_type]
    cursor.execute('INSERT INTO timeseries(series, {}, given_ident) values (?, ?, ?)'.format(value_field), (series, value, ident))
    db.commit()

def get_values(db, series, ident=None):
    query_options = []
    wheres = []
    if series:
        wheres.append('series=?')
        query_options.append(series)

    if ident:
        wheres.append('given_ident=?')
        query_options.append(ident)

    query1 = 'SELECT time, series, given_ident, coalesce(float_value, string_value) from timeseries'
    query2 = 'order by time'

    if wheres:
        query = '{} where {} {}'.format(query1, 'AND '.join(wheres), query2)
    else:
        query = '{} {}'.format(query1, query2)

    cursor = db.cursor()
    cursor.execute(query, query_options)
    return cursor.fetchall()

def only_show_indexes(iterable, indexes):
    if any(index < 0 for index in indexes):
        items = list(iterable)
        for index in indexes:
            yield items[index]

    for index, x in enumerate(iterable):
        if index in indexes:
            yield x

def show(db, series, ident, json_output, indexes=None):
    records = get_values(db, series, ident=ident)
    records = only_show_indexes(records, indexes) if indexes is not None else records
    if not json_output:
        result = []
        for time_string, series, ident, value in records:
            if isinstance(value, (str, unicode)):
                value = value.strip('\n')

            dt = datetime.datetime.strptime(time_string, '%Y-%m-%d %H:%M:%S')
            result.append('{} {} {} {}'.format(dt.isoformat(), ident, series, value))
        return '\n'.join(result)
    else:
        result = []
        for time_string, series, ident, value in records:
            dt = datetime.datetime.strptime(time_string, '%Y-%m-%d %H:%M:%S')
            unix_time = time.mktime(dt.timetuple())
            result.append(dict(time=unix_time, series=series, id=ident, value=value))
        return json.dumps(result)


PARSER = argparse.ArgumentParser(description='Very simple command line timeseries')
PARSER.add_argument('--debug', action='store_true', help='Include debug output (to stderr)')
PARSER.add_argument('--config-dir', '-C', help='Directory to store configuration and data')

parsers = PARSER.add_subparsers(dest='command')

append_command = parsers.add_parser('append', help='Add a value')
append_command.add_argument('series', type=str, help='Timeseries')
append_command.add_argument('--string', action='store_const', dest='value_type', const=str, default=float)
append_command.add_argument('--id', type=str, help='Name a value', dest='ident')
append_command.add_argument('value', type=str)

series_command = parsers.add_parser('series', help='List the series')
series_command.add_argument('--quiet', '-q', action='store_true', help='Only show names')
series_command.add_argument('--prefix', '-p', type=str, help='Find series with this prefix')

PERIODS = {
    'm': datetime.timedelta(minutes=1),
    'h': datetime.timedelta(hours=1),
    'd': datetime.timedelta(days=1),
}

def mean(lst):
    return float(sum(lst)) /  len(lst)

def rng(lst):
    return max(lst) - min(lst)

def display_values(lst):
    return ' '.join(map(str, lst))

def sorted_values(lst):
    return ' '.join(map(str, sorted(lst)))

AGGREGATION_FUNCTIONS = {
    'min': min,
    'max': max,
    'mean': mean,
    'rng': rng,
    'values': display_values,
    'sorted_values': sorted_values,
}


def time_period(string):
    time_string, unit = string[:-1], string[-1]
    return int(time_string) * PERIODS[unit]

def get_agg_func(string):
    return AGGREGATION_FUNCTIONS[string]

aggregate_command = parsers.add_parser('aggregate', help='Combine together values over different periods')
aggregate_command.add_argument('period', type=time_period, help='Aggregate values over this period')
aggregate_command.add_argument('--series', type=str, help='Only display this series')
aggregate_command.add_argument(
    '--func', '-f',
    help='Function to use for aggregation',
    action='append',
    choices=tuple(AGGREGATION_FUNCTIONS),
    )
aggregate_command.add_argument('--missing-value', '-v', type=float, help='Value to fill in gaps with')
aggregate_command.add_argument('--missing', '-m', action='store_true', help='Include missing values')

format_mutex = aggregate_command.add_mutually_exclusive_group()
format_mutex.add_argument('--record-stream', '-R', action='store_true', help='entries are written separately json on one line')

show_command = parsers.add_parser('show', help='Show the values in a series')
show_command.add_argument('--series', type=str, help='Only show this timeseries')
show_command.add_argument('--id', type=str, help='Only show the entry with this id', dest='ident')
show_command.add_argument('--json', action='store_true', help='Output in machine readable json')
show_command.add_argument('--index', type=int, help='Only show the INDEX entry', action='append')
show_command.add_argument('--delete', help='Delete the matches entries', action='store_true')

delete_parser = parsers.add_parser('delete', help='Delete a value from a timeseries')
delete_parser.add_argument('series', type=str, help='Which series to delete from')
mx = delete_parser.add_mutually_exclusive_group(required=True)
mx.add_argument('--id', type=str, help='Delete entry with this id', dest='ident')


def main():
    options = PARSER.parse_args()

    config_dir = options.config_dir or DEFAULT_CONFIG_DIR

    if options.debug:
        logging.basicConfig(level=logging.DEBUG)

    if not os.path.isdir(config_dir):
        os.mkdir(config_dir)

    db = ensure_database(config_dir)
    if options.command == 'append':
        append(db, options.series, options.value, options.value_type, options.ident)
    elif options.command == 'show':

        if options.delete:
            delete(db, options.series, options.ident, indexes=options.index)
        else:
            print show(db, options.series, options.ident, options.json, indexes=options.index)

    elif options.command == 'aggregate':
        aggregate(
            db, options.series, options.period, options.record_stream,
            funcs=map(get_agg_func, options.func or ['min']),
            missing_value=options.missing_value,
            include_missing=options.missing)
    elif options.command == 'delete':
        delete(db, options.series, options.ident)
    elif options.command == 'series':
        show_series(db, prefix=options.prefix)
    else:
        raise ValueError(options.command)

epoch = datetime.datetime(1970, 1, 1)
def aggregate(db, series, period, record_stream, missing_value, include_missing, funcs):
    for row in aggregate_values(db, series, period, funcs, include_empty=include_missing):
        dt, series = row[:2]
        values = row[2:]
        values = [value.strip('\n') if isinstance(value, (str, unicode)) else value for value in values]
        values = [missing_value if value is None else value for value in values]
        dt_time = time.mktime(dt.timetuple())
        if record_stream:
            value = values[0] if len(values) == 1 else values
            print json.dumps(dict(isodate=dt.isoformat(), value=value, series=series, time=dt_time))
        else:
            print dt, series,
            for value in values:
                print value,
            print

def aggregate_values(db, series, period, agg_funcs, include_empty=False):
    # Could be done in sql but this would
    #   be less generalisable

    all_series = get_series(db)
    group_dt = None
    group_values = collections.defaultdict(list)
    for time_string, series, _ident, value in get_values(db, series):
        dt = datetime.datetime.strptime(time_string, '%Y-%m-%d %H:%M:%S')
        seconds_since_epoch = (dt - epoch).total_seconds() // period.total_seconds() * period.total_seconds()
        period_dt = epoch + datetime.timedelta(seconds=seconds_since_epoch)
        if period_dt != group_dt:
            LOGGER.debug('Group values %r %r', period_dt, group_values)
            for series in sorted(group_values):
                yield [group_dt, series] + [f(group_values[series]) for f in agg_funcs]
            group_values = collections.defaultdict(list)

            if include_empty:
                while True:
                    if group_dt is None:
                        break

                    group_dt += period
                    if group_dt >= period_dt:
                        break

                    for value_series in all_series:
                        if series is None or series == value_series:
                            yield [group_dt, series] + [None] * len(agg_funcs)

            group_dt = period_dt

        group_values[series].append(value)

def get_series(db):
    cursor = db.cursor()
    cursor.execute('''
    SELECT DISTINCT series FROM timeseries ORDER BY 1;
    ''')
    return [x for (x,) in cursor.fetchall()]

def delete(db, series, ident=None, indexes=None):
    if indexes is None:
        cursor = db.cursor()
        cursor.execute('''
        SELECT * FROM timeseries
        WHERE series=? AND given_ident=?
        ''', (series, ident))
        db.commit()
    else:
        for index in indexes:
            if index < 0:
                backwards = index < 0
                index = -index -1
            else:
                index = index

            cursor = db.cursor()

            #values = [series] + ([ident] if ident else [])

            query = StupidQuery(action='DELETE')
            query.where_equals('series', series)
            if ident:
                query.where_equals('given_ident', ident)

            query.order('id', reverse=backwards)
            query.offset(index)
            query.limit(1)

            print query.query()

            cursor.execute(query.query(), query.values)
            print cursor.fetchall()
            db.commit()

class StupidQuery(object):
    # Braindead orm, because using sqlalchemy isn't worthwhile
    #  for this sore of simple activity

    # If only there was a library that just helped me build
    # an sql expession.

    def __init__(self, action='SELECT', table='timeseries', fields=None):
        self.action = action
        self.table = table
        self.values = []
        self.conditions = []
        if fields is None:
            self.fields = ('*',) if action == 'SELECT' else None

        if self.action == 'DELETE':
            if fields is not None:
                raise Exception('Cannot delete with fields')

        self.order_key = None
        self._offset = None
        self._limit = None

    def where_equals(self, key, value):
        self.conditions.append('{} = ?'.format(key))
        self.values.append(value)

    def offset(self, offset):
        self._offset = offset

    def limit(self, limit):
        self._limit = limit

    def where(self, condition, *values):
        self.conditions.append(condition)
        self.values.extend(values)

    def order(self, key, reverse=False):
        if reverse:
            self.order_key = '{} DESC'.format(key)
        else:
            self.order_key = key

    def query(self):
        if self.fields:
            field_string = ','.join(self.fields)
        else:
            field_string = ''

        if self.conditions:
            condition_string = 'WHERE ' + ' AND '.join(self.conditions)
        else:
            condition_string = ''

        if self.order_key:
            order_string = 'ORDER BY {}'.format(self.order_key)
        else:
            order_string = ''

        if self._limit:
            limit_string = 'LIMIT {}'.format(self._limit)
        else:
            limit_string = ''

        if self._offset:
            offset_string = 'OFFSET {}'.format(self._offset)
        else:
            offset_string = ''

        return '''{action} {field_string} FROM {table} {condition_string} {order_string} {limit_string} {offset_string}'''.format(
            action=self.action,
            field_string=field_string,
            table=self.table,
            condition_string=condition_string,
            order_string=order_string,
            limit_string=limit_string,
            offset_string=offset_string,
            )


def show_series(db, prefix=None):
    cursor = db.cursor()
    cursor.execute('''
    SELECT series FROM timeseries GROUP BY 1 ORDER BY 1
    ''')
    for name, in cursor.fetchall():
        if prefix:
            if not name.startswith(prefix):
                continue
        print name

if __name__ == '__main__':
	main()
