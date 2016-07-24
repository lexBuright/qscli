#!/usr/bin/python
# -*- coding: utf-8 -*-

# This is to be classified as useful glue code

import argparse
import contextlib
import copy
import datetime
import decimal
import json
import logging
import os
import subprocess
import sys
import time
import unittest

import fasteners

import walking
from histogram import Histogram

LOGGER = logging.getLogger()

ARROW = {True: ">", False: "<"}
PROMPT = 'PROMPT'


DATA_DIR =  os.path.join(os.environ['HOME'], '.config', 'exercise-track')
if not os.path.isdir(DATA_DIR):
   os.mkdir(DATA_DIR)

DATA_FILE = os.path.join(DATA_DIR, 'data')

def main():
    #pylint: disable=too-many-branches
    parser = build_parser()
    args = parser.parse_args()
    if args.debug:
        print 'Debug logging'
        logging.basicConfig(level=logging.DEBUG)

    if args.action == 'start':
        walking.start_walking()
    elif args.action == 'incline-up':
        walking.change_incline(1)
    elif args.action == 'incline-down':
        walking.change_incline(-1)
    elif args.action == 'speed-up':
        walking.change_speed(1)
    elif args.action == 'speed-down':
        walking.change_speed(-1)
    elif args.action == 'show':
        walking.show()
    elif args.action == 'show-all':
        walking.show_all()
    elif args.action == 'rep-start':
        # IMPROVEMENT: we might like to bunch up things to do with reps
        exercise_name = 'exercise.{}'.format(args.exercise_name)
        backticks(['cli-alias', '--set', 'exercisetrack.exercise'], stdin=exercise_name)
        backticks(['cli-count.py', 'new-set', exercise_name])
        backticks(['cli-score.py', 'store', exercise_name, '0'])
    elif args.action == 'rep-note':
        backticks(['cli-count.py', 'note', args.note])
    elif args.action == 'rep':
        record_rep()
    elif args.action == 'aggregates':
        aggregates_for_speeds(walking.get_current_speed_histogram())
    elif args.action == 'daily-aggregates':
        aggregates_for_speeds(
            walking.get_speed_histogram_for_day(datetime.date.today()))
    elif args.action == 'stop':
        walking.stop()
    elif args.action == 'start-sprint':
        start_sprint('free')
    elif args.action == 'stop-sprint':
        stop_sprint('free')
    elif args.action == 'record-sprint':
        duration = args.duration
        display_period = 30
        start = time.time()
        start_sprint(duration)
        end = start + duration
        while time.time() < end:
            time.sleep(min(end - time.time(), display_period))
            print time.time() - start
        stop_sprint(duration)
    elif args.action == 'rep-versus':
        show_rep_comparison(args.days_ago)
    elif args.action == 'rep-set-score':
        # Perhaps this could all be done
        #    better with a single configuration file edited hand
        #    but to actually be useable this
        #    needs to be easy and *fun* to change
        exercise_set_score(args.exercise, args.days_ago, args.score)
    elif args.action == 'rep-ignore':
        activities = args.activity or []
        with with_data(DATA_FILE) as data:
            ignore_list = Data.get_to_ignore(data)

            if args.clear:
                ignore_list = []

            ignore_list = sorted(set(ignore_list + ['exercise.' + activity for activity in activities]))
            Data.set_to_ignore(data, ignore_list)

        print '\n'.join(ignore_list)
    elif args.action == 'versus':
        print 'Today versus {} days ago'.format(args.days)
        time_at_speed1 = walking.get_speed_histogram_for_day(
            datetime.date.today())
        time_at_speed2 = walking.get_speed_histogram_for_day(
            (datetime.datetime.now() - datetime.timedelta(days=args.days)).date())
        versus_clocks(time_at_speed1, time_at_speed2)
    elif args.action == 'reset':
        walking.reset_settings()
        print 'Speed and incline set to their minimum'
    elif args.action == 'test':
        sys.argv[1:] = []
        unittest.main()
    else:
        raise ValueError(args.action)

