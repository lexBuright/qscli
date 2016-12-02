#!/usr/bin/python

import argparse
import json
import os
import select
import sys
import time
import tty

import numpy
from scipy import stats

import termios

PARSER = argparse.ArgumentParser(description='Work out the frequency of a number of keypresses. Can be used to e.g. track pulse or breathing rate with no hardware. Use C-c to quite.')
PARSER.add_argument('--confidence', '-c', default=0.95, type=float)
PARSER.add_argument('--tolerance', '-t', default=5.0, type=float)
PARSER.add_argument('--show-periods', '-p', action='store_true', help='Show period information about every key press')
PARSER.add_argument('--raw', '-r', action='store_true', help='Do not clear lines between prints')
PARSER.add_argument('--json', '-j', action='store_true', help='Output as machine-readable json')
PARSER.add_argument('--auto', '-a', action='store_true', help='Stop as soon as a stable reading is reached')
PARSER.add_argument('--no-tty', '-T', action='store_true', help='Use stdin and standard out for interactivity (rather than tty)')
PARSER.add_argument('--beat-file', '-b', type=str, help='Write the timeseries of beats to a file')


def readchar(stream, wait_for_char=True):
    # Taken from
    # https://github.com/magmax/python-readchar.git

    if hasattr(stream, 'readchar'):
        return stream.readchar()

    old_settings = termios.tcgetattr(stream)
    tty.setcbreak(stream.fileno())
    try:
        if wait_for_char or select.select([stream, ], [], [], 0.0)[0]:
            char = os.read(stream.fileno(), 1)
            return char if type(char) is str else char.decode()
    finally:
        termios.tcsetattr(stream, termios.TCSADRAIN, old_settings)


def get_character(terminal):
    c = readchar(terminal)
    if c == '\x03': # C-c
        raise KeyboardInterrupt()

    if c == '\x0a': # Enter
        return True

    return False

class ClickTimer(object):
    def __init__(self):
        self._last_click = None
        self.periods = []
        self.frequencies = []

    def click(self):
        click = time.time()
        if self._last_click:
            self.periods.append(click - self._last_click)
            self.frequencies.append(60.0 / (click - self._last_click))
        self._last_click = click


class TerminalDisplay(object):
    def __init__(self, terminal, raw):
        self._terminal = terminal
        self._raw = raw
        self._last_string = None

    def show(self, string):
        self.clear()
        self._terminal.write(string)
        self._terminal.flush()
        self._last_string = string

        if self._raw:
            self._terminal.write('\n')
            self._terminal.flush()

    def clear(self):
        if self._raw:
            return

        if self._last_string:
            self._terminal.write('\r' + ' ' * len(self._last_string) + '\r')

        self._last_string = None
        self._terminal.flush()

class InfoFormatter(object):
    def __init__(self, show_periods):
        self._show_periods = show_periods

    def format_triple(self, index, triple, periods):
        period = sum(periods[:index])
        (lower, mid, upper) = triple
        size = (upper - lower) / 2.0
        result = '{:.1f} +/- {:.1f} bpm (over {:.1f}s)'.format(mid, size, period)

        if self._show_periods:
            result = '{:.1f} bpm '.format(60.0 / periods[-1]) + result

        return result

def calculate_bpm(timer, confidence, tolerance):
    beat_time = time.time()
    result = non_result = None

    if timer.periods:
        # This should really be corrected for multicomparison problems...
        #   This will show up if the data has no really periodicity,
        #   we are likely to find a sperious periodicity over
        #   a large period
        confidences = list(timeseries_confidences(timer.frequencies, confidence))
        for index, triple in enumerate(confidences):

            (lower, mid, upper) = triple
            plus_minus = (upper - lower) / 2.0

            if plus_minus < tolerance:
                result = dict(
                    estimate=mid,
                    plus_minus=plus_minus,
                    status='success',
                    time=beat_time,
                    index=index,
                    triple=triple
                    )
                return result, None
        else:
            if not confidences:
                return None, None
            else:
                temp = [((upper - lower), i) for i, (lower, _mid, upper) in list(enumerate(confidences))]
                _, index = min(temp)
                triple = confidences[index]
                (lower, mid, upper) = triple
                plus_minus = (upper - lower) / 2.0

                non_result = dict(
                    best_guess=triple[1],
                    plus_minus=plus_minus,
                    status='did-not-converge',
                    time=beat_time,
                    triple=triple
                )

                return None, non_result
    raise Exception('Unreachable')


def format_result(formatter, periods, result, non_result):
    index = result.get('index') if result else  non_result.get('index')
    triple = result.get('triple') if result else non_result.get('triple')

    if result:
        return 'GOOD {}'.format(formatter.format_triple(index, triple, periods))
    elif non_result:
        return 'BAD {}'.format(formatter.format_triple(index, triple, periods))
    else:
        return  'BAD '


def main():
    args = PARSER.parse_args()
    if args.no_tty:
        interactive_in = sys.stdin
        interactive_out = sys.stdout
    else:
        interactive_in = interactive_out = open('/dev/tty', 'w+')

    beat_stream = args.beat_file and open(args.beat_file, 'w')

    timer = ClickTimer()
    display = TerminalDisplay(interactive_out, args.raw)

    formatter = InfoFormatter(args.show_periods)

    display.show('Press any key at a rate. Enter to finish result written to stdout\n')
    result = None

    result = None
    while not args.auto or result is None:
        if get_character(interactive_in):
            break
        timer.click()
        if not timer.periods:
            continue

        result, non_result = calculate_bpm(timer, args.confidence, args.tolerance)
        output = format_result(formatter, timer.periods, result, non_result)
        display.show(output)

        if beat_stream:
            write_beat(beat_stream, result or non_result)

    display.clear()
    show_result(result or non_result, args.json)

def write_beat(beat_stream, result):
    beat_stream.write(json.dumps(result))
    beat_stream.write('\n')
    beat_stream.flush()

def show_result(result, is_json):
    if is_json:
        if result is None:
            print json.dumps(dict(status='did-no-stabilise'))
        else:
            print json.dumps(result)
    else:
        if result is None:
            print 'Did not find a reading'
            sys.exit(1)
        else:
            print result['estimate']

def show_output(terminal, raw, string):
    if raw:
        terminal.write(string + '\n')
    else:
        terminal.write('\r' + string)
    terminal.flush()

def timeseries_confidences(values, confidence):
    # This approach is not statistically valid...
    #   but it's a functional hack

    for i in range(1, len(values) + 1):
        yield confidence_interval(confidence, values[-i:])


def confidence_interval(confidence, values):
    mean = numpy.mean(values)
    if len(values) <= 2:
        return 0, mean, 10000

    lower, upper = stats.t.interval(confidence, len(values)-1, loc=numpy.mean(values), scale=stats.sem(values))
    return lower, mean, upper

if __name__ == '__main__':
	main()