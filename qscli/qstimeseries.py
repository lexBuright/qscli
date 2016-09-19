"""An easy to use command-line time-series storage interface.

For bigger projects you may prefer to use something like graphite, innodb, or elastic search

qstimeseries append series 1.0
qstimeseries append stringseries --string "this is a string value"

"""

import argparse
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

def show(db, series, ident, json_output):
    cursor = db.cursor()

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

    cursor.execute(query, query_options)
    if not json_output:
        result = []
        for time_string, series, ident, value in cursor.fetchall():
            dt = datetime.datetime.strptime(time_string, '%Y-%m-%d %H:%M:%S')
            result.append('{} {} {} {}'.format(dt.isoformat(), ident, series, value))
        return '\n'.join(result)
    else:
        result = []
        for time_string, series, ident, value in cursor.fetchall():
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

show_command = parsers.add_parser('show', help='Show the values in a series')
show_command.add_argument('--series', type=str, help='Only show this timeseries')
show_command.add_argument('--id', type=str, help='Only show the entry with this id', dest='ident')
show_command.add_argument('--json', action='store_true', help='Output in machine readable json')

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
        print show(db, options.series, options.ident, options.json)
    elif options.command == 'delete':
        delete(db, options.series, options.ident)
    else:
        raise ValueError(options.command)

def delete(db, series, ident):
    cursor = db.cursor()
    cursor.execute('''
    DELETE FROM timeseries
    WHERE series=? AND given_ident=?
    ''', (series, ident))
    db.commit()


if __name__ == '__main__':
	main()
