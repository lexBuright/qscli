
import argparse
import calendar
import json
import logging
import sys
import time

import iso8601

from qscli import ipc

from . import config, qswatch
from .config import DEFAULT_CLOCK

# needed for unittest

LOGGER = logging.getLogger()

def run(data_dir, time_mod, stdout, args):
    parser = build_parser()
    args = args or ['toggle']
    options = parser.parse_args(args)

    if options.debug:
        logging.basicConfig(level=logging.DEBUG)

    if options.command == 'daemon':
        watch = qswatch.Watch(data_dir, time_mod)
        ipc.run_server(build_parser(), lambda options: watch_run(watch, options))
    else:
        watch = qswatch.Watch(data_dir, time_mod)
        for part in watch_run(watch, options):
            stdout.write(part)

def main():
    run(config.DATA_DIR, time, sys.stdout, sys.argv[1:])
    LOGGER.debug('Exiting')

def watch_run(watch, options):
    if options.command == 'toggle':
        if watch.running(options.clock):
            return watch.stop(options.clock)
        else:
            return watch.start(options.clock)

    elif options.command == 'clocks':
        return watch.clocks(options.quiet, options.running, options.json)
    elif options.command == 'start':
        return watch.start(options.clock, options.next_label, interactive=options.interactive, start=options.start)
    elif options.command == 'stop':
        return watch.stop(options.clock)
    elif options.command == 'edit':
        return watch.edit(options.clock, options.start, options.stop)
    elif options.command == 'import-all':
        return watch.import_all(options.filename)
    elif options.command == 'export-all':
        return watch.export_all()
    elif options.command == 'show':
        return watch.show(options.clock, options.json, options.interactive)
    elif options.command == 'show-split':
        return watch.show_split(options.clock, options.interactive)
    elif options.command == 'split':
        return watch.split(options.clock, options.label, options.next_label)
    elif options.command == 'label-split':
        return watch.label_split(options.clock, options.label)
    elif options.command == 'export':
        return watch.export(options.clock)
    elif options.command == 'export-all':
        return watch.export_all()
    elif options.command == 'delete':
        return watch.delete(options.clocks)
    elif options.command == 'move':
        return watch.move(options.source, options.target)
    elif options.command == 'play':
        return watch.play(options.clocks, options.wait, options.absolute, options.after, options.before)
    elif options.command == 'split-data':
        assert len(options.keypairs) % 2 == 0
        split_data = dict(zip(options.keypairs[::2], options.keypairs[1::2]))
        split_data.update(options.data or dict())
        return watch.set_split_data(options.clock, split_data)
    else:
    	raise ValueError(options.command)

def build_parser():
    parser = argparse.ArgumentParser(description='')
    parsers = parser.add_subparsers(dest='command')

    parser.add_argument('--debug', action='store_true', help='Print debug output')
    daemon = parsers.add_parser(
        'daemon',
        help='Run in a daemon mode. Commands are read from stdin, response written to stdout as json')

    toggle = parsers.add_parser('toggle', help='Stop or start the stopwatch')
    toggle.add_argument('clock', type=str, nargs='?', default=DEFAULT_CLOCK)

    edit = parsers.add_parser('edit', help='Edit an existing timing')
    edit.add_argument('clock', type=str, nargs='?', default=DEFAULT_CLOCK)
    edit.add_argument('--start', type=parse_isodate, help='Set the time the clock started (utc)', metavar='ISODATE')
    edit.add_argument('--stop', type=parse_isodate, help='Set the time start time (utc)', metavar='ISODATE')

    start = parsers.add_parser('start', help='Stop or start the stopwatch')
    start.add_argument('clock', type=str, nargs='?', default=DEFAULT_CLOCK)
    start.add_argument('--next-label', '-n', type=str, help='Label for the next split')
    start.add_argument('--interactive', '-i', action='store_true', help='Block and interactive change display')
    start.add_argument('--start', type=parse_isodate, help='Set the clock start time (utc timestamp)', metavar='ISODATE')

    clocks = parsers.add_parser('clocks', help='Show all the clocks')
    clocks.add_argument('--quiet', action='store_true', help='Only output the clock name')
    clocks.add_argument('--json', action='store_true', help='Output in json format')

    clocks_runningness = clocks.add_mutually_exclusive_group()
    clocks_runningness.add_argument('--running', action='store_true', help='Only output currently running clocks', dest='running')
    clocks_runningness.add_argument('--stopped', action='store_false', help='Only output current stopped clocks', dest='running')

    delete = parsers.add_parser('delete', help='Delete a clock')
    delete.add_argument('clocks', type=str, help='Clock(s) to delete', nargs='+')

    show = parsers.add_parser('show', help='Show the current elapsed time')
    show.add_argument('clock', type=str, nargs='?', default=DEFAULT_CLOCK)
    show.add_argument('--json', action='store_true', help='Output in json format')
    show.add_argument('--interactive', '-i', action='store_true', help='Block and interactive change display')

    show_split = parsers.add_parser('show-split', help='Show the current elapsed time')
    show_split.add_argument('clock', type=str, nargs='?', default=DEFAULT_CLOCK)
    show_split.add_argument('--interactive', action='store_true', help='Block and interactively change display')

    stop = parsers.add_parser('stop', help='Stop the current elapsed time')
    stop.add_argument('clock', type=str, nargs='?', default=DEFAULT_CLOCK)

    split = parsers.add_parser('split', help='Split the current clock')
    split.add_argument('clock', type=str, nargs='?', default=DEFAULT_CLOCK)
    split.add_argument('--label', '-l', type=str, help='Label the split that has just finished')
    split.add_argument('--next-label', '-n', type=str, help='Label for the next split')

    label_split = parsers.add_parser('label-split', help='Label the current clock split')
    label_split.add_argument('--clock', type=str, default=DEFAULT_CLOCK)
    label_split.add_argument('label', type=str, help='Label for the current split')

    split_data = parsers.add_parser('split-data', help='Add key value data to a split')
    split_data.add_argument('keypairs', type=str, nargs='*', help='Key value pairs to set')
    split_data.add_argument('--json', dest='data', type=json.loads, help='json string of key value pairs', default=None)
    split_data.add_argument('--clock', type=str, default=DEFAULT_CLOCK)

    export = parsers.add_parser('export', help='Export a clocks data')
    export.add_argument('clock', type=str, default=DEFAULT_CLOCK, nargs='?')

    import_all = parsers.add_parser('import-all', help='Import all data')
    import_all.add_argument('filename', type=str, help='')
    parsers.add_parser('export-all', help='Export all data')

    play = parsers.add_parser('play', help='Export a clocks data')
    play.add_argument('clocks', type=str, nargs='+', default=DEFAULT_CLOCK)
    play.add_argument('--no-wait', dest='wait', action='store_false', help='Do not wait for new values if a clock is already finished', default=True)
    play.add_argument('--absolute', action='store_true', help='Output absolute time stamps rather than relative time stamps')
    play.add_argument('--after', type=float, help='Return values after this offset or unix time')
    play.add_argument('--before', type=float, help='Return values after this offset or unix time')

    move = parsers.add_parser('move', help='Copy the clock to a new name')
    move.add_argument('source', type=str, default=DEFAULT_CLOCK, nargs='?')
    move.add_argument('target', type=str)

    return parser


def datetime_to_timestamp(dt):
    return calendar.timegm(dt.timetuple()) + dt.microsecond * 1e-6

def parse_isodate(string):
    return datetime_to_timestamp(iso8601.parse_date(string))
