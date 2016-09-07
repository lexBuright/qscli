import json

from .. import guiutils

from .data import SCORER, Data
from .watch import Watch
from . import const
from . import parsers


def add_subparser(parser):
    sub = parser.add_subparsers(dest='endurance_action')
    set_endurance = sub.add_parser('set')
    parsers.exercise_prompt(set_endurance)

    start_endurance = sub.add_parser('start')
    start_endurance.add_argument('--exercise', type=str)

    sub.add_parser('stop')
    sub.add_parser('stats')

    points = sub.add_parser('points')
    points.add_argument('days_ago', default=0, type=int, nargs='?')

    set_weight = sub.add_parser('set-exercise-weight', help='Set the number of points earned per second of exercise')
    parsers.exercise_prompt(set_weight)
    score = set_weight.add_mutually_exclusive_group(required=True)
    score.add_argument('--score', type=float)
    score.add_argument('--prompt-for-score', action='store_const', const=const.PROMPT, dest='score')

    endurance_versus = sub.add_parser('versus')
    parsers.days_ago_option(endurance_versus)

def run(args):
    if args.endurance_action == 'set':
        set_endurance_exercise(args.exercise)
    elif args.endurance_action == 'start':
        start_endurance_exercise(args.exercise)
    elif args.endurance_action == 'stats':
        endurance_stats()
    elif args.endurance_action == 'stop':
        stop_endurance_exercise()
    elif args.endurance_action == 'points':
        print str(calculate_points(args.days_ago))
    elif args.endurance_action == 'set-exercise-weight':
        set_weight(args.exercise, args.score)
    elif args.endurance_action == 'versus':
        days_ago = args.days_ago if args.days_ago is not None else Data.get_versus_days_ago()
        show_endurance_comparison(days_ago)
    else:
        raise ValueError(args.endurance_action)

def set_weight(exercise, score):
    if exercise == const.PROMPT:
        weights = Data.get_endurance_weights()
        exercise = guiutils.combo_prompt('endurance exercise', weights)

    if score == const.PROMPT:
        score = guiutils.float_prompt('score')

    Data.set_endurance_weight(exercise, score)

def calculate_points(days_ago):
    points = 0
    data = json.loads(SCORER.get().run(['log', '-x', '^exercise.endurance.', '--days-ago', str(days_ago), '--json']))
    for entry in data:
        exercise = entry['metric'].split('.', 2)[-1]
        points += get_weight(exercise) * entry['value']
    return points

def get_weight(exercise):
    return Data.get_endurance_weight(exercise)

def endurance_stats():
    exercise = Data.get_endurance_exercise()

    with Watch() as watch:
        data = json.loads(watch.run(['show', 'exercise-endurance', '--json']))

    duration = data['duration']
    SCORER.get().run(['update', 'exercise.endurance.{}'.format(exercise), str(duration)])
    summary = SCORER.get().run(['summary', 'exercise.endurance.{}'.format(exercise)])
    print exercise
    print summary.encode('utf8')

def set_endurance_exercise(exercise):
    if exercise is None:
        raise Exception('Must specify an exercise')

    if exercise == const.PROMPT:
        weights = Data.get_endurance_weights()
        exercise_name = guiutils.combo_prompt('endurance exercise', weights)

    if exercise_name == '':
        return
    Data.set_endurance_exercise(exercise_name)

def start_endurance_exercise(exercise):
    exercise = exercise or Data.get_endurance_exercise(None)

    with Watch() as watch:
        watch.run(['start', 'exercise-endurance'])

    SCORER.get().run(['store', 'exercise.endurance.{}'.format(exercise), '0'])
    print 'Starting endurance exercise: {}'.format(exercise)

def stop_endurance_exercise():
    exercise = Data.get_endurance_exercise()

    with Watch() as watch:
        watch.run(['stop', 'exercise-endurance'])
        data = json.loads(watch.run(['show', 'exercise-endurance', '--json']))

    duration = data['duration']

    print 'Finished'
    SCORER.get().run(['update', 'exercise.endurance.{}'.format(exercise), str(duration)])
    summary = SCORER.get().run(['summary', 'exercise.endurance.{}'.format(exercise)])
    print exercise
    print summary

def show_endurance_comparison(days_ago):
    today_scores = Data.get_endurance_scores(0)
    compare_day_scores = Data.get_endurance_scores(days_ago)

    print 'Num types', compare_day_scores.num_types(), today_scores.num_types()
    print 'Total time', compare_day_scores.total_seconds(), today_scores.total_seconds()

    today_by_exercise = today_scores.by_exercise()
    compare_day_by_exercise = compare_day_scores.by_exercise()

    all_exercises = list(set(today_by_exercise) | set(compare_day_by_exercise))
    all_exercises.sort(
        key=lambda x: (compare_day_by_exercise[x]["total"] if x in today_by_exercise else 0) - (today_by_exercise[x]["total"] if x in today_by_exercise else 0)
    )

    for exercise in all_exercises:
        today_duration = today_by_exercise[exercise]["total_seconds"] if exercise in today_by_exercise else 0.0
        compare_day_duration = compare_day_by_exercise[exercise]["total_seconds"] if exercise in compare_day_by_exercise else 0.0

        compare_day_scores = compare_day_by_exercise[exercise]['values'] if exercise in compare_day_by_exercise else []
        today_scores = today_by_exercise[exercise]['values'] if exercise in today_by_exercise else []

        print exercise
        print '    Total {:.1f} {:.1f}'.format(compare_day_duration, today_duration)
        print '    Best {:.1f} {:.1f}'.format(max(compare_day_scores) if compare_day_scores else 0, max(today_scores) if today_scores else 0)
        print '    Comparison scores', ' '.join('{:.1f}'.format(x) for x in compare_day_scores)
        print '    Today scores', ' '.join('{:.1f}'.format(x) for x in today_scores)
        print ''
