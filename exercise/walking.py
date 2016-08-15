import collections
import datetime
import decimal
import json
import logging
import subprocess


from histogram import Histogram
from watch import Watch

LOGGER = logging.getLogger('walking')

MINUTE_SPEC = '%Y-%m-%dT%H%M'

INCLINES = [
    "0.0", "0.5", "1.0", "1.5", "2.0", "2.5", "3.0", "3.5", "4.0", "4.5",
    "5.0", "5.5", "6.0", "6.5", "7.0", "7.5", "8.0", "8.5", "9.0", "9.5",
    "10.0", "10.5", "11.0", "11.5", "12.0", "12.5", "13.0", "13.5", "14.0", "14.5", "15.0"]
SPEEDS = [
    '0.8', '0.9', '1.0', '1.1', '1.2', '1.3', '1.4', '1.5', '1.6', '1.7', '1.8', '1.9',
    '2.0', '2.1', '2.2', '2.3', '2.4', '2.5', '2.6', '2.7', '2.8', '2.9', '3.0', '3.1',
    '3.2', '3.3', '3.4', '3.5', '3.6', '3.7', '3.8', '3.9', '4.0', '4.1', '4.2', '4.3',
    '4.4', '4.5', '4.6', '4.7', '4.8', '4.9', '5.0', '5.1', '5.2', '5.3', '5.4', '5.5',
    '5.6', '5.7', '5.8', '5.9', '6.0', '6.1', '6.2', '6.3', '6.4', '6.5', '6.6', '6.7',
    '6.8', '6.9', '7.0', '7.1', '7.2', '7.3', '7.4', '7.5', '7.6', '7.7', '7.8', '7.9',
    '8.0', '8.1', '8.2', '8.3', '8.4', '8.5', '8.6', '8.7', '8.8', '8.9', '9.0', '9.1',
    '9.2', '9.3', '9.4', '9.5', '9.6', '9.7', '9.8', '9.9', '10.0', '10.1', '10.2', '10.3',
    '10.4', '10.5', '10.6', '10.7', '10.8', '10.9', '11.0', '11.1', '11.2', '11.3', '11.4',
    '11.5', '11.6', '11.7', '11.8', '11.9', '12.0', '12.1', '12.2', '12.3', '12.4', '12.5',
    '12.6', '12.7', '12.8', '12.9', '13.0', '13.1', '13.2', '13.3', '13.4', '13.5', '13.6',
    '13.7', '13.8', '13.9', '14.0', '14.1', '14.2', '14.3', '14.4', '14.5', '14.6', '14.7',
    '14.8', '14.9', '15.0', '15.1', '15.2', '15.3', '15.4', '15.5', '15.6', '15.7', '15.8',
    '15.9', '16.0', '16.1', '16.2', '16.3', '16.4', '16.5', '16.6', '16.7', '16.8', '16.9',
    '17.0', '17.1', '17.2', '17.3', '17.4', '17.5', '17.6', '17.7', '17.8', '17.9', '18.0',
    '18.1', '18.2', '18.3', '18.4', '18.5', '18.6', '18.7', '18.8', '18.9', '19.0', '19.1',
    '19.2', '19.3', '19.4', '19.5', '19.6', '19.7', '19.8', '19.9', '20.0']



def backticks(command):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)

    LOGGER.debug('Running %r', command)
    result, _ = process.communicate(command)
    LOGGER.debug('Finished %r', command)

    if process.returncode != 0:
        raise Exception('{!r} returned non-zero return code {!r}'.format(command, process.returncode))
    return result

def noshell_backticks(command):
    process = subprocess.Popen(command, stdout=subprocess.PIPE)

    LOGGER.debug('Running %r', command)
    result, _ = process.communicate(command)
    LOGGER.debug('Finished %r', command)

    if process.returncode != 0:
        raise Exception('{!r} returned non-zero return code {!r}'.format(command, process.returncode))
    return result

nbt = noshell_backticks

bt = backticks

def change_setting(lst, value, incr):
    index = min(len(lst), max(lst.index(value) + incr, 0))
    return lst[index]

def start_walking():
    watch = Watch()
    watch.initialize()
    watch.run(['start', 'walking.speed', '-n', '0.8'])
    watch.run(['start', 'walking.incline', '-n', '0.0'])
    print 'Starting exercise'

def change_incline(incr):
    watch = Watch()
    watch.initialize()

    data = json.loads(watch.run(['show', 'walking.incline', '--json']))
    incline, = [x['name'] for x in data['splits'] if x['current']]
    new_incline = next_incline(incline, incr)
    watch.run(['split', 'walking.incline', '-n', new_incline])
    watch.shutdown()

    print 'incline', new_incline

def change_speed(incr):
    watch = Watch()
    watch.initialize()

    data = json.loads(watch.run(['show', 'walking.speed', '--json']))
    speed, = [x['name'] for x in data['splits'] if x['current']]

    new_speed = next_speed(speed, incr)
    watch.run(['split', 'walking.speed', '-n', new_speed])
    print 'Stopping watch'
    watch.shutdown()

    print 'speed', new_speed

def next_incline(incline, incr):
    return change_setting(INCLINES, incline, incr)

def next_speed(incline, incr):
    return change_setting(SPEEDS, incline, incr)

def reset_settings():
    watch = Watch()
    watch.initialize()

    watch.run(['split', 'walking.speed', '-n', SPEEDS[0]])
    watch.run(['split', 'walking.incline', '-n', INCLINES[0]])
    watch.shutdown()

def get_distance(clock='walking.speed', start=None, end=None):
    "Distance walked in kilometers per hour"
    import numpy # numpy takes 3-4 milliseconds to import
    data = load_play(clock, start=start, end=end)
    return sum(numpy.diff(data[:, 0]) * map(float, data[1:, 1])) / 3600

def show():
    watch = Watch()
    watch.initialize()
    print 'speeds'
    print '\n'.join(watch.run(['show', 'walking.speed']).splitlines()[-10:])
    print 'inclines'
    print '\n'.join(watch.run(['show', 'walking.incline']).splitlines()[-10:])

def show_all():
    watch = Watch()
    watch.initialize()
    print 'speeds'
    print watch.run(['show', 'walking.speed'])
    print 'inclines'
    print watch.run(['show', 'walking.incline'])

def stop():
    watch = Watch()
    watch.initialize()
    watch.run(['stop', 'walking.speed'])
    watch.run(['stop', 'walking.incline'])
    timestamp = datetime.datetime.now().strftime(MINUTE_SPEC)
    watch.run(['move', 'walking.speed', 'walking.speed.{}'.format(timestamp)])
    watch.run(['move', 'walking.incline', 'walking.incline.{}'.format(timestamp)])
    watch.run(['delete', 'walking.speed'])
    watch.run(['delete', 'walking.incline'])
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
    import numpy # numpy takes 3-4 milliseconds to import
    data = load_play(clock)
    time_spent = numpy.diff(data[:, 0])
    speed = data[1:, 1]

    totals = collections.defaultdict(float)
    for speed, time in zip(speed, time_spent):
        totals[speed] += time

    return totals

def load_play(clock, start=None, end=None):
    import numpy # numpy takes 3-4 milliseconds to import
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
