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

def main():
    terminal = open('/dev/tty', 'w+')

    args = PARSER.parse_args()

    timer = ClickTimer()
    display = TerminalDisplay(terminal, args.raw)

    formatter = InfoFormatter(args.show_periods)

    display.show('Press any key at a rate. Enter to finish result written to stdout\n')

    result = None
    while True:
        if get_character(terminal):
            break
        timer.click()

        if timer.periods:
            # This should really be corrected for multicomparison problems...
            #   This will show up if the data has no really periodicity,
            #   we are likely to find a sperious periodicity over
            #   a large period
            confidences = list(timeseries_confidences(timer.frequencies, args.confidence))
            for index, triple in enumerate(confidences):
                (lower, mid, upper) = triple
                plus_minus = (upper - lower) / 2.0
                if plus_minus < args.tolerance:
                    result = dict(estimate=mid, plus_minus=plus_minus, status='success')
                    output = 'GOOD {}'.format(formatter.format_triple(index, triple, timer.periods))
                    display.show(output)
                    break
            else:
                if not confidences:
                    output = 'BAD '
                    display.show(output)
                else:
                    temp = [((upper - lower), i) for i, (lower, _mid, upper) in list(enumerate(confidences))]
                    _, index = min(temp)
                    triple = confidences[index]
                    output = 'BAD  {}'.format(formatter.format_triple(index, triple, timer.periods))
                    display.show(output)

    display.clear()
    show_result(result, args.json)

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
