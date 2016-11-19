#!/usr/bin/python


import argparse
import math
import time

import numpy
import readchar
from scipy import stats

PARSER = argparse.ArgumentParser(description='Work out the frequency of a number of keypresses. Can be used to e.g. track pulse or breathing rate with no hardware. Use C-c to quite.')
PARSER.add_argument('--confidence', '-c', default=0.95, type=float)
PARSER.add_argument('--tolerance', '-t', default=5.0, type=float)

def main():
    args = PARSER.parse_args()
    periods = []
    frequencies = []
    last_click = None
    while True:
        c = readchar.readchar()
        if c == '\x03': # C-c
            raise KeyboardInterrupt()

        if c == '\x10': # Enter
            break

        click = time.time()
        if last_click:
            periods.append(click - last_click)
            frequencies.append(60.0 / (click - last_click))
        last_click = click

        if periods:
            confidences = list(timeseries_confidences(frequencies, args.confidence))
            for index, triple in enumerate(confidences):
                (lower, _mid, upper) = triple
                if (upper - lower) / 2.0 < args.tolerance:
                    output = 'GOOD {}'.format(format_triple(index, triple, periods))
                    print '\r' + output,
                    break
            else:
                if not confidences:
                    output = 'BAD '
                    print '\r' + output,
                else:
                    temp = [((upper - lower), i) for i, (lower, _mid, upper) in list(enumerate(confidences))]
                    _, index = min(temp)
                    triple = confidences[index]
                    output = 'BAD  {}'.format(format_triple(index, triple, periods))
                    print '\r' + output,

def format_triple(index, triple, periods):
    period = sum(periods[:index])
    (lower, mid, upper) = triple
    size = (upper - lower) / 2.0
    return '{:.1f} +/- {:.1f} bpm (over {:.1f}s)'.format(mid, size, period)

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
