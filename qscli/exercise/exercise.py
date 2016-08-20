#!/usr/bin/python -u
# -*- coding: utf-8 -*-

# This is to be classified as useful glue code

import argparse
import datetime
import decimal
import json
import logging
import random
import subprocess
import sys
import time
import unittest

from .data import Data, SCORER
from . import reps, endurance
from . import guiutils
from . import walking
from . import const
from .histogram import Histogram
from . import parsers

LOGGER = logging.getLogger()

ARROW = {True: ">", False: "<"}

def main():
    #pylint: disable=too-many-branches
    parser = build_parser()
    args = parser.parse_args()
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    if args.action == 'start':
        walking.start_walking()
    elif args.action == 'versus-days':
        Data.set_versus_days_ago(args.days_ago)
    elif args.action == 'incr-versus-days':
        Data.incr_versus_days_ago(1)
        print Data.get_versus_days_ago()
    elif args.action == 'decr-versus-days':
        Data.incr_versus_days_ago(-1)
        print Data.get_versus_days_ago()
    elif args.action == 'reset-versus-days':
        Data.set_versus_days_ago(1)
        print Data.get_versus_days_ago()
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
    elif args.action == 'set-score':
        record_score(args.exercise, args.score)

    elif args.action == 'reps':
        reps.run(args)
    elif args.action == 'endurance':
        endurance.run(args)

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

    elif args.action == 'versus':
        days_ago = args.days if args.days is not None else Data.get_versus_days_ago()
        versus_summary(days_ago)
    elif args.action == 'walking-versus':
        days_ago = args.days if args.days is not None else Data.get_versus_days_ago()

        print 'Today versus {} days ago'.format(days_ago)
        time_at_speed1 = walking.get_speed_histogram_for_day(
            datetime.date.today())
        time_at_speed2 = walking.get_speed_histogram_for_day(
            (datetime.datetime.now() - datetime.timedelta(days=days_ago)).date())
        versus_clocks(time_at_speed1, time_at_speed2)
    elif args.action == 'reset':
        walking.reset_settings()
        print 'Speed and incline set to their minimum'
    elif args.action == 'test':
        sys.argv[1:] = []
        unittest.main()
    elif args.action == 'random-suggestion':
        random_suggestion()
    else:
        raise ValueError(args.action)

def random_suggestion():
    endurance_exercises = Data.get_endurance_exercises()
    repetition_exercises = Data.get_rep_exercises()
    ignore_list = Data.get_to_ignore()

    exercise_type, choices = random.choice([('endurance', endurance_exercises), ('repetition', repetition_exercises)])
    exercise = random.choice([x for x in choices if x not in ignore_list])
    print '{}: {}'.format(exercise_type, exercise)

def build_parser():
    parser = argparse.ArgumentParser(description='Keep track of exercise')
    parser.add_argument('--debug', action='store_true', help='Print debug output')
    sub = parser.add_subparsers(dest='action')
    sub.add_parser('aggregates')
    sub.add_parser('start')
    sub.add_parser('stop')
    sub.add_parser('incline-up')
    sub.add_parser('speed-up')
    sub.add_parser('incline-down')
    sub.add_parser('speed-down')
    sub.add_parser('show')
    sub.add_parser('show-all')

    reps.add_subparser(sub.add_parser('reps', help='Actions related to recording reps'))
    endurance.add_subparser(sub.add_parser('endurance', help='Actions related to endurance exercise (do something for as long as possible)'))

    sub.add_parser('random-suggestion')

    sub.add_parser('random-report')

    set_versus = sub.add_parser('versus-days')
    set_versus.add_argument('days_ago', type=int, help='Compare activity to this many days ago')

    sub.add_parser('incr-versus-days')
    sub.add_parser('decr-versus-days')

    set_score = sub.add_parser('set-score', help='Set the score for a particular exercise')
    set_score.add_argument('--exercise', type=str)
    set_score.add_argument('--prompt-for-exercise', dest='exercise', action='store_const', const=const.PROMPT, help='Prompt for the exercise with a graphical pop up')
    set_score.add_argument('--score', type=float)
    set_score.add_argument('--prompt-for-score', action='store_const', dest='score', const=const.PROMPT, help='Prompt for the exercise with a graphical pop up')

    sub.add_parser('daily-aggregates')
    sub.add_parser('start-sprint')
    sub.add_parser('stop-sprint')
    record_sprint = sub.add_parser('record-sprint')
    record_sprint.add_argument('duration', type=int, help='How long to sprint for')
    sub.add_parser('test')

    walking_versus = sub.add_parser('walking-versus')
    walking_versus.add_argument('days', default=1, type=int, help='Compare to this many days ago', nargs='?')

    versus = sub.add_parser('versus')
    versus.add_argument(
        'days',
        type=int,
        help='How many days ago to compare to',
        nargs='?')

    sub.add_parser('reset')
    return parser

