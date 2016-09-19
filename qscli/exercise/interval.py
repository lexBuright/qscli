import collections
import itertools
import json
import time

from . import const, parsers
from .. import guiutils
from .data import SCORER, WATCH, Data

PARAM_DIRECTIONS = ('incline', 'speed', 'active', 'rest', 'count')

def add_subparser(parser):
    sub = parser.add_subparsers(dest='interval_action')

    new_endurance = sub.add_parser('new')
    parsers.exercise_prompt(new_endurance)
    settings_prompt(new_endurance, True)

    start_parser = sub.add_parser('start')
    parsers.exercise_prompt(start_parser, required=False)
    settings_prompt(start_parser, False)

    sub.add_parser('stop')
    sub.add_parser('stats')
    graph = sub.add_parser('graph', help='Draw a graph of intervals')
    graph.add_argument('exercise', type=str)

    frontier = sub.add_parser('frontier').add_subparsers(dest='frontier_action')
    move_action = frontier.add_parser('move', help='Move around the frontier surface in a particular direction')
    move_action.add_argument('exercise', type=str)
    increase_decrease = move_action.add_mutually_exclusive_group()
    increase_decrease.add_argument('--increase', type=str, choices=PARAM_DIRECTIONS)
    #increase_decrease.add_argument('--decrease', type=str, choices=PARAM_DIRECTIONS)

    radiate_action = frontier.add_parser('radiate', help='Find the edge along a particular ray from the origin')
    radiate_action.add_argument('exercise', type=str)
    radiate_action.add_argument('direction', type=str, choices=PARAM_DIRECTIONS)


def settings_prompt(parser, required):
    active = parser.add_mutually_exclusive_group(required=required)
    active.add_argument('--active-time', type=int, help='Activity time in seconds')
    active.add_argument('--prompt-for-active-time', action='store_const', const=const.PROMPT, dest='active_time')

    rest = parser.add_mutually_exclusive_group(required=required)
    rest.add_argument('--rest-time', type=int, help='Rest time in seconds')
    rest.add_argument('--prompt-for-rest-time', action='store_const', const=const.PROMPT, dest='rest_time')

    incline = parser.add_mutually_exclusive_group(required=required)
    incline.add_argument('--incline', type=float, help='Incline of machine')
    incline.add_argument('--prompt-for-incline', action='store_const', const=const.PROMPT, dest='incline')

    speed = parser.add_mutually_exclusive_group(required=required)
    speed.add_argument('--speed', type=float, help='Speed of machine')
    speed.add_argument('--prompt-for-speed', action='store_const', const=const.PROMPT, dest='speed')

def run(args):
    if args.interval_action == 'new':
        new_exercise(args.exercise, args.active_time, args.rest_time, args.incline, args.speed)
    elif args.interval_action == 'start':
        start(args.exercise)
    elif args.interval_action == 'stop':
        stop()
    elif args.interval_action == 'stats':
        stats()
    elif args.interval_action == 'graph':
        graph(args.exercise)
    elif args.interval_action == 'frontier':
        frontier_run(args)
    else:
        raise ValueError(args.interval_action)

def frontier_run(args):
    if args.frontier_action == 'radiate':
        radiate_frontier(args.exercise, args.direction)
    elif args.frontier_action == 'move':
        move_frontier(args.exercise, args.increase)
    else:
        raise ValueError(args.frontier_action)

def move_frontier(exercise, increase):
    print 'Increasing', increase
    from pandas import Series
    frontier_point = Series(Data.get_interval_frontier_point())
    # We want to find the closest frontier point with a
    # value a little bit bigger than frontier_point[increase]

    # Find a value that increase `increase` the least
    # of all such values get the other values as close
    # as possible to the current value and then push out
    # to a frontier

    def stupid_distance(p1, p2):
        return sum([abs(p1[k] - p2[k]) for k in p1.to_dict() if k != 'name'])

    data = get_data_points(exercise)
    if increase is not None:
        greater_values = [x for x in data[increase] if x > frontier_point[increase]]
        if greater_values:
            new_value = min(greater_values)
            possible_points = [x for _, x in data.iterrows() if x[increase] == new_value]
            closest_point = min(possible_points, key=lambda p: stupid_distance(p, frontier_point))
            new_point = random_maximise(data, closest_point)
            Data.set_interval_frontier_point(new_point.to_dict())
            print new_point
        else:
            print 'No greater value'
            print frontier_point

def random_maximise(data, initial):
    "Find a frontier point near the initial"
    point = initial

    while True:
        for _, other_point in data.iterrows():
            if all(other_point[k] >= point[k] for k in point.to_dict()):
                if not all(point == other_point):
                    point = other_point
                    break
        else:
            return point


def multi_argmax(columns, data):
    "Find the argument that maximizes these columns in order"
    # Pandas has weird bugs, do this manually

    def get_maximal_indexes(column, data):
        result = set()
        max_value = None
        for index, row in data.iterrows():
            if max_value is None or row[column] > max_value:
                max_value = row[column]
                result = set([index])
            elif row[column] == max_value:
                result.add(index)
        return result

    for column in columns:
        maximal_indexes = get_maximal_indexes(column, data)
        data = data.loc[maximal_indexes]
    (_, result), = data.iterrows()
    return result

def radiate_frontier(exercise, direction):
    order = [direction] + [x for x in PARAM_DIRECTIONS if x != direction]
    data = get_data_points(exercise)
    point = multi_argmax(order, data)
    print point
    Data.set_interval_frontier_point(point.to_dict())


