import json

from .. import guiutils

from .data import SCORER, Data
from .watch import Watch
from . import const
from . import parsers
from . import points
from . import dict_score

def settings_option(parser):
    parser.add_argument('--setting', '-s', action='append', help='Settings for this exercise, of the form a=b;c=d;e=PROMPT or PROMPT')

def add_subparser(parser):
    sub = parser.add_subparsers(dest='endurance_action')
    set_endurance = sub.add_parser('set')
    parsers.exercise_prompt(set_endurance)
    settings_option(set_endurance)

    start_endurance = sub.add_parser('start')
    start_endurance.add_argument('--exercise', type=str)
    settings_option(start_endurance)

    sub.add_parser('stop')
    sub.add_parser('stats')

    result_parser = sub.add_parser('results', help='Show history results')
    result_parser.add_argument('exercise', type=str)


    edit_parser = sub.add_parser('edit', help='Edit an endurance exercise')
    edit_parser.add_argument('exercise', type=str, help='Exercise name')
    edit_parser.add_argument('--float-setting', type=parse_csv, help='List of setting names which are floats')
    edit_parser.add_argument('--string-setting', type=parse_csv, help='List of setting names which are strings')

    points = sub.add_parser('points')
    points.add_argument('days_ago', default=0, type=int, nargs='?')

    set_weight = sub.add_parser('set-exercise-weight', help='Set the number of points earned per second of exercise')
    parsers.exercise_prompt(set_weight)
    score = set_weight.add_mutually_exclusive_group(required=True)
    score.add_argument('--score', type=float)
    score.add_argument('--prompt-for-score', action='store_const', const=const.PROMPT, dest='score')

    endurance_versus = sub.add_parser('versus')
    parsers.days_ago_option(endurance_versus)

def parse_csv(csv_string):
    return [s.strip() for s in csv_string.split(',')]

def parse_settings(setting):
    if setting is None:
        return None
    if any(s == 'PROMPT' for s in setting):
        return const.PROMPT
    result = {}
    for string in setting:
        for pair_string in string.split(';'):
            key, value = pair_string.strip().split('=')
            if key in result:
               raise Exception('Setting {} set twice'.format(key))
            parse_setting_value(value)
            result[key] = value

    return result

def parse_setting_value(value):
    try:
        return float(value)
    except ValueError:
        return value

def run(args):
    if args.endurance_action == 'set':
        set_endurance_exercise(args.exercise, parse_settings(args.setting))
    elif args.endurance_action == 'start':
        start_endurance_exercise(args.exercise, parse_settings(args.setting))
    elif args.endurance_action == 'stats':
        endurance_stats()
    elif args.endurance_action == 'stop':
        stop_endurance_exercise()
    elif args.endurance_action == 'points':
        print str(calculate_points(args.days_ago).total)
    elif args.endurance_action == 'set-exercise-weight':
        set_weight(args.exercise, args.score)
    elif args.endurance_action == 'versus':
        days_ago = args.days_ago if args.days_ago is not None else Data.get_versus_days_ago()
        show_endurance_comparison(days_ago)
    elif args.endurance_action == 'edit':
        edit_exercise(args.exercise, args.float_setting, args.string_setting)
    elif args.endurance_action == 'results':
        show_results(args.exercise)
    else:
        raise ValueError(args.endurance_action)

def show_results(exercise):
    required_settings = set(Data.get_endurance_settings(exercise) or {})
    scorer = make_scorer(exercise)
    def settings_key(score):
        return tuple(score.settings[k] for k in required_settings)

    for setting, value in sorted(scorer.all_scores(), key=settings_key):
        print setting, value

def edit_exercise(exercise, float_settings, string_settings):
    float_setting_dict = dict([(n, 'float') for n in (float_settings or [])])
    string_setting_dict = dict([(n, 'string') for n in (string_settings or [])])
    settings = dict(float_setting_dict, **string_setting_dict)
    Data.set_endurance_settings(exercise, settings)

