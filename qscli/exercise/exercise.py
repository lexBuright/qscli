# -*- coding: utf-8 -*-

# This is to be classified as useful glue code

import argparse
import decimal
import json
import logging
import random
import sys
import tempfile
import unittest

from .. import guiutils

from . import const, endurance, reps, walk_args, interval, gymtime
from .. import edit
from .data import SCORER, Data
from .histogram import Histogram

LOGGER = logging.getLogger()

def main():
    #pylint: disable=too-many-branches
    parser = build_parser()
    args = parser.parse_args()
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    if args.action == 'versus-days':
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

    elif args.action == 'set-score':
        record_score(args.exercise, args.score)
    elif args.action == 'reps':
        reps.run(args)
    elif args.action == 'gymtime':
        print gymtime.run(args),
    elif args.action == 'endurance':
        endurance.run(args)
    elif args.action == 'walking':
        walk_args.run(args)
    elif args.action == 'interval':
        interval.run(args)
    elif args.action == 'versus':
        days_ago = args.days if args.days is not None else Data.get_versus_days_ago()
        versus_summary(days_ago)
    elif args.action == 'test':
        sys.argv[1:] = []
        unittest.main()
    elif args.action == 'random-suggestion':
        random_suggestion()
    elif args.action == 'report':
        show_report(args.name, args.forget)
    elif args.action == 'last-report':
        print Data.get_last_report()
    elif args.action == 'edit-notes':
        edit_notes(args.editor)
    else:
        raise ValueError(args.action)

def edit_notes(editor):
    with tempfile.NamedTemporaryFile(delete=False) as stream:
        old_notes = Data.get_current_notes() or ''
        stream.write(old_notes)

    with open(stream.name) as edited_stream:
        print edited_stream.read()

    editors = [editor] if editor is not None else None
    edit.edit(stream.name, editors=editors)
    with open(stream.name) as edited_stream:
        Data.set_current_notes(edited_stream.read())


def show_notes():
    return Data.get_current_notes()

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

    gymtime.add_subparser(sub.add_parser('gymtime', help='Record the amount of time at the gym'))

    reps.add_subparser(sub.add_parser('reps', help='Actions related to recording reps'))
    endurance.add_subparser(sub.add_parser('endurance', help='Actions related to endurance exercise (do something for as long as possible)'))
    walk_args.add_subparser(sub.add_parser('walking', help='Actions related to walking exercise (Varying speed over time)'))
    interval.add_subparser(sub.add_parser('interval', help='Interval training'))

    sub.add_parser('random-suggestion')

    report = sub.add_parser('report')
    mx = report.add_mutually_exclusive_group()
    mx.add_argument('--prompt-for-name', action='store_const', help='Prompt for the name with a gui', dest='name', const=const.PROMPT)
    mx.add_argument('--again', action='store_const', help='Redisplay the last displayed report', dest='name', const=const.LAST)
    mx.add_argument('--previous', action='store_const', help='Display the report before this one', dest='name', const=const.PREVIOUS)
    mx.add_argument('--name', type=str, help='Which report to show', choices=list(REPORTS))
    mx.add_argument('--next', action='store_const', help='Display the report after this one', dest='name', const=const.NEXT)

    report.add_argument('--forget', action='store_true', help="Do not remember showing report for history")

    sub.add_parser('last-report')

    set_versus = sub.add_parser('versus-days')
    set_versus.add_argument('days_ago', type=int, help='Compare activity to this many days ago')

    sub.add_parser('incr-versus-days')
    sub.add_parser('decr-versus-days')

    set_score = sub.add_parser('set-score', help='Set the score for a particular exercise')
    set_score.add_argument('--exercise', type=str)
    set_score.add_argument('--prompt-for-exercise', dest='exercise', action='store_const', const=const.PROMPT, help='Prompt for the exercise with a graphical pop up')
    set_score.add_argument('--score', type=float)
    set_score.add_argument('--prompt-for-score', action='store_const', dest='score', const=const.PROMPT, help='Prompt for the exercise with a graphical pop up')


    sub.add_parser('test')

    edit = sub.add_parser('edit-notes')
    edit.add_argument('--editor', type=str, help='Do not use the default editor')

    versus = sub.add_parser('versus')
    versus.add_argument(
        'days',
        type=int,
        help='How many days ago to compare to',
        nargs='?')

    return parser

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

def new_records():
    output = []
    rep_records = reps.get_records()
    for name, record in rep_records.items():
        output.append('{} {:.2f} +{:.2f}'.format(name.split('.', 1)[1], record['value'], record['improvement'] or 0))
    improved_rep = len([d for d in rep_records.values() if d['improvement'] is not None])

    data = json.loads(SCORER.get().run(['records', '--json', '--days-ago', '0', '--regex', '^exercise.endurance']))
    for name, record in data['records'].items():
        output.append('{} {:.2f} +{:.2f}'.format(name.split('.', 1)[1], record['value'], record['improvement'] or 0))
    improved_endurance = len([d for d in data['records'].values() if d['improvement'] is not None])

    output.insert(0, '{} improved records\n'.format(improved_rep + improved_endurance))
    return '\n'.join(output)

def show_report(name=None, forget=False):
    if name == const.PROMPT:
        name = guiutils.combo_prompt('report', list(REPORTS))
    elif name == const.LAST:
        name = Data.get_last_report()
    elif name == const.NEXT:
        last = Data.get_last_report()
        name = REPORT_ORDER[min(REPORT_ORDER.index(last) + 1, len(REPORT_ORDER) - 1)]
    elif name == const.PREVIOUS:
        last = Data.get_last_report()
        name = REPORT_ORDER[max(REPORT_ORDER.index(last) - 1, 0)]

    if name is None:
        name = random.choice(list(REPORTS))

    heading, func = REPORTS[name]
    if not forget:
        Data.set_last_report(name)
    print heading
    print func()

def records_timeseries():
    length = 20
    records_by_days_ago = reps.get_record_history(length)
    return ' '.join(map(str, (records_by_days_ago[i] for i in range(length))))

def points_timeseries():
    length = 20
    return ' '.join(["{:.0f}".format(calculate_points(i).total) for i in range(length)])

def calculate_points(days_ago):
    return reps.calculate_points(days_ago)

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


REPORTS = {
    #('Walking', lambda: walk_args.versus(days_ago)),
    'summary': ('Summary', lambda: versus_summary(Data.get_versus_days_ago())),
    'reps': ('Reps comparison', lambda: reps.versus(Data.get_versus_days_ago())),
    'gymtime': ('Time at gym', gymtime.show),
    'gymtime-history': ('Time at gym', gymtime.timeseries),
    'records': ('New records set today', new_records),
    'records-history': ('Records per day', records_timeseries),
    'points-history': ('Points per day', points_timeseries),
    'notes': ('Notes', show_notes),
    'rep-matrix': ('Rep matrix', reps.rep_matrix)
    # 'distance': ('Distance walked', walk_args.distance_summary),
    # Too slow - getting qswatch to give us a sparse histogram would probably make this faster
}
REPORT_ORDER = sorted(REPORTS.keys())
