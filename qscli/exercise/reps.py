import collections
import datetime
import json

from . import const, guiutils
from .data import COUNTER, SCORER, Data
from . import parsers

def add_subparser(parser):
    sub = parser.add_subparsers(dest='rep_action')

    set_score_ = sub.add_parser('set-score', help='Set the score for a rep based exercise exercise')
    set_score_.add_argument('--exercise', type=str)
    set_score_.add_argument('--prompt-for-exercise', dest='exercise', action='store_const', const=const.PROMPT, help='Prompt for the exercise with a graphical pop up')
    set_score_.add_argument('--score', type=float)
    set_score_.add_argument('--prompt-for-score', action='store_const', dest='score', const=const.PROMPT, help='Prompt for the exercise with a graphical pop up')
    set_score_.add_argument('--days-ago', '-A', type=int, help='Only set scores for exercises you did this many days ago')

    ignore = sub.add_parser('ignore', help='Ignore these activities today')
    ignore.add_argument('activity', type=str, help='', nargs='*')
    ignore.add_argument('--clear', action='store_true', help='Clear ignore list')

    versus = sub.add_parser('versus')
    parsers.days_ago_option(versus)

    # repetitions
    start = sub.add_parser('start')
    start.add_argument('exercise_name', type=str, help='Name of exercise')
    sub.add_parser('rep')
    note_parser = sub.add_parser('note')
    note_parser.add_argument('note', type=str, help='Record a note about the reps that you are doing')

def run(args):
    if args.rep_action == 'start':
        # IMPROVEMENT: we might like to bunch up things to do with reps
        exercise_name = 'exercise.{}'.format(args.exercise_name)
        exercise_score = 'exercise-score.{}'.format(args.exercise_name)

        Data.set_rep_exercise(exercise_name)

        COUNTER.get().run(['new-set', exercise_name])
        SCORER.get().run(['store', exercise_score, '0'])
    elif args.rep_action == 'note':
        COUNTER.get().run(['note', args.note])
    elif args.rep_action == 'rep':
        record_rep()
    elif args.rep_action == 'versus':
        days_ago = args.days_ago if args.days_ago is not None else Data.get_versus_days_ago()
        show_rep_comparison(days_ago)
    elif args.rep_action == 'set-score':
        # Perhaps this could all be done
        #    better with a single configuration file edited hand
        #    but to actually be useable this
        #    needs to be easy and *fun* to change
        set_score(args.exercise, args.days_ago, args.score)
    elif args.rep_action == 'ignore':
        activities = args.activity or []
        ignore_list = Data.get_to_ignore()

        if args.clear:
            ignore_list = []
        ignore_list = sorted(set(ignore_list + ['exercise.' + activity for activity in activities]))
        Data.set_to_ignore(ignore_list)

        print '\n'.join(ignore_list)

def record_rep():
    exercise_name = Data.get_rep_exercise()
    exercise_score = 'exercise-score.' + exercise_name.split('.', 1)[1]
    versus_days = Data.get_versus_days_ago()

    points = calculate_points(0)
    versus_points = calculate_points(versus_days)
    store_points(datetime.date.today(), points.total)

    import sparklines # This takes 2-3 milliseconds, so delay this (from __future__ import round)
    # graph = sparklines.sparklines([
    #     calculate_points(data, i).total
    #     for i in range(0, 7, 1)])[0]
    # print graph

    print 'Points: {} (vs {})'.format(points.total, versus_points.total)

    print 'Count:', exercise_name
    COUNTER.get().run(['incr', exercise_name])
    events = json.loads(COUNTER.get().run(['log', '--set', 'CURRENT', '--json', exercise_name]))

    if events:
        start = events['events'][0]['time']
        end = events['events'][-1]['time']
        duration = end - start
    else:
        duration = 0

    print 'Duration: {:.0f}'.format(duration)
    count = COUNTER.get().run(['count', '--set', 'CURRENT', exercise_name])
    count = int(count.strip())
    rate = count / duration if (count and duration) else 0

    print 'Rate: {:.2f}'.format(rate)
    SCORER.get().run(['update', exercise_score, str(count)])
    print SCORER.get().run(['summary', exercise_score, '--update'])

def calculate_points(days_ago):
    by_exercise_scores = Data.get_exercise_scores()
    counts = Data.get_exercise_counts(days_ago)

    total = 0
    uncounted = 0
    unscored_exercises = set()
    for count in counts:
        score = by_exercise_scores.get(count['name'])
        if score:
            activity_total = score.last_value() * count['count']
            total += activity_total
        else:
            uncounted += count['count']
            unscored_exercises.add(count['name'])
    return Points(total=total, uncounted=uncounted, unscored_exercises=unscored_exercises)

Points = collections.namedtuple('Points', 'total uncounted unscored_exercises')

def show_rep_comparison(days_ago):
    to_ignore = Data.get_to_ignore()
    today_points = calculate_points(0)
    old_points = calculate_points(days_ago)

    print SCORER.get().run(['summary', 'exercise-score.daily-points', '--update'])
    print 'Points:', old_points.total, today_points.total

    if today_points.uncounted + old_points.uncounted:
        print 'Uncounted:', today_points.uncounted + old_points.uncounted
    if today_points.unscored_exercises:
        print 'Unscored activities', ' '.join(sorted(set(today_points.unscored_exercises) | set(old_points.unscored_exercises)))

    results = json.loads(COUNTER.get().run([
        'compare',
        '{} days ago'.format(days_ago), '+1d',
        'today', '+1d',
        '--regex', '^exercise\\.',
        '--sort', 'shortfall',
        '--json']))

    results = [result for result in results if result[0] not in to_ignore]
    print '\n'.join(['{} {} {}'.format(*r) for r in results])

def set_score(exercise, days_ago, score):
    if exercise == const.PROMPT:
        rep_exercises = Data.get_rep_exercises(days_ago)
        scores = Data.get_exercise_scores()

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

    if score == const.PROMPT:
        score = guiutils.float_prompt('Score:')
    elif score is not None:
        score = score
    else:
        raise Exception('Must specify a score somehow')

    Data.set_exercise_score(exercise, score)

def store_points(day, points):
    SCORER.get().run(['update', '--id', day.isoformat(), 'exercise-score.daily-points', str(points)])
