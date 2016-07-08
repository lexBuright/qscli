import collections
import datetime
import decimal
import json
import logging
import subprocess

import numpy

from histogram import Histogram

LOGGER = logging.getLogger()

MINUTE_SPEC = '%Y-%m-%dT%H%M'


INCLINES = [
    "0.0", "0.5", "1.0", "1.5", "2.0", "2.5", "3.0", "3.5", "4.0", "4.5",
    "5.0", "5.5", "6.0", "6.5", "7.0", "7.5", "8.0", "8.5", "9.0", "9.5",
    "10.0", "10.5", "11.0", "11.5", "12.0", "12.5", "13.0", "13.5", "14.0", "14.5", "15.0"]
SPEEDS = ["{:.1f}".format(n) for n  in numpy.arange(0.8, 20.1, 0.1)]

def backticks(command):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)

    LOGGER.debug('Running %r', command)
    result, _ = process.communicate(command)
    LOGGER.debug('Finished %r', command)

    if process.returncode != 0:
        raise Exception('{!r} returned non-zero return code {!r}'.format(command, process.returncode))
    return result

bt = backticks

def change_setting(lst, value, incr):
    index = min(len(lst), max(lst.index(value) + incr, 0))
    return lst[index]

def start_walking():
    bt('superwatch.sh start walking.speed -n 0.8')
    bt('superwatch.sh start walking.incline -n 0.0')
    print 'Starting exercise'

def change_incline(incr):
    bt('superwatch.sh show walking.incline --json ')
    incline = json.loads(
        bt("""
superwatch.sh show walking.incline --json | jq '.splits | map(select(.current)) | map (.name) | .[0]'"""
          ).strip())
    new_incline = next_incline(incline, incr)
    bt('superwatch.sh split walking.incline -n {}'.format(new_incline))
    print 'incline', new_incline

def change_speed(incr):
    bt('superwatch.sh show walking.incline --json ')
    speed = json.loads(bt("""
    	superwatch.sh show walking.speed --json | jq '.splits | map(select(.current)) | map (.name) | .[0]'
    """).strip())
    new_speed = next_speed(speed, incr)
    bt('superwatch.sh split walking.speed -n {}'.format(new_speed))
    print 'speed', new_speed

def next_incline(incline, incr):
    return change_setting(INCLINES, incline, incr)

def next_speed(incline, incr):
    return change_setting(SPEEDS, incline, incr)

def reset_settings():
    bt('superwatch.sh split walking.speed -n {}'.format(SPEEDS[0]))
    bt('superwatch.sh split walking.incline -n {}'.format(INCLINES[0]))

def get_distance(clock='walking.speed', start=None, end=None):
    "Distance walked in kilometers per hour"
    data = load_play(clock, start=start, end=end)
    return sum(numpy.diff(data[:, 0]) * map(float, data[1:, 1])) / 3600

def show():
    print 'speeds'
    print bt('superwatch.sh show walking.speed | tail -n 10')
    print 'inclines'
    print bt('superwatch.sh show walking.incline | tail -n 10')

def show_all():
    print 'speeds'
    print bt('superwatch.sh show walking.speed')
    print 'inclines'
    print bt('superwatch.sh show walking.incline')

def stop():
    bt('superwatch.sh stop walking.speed')
    bt('superwatch.sh stop walking.incline')
    timestamp = datetime.datetime.now().strftime(MINUTE_SPEC)
    bt('superwatch.sh save walking.speed walking.speed.{}'.format(timestamp))
    bt('superwatch.sh save walking.incline walking.incline.{}'.format(timestamp))
    bt('superwatch.sh delete walking.speed')
    bt('superwatch.sh delete walking.incline')
    print 'Done walking'

def _get_clocks_for_day(seek_day):
    today = datetime.datetime.now().date()
    for clock in bt('superwatch.sh clocks --quiet').splitlines():
        if clock.startswith('walking.speed'):
            if clock == 'walking.speed':
                date = today
            else:
                _, date_string = clock.rsplit('.', 1)
                date = datetime.datetime.strptime(date_string, MINUTE_SPEC).date()

            if date == seek_day:
                yield clock

def get_speed_histogram_for_day(day):
    clocks = _get_clocks_for_day(day)
    return Histogram(clocks_time_at_speed(clocks))

def get_current_speed_histogram():
    return Histogram(clocks_time_at_speed(['walking.speed']))

def clocks_time_at_speed(clocks):
    time_at_speeds = collections.defaultdict(float)
    for clock in clocks:
        for key, value in get_time_at_speed(clock).items():
            time_at_speeds[decimal.Decimal(key)] += value
    return time_at_speeds

def get_time_at_speed(clock='walking.speed'):
    data = load_play(clock)
    time_spent = numpy.diff(data[:, 0])
    speed = data[1:, 1]

    totals = collections.defaultdict(float)
    for speed, time in zip(speed, time_spent):
        totals[speed] += time

    return totals

def load_play(clock, start=None, end=None):
    start_string = '--after {} '.format(start) if start else ''
    end_string = '--before {} '.format(end) if start else ''
    data_string = bt('superwatch.sh play {} --no-wait --absolute {} {}'.format(clock, start_string, end_string))
    data = numpy.array([
        (float(line.split()[0]), decimal.Decimal(line.split()[1]))
        for line in data_string.splitlines()])
    return data

def get_current_speed():
    result = backticks(['superwatch.sh show walking.speed --json'])
    data = json.loads(result)
    return decimal.Decimal(data['splits'][-1]['name'])

def get_time_blocks(day):
    "Return blocks form (start, speed, duration) for a given day"
    for clock in sorted(_get_clocks_for_day(day)):
        data = load_play(clock)
        starts = data[:-1, 0]
        ends = data[1:, 0]
        speeds = data[:-1, 1]

        last_start, last_end, last_speed = None, None, None
        for start, end, speed in zip(starts, ends, map(decimal.Decimal, speeds)):
            print start, end, speed
            assert end > start

            if last_speed != speed:
                if last_speed:
                    assert last_end > last_start
                    yield last_start, last_end, last_speed

                last_start = start
                last_speed = speed
            last_end = end


        assert last_end > last_start
        yield last_start, last_end, speed
