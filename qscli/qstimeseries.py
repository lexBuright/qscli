"""An easy to use command-line time-series storage interface.

For bigger projects you may prefer to use something like graphite, innodb, or elastic search

qstimeseries append series 1.0
qstimeseries append stringseries --string "this is a string value"

"""

import argparse
import calendar
import collections
import datetime
import json
import logging
import os
import sqlite3
import sys
import time
import pytz

from . import sqlexp
from . import ipc

LOGGER = logging.getLogger()

DEFAULT_CONFIG_DIR = os.path.join(os.environ['HOME'], '.config', 'qstimeseries')

IdentUnion = collections.namedtuple('IdentUnion', 'native_id given_id')

def ensure_database(config_dir):
    if not os.path.isdir(config_dir):
        os.mkdir(config_dir)

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

def append(db, series, value_string, value_type, ident, time_value, update):
    if ident and ident.native_id is not None:
        raise Exception('internal-- ids reserved for internal assignment')
    value = value_type(value_string)

    value_field = {str: 'string_value', float: 'float_value'}[value_type]

    if update:
        query = sqlexp.Query(action='INSERT OR REPLACE')
    else:
        query = sqlexp.Query(action='INSERT')

    query.insert_field('series', series)
    query.insert_field(value_field, value)
    query.insert_field('given_ident', ident and ident.given_id)
    if time_value is not None:
        query.insert_field_expression('time', "datetime(?, 'unixepoch')", time_value)
    cursor = db.cursor()
    try:
        cursor.execute(query.query(), query.values())
    except:
        print query.query()
        db.rollback()
        raise
    db.commit()

def get_values(db, series, ids=None):
    query = sqlexp.Query(
        action='SELECT',
        fields=('time', 'series', "coalesce(given_ident, 'internal--' || id)", "coalesce(float_value, string_value)"))

    if series is not None:
        query.where_equals('series', series)

    if ids:
        for ident in ids:
            if ident.given_id is not None:
                query.where_equals('given_ident', ident.given_id)
            if ident.native_id:
                query.where_equals('id', ident.native_id)

    query.order('time')

    return execute(db, query.query(), query.values())

def execute(db, query, values):
    cursor = db.cursor()
    cursor.execute(query, values)
    LOGGER.debug('Running %r %r', query, values)
    return cursor.fetchall()

def only_show_indexes(iterable, indexes):
    if any(index < 0 for index in indexes):
        items = list(iterable)
        for index in indexes:
            yield items[index]
    else:
        for index, x in enumerate(iterable):
            if index in indexes:
                yield x

def show(db, series, ids, json_output, indexes=None):
    records = get_values(db, series, ids=ids)
    records = only_show_indexes(records, indexes) if indexes is not None else records
    if not json_output:
        result = []
        for time_string, series, ident, value in records:
            if isinstance(value, (str, unicode)):
                value = value.strip('\n')

            dt = datetime.datetime.strptime(time_string, '%Y-%m-%d %H:%M:%S')
            result.append('{} {} {} {}'.format(dt.isoformat(), ident, series, value))
        return '\n'.join(result),
    else:
        result = []
        for time_string, series, ident, value in records:
            dt = pytz.UTC.localize(datetime.datetime.strptime(time_string, '%Y-%m-%d %H:%M:%S'), is_dst=None)
            unix_time = calendar.timegm(dt.timetuple())
            result.append(dict(time=unix_time, series=series, id=ident, value=value))
        return json.dumps(result),

def build_parser():
    parser = argparse.ArgumentParser(description='Very simple command line timeseries')
    parser.add_argument('--debug', action='store_true', help='Include debug output (to stderr)')
    parser.add_argument('--config-dir', '-C', help='Directory to store configuration and data')

    parsers = parser.add_subparsers(dest='command')

    append_command = parsers.add_parser('daemon', help='Start a daemon to run commands')

    append_command = parsers.add_parser('append', help='Add a value')
    append_command.add_argument('series', type=str, help='Timeseries')
    append_command.add_argument('--string', action='store_const', dest='value_type', const=str, default=float)
    append_command.add_argument('--id', type=parse_ident, help='Name a value', dest='ident')
    append_command.add_argument('--time', type=float, help='Insert the value at this unix time (rather than the current time)')
    append_command.add_argument('--update', action='store_true', help='Update existing values rather than erroring out')
    append_command.add_argument('value', type=str)

    series_command = parsers.add_parser('series', help='List the series')
    series_command.add_argument('--quiet', '-q', action='store_true', help='Only show names')
    series_command.add_argument('--prefix', '-p', type=str, help='Find series with this prefix')

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
    show_command.add_argument('--id', type=parse_ident, help='Only show the entry with this id', dest='ident', action='append')
    show_command.add_argument('--json', action='store_true', help='Output in machine readable json')
    show_command.add_argument('--index', type=int, help='Only show the INDEX entry', action='append')
    show_command.add_argument('--delete', help='Delete the matches entries', action='store_true')

    delete_parser = parsers.add_parser('delete', help='Delete a value from a timeseries')
    delete_parser.add_argument('series', type=str, help='Which series to delete from')
    mx = delete_parser.add_mutually_exclusive_group(required=True)
    mx.add_argument('--id', type=parse_ident, help='Delete entry with this id', dest='ident', action='append')
    return parser

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

