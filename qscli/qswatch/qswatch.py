#!/usr/bin/python
"""Very feature-complete command line stopwatch / timer

# Very simple mode
qswatch # toggle the default stop watch (start or stop)

# More complicated modes
qswatch start
qswatch show
qswatch stop
qswatch split
qswatch split -l splitlabel
qswatch label-split # label the current split (before it is finished)
qswatch play clock1 clock2 # Output a csv of the clock labels every second

# Multiple timers
qswatch start timername
qswatch show timername
qswatch stop timername
qswatch split timername

If qswatch isn't quite super enough for you, you might want to look into timetrap.
"""

from . import jsdb_backend as backend
# from . import json_backend as backend

import contextlib
import json
import logging
import os

LOGGER = logging.getLogger(__name__)

class Watch(object):
    def __init__(self, data_dir, time_mod):
        self.data_dir = data_dir
        self.time_mod = time_mod

    def with_data(self, data=None):
        if data is not None:
            @contextlib.contextmanager
            def f():
                yield data
            return f()

        else:
            if not os.path.isdir(self.data_dir):
                os.mkdir(self.data_dir)
            data_file = os.path.join(self.data_dir, backend.DATA_FILE)
            return backend.with_data(data_file)

    @contextlib.contextmanager
    def with_clock_data(self, clock_name, data=None, clear=False):
        LOGGER.debug('Loading data...')
        with self.with_data(data=data) as d:
            clock_data = self.clock_data(d, clock_name, clear=clear)

            LOGGER.debug('Data Loaded.')
            yield clock_data


    def running(self, clock_name):
        "Check that the clock is currently running"
        with self.with_clock_data(clock_name) as clock_data:
            if clock_data and clock_data['running']:
                return True
            else:
                return False

    def clocks(self, quiet, is_running):
        with self.with_data() as data:
            for clock_name in sorted(data['clocks'].keys()):
                LOGGER.debug('Considering clock %r', clock_name)

                clock_data = data['clocks'][clock_name]

                if is_running is not None:
                    if is_running != clock_data['running']:
                        continue

                running_flag = '*' if clock_data['running'] else ''
                clock_duration = (clock_data['stop'] or self.time_mod.time()) - clock_data['start']
                if quiet:
                    yield '{}\n'.format(clock_name)
                else:
                    yield '{}{} {:.2f}\n'.format(running_flag, clock_name, clock_duration)

    def start(self, clock_name, next_label=None, interactive=False):
        with self.with_data() as data:
            with self.with_clock_data(clock_name, data=data) as clock_data:
                if not clock_data.get('running', False):
                    start = self.time_mod.time()
                    clock_data['running'] = True
                    clock_data['start'] = start
                    clock_data['stop'] = None
                    clock_data['splits'] = backend.new_list([ClockDataParser.new_split(start, name=next_label)])

        if interactive:
            return self.show(clock_name, is_interactive=True)

        return ''

    def label_split(self, clock_name, label):
        with self.with_clock_data(clock_name) as clock_data:
            clock_data['splits'][-1]['name'] = label
        return []

    def set_split_data(self, clock_name, data):
        with self.with_clock_data(clock_name) as clock_data:
            old_data = clock_data['splits'][-1]['data']
            old_data = old_data or backend.new_dict()
            old_data.update(data)
            clock_data['splits'][-1]['data'] = old_data
        return []

    def export(self, clock_name):
        with self.with_clock_data(clock_name) as clock_data:
            return backend.json_dumps(clock_data)

    def export_all(self):
        with self.with_data() as data:
            return backend.json_dumps(data)

    def import_all(self, filename):
        with self.with_data() as data:
            with open(filename) as stream:
                new_data = backend.json_loads(stream.read())

            for k, v in new_data.items():
                data[k] = v

        return []

    def delete(self, clocks):
        with self.with_data() as d:
            for clock in clocks:
                del d['clocks'][clock]
        return []

    def move(self, source_clock, target_clock):
        with self.with_data() as d:
            clock_data = self.clock_data(d, source_clock)
            d['clocks'][target_clock] = clock_data
        return []

    def play(self, clock_names, wait, absolute, after, before):
        assert len(clock_names) == 1 or not absolute

        clock_time = 0

        with self.with_data() as out_of_date_data:
            # horrible hack to get a data that
            #   is accessible without a connection
            data = json.loads(backend.json_dumps(out_of_date_data))


        while True:
            split_labels = []
            clock_name = None
            for clock_name in clock_names:
                LOGGER.debug('Waiting for split %r at %r', clock_name, clock_time)

                for _ in range(2):
                    try:
                        split_name = self.wait_for_split_at_time(clock_name, clock_time, wait=wait, data=data)
                        break
                    except IndexError:
                        data = None
                        continue
                    except NoMoreData:
                        split_name = 'MISSING'

                LOGGER.debug('Got split %r for %r', split_name, clock_name)
                split_labels.append(split_name)

            if all(split_label in ('MISSING', 'STOPPED') for split_label in split_labels):
                break

            if absolute:
                display_time = data['clocks'][clock_name]['start'] + clock_time
            else:
                display_time = clock_time

            if (after is None or display_time >= after) and (before is None or display_time <= before):
                yield '{:.1f} {}\n'.format(display_time, ' '.join(split_labels))
            clock_time += 1

    def wait_for_split_at_time(self, clock_name, clock_time, data=None, wait=False):
        while True:
            with self.with_clock_data(clock_name, data=data) as clock_data:
                LOGGER.debug('Looking for split at %r for %r', clock_time, clock_name)
                split = ClockDataParser.get_split_at_time(clock_data, clock_time, self.time_mod.time())
                if split is None:
                    if clock_data['running']:
                        pass
                    else:
                        return 'STOPPED'
                else:
                    return split['name'] or 'MISSING'
            if data:
                raise IndexError((clock_name, clock_time))
            elif wait:
                self.time_mod.sleep(1.0)
            else:
                raise NoMoreData()

    def show(self, clock_name, json_output=False, is_interactive=False):
        LOGGER.debug('Showing %r', clock_name)

        if json_output and is_interactive:
            raise Exception('Cannot have both json output and interactive output')

        if is_interactive:
            yield '\n'
            while True:
                self.time_mod.sleep(0.1)
                output = self.show_raw(clock_name, json_output).strip()
                yield '\r'
                yield output
        else:
            yield self.show_raw(clock_name, json_output)

    def show_split(self, clock_name, is_interactive):
        if is_interactive:
            old_name = None
            while True:
                self.time_mod.sleep(0.1)

                with self.with_clock_data(clock_name) as data:
                    new_name = data['splits'][-1]['name']
                    if new_name != old_name and old_name is not None:
                        yield '\n'
                    old_name = new_name

                    yielded = self.show_split_raw(data, clock_name).strip('\n')
                    # HACK - we should probably use blessings
                    yield '\r                                                  \r'
                    yield yielded
        else:
            with self.with_clock_data(clock_name) as data:
                yield self.show_split_raw(data, clock_name)

    def show_split_raw(self, data, clock_name):
            name = data['splits'][-1]['name']
            start = data['splits'][-1]['start']
            return '{} {:.2f}\n'.format(name, self.time_mod.time() - start)

    def show_raw(self, clock_name, json_output):
        with self.with_clock_data(clock_name) as clock_data:
            if not clock_data:
                return ''

            split_display = (
                len(clock_data['splits']) >= 2 or
                clock_data['splits'][0]['name'] != None or
                clock_data['splits'][0]['data'] != None)
            if split_display:
                return self.splits_show(clock_data, json_output)
            else:
                return self.simple_show(clock_data, json_output)

    def simple_show(self, clock_data, json_output):
        if not 'start' in clock_data:
            # No clock
            return ''

        if clock_data['running']:
            duration = self.time_mod.time() - clock_data['start']
        else:
            duration = clock_data['duration']

        if json_output:
            return backend.json_dumps(dict(running=clock_data['running'], duration=duration, start=clock_data['start'], stop=clock_data['stop']))
        else:
            return self.format_float(duration)

    def splits_show(self, data, json_output):
        if 'splits' not in data:
            data['splits'] = backend.new_list()

        splits = data['splits']

        for i in range(len(splits)):
            splits[i] = splits[i].copy()
            splits[i]['name'] = splits[i]['name'] or str(i)

        current_time = self.time_mod.time()
        last_split = splits[-1]

        if data['running']:
            last_split['current'] = True
            last_split['duration'] = current_time - splits[-1]['start']

        if json_output:
            duration = (data['stop'] or current_time) - data['start']
            return backend.json_dumps(dict(splits=splits, duration=duration))
        else:
            split_formats = []
            for split in splits:
                display_name = split_display_name(split)
                data = split.get('data')

                if not data:
                    split_formats.append('{} {:.2f}'.format(display_name, split['duration']))
                else:
                    split_formats.append('{} {} {:.2f}'.format(display_name, backend.json_dumps(data), split['duration']))

            total = sum(split['duration'] for split in splits)

            return '\n'.join(split_formats) + '\n-----\ntotal {:.2f}\n'.format(total)

    def split(self, clock_name, split_name, next_split_name, data=None, clock_time=None):
        with self.with_clock_data(clock_name, data=data) as clock_data:

            if 'splits' not in clock_data:
                clock_data['splits'] = backend.new_list()

            split_data = clock_data['splits']

            previous_split = split_data[-1]

            split_name = split_name or split_data[-1]['name']
            split_end = clock_time or self.time_mod.time()

            ClockDataParser.close_split(previous_split, split_end=split_end, name=split_name)

            new_split = ClockDataParser.new_split(start=split_end, name=next_split_name)
            split_data.append(new_split)

            return self.format_float(previous_split['duration'])

    def stop(self, clock_name):
        clock_time = self.time_mod.time()
        with self.with_data() as d:
            clock_data = self.clock_data(d, clock_name)
            if clock_data['running']:
                clock_data['running'] = False
                clock_data['stop'] = clock_time

                if clock_data.get('splits'):
                    self.split(clock_name, None, None, data=d, clock_time=clock_time)
                clock_data['splits'].pop()

            duration = clock_data['duration'] = clock_data['stop'] - clock_data['start']
            return self.format_float(duration)

    def format_float(self, number):
        return '{:.2f}\n'.format(number)

    @staticmethod
    def clock_data(data, clock_name, clear=False):
        if clear:
            if 'clocks' not in data:
                data['clocks'] = backend.new_dict()
            clocks_data = data['clocks']
            clock_data = clocks_data[clock_name] = backend.new_dict()
            return clock_data
        else:
            if 'clocks' not in data:
                data['clocks'] = backend.new_dict()

            if clock_name not in data['clocks']:
                data['clocks'][clock_name] = {}
            return data['clocks'][clock_name]