def set_weight(exercise, score):
    if exercise == const.PROMPT:
        weights = Data.get_endurance_weights()
        exercise = guiutils.combo_prompt('endurance exercise', weights)

    if score == const.PROMPT:
        score = guiutils.float_prompt('score')

    Data.set_endurance_weight(exercise, score)

def calculate_points(days_ago):
    uncounted = total = 0
    data = json.loads(SCORER.get().run(['log', '-x', '^exercise.endurance.', '--days-ago', str(days_ago), '--json']))
    unscored = set()

    for entry in data:
        exercise = entry['metric'].split('.', 2)[-1]
        weight = get_weight(exercise)
        if weight == 0:
            uncounted += 1
            unscored.add(exercise)
        total += weight * entry['value']

    return points.Points(total=total, uncounted=uncounted, unscored_exercises=unscored)

def get_weight(exercise):
    return Data.get_endurance_weight(exercise)

def endurance_stats():
    exercise = Data.get_endurance_exercise()
    settings = Data.get_current_endurance_settings()

    with Watch() as watch:
        data = json.loads(watch.run(['show', 'exercise-endurance', '--json']))

    duration = data['duration']

    scorer = make_scorer(exercise)
    scorer.update(settings, duration)
    summary = scorer.summary(settings)

    print exercise
    print summary.encode('utf8')

def make_scorer(exercise):
    return dict_score.DictScorer(SCORER.get(), 'exercise.endurance.{}'.format(exercise))

def get_settings(exercise, settings):
    required_settings = Data.get_endurance_settings(exercise) or {}
    if settings == const.PROMPT:
        settings = prompt_for_settings(required_settings)
    settings = settings or dict()
    unknown_settings = set(settings) - set(required_settings)
    if unknown_settings:
        raise Exception('Exercise does not support {!r}'.format(unknown_settings))
    missing_settings = set(required_settings) - set(settings)
    if missing_settings:
        raise Exception('There are missing settings {!r}'.format(missing_settings))
    return settings

def set_endurance_exercise(exercise, settings):
    if exercise is None:
        raise Exception('Must specify an exercise')

    if exercise == const.PROMPT:
        weights = Data.get_endurance_weights()
        exercise_name = guiutils.combo_prompt('endurance exercise', weights)

    if exercise_name == '':
        return

    settings = get_settings(exercise_name, settings)
    Data.set_endurance_exercise(exercise_name)
    Data.set_current_endurance_settings(settings)

def prompt_for_settings(required_settings):
    settings = dict()
    for setting_name, setting_type in required_settings.items():
        if setting_type == 'float':
            setting_value = guiutils.float_prompt(setting_name)
        elif setting_type == 'string':
            setting_value = guiutils.str_prompt(setting_name)
        else:
            raise ValueError(setting_type)
        settings[setting_name] = setting_value
    return settings

def start_endurance_exercise(exercise, settings):
    exercise = exercise or Data.get_endurance_exercise(None)
    settings = settings or Data.get_current_endurance_settings()
    settings = get_settings(exercise, settings)

    Data.set_endurance_exercise(exercise)
    Data.set_current_endurance_settings(settings)

    with Watch() as watch:
        watch.run(['start', 'exercise-endurance'])

    scorer = make_scorer(exercise)
    scorer.store(settings, 0)

    if settings:
        settings_string = '({})'.format(' '.join('{}={}'.format(k, v) for k, v in settings.items()))
    else:
        settings_string = ''

    print 'Starting endurance exercise: {}{}'.format(exercise, settings_string)

def stop_endurance_exercise():
    exercise = Data.get_endurance_exercise()
    settings = Data.get_current_endurance_settings()

    with Watch() as watch:
        watch.run(['stop', 'exercise-endurance'])
        data = json.loads(watch.run(['show', 'exercise-endurance', '--json']))

    duration = data['duration']

    print 'Finished'
    make_scorer(exercise).update(settings, duration)
    summary = make_scorer(exercise).summary(settings)

    print exercise
    print summary

def get_results(exercise):
    data = json.loads(SCORER.get().run(['records', '--json', '--regex', '^exercise.score.interval.{}.'.format(exercise)]))


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