def build_parser():
    parser = argparse.ArgumentParser(description='Keep track of exercise')
    parser.add_argument('--debug', action='store_true', help='Print debug output')
    parsers = parser.add_subparsers(dest='action')
    parsers.add_parser('aggregates')
    parsers.add_parser('start')
    parsers.add_parser('stop')
    parsers.add_parser('incline-up')
    parsers.add_parser('speed-up')
    parsers.add_parser('incline-down')
    parsers.add_parser('speed-down')
    parsers.add_parser('show')
    parsers.add_parser('show-all')

    rep_set_score = parsers.add_parser('rep-set-score', help='Set the score for a particular exercise')
    rep_set_score.add_argument('--exercise', type=str)
    rep_set_score.add_argument('--prompt-for-exercise', dest='exercise', action='store_const', const=PROMPT, help='Prompt for the exercise with a graphical pop up')
    rep_set_score.add_argument('--score', type=float)
    rep_set_score.add_argument('--prompt-for-score', action='store_const', dest='score', const=PROMPT, help='Prompt for the exercise with a graphical pop up')
    rep_set_score.add_argument('--days-ago', '-A', type=int, help='Only set scores for exercises you did this many days ago')

    ignore = parsers.add_parser('rep-ignore', help='Ignore these activities today')
    ignore.add_argument('activity', type=str, help='', nargs='*')
    ignore.add_argument('--clear', action='store_true', help='Clear ignore list')

    # repetitions
    rep_start = parsers.add_parser('rep-start')
    rep_start.add_argument('exercise_name', type=str, help='Name of exercise')
    parsers.add_parser('rep')
    note_parser = parsers.add_parser('rep-note')
    note_parser.add_argument('note', type=str, help='Record a note about the reps that you are doing')

    parsers.add_parser('daily-aggregates')
    parsers.add_parser('start-sprint')
    parsers.add_parser('stop-sprint')
    record_sprint = parsers.add_parser('record-sprint')
    record_sprint.add_argument('duration', type=int, help='How long to sprint for')
    parsers.add_parser('test')

    rep_versus = parsers.add_parser('rep-versus')
    rep_versus.add_argument(
        'days_ago',
        default=1,
        type=int,
        help='How many days ago to compare to')

    versus = parsers.add_parser('versus')

    versus.add_argument(
        'days',
        default=1,
        type=int,
        help='How many days ago to compare to')

    parsers.add_parser('reset')
    return parser

def aggregates_for_speeds(time_at_speeds):
    time = time_at_speeds.total()
    distance = sum(
        speed * time / 3600
        for (speed, time) in time_at_speeds.counts())
    quartiles = time_at_speeds.values_at_quantiles([0.0, 0.25, 0.5, 0.75, 1.0])
    speed = distance / time * 1000.0
    print '{:.2f}km'.format(distance)
    print '{:.0f}s'.format(time)
    print '{:.2f} m/s'.format(speed)
    quartile_string = ' - '.join(['{:.2}'.format(q / 3.6) for q in quartiles])
    print 'Speed quartiles', quartile_string

def record_rep():
    exercise_name = backticks(['cli-alias', 'exercisetrack.exercise']).strip()
    print 'Count:', exercise_name
    backticks(['cli-count.py', 'incr', exercise_name])

    events = json.loads(backticks(['cli-count.py', 'log', '--set', 'CURRENT', '--json', exercise_name]))
    if events:
        start = events['events'][0]['time']
        end = events['events'][-1]['time']
        duration = end - start
    else:
        duration = 0

    print 'Duration: {:.0f}'.format(duration)

    count = backticks(['cli-count.py', 'count', '--set', 'CURRENT', exercise_name])
    count = int(count.strip())
    rate = count / duration if (count and duration) else 0

    print 'Rate: {:.2f}'.format(rate)
    backticks(['cli-score.py', 'update', exercise_name, str(count)])
    print backticks(['cli-score.py', 'summary', exercise_name, '--update'])

