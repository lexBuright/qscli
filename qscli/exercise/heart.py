import json
import logging
import subprocess
import time
import uuid

from .. import guiutils, os_utils
from . import data

LOGGER = logging.getLogger('heart')


def settings_option(parser):
    parser.add_argument('--setting', '-s', action='append', help='Settings for this exercise, of the form a=b;c=d;e=PROMPT or PROMPT')

def add_subparser(parser):
    sub = parser.add_subparsers(dest='heart_action')
    read_parser = sub.add_parser('read')
    read_parser.add_argument('--tolerance', type=float, help='Bpm tolerance for heart rate', default=5)
    sub.add_parser('show', help='Show recent heart rates')
    sub.add_parser('reset', help='Reset targets')

    target = sub.add_parser('target', help='Target some heart rate')
    target.add_argument('bpm', type=float, help='Desired bpm')
    target.add_argument('--tolerance', type=float, help='Bpm tolerance for heart rate', default=5)

def run(args):
    if args.heart_action == 'read':
        read_heart_rate(args.tolerance)
    elif args.heart_action == 'show':
        show_heart_rate()
    elif args.heart_action == 'target':
        target_heart_rate(args.bpm, args.tolerance)
    elif args.heart_action == 'reset':
        reset()
    else:
        raise ValueError(args.heart_action)

def reset():
    data.Data.set_heart_rate_targetter('')

def read_heart_rate(tolerance):
    estimate = get_heart_rate(tolerance)
    print '{:.1f}'.format(estimate)

def get_heart_rate(tolerance):
    LOGGER.debug('Getting heart rate with tolerance %r', tolerance)
    result = json.loads(guiutils.run_in_window(['qsrate', '--auto', '--json', '--tolerance', str(tolerance)]))
    subprocess.check_call(['qstimeseries', 'append', 'exercise.heart-rate', str(result['estimate'])])
    return result['estimate']

def show_heart_rate():
    result = json.loads(os_utils.backticks(['qstimeseries', 'show', '--series', 'exercise.heart-rate', '--json']))
    for reading in result[:-10:-1]:
        seconds_ago = time.time() - reading['time']
        print '{:.0f} {:.1f}'.format(seconds_ago, reading['value'])

def target_heart_rate(bpm, tolerance):
    INITIAL_PERIOD = 15
    MULTIPLIER = 2.0
    HEART_RATE_STABLE_PERIOD = 300
    period = INITIAL_PERIOD

    ident = (str(uuid.uuid1))
    data.Data.set_heart_rate_targetter(ident)

    while True:
        if ident != data.Data.get_heart_rate_targetter(ident):
            LOGGER.debug('New targetter spawned')
            return

        rate = get_heart_rate(tolerance=tolerance)
        if rate + tolerance < bpm:
            print '{:.0f} > {:.0f} faster'.format(rate, bpm)
            period = INITIAL_PERIOD
        elif rate - tolerance > bpm:
            print '{:.0f} > {:.0f} slower'.format(rate, bpm)
            period = INITIAL_PERIOD
        else:
            period = min(period * MULTIPLIER, HEART_RATE_STABLE_PERIOD)
            print 'Correct rate ({:.0f} =~ {:.0f}). Next check in {:.0f}'.format(rate, bpm, period)
        LOGGER.debug('Waiting %r until next reading...', period)
        time.sleep(period)
