# -*- coding: utf-8 -*-

# This is to be classified as useful glue code

import argparse
import decimal
import json
import logging
import os
import random
import subprocess
import sys
import tempfile
import unittest

from . import const, endurance, guiutils, reps, walk_args
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
    elif args.action == 'endurance':
        endurance.run(args)
    elif args.action == 'walking':
        walk_args.run(args)
    elif args.action == 'versus':
        days_ago = args.days if args.days is not None else Data.get_versus_days_ago()
        versus_summary(days_ago)
    elif args.action == 'test':
        sys.argv[1:] = []
        unittest.main()
    elif args.action == 'random-suggestion':
        random_suggestion()
    elif args.action == 'report':
        name = args.name if not args.prompt_for_name else const.PROMPT
        name = name if not args.last else const.LAST
        show_report(name)
    elif args.action == 'last-report':
        print Data.get_last_report()
    elif args.action == 'edit-notes':
        edit_notes(args.editor)
    else:
        raise ValueError(args.action)

def run(command, stdin=None, shell=False):
    stdin = subprocess.PIPE if stdin is not None else None

    process = subprocess.Popen(command, shell=shell)
    result, _ = process.communicate(stdin)
    if process.returncode != 0:
        raise ProgramFailed(command, process.returncode)
    return result

class ProgramFailed(Exception):
    def __init__(self, command, returncode):
        Exception.__init__(self)
        self.command = command
        self.returncode = returncode

    def __str__(self):
        return '{!r} returned non-zero return code {!r}'.format(self.command, self.returncode)

def get_default_editors():
    return [os.environ.get('VISUAL'), os.environ.get('EDITOR'), 'sensible-editor', 'vim', 'vi', 'nano', 'ed']

def edit_notes(editor):
    with tempfile.NamedTemporaryFile(delete=False) as stream:
        old_notes = Data.get_current_notes() or ''
        stream.write(old_notes)

    with open(stream.name) as edited_stream:
        print edited_stream.read()

    editors = [editor] if editor is not None else get_default_editors()
    for editor in editors:
        if editor is None:
            continue
        try:
            print [editor, stream.name]
            run([editor, stream.name])
        except ProgramFailed as e:
            if e.returncode == 127:
                continue
            else:
                raise
        else:
            with open(stream.name) as edited_stream:
                Data.set_current_notes(edited_stream.read())
                break
    else:
        raise Exception('Could not find a working editor (maybe set EDITOR)')

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

    reps.add_subparser(sub.add_parser('reps', help='Actions related to recording reps'))
    endurance.add_subparser(sub.add_parser('endurance', help='Actions related to endurance exercise (do something for as long as possible)'))
    walk_args.add_subparser(sub.add_parser('walking', help='Actions related to walking exercise (Varying speed over time)'))

    sub.add_parser('random-suggestion')

    report = sub.add_parser('report')
    report.add_argument('name', nargs='?', help='Which report to show', choices=list(REPORTS))
    report.add_argument('--prompt-for-name', action='store_true', help='Prompt for the name with a gui')
    report.add_argument('--last', action='store_true', help='Redisplay the last displayed report')

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
    data = json.loads(SCORER.get().run(['records', '--json', '--days-ago', '0', '--regex', '^exercise-score.']))
    output = []

    for name, record in data['records'].items():
        output.append('{} {:.2f} +{:.2f}'.format(name.split('.', 1)[1], record['value'], record['improvement'] or 0))

    data = json.loads(SCORER.get().run(['records', '--json', '--days-ago', '0', '--regex', '^exercise.endurance']))
    for name, record in data['records'].items():
        output.append('{} {:.2f} +{:.2f}'.format(name.split('.', 1)[1], record['value'], record['improvement'] or 0))

    return '\n'.join(output)

def show_report(name=None):
    if name == const.PROMPT:
        name = guiutils.combo_prompt('report', list(REPORTS))
    if name == const.LAST:
        name = Data.get_last_report()

    if name is None:
        name = random.choice(list(REPORTS))

    heading, func = REPORTS[name]
    Data.set_last_report(name)
    print heading
    print func()

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
    'records': ('New records set today', new_records),
    'notes': ('Notes', show_notes)
    # 'distance': ('Distance walked', walk_args.distance_summary),
    # Too slow - getting qswatch to give us a sparse histogram would probably make this faster
}