def versus_clocks(time_at_speed1, time_at_speed2):
    if time_at_speed2.empty():
        print 'No data to compare to'
        return
    remaining_hist = time_at_speed2.subtract(time_at_speed1)

    time_diff = time_at_speed1.total() - time_at_speed2.total()
    zero_to_add1 = max(-time_diff, 0)
    zero_to_add2 = max(time_diff, 0)

    if zero_to_add1 > 0:
        time_at_speed1.update({decimal.Decimal("0.0"): zero_to_add1})

    if zero_to_add2 > 0:
        time_at_speed2.update({decimal.Decimal("0.0"): zero_to_add2})

    quarters = [0.0, 0.25, 0.5, 0.75, 1.00]
    quarter_pairs = zip(
        time_at_speed1.values_at_quantiles(quarters),
        time_at_speed2.values_at_quantiles(quarters))

    current_speed = walking.get_current_speed()

    print ' -- '.join(
        '{}{}{}'.format(
            current,
            ARROW[current - old >= 0],
            old)
        for current, old in quarter_pairs)

    print 'Remaining time: {}/{} '.format(
        remaining_hist.total(),
        time_at_speed2.total())

    if remaining_hist.empty():
        print 'YOU HAVE WON!'
    else:
        print 'Remaining top:', remaining_hist.value_at_quantile(1.00)
        print 'Current speed: {} (abs:{:.2f}, remaining:{:.2f})'.format(
            current_speed,
            time_at_speed2.quantile_at_value(current_speed),
            remaining_hist.quantile_at_value(current_speed))

def show_rep_comparison(days_ago):
    today_json = json.loads(backticks([
        'cli-count.py',
        'summary',
        '--days-ago',
        str(days_ago),
        '--json']))

    today_counts = [
        dict_replace(x, name=x['name'].split('.', 1)[1]) for x in today_json['counts'] if x['name'].startswith('exercise.')]

    with with_data(DATA_FILE) as data:
        by_exercise_scores = Data.get_exercise_scores(data)

        ignore_date = data.get('versus.rep.ignore.date')
        ignore_date = ignore_date and datetime.date(*ignore_date)

        if ignore_date == datetime.date.today():
            to_ignore = data.get('versus.rep.ignore', [])
        else:
            to_ignore = []

    total = 0
    uncounted = 0
    unscored_exercises = set()
    for count in today_counts:
        score = by_exercise_scores.get(count['name'])
        if score:
            activity_total = score.last_value() * count['count']
            total += activity_total
        else:
            uncounted += count['count']
            unscored_exercises.add(count['name'])

    print 'Points:', total

    if uncounted:
        print 'Uncounted:', uncounted

    if unscored_exercises:
        print 'Unscored activities', ' '.join(sorted(unscored_exercises))

    results = json.loads(backticks([
        'cli-count.py',
        'compare',
        '{} days ago'.format(days_ago), '+1d',
        'today', '+1d',
        '--regex', '^exercise\\.',
        '--sort', 'shortfall',
        '--json']))

    results = [result for result in results if result[0] not in to_ignore]
    print '\n'.join(['{} {} {}'.format(*r) for r in results])

def start_sprint(duration):
    backticks(['superwatch.sh', 'start', 'walking.sprint.{}'.format(duration)])

def stop_sprint(duration):
    backticks(['superwatch.sh', 'stop', 'walking.sprint.{}'.format(duration)])
    result = backticks(['superwatch.sh', 'show', '--json', 'walking.sprint.{}'.format(duration)])
    data = json.loads(result)
    distance = walking.get_distance(start=data['start'], end=data['stop'])
    backticks(['cli-score.py', 'store', 'walking.sprint.{}'.format(duration), str(distance)])
    print backticks(['cli-score.py', 'summary', 'walking.sprint.{}'.format(duration)])

class ScoreTimeSeries(object):
    def __init__(self, time_series):
        self.time_series = time_series

    def last_value(self):
        return self.time_series[-1][1]

def exercise_set_score(exercise, days_ago, score):
    if exercise == PROMPT:
        rep_exercises = Data.get_rep_exercises(days_ago)
        with with_data(DATA_FILE) as data:
            scores = Data.get_exercise_scores(data)

        rep_exercises.sort(key=lambda x: scores[x].last_value() if x in scores else None)

        choices = ['{} {}'.format(
            exercise,
            scores[exercise].last_value()
            if exercise in scores else 'UNKNOWN')
                       for exercise in rep_exercises]

        exercise = guiutils.combo_prompt('exercise', choices).split()[0]
    elif exercise is not None:
        exercise = exercise
    else:
        raise Exception('Must specify an exercise')

    if score == PROMPT:
        score = guiutils.float_prompt('Score:')
    elif score is not None:
        score = score
    else:
        raise Exception('Must specify a score somehow')

    with with_data(DATA_FILE) as data:
        Data.set_exercise_score(data, exercise, score)


