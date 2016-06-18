#!/usr/bin/python
# -*- coding: utf-8 -*-

# This is to be classified as useful glue code

import argparse
import datetime
import decimal
import subprocess
import sys
import unittest

import walking
from histogram import Histogram


def backticks(command):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)
    result, _ = process.communicate(command)
    if process.returncode != 0:
        raise Exception(
            '{!r} returned non-zero return code {!r}'.format(
                command,
                process.returncode))
    return result

bt = backticks

PARSER = argparse.ArgumentParser(description='Keep track of exercise')
parsers = PARSER.add_subparsers(dest='action')
parsers.add_parser('aggregates')
parsers.add_parser('start')
parsers.add_parser('stop')
parsers.add_parser('incline-up')
parsers.add_parser('speed-up')
parsers.add_parser('incline-down')
parsers.add_parser('speed-down')
parsers.add_parser('show')
parsers.add_parser('show-all')
parsers.add_parser('daily-aggregates')
parsers.add_parser('test')
versus = parsers.add_parser('versus')
versus.add_argument(
    'days',
    default=1,
    type=int,
    help='How many days ago to compare to')
parsers.add_parser('reset')


args = PARSER.parse_args()

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

ARROW = {True: ">", False: "<"}

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

def main():
    #pylint: disable=too-many-branches
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
    elif args.action == 'aggregates':
        aggregates_for_speeds(walking.get_current_speed_histogram())
    elif args.action == 'daily-aggregates':
        aggregates_for_speeds(
            walking.get_speed_histogram_for_day(datetime.date.today()))
    elif args.action == 'stop':
        walking.stop()
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


if __name__ == '__main__':
    main()
