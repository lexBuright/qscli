import datetime
import decimal
import json
import time

from . import parsers, walking
from .data import Data
from .watch import Watch

ARROW = {True: ">", False: "<"}

def add_subparser(parser):
    sub = parser.add_subparsers(dest='walking_action')
    sub.add_parser('aggregates')
    sub.add_parser('start')
    sub.add_parser('stop')
    sub.add_parser('incline-up')
    sub.add_parser('speed-up')
    sub.add_parser('incline-down')
    sub.add_parser('speed-down')
    sub.add_parser('show')
    sub.add_parser('show-all')
    sub.add_parser('daily-aggregates')
    sub.add_parser('reset')
    sub.add_parser('start-sprint')
    sub.add_parser('stop-sprint')
    record_sprint = sub.add_parser('record-sprint')
    record_sprint.add_argument('duration', type=int, help='How long to sprint for')
    versus = sub.add_parser('versus')
    parsers.days_ago_option(versus)

def run(args):
    if args.walking_action == 'start':
        walking.start_walking()
    elif args.walking_action == 'incline-up':
        walking.change_incline(1)
    elif args.walking_action == 'incline-down':
        walking.change_incline(-1)
    elif args.walking_action == 'speed-up':
        walking.change_speed(1)
    elif args.walking_action == 'speed-down':
        walking.change_speed(-1)
    elif args.walking_action == 'show':
        walking.show()
    elif args.walking_action == 'show-all':
        walking.show_all()
    elif args.walking_action == 'aggregates':
        aggregates_for_speeds(walking.get_current_speed_histogram())
    elif args.walking_action == 'daily-aggregates':
        aggregates_for_speeds(
            walking.get_speed_histogram_for_day(datetime.date.today()))
    elif args.walking_action == 'stop':
        walking.stop()
    elif args.walking_action == 'reset':
        walking.reset_settings()
        print 'Speed and incline set to their minimum'
    elif args.walking_action == 'versus':
        days_ago = args.days if args.days is not None else Data.get_versus_days_ago()
        versus(days_ago)
    elif args.walking_action == 'start-sprint':
        start_sprint('free')
    elif args.walking_action == 'stop-sprint':
        stop_sprint('free')
    elif args.walking_action == 'record-sprint':
        record_sprint(args.duration)
    else:
        raise ValueError(args.walking_action)

def versus(days_ago):
    print 'Today versus {} days ago'.format(days_ago)
    time_at_speed1 = walking.get_speed_histogram_for_day(
        datetime.date.today())

    time_at_speed2 = walking.get_speed_histogram_for_day(
        (datetime.datetime.now() - datetime.timedelta(days=days_ago)).date())

    versus_clocks(time_at_speed1, time_at_speed2)

def aggregates_for_speeds(time_at_speeds):
    total_time = time_at_speeds.total()
    distance = walking.histogram_to_distance(time_at_speeds)
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
    with Watch() as watch:
        watch.run(['start', 'walking.sprint.{}'.format(duration)])

def stop_sprint(duration):
    with Watch() as watch:
        watch.run(['stop', 'walking.sprint.{}'.format(duration)])
        result = watch.run(['show', '--json', 'walking.sprint.{}'.format(duration)])
        data = json.loads(result)
        distance = walking.get_distance(start=data['start'], end=data['stop'])
        watch.run(['store', 'walking.sprint.{}'.format(duration), str(distance)])
        print watch.run(['summary', 'walking.sprint.{}'.format(duration)])

def record_sprint(duration):
    display_period = 30
    start = time.time()
    start_sprint(duration)
    end = start + duration
    while time.time() < end:
        time.sleep(min(end - time.time(), display_period))
        print time.time() - start
    stop_sprint(duration)

def distance_summary():
    today_distance = walking.get_day_distance(0)
    hour_distance = walking.get_distance(start=datetime.datetime.utcnow() - datetime.timedelta(seconds=3600))
    ten_distance = walking.get_distance(start=datetime.datetime.utcnow() - datetime.timedelta(seconds=600))
    return 'Today {:.2f} km\nHour: {:.2f}\nTen minutes: {:.2f}'.format(today_distance, hour_distance, ten_distance)