@contextlib.contextmanager
def with_data(data_file):
    "Read from a json file, write back to it when we are finished"
    with fasteners.InterProcessLock(data_file + '.lck'):
        data = read_json(data_file)
        yield data
        output_data = json.dumps(data)

        with open(data_file, 'w') as stream:
            stream.write(output_data)


class Data(object):
    @staticmethod
    def get_rep_exercises(days_ago=None):
        if days_ago is not None:
            counters = backticks(['cli-count.py', 'list', '--days-ago', str(days_ago)]).splitlines()
        else:
            counters = backticks(['cli-count.py', 'list']).splitlines()

        exercises = [x.split('.', 1)[1]
            for x in counters if x.startswith('exercise.')]
        return exercises

    @staticmethod
    def get_exercise_scores(data):
        return {k: ScoreTimeSeries(v) for (k, v) in data.get('rep.scores.by.exercise', {}).items()}

    @staticmethod
    def set_exercise_score(data, exercise, score):
        by_exercise_scores = data.setdefault('rep.scores.by.exercise', {})
        exercise_scores = by_exercise_scores.setdefault(exercise, [])
        exercise_scores.append((time.time(), score))

    @staticmethod
    def get_to_ignore(data):
        ignore_date = data.get('versus.rep.ignore.date')
        ignore_date = ignore_date and datetime.date(*ignore_date)

        if ignore_date == datetime.date.today():
            return data.get('versus.rep.ignore', [])
        else:
            return []

    @staticmethod
    def set_to_ignore(data, ignore_list):
        today = datetime.date.today()
        data['versus.rep.ignore'] = ignore_list
        data['versus.rep.ignore.date'] = [today.year, today.month, today.day]


# UTILITY FUNCTIONS

def dict_replace(dict, **kwargs):
    updated = copy.copy(dict)
    for key, value in kwargs.items():
        updated[key] = value
    return updated

def backticks(command, stdin=None):
    if stdin:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    else:
        process = subprocess.Popen(command, stdout=subprocess.PIPE)

    result, _ = process.communicate(stdin)
    LOGGER.debug('Running %r (%r)', command, ' '.join(command))
    if process.returncode != 0:
        raise Exception(
            '{!r} returned non-zero return code {!r}'.format(
                command,
                process.returncode))
    return result

def read_json(filename):
    if os.path.exists(filename):
        with open(filename) as stream:
            return json.loads(stream.read())
    else:
        return dict()


class TrackTest(unittest.TestCase):
    def test_count_to_quantiles(self):
        hist = Histogram({0:20, 20:20, 40:20, 60:20, 80:20})
        self.assertEquals(
            hist.values_at_quantiles([0.0, 0.5]),
            [0, 40])
        self.assertEquals(
            hist.values_at_quantiles([0.1, 0.2, 0.3, 0.4, 0.41]),
            [0, 0, 20, 20, 40])

    def test_count_to_quantiles_decimals(self):
        hist = Histogram({
            decimal.Decimal(0):20,
            decimal.Decimal(20):20,
            decimal.Decimal(40):20,
            decimal.Decimal(60):20,
            decimal.Decimal(80):20})
        self.assertEquals(
            hist.values_at_quantiles([0.0, 0.5]),
            [0, 40])
        self.assertEquals(
            hist.values_at_quantiles([0.1, 0.2, 0.3, 0.4, 0.41]),
            [0, 0, 20, 20, 40])

    def test_substract(self):
        hist1 = Histogram({1:10, 2:5, 4:5, 7:1})
        hist2 = Histogram({0:20, 3:10, 5:1, 6:1})
        self.assertEquals(hist1.subtract(hist2).counts, {1:5, 4:3, 7:1})



if __name__ == '__main__':
    main()