class ClockDataParser(object):
    "Parse things to do with clock data"
    # It might be a better move to serialize and then deserialize
    #   however, I feel that interacting directly with
    #   stored data has some advantages from a "simplicity"
    #   point of view (simple but complicated)

    @classmethod
    def new_split(cls, start, name=None):
        return backend.new_dict(dict(name=name, start=start, end=None, data=None, duration=None))

    @classmethod
    def close_split(cls, split, split_end, name=None):
        duration = split_end - split['start']
        # update doesn't work with PersistentList
        split['end'] = split_end
        split['duration'] = duration
        split['name'] = name if name is not None else split['name']
        split['current'] = False

    @classmethod
    def get_split_at_time(cls, clock_data, sought_time, clock_time):
        actual_time = sought_time + clock_data['start']
        for split in clock_data['splits']:
            LOGGER.debug('Looking for %r in %s', actual_time, DelayFormat(lambda: str(backend.deep_copy(split))))
            if actual_time < split['start']:
                raise ValueError(actual_time)
            elif split['end'] is not None:
                if actual_time < split['end']:
                    return split
                else:
                    continue
            else:
                if actual_time < clock_time:
                    return split
                else:
                    continue
        else:
            return None

def split_display_name(split):
    name = '' if not split.get('name') else split['name']
    if split.get('current'):
        return '*' + name
    else:
        return name

class DelayFormat(object):
    def __init__(self, thunk):
        self.thunk = thunk

    def __str__(self):
        return self.thunk()

class NoMoreData(Exception):
    "We have run out of data"
