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

    def tolerance_option(parser):
        parser.add_argument('--tolerance', type=float, help='Bpm tolerance for heart rate', default=5)

    sub = parser.add_subparsers(dest='heart_action')
    read_parser = sub.add_parser('read')
    tolerance_option(read_parser)

    sub.add_parser('show', help='Show recent heart rates')
    sub.add_parser('reset', help='Reset targets')

    delay_parser = sub.add_parser('delay', help='Delay the next reading')
    delay_parser.add_argument('seconds', type=float, help='How long to delay for')

    multiplier_parser = sub.add_parser('multiplier', help='Scale the amount of time between interaction')
    multiplier_parser.add_argument('multiplier', type=float, help='Scaling factor')

    poll_parser = sub.add_parser('poll', help='Periodically poll for heart readings')
    tolerance_option(poll_parser)
    poll_parser.add_argument('period', type=float, help='How often to poll in seconds')

    target = sub.add_parser('target', help='Target some heart rate')
    target.add_argument('bpm', type=float, help='Desired bpm')
    tolerance_option(target)

def run(args):
    if args.heart_action == 'read':
        read_heart_rate(args.tolerance)
    elif args.heart_action == 'show':
        show_heart_rate()
    elif args.heart_action == 'target':
        target_heart_rate(args.bpm, args.tolerance)
    elif args.heart_action == 'poll':
        poll_heart_rate(args.tolerance, args.period)
    elif args.heart_action == 'delay':
        delay_reading(args.seconds)
    elif args.heart_action == 'multiplier':
        set_multiplier(args.multiplier)
    elif args.heart_action == 'reset':
        reset()
    else:
        raise ValueError(args.heart_action)

def set_multiplier(multiplier):
    data.Data.set_heart_multiplier(multiplier)
    poll_period = data.Data.get_heart_poll_period()
    target_period = data.Data.get_heart_target_period()
    print 'Target', target_period
    if poll_period:
        print 'Time between polls', poll_period * multiplier
    if target_period:
        print 'Time between targets', target_period * multiplier


def reset():
    data.Data.set_heart_rate_targetter('')
    data.Data.set_heart_multiplier(1.0)
    data.Data.set_heart_poll_period(None)
    data.Data.set_heart_target_period(None)

def delay_reading(delay_seconds):
    data.Data.set_heart_reading_delay(delay_seconds)

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

def poll_heart_rate(tolerance, period):
    reset() # kill other targets
    while True:
        data.Data.set_heart_poll_period(period)
        rate = get_heart_rate(tolerance=tolerance)
        print 'Rate {} bpm'.format(rate)
        sleep_time = period * data.Data.get_heart_multiplier()
        LOGGER.debug('Sleeping for %r seconds until next reading', sleep_time)
        time.sleep(sleep_time)


def target_heart_rate(bpm, tolerance):
    reset()
    INITIAL_PERIOD = 15
    MULTIPLIER = 2.0
    HEART_RATE_STABLE_PERIOD = 300
    period = INITIAL_PERIOD

    ident = (str(uuid.uuid1))
    data.Data.set_heart_rate_targetter(ident)

    while True:
        if ident != data.Data.get_heart_rate_targetter():
            LOGGER.debug('New targetter spawned')
            return

        print 'Getting heart rate'
        rate = get_heart_rate(tolerance=tolerance)
        if rate + tolerance < bpm:
            period = INITIAL_PERIOD
            print '{:.0f} > {:.0f} faster. Next check {}'.format(rate, bpm, period)
        elif rate - tolerance > bpm:
            period = INITIAL_PERIOD
            print '{:.0f} > {:.0f} slower. Next check {}'.format(rate, bpm, period)
        else:
            period = min(period * MULTIPLIER, HEART_RATE_STABLE_PERIOD)
            print 'Correct rate ({:.0f} =~ {:.0f}). Next check in {:.0f}'.format(rate, bpm, period)
        LOGGER.debug('Waiting %r until next reading...', period)
        data.Data.set_heart_target_period(period)
        time.sleep(period * data.Data.get_heart_multiplier())
