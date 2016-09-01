"""An easy to use command-line time-series storage interface.

For bigger projects you may prefer to use something like graphite, innodb, or elastic search

qstimeseries append series 1.0
qstimeseries append stringseries --string "this is a string value"

"""

import argparse
import datetime
import logging
import os
import sqlite3

LOGGER = logging.getLogger()
logging.basicConfig(level=logging.DEBUG)

DEFAULT_CONFIG_DIR = os.path.join(os.environ['HOME'], '.config', 'qstimeseries')

def ensure_database(config_dir):
    data_file = os.path.join(config_dir, 'data.sqlite')
    if not os.path.exists(data_file):
        try:
            LOGGER.debug('Creating database')
            db = sqlite3.connect(data_file)
            cursor = db.cursor()
            cursor.execute('''
            CREATE TABLE timeseries(id INTEGER PRIMARY KEY, time TIMESTAMP DEFAULT CURRENT_TIMESTAMP, series TEXT, float_value REAL, string_value TEXT);
            ''')
            db.commit()
            return db
        except:
            os.unlink(data_file)
            raise
    else:
        LOGGER.debug('Database already exists')

    return sqlite3.connect(data_file)

def append(db, series, value_string, value_type):
    value = value_type(value_string)
    cursor = db.cursor()
    value_field = {str: 'string_value', float: 'float_value'}[value_type]
    cursor.execute('INSERT INTO timeseries(series, {}) values (?, ?)'.format(value_field), (series, value))
    db.commit()

def show(db, series):
    cursor = db.cursor()
    cursor.execute('SELECT time, case float_value is not null then float_value else string_value end from timeseries where series=? order by id', (series,))
    for time_string, value in  cursor.fetchall():
        time = datetime.datetime.strptime(time_string, '%Y-%m-%d %H:%M:%S')
        print time.isoformat(), value
        print time.isoformat(), value


PARSER = argparse.ArgumentParser(description='Very simple command line timeseries')
PARSER.add_argument('--config-dir', '-C', help='Directory to store configuration and data')

parsers = PARSER.add_subparsers(dest='command')

append_command = parsers.add_parser('append', help='Add a value')
append_command.add_argument('series', type=str, help='Timeseries')
append_command.add_argument('--string', action='store_const', dest='value_type', const=str, default=float)
append_command.add_argument('value', type=str)

show_command = parsers.add_parser('show', help='Show the values in a series')
show_command.add_argument('series', type=str, help='Timeseries')


def main():
    options = PARSER.parse_args()

    config_dir = options.config_dir or DEFAULT_CONFIG_DIR

    if not os.path.isdir(config_dir):
        os.mkdir(config_dir)

    db = ensure_database(config_dir)
    if options.command == 'append':
        append(db, options.series, options.value, options.value_type)
    elif options.command == 'show':
        show(db, options.series)
    else:
        raise ValueError(options.command)


if __name__ == '__main__':
	main()
