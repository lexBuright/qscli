import collections
import datetime
import decimal
import json
import subprocess

import numpy

from histogram import Histogram

MINUTE_SPEC = '%Y-%m-%dT%H%M'
INCLINES = [
    "0.0", "0.5", "1.0", "1.5", "2.0", "2.5", "3.0", "3.5", "4.0", "4.5",
    "5.0", "5.5", "6.0", "6.5", "7.0", "7.5", "8.0", "8.5", "9.0", "9.5",
    "10.0", "10.5", "11.0", "11.5", "12.0", "12.5", "13.0", "13.5", "14.0", "14.5", "15.0"]
SPEEDS = ["{:.1f}".format(n) for n  in numpy.arange(0.8, 20.1, 0.1)]

def backticks(command):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)
    result, _ = process.communicate(command)
    if process.returncode != 0:
        raise Exception('{!r} returned non-zero return code {!r}'.format(command, process.returncode))
    return result

bt = backticks



def change_setting(lst, value, incr):
    index = min(len(lst), max(lst.index(value) + incr, 0))
    return lst[index]

def start_walking():
    bt('superwatch.py start walking.speed -n 0.8')
    bt('superwatch.py start walking.incline -n 0.0')
    print 'Starting exercise'

def change_incline(incr):
    bt('superwatch.py show walking.incline --json ')
    incline = json.loads(
        bt("""
superwatch.py show walking.incline --json | jq '.splits | map(select(.current)) | map (.name) | .[0]'"""
          ).strip())
    new_incline = next_incline(incline, incr)
    bt('superwatch.py split walking.incline -n {}'.format(new_incline))
    print 'incline', new_incline

def change_speed(incr):
    bt('superwatch.py show walking.incline --json ')
    speed = json.loads(bt("""
    	superwatch.py show walking.speed --json | jq '.splits | map(select(.current)) | map (.name) | .[0]'
    """).strip())
    new_speed = next_speed(speed, incr)
    bt('superwatch.py split walking.speed -n {}'.format(new_speed))
    print 'speed', new_speed

def next_incline(incline, incr):
    return change_setting(INCLINES, incline, incr)

def next_speed(incline, incr):
    return change_setting(SPEEDS, incline, incr)

def reset_settings():
    bt('superwatch.py split walking.speed -n {}'.format(SPEEDS[0]))
    bt('superwatch.py split walking.incline -n {}'.format(INCLINES[0]))

def get_distance(clock='walking.speed'):
    "Distance walked in kilometers per hour"
    data = load_play(clock)
    return sum(numpy.diff(data[:, 0]) * data[1:, 1]) / 3600

def show():
    print 'speeds'
    print bt('superwatch.py show walking.speed | tail -n 10')
    print 'inclines'
    print bt('superwatch.py show walking.incline | tail -n 10')

def show_all():
    print 'speeds'
    print bt('superwatch.py show walking.speed')
    print 'inclines'
    print bt('superwatch.py show walking.incline')

def stop():
    bt('superwatch.py stop walking.speed')
    bt('superwatch.py stop walking.incline')
    timestamp = datetime.datetime.now().strftime(MINUTE_SPEC)
    bt('superwatch.py save walking.speed walking.speed.{}'.format(timestamp))
    bt('superwatch.py save walking.incline walking.incline.{}'.format(timestamp))
    bt('superwatch.py delete walking.speed')
    bt('superwatch.py delete walking.incline')
    print 'Done walking'

def _get_clocks_for_day(seek_day):
    today = datetime.datetime.now().date()
    for clock in bt('superwatch.py clocks --quiet').splitlines():
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

def load_play(clock):
    data_string = bt('superwatch.py play {} --no-wait'.format(clock))
    data = numpy.array([
        (float(line.split()[0]), decimal.Decimal(line.split()[1]))
        for line in data_string.splitlines()])
    return data

def get_current_speed():
    result = backticks(['superwatch.py show walking.speed --json'])
    data = json.loads(result)
    return decimal.Decimal(data['splits'][-1]['name'])

def get_time_blocks(day):
    "Return blocks form (start, speed, duration) for a given day"
    for clocks in sorted(_get_clocks_for_day(day)):
        data = load_play(clock)
        timestamps = data[:-1, 0]
        time_spent = numpy.diff(data[:, 0])
        speed = data[:-1, 1]
        start_time, last_speed, total_time = None, None, 0
        for timestamp, speed, time in  zip(timestamps, decimal.Decimal(speed), time_spent):
            if last_speed != speed:
                if total_time > 0:
                    yield start_time, last_speed, total_time
                start_time, last_speed, total_time = timestamp, speed, 0
            total_time += time
        yield start_time, last_speed, total_time
