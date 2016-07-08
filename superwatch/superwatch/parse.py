
import argparse
import json
import logging
import sys
import time
import unittest

from . import config, superwatch
from .config import DEFAULT_CLOCK

# needed for unittest
from .test import SuperTest # pylint: disable=unused-import

def run(data_dir, time_mod, stdout, args):
    args = args or ['toggle']
    options = PARSER.parse_args(args)

    if options.debug:
        logging.basicConfig(level=logging.DEBUG)

    watch = superwatch.Superwatch(data_dir, time_mod)
    for part in watch_run(watch, options):
        stdout.write(part)


def get_tests():
    return unittest.makeSuite(SuperTest, 'test')

def main():
    args = sys.argv[:]
    if '--test' in args:
        args.remove('--test')
        if '--debug' in args:
            logging.basicConfig(level=logging.DEBUG)
            args.remove('--debug')
        sys.argv = args
        unittest.main(module='superwatch.parse', defaultTest='get_tests')
    else:
        sys.exit(run(config.DATA_DIR, time, sys.stdout, sys.argv[1:]))

def watch_run(watch, options):
    if options.command == 'toggle':
        if watch.running(options.clock):
            return watch.stop(options.clock)
        else:
            return watch.start(options.clock)
    elif options.command == 'clocks':
        return watch.clocks(options.quiet)
    elif options.command == 'start':
        return watch.start(options.clock, options.next_label)
    elif options.command == 'stop':
        return watch.stop(options.clock)
    elif options.command == 'import-all':
        return watch.import_all(options.filename)
    elif options.command == 'export-all':
        return watch.export_all()
    elif options.command == 'show':
        return watch.show(options.clock, options.json)
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
    elif options.command == 'save':
        return watch.save(options.source, options.target)
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

    toggle = parsers.add_parser('toggle', help='Stop or start the stopwatch')
    toggle.add_argument('clock', type=str, nargs='?', default=DEFAULT_CLOCK)

    start = parsers.add_parser('start', help='Stop or start the stopwatch')
    start.add_argument('clock', type=str, nargs='?', default=DEFAULT_CLOCK)
    start.add_argument('--next-label', '-n', type=str, help='Label for the next split')

    clocks = parsers.add_parser('clocks', help='Show all the clocks')
    clocks.add_argument('--quiet', action='store_true', help='Only output the clock name')

    delete = parsers.add_parser('delete', help='Delete a clock')
    delete.add_argument('clocks', type=str, help='Clock(s) to delete', nargs='+')

    show = parsers.add_parser('show', help='Show the current elapsed time')
    show.add_argument('clock', type=str, nargs='?', default=DEFAULT_CLOCK)
    show.add_argument('--json', action='store_true', help='Output in json format')

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

    save = parsers.add_parser('save', help='Copy the clock to a new name')
    save.add_argument('source', type=str, default=DEFAULT_CLOCK, nargs='?')
    save.add_argument('target', type=str)

    return parser

PARSER = build_parser()