def aggregates_for_speeds(time_at_speeds):
    total_time = time_at_speeds.total()
    distance = sum(
        speed * time_at_speed / 3600
        for (speed, time_at_speed) in time_at_speeds.counts())
    quartiles = time_at_speeds.values_at_quantiles([0.0, 0.25, 0.5, 0.75, 1.0])
    speed = distance / total_time * 1000.0
    print '{:.2f}km'.format(distance)
    print '{:.0f}s'.format(total_time)
    print '{:.2f} m/s'.format(speed)
    quartile_string = ' - '.join(['{:.2}'.format(q / 3.6) for q in quartiles])
    print 'Speed quartiles', quartile_string

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


def start_sprint(duration):
    backticks(['qswatch', 'start', 'walking.sprint.{}'.format(duration)])

def stop_sprint(duration):
    backticks(['qswatch', 'stop', 'walking.sprint.{}'.format(duration)])
    result = backticks(['qswatch', 'show', '--json', 'walking.sprint.{}'.format(duration)])
    data = json.loads(result)
    distance = walking.get_distance(start=data['start'], end=data['stop'])
    backticks(['qsscore', 'store', 'walking.sprint.{}'.format(duration), str(distance)])
    print backticks(['qsscore', 'summary', 'walking.sprint.{}'.format(duration)])

# UTILITY FUNCTIONS

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

def versus_summary(days_ago):
    print 'Todays versus {} days ago'.format(days_ago)
    print ''
    today_points = reps.calculate_points(0)
    old_points = reps.calculate_points(days_ago)

    print 'Points:', old_points.total, today_points.total

    if today_points.uncounted + old_points.uncounted:
        print 'Uncounted:', today_points.uncounted + old_points.uncounted
    if today_points.unscored_exercises:
        print 'Unscored activities', ' '.join(sorted(set(today_points.unscored_exercises) | set(old_points.unscored_exercises)))

    today_counts = Data.get_exercise_counts(0)
    compare_day_counts = Data.get_exercise_counts(days_ago)

    def rep_total(counts):
        return sum(x['count'] for x in counts)

    print 'Rep exercises', len(compare_day_counts), len(today_counts)
    print 'Reps', rep_total(compare_day_counts), rep_total(today_counts)

    today_endurance_scores = Data.get_endurance_scores(0)
    compare_endurance_scores = Data.get_endurance_scores(days_ago)

    print 'Endurance types', compare_endurance_scores.num_types(), today_endurance_scores.num_types()
    print 'Endurance seconds {:.0f} {:.0f}'.format(compare_endurance_scores.total_seconds(), today_endurance_scores.total_seconds())

def record_score(exercise_name, score):
    if exercise_name == const.PROMPT:
        exercise_name = guiutils.combo_prompt('exercise', Data.get_score_exercises())

    if score == const.PROMPT:
        score = guiutils.float_prompt('Score:')

    if exercise_name is None:
        raise Exception('Must specify exercise')
    if score is None:
        raise Exception('Must specify score')

    store_name = 'exercise.{}'.format(exercise_name)
    SCORER.get().run(['store', store_name, str(score)])
    print SCORER.get().run(['summary', store_name, '--update'])



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