DataPoint = collections.namedtuple('DataPoint', 'speed incline active rest count name')

def parse_score(score_name, value):
    _literal_exercise, _score, _interval, _exercise, speed_string, incline_string, active_string, rest_string = score_name.split('.')
    speed = float(speed_string.split(':')[1].replace(',', '.'))
    incline = float(incline_string.split(':')[1].replace(',', '.'))
    active = int(active_string.split(':')[1])
    rest = int(rest_string.split(':')[1])
    return DataPoint(speed=speed, incline=incline, active=active, rest=rest, count=float(value), name=str(speed))


def get_data_points(exercise):
    import pandas

    df = pandas.DataFrame(columns=DataPoint._fields)
    data = json.loads(SCORER.get().run(['records', '--json', '--regex', '^exercise.score.interval.{}.'.format(exercise)]))
    for index, (score_name, record) in enumerate(data['records'].items()):
        point = parse_score(score_name, record['value'])
        df.loc[index] = point

    return df

def plot_graph(exercise, points):
    from pandas.tools.plotting import parallel_coordinates # pandas is big
    import pylab
    parallel_coordinates(points, 'name')
    pylab.show()

def graph(exercise):
    points = get_data_points(exercise)
    plot_graph(exercise, points)


def maybe_int(float_or_int):
    if float(int(float_or_int)) == float_or_int:
        return int(float_or_int)
    else:
        return float_or_int

def format_float_or_int(float_or_int):
    float_or_int = maybe_int(float_or_int)
    if isinstance(float_or_int, int):
        return str(float_or_int)
    else:
        return str(float_or_int).strip('0').replace('.', ',')

def get_score_name():
    exercise = Data.get_interval_exercise()
    active_period = int(Data.get_interval_active())
    rest_period = int(Data.get_interval_rest())
    incline = Data.get_interval_incline()
    speed = Data.get_interval_speed()

    speed_string = format_float_or_int(speed)
    incline_string = format_float_or_int(incline)

    return 'exercise.score.interval.{}.speed:{}.incline:{}.active:{}.rest:{}'.format(exercise, speed_string, incline_string, int(active_period), int(rest_period))

def start(exercise):
    if exercise is not None:
        Data.set_interval_exercise(exercise)

    exercise = Data.get_interval_exercise()
    active_period = Data.get_interval_active()
    rest_period = Data.get_interval_rest()

    data = json.loads(WATCH.get().run(['show', 'exercise.interval', '--json']))
    if data['running']:
        print 'Already running\n\n'
        return
    score_name = get_score_name()

    SCORER.get().run(['store', score_name, '0'])
    WATCH.get().run(['start', 'exercise.interval'])
    print 'Start', exercise
    for index in itertools.count(1):
        # IMPROVEMENT: Ideally this would immediately break when the clock stops
        data = json.loads(WATCH.get().run(['show', 'exercise.interval', '--json']))
        if not data['running']:
            break

        print '{} for {} seconds'.format(exercise, active_period)
        print '\n\n'

        time.sleep(active_period)
        data = json.loads(WATCH.get().run(['show', 'exercise.interval', '--json']))
        if not data['running']:
            break

        SCORER.get().run(['update', score_name, str(index)])
        print 'rest from {} for {} seconds'.format(exercise, rest_period)
        print SCORER.get().run(['summary', score_name, '--update']).encode('utf8')
        print '\n\n'

        time.sleep(rest_period)
    print 'Finished'

def stop():
    print 'Stopping'
    WATCH.get().run(['stop', 'exercise.interval'])

def stats():
    exercise = Data.get_interval_exercise()
    speed = Data.get_interval_speed()
    incline = Data.get_interval_incline()
    active = Data.get_interval_active()
    rest = Data.get_interval_rest()

    score_name = get_score_name()
    data = json.loads(WATCH.get().run(['show', 'exercise.interval', '--json']))

    print 'speed incline active rest'
    print speed, incline, active, rest
    print

    active_period = Data.get_interval_active()
    rest_period = Data.get_interval_rest()

    cycle_offset = data['duration'] % (active_period + rest_period)
    if cycle_offset <= active_period:
        remaining = active_period - cycle_offset
        print '{} Interval {:.1f}/{:1f} ({:.1f} remaining)'.format(exercise, cycle_offset, active_period, remaining)
    else:
        remaining = active_period + rest_period - cycle_offset
        done = cycle_offset - active_period
        print '{} Rest {:.1f}/{:.1f} ({:.1f} remaining)'.format(exercise, done, rest_period, remaining)
    print SCORER.get().run(['summary', score_name, '--update']).encode('utf8')

def new_exercise(exercise, active_time, resting_time, incline, speed):
    if exercise == const.PROMPT:
        exercise_name = guiutils.combo_prompt('interval_exercise', Data.get_interval_exercises())

    if speed == const.PROMPT:
        speed = guiutils.float_prompt('Speed')

    if incline == const.PROMPT:
        incline = guiutils.float_prompt('Incline')

    if active_time == const.PROMPT:
        active_time = guiutils.int_prompt('Active time')

    if resting_time == const.PROMPT:
        resting_time = guiutils.int_prompt('Resting time')

    if exercise_name == '':
        return

    Data.set_interval_exercise(exercise_name)
    Data.set_interval_incline(incline)
    Data.set_interval_speed(speed)
    Data.set_interval_active(active_time)
    Data.set_interval_rest(resting_time)