def main():
    result = run(sys.argv[1:])
    if result:
        for x in result:
            print x,

def run(args):
    options = build_parser().parse_args(args)
    if options.command == 'daemon':
        db = ensure_database(options.config_dir)
        return ipc.run_server(build_parser(), lambda x: run_options(x, db, options.debug), options.debug)
    else:
        return run_options(options, None, options.debug)

def run_options(options, db, debug):
    if debug:
        logging.basicConfig(level=logging.DEBUG)

    if db is None:
        db = ensure_database(options.config_dir)


    if options.command == 'append':
        return append(db, options.series, options.value, options.value_type, options.ident, options.time, options.update)
    elif options.command == 'show':

        if options.delete:
            return delete(db, options.series, options.ident, indexes=options.index)
        else:
            return show(db, options.series, options.ident, options.json, indexes=options.index)

    elif options.command == 'aggregate':
        return aggregate(
            db, options.series, options.period, options.record_stream,
            funcs=map(get_agg_func, options.func or ['min']),
            missing_value=options.missing_value,
            include_missing=options.missing)
    elif options.command == 'delete':
        return delete(db, options.series, options.ident)
    elif options.command == 'series':
        return show_series(db, prefix=options.prefix)
    else:
        raise ValueError(options.command)

def aggregate(db, series, period, record_stream, missing_value, include_missing, funcs):
    for row in aggregate_values(db, series, period, funcs, include_empty=include_missing):
        dt, series = row[:2]
        values = row[2:]
        values = [value.strip('\n') if isinstance(value, (str, unicode)) else value for value in values]
        values = [missing_value if value is None else value for value in values]
        dt_time = time.mktime(dt.timetuple())
        if record_stream:
            value = values[0] if len(values) == 1 else values
            yield json.dumps(dict(isodate=dt.isoformat(), value=value, series=series, time=dt_time))
        else:
            result = []
            result.append('{} {} '.format(dt, series))
            for value in values:
                result.append('{} '.format(value))
            result.append('\n')
            yield ''.join(result)

EPOCH = datetime.datetime(1970, 1, 1)
def aggregate_values(db, series, period, agg_funcs, include_empty=False):
    # Could be done in sql but this would
    #   be less generalisable

    all_series = get_series(db)
    group_dt = None
    group_values = collections.defaultdict(list)
    for time_string, series, _ident, value in get_values(db, series):
        dt = datetime.datetime.strptime(time_string, '%Y-%m-%d %H:%M:%S')
        seconds_since_epoch = (dt - EPOCH).total_seconds() // period.total_seconds() * period.total_seconds()
        period_dt = EPOCH + datetime.timedelta(seconds=seconds_since_epoch)
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

def parse_ident(ident_string):
    if ident_string is not None:
        if ident_string.startswith('internal--'):
            return IdentUnion(int(ident_string[len('internal--'):]), None)
        else:
            return IdentUnion(None, ident_string)
    else:
        return IdentUnion(None, None)

def delete(db, series, ids=None, indexes=None):
    if not ids and not indexes:
        raise ValueError()

    if ids is not None :
        query = sqlexp.Query(action='DELETE')
        id_filter = sqlexp.Or()
        for ident in ids:
            if ident.native_id is not None:
                id_filter.add_equals('id', ident.native_id)

            if ident.given_id:
                id_filter.add_equals('given_ident', ident.given_id)

        query.where_expression(id_filter)

        cursor = db.cursor()
        cursor.execute(query.query(), query.values())
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

            query = sqlexp.Query(action='DELETE')
            query.where_equals('series', series)
            if ident:
                query.where_equals('given_ident', ident)

            query.order('id', reverse=backwards)
            query.offset(index)
            query.limit(1)

            cursor.execute(query.query(), query.values())
            db.commit()

def show_series(db, prefix=None):
    cursor = db.cursor()
    cursor.execute('''
    SELECT series FROM timeseries GROUP BY 1 ORDER BY 1
    ''')
    result = []
    for name, in cursor.fetchall():
        if prefix:
            if not name.startswith(prefix):
                continue
        result.append("{}\n".format(name))
    return ''.join(result),

if __name__ == '__main__':
	main()
