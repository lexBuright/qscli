import json
import logging
import os
import shutil
import StringIO
import tempfile
import threading
import time
import unittest

LOGGER = logging.getLogger(__name__)


class SuperTest(unittest.TestCase):
    def setUp(self):
        self.direc = tempfile.mkdtemp()

        self.fake_time = FakeTime()

    def tearDown(self):
        shutil.rmtree(self.direc)

    def run_watch(self, *args):
        output_buffer = StringIO.StringIO()
        return self.run_watch_streaming(output_buffer, *args)

    def run_watch_streaming(self, output_buffer, *args):
        from .parse import run
        LOGGER.debug("Test running %r", args)
        run(self.direc, self.fake_time, output_buffer, args)
        return output_buffer.getvalue()

    def set_time(self, value):
        self.fake_time.set_time(value)

    def incr_time(self, incr):
        self.fake_time.incr_time(incr)

    def test_basic(self):
        self.assertEqual(self.run_watch(), "")
        self.set_time(5)
        self.assertEquals(self.run_watch(), "5.00\n")

    def test_stop(self):
        self.assertEqual(self.run_watch(), "")
        self.set_time(5)
        self.assertEquals(self.run_watch('stop'), "5.00\n")
        self.set_time(100)
        self.assertEquals(self.run_watch('show'), "5.00\n")
        self.set_time(105)
        self.assertEquals(self.run_watch('stop'), "5.00\n")
        self.assertEquals(self.run_watch('show'), "5.00\n")

        self.assertEqual(self.run_watch(), "")
        self.set_time(106)
        self.assertEquals(self.run_watch('show'), "1.00\n")

    def test_show(self):
        self.assertEquals(self.run_watch('show'), '')
        self.run_watch()
        self.set_time(1)
        self.assertEquals(self.run_watch('show'), '1.00\n')
        self.set_time(2)
        self.assertEquals(self.run_watch('show'), '2.00\n')
        self.assertEquals(self.run_watch(), '2.00\n')
        self.assertEquals(self.run_watch('show'), '2.00\n')

    def test_split(self):
        self.assertEquals(self.run_watch(), '')
        self.incr_time(1)
        self.assertEquals(self.run_watch('split'), '1.00\n')
        self.incr_time(2)
        self.assertEquals(self.run_watch('split', '--label', 'second'), '2.00\n')
        self.incr_time(1)
        self.assertEquals(self.run_watch('show'), '0 1.00\nsecond 2.00\n*2 1.00\n-----\ntotal 4.00\n')
        self.incr_time(1)
        self.run_watch('stop')
        self.incr_time(1)
        self.assertEquals(self.run_watch('show'), '0 1.00\nsecond 2.00\n2 2.00\n-----\ntotal 5.00\n')
        self.run_watch('start')
        self.incr_time(1)
        self.assertEquals(self.run_watch('show'), '1.00\n')

    def test_split_label(self):
        self.assertEquals(self.run_watch(), '')
        self.run_watch('label-split', 'one')
        self.incr_time(1)
        self.assertEquals(self.run_watch('show'), '*one 1.00\n-----\ntotal 1.00\n')
        self.run_watch('split')
        self.incr_time(1)
        self.assertEquals(self.run_watch('show'), 'one 1.00\n*1 1.00\n-----\ntotal 2.00\n')
        self.run_watch('split', '-l', 'two', '-n', 'three')
        self.assertEquals(self.run_watch('show'), 'one 1.00\ntwo 1.00\n*three 0.00\n-----\ntotal 2.00\n')

    def test_save(self):
        self.run_watch('start')
        self.incr_time(2)
        self.run_watch('stop')
        self.run_watch('save', 'saved-clock')
        self.run_watch('start')
        self.incr_time(1)
        self.run_watch('stop')
        self.run_watch('save', 'saved-clock', 'saved-clock-copy')
        self.assertEquals(self.run_watch('show'), '1.00\n')
        self.assertEquals(self.run_watch('show', 'saved-clock'), '2.00\n')
        self.assertEquals(self.run_watch('show', 'saved-clock-copy'), '2.00\n')

    def test_start_label(self):
        self.assertEquals(self.run_watch('start', '-n', 'one'), '')
        self.incr_time(1)
        self.assertEquals(self.run_watch('show'), '*one 1.00\n-----\ntotal 1.00\n')

    def test_json_duration(self):
        self.run_watch('start', 'new-clock')
        self.incr_time(1)
        self.run_watch('stop', 'new-clock')
        self.incr_time(1000)
        data = json.loads(self.run_watch('show', '--json', 'new-clock'))
        self.assertEquals(data['duration'], 1)

    def test_split_data(self):
        self.run_watch()
        self.run_watch('split-data', 'incline', '6')
        self.run_watch('split-data', 'foo', 'bar')
        self.incr_time(1)
        self.assertEquals(self.run_watch('show'), '*0 {"foo": "bar", "incline": "6"} 1.00\n-----\ntotal 1.00\n')

    def test_split_data2(self):
        self.run_watch()
        self.run_watch('split-data', '--json', '{"a": 1}', "b", "2")

        self.incr_time(1)
        self.assertEquals(self.run_watch('show'), '*0 {"a": 1, "b": "2"} 1.00\n-----\ntotal 1.00\n')

    def test_json(self):
        self.run_watch()
        self.incr_time(1)
        self.run_watch('split', '-n', 'split')
        self.assertEquals(self.run_watch('show', '--json'), '''{"duration": 1.0, "splits": [{"end": 1.0, "name": "0", "current": false, "start": 0.0, "duration": 1.0, "data": null}, {"end": null, "name": "split", "current": true, "start": 1.0, "duration": 0.0, "data": null}]}''')

    def test_start(self):
        self.run_watch('start')
        self.incr_time(1)
        self.run_watch('start')
        self.incr_time(1)
        self.assertEquals(self.run_watch('show'), '2.00\n')

    def test_abs_play(self):
        self.set_time(10)
        self.run_watch('start', 'run1', '-n', '1.0')
        self.set_time(11)
        self.run_watch('split', 'run1', '-n', '2.0')
        self.set_time(12)
        self.run_watch('split', 'run1', '-n', '3.0')
        self.set_time(15)
        self.run_watch('stop', 'run1')

        result = self.run_watch('play', 'run1', '--absolute')
        self.assertEqual(result, '10.0 1.0\n11.0 2.0\n12.0 3.0\n13.0 3.0\n14.0 3.0\n')

    def test_play_between(self):
        self.set_time(10)
        self.run_watch('start', 'run1', '-n', '1.0')
        self.set_time(11)
        self.run_watch('split', 'run1', '-n', '2.0')
        self.set_time(12)
        self.run_watch('split', 'run1', '-n', '3.0')
        self.set_time(13)
        self.run_watch('split', 'run1', '-n', '4.0')
        self.set_time(14)
        self.run_watch('stop', 'run1')
        result = self.run_watch('play', 'run1', '--before', '3.0', '--after', '1.0')
        self.assertEqual(result, '1.0 2.0\n2.0 3.0\n3.0 4.0\n')

    def test_zodb(self):
        from . import zodb
        data_file = os.path.join(self.direc, 'test_data')

        with zodb.with_data(data_file) as data:
            data['a'] = 1
            data.setdefault('b', 2)
            data.setdefault('b', 3)
            dictionary = data.setdefault('dict', dict())
            dictionary['value'] = 5
            lst = data.setdefault('list', [])
            lst.append('hello')
            lst.append('world')

        with zodb.with_data(data_file) as data:
            self.assertEquals(data['a'], 1)
            self.assertEquals(data['b'], 2)
            self.assertEquals(data['dict']['value'], 5)
            self.assertEquals(data['list'], ["hello", "world"])

    def test_jsondb(self):
        from . import json_backend
        data_file = os.path.join(self.direc, 'test_data')

        with json_backend.with_data(data_file) as data:
            data['a'] = 1
            data.setdefault('b', 2)
            data.setdefault('b', 3)
            dictionary = data.setdefault('dict', dict())
            dictionary['value'] = 5
            lst = data.setdefault('list', [])
            lst.append('hello')
            lst.append('world')

        with json_backend.with_data(data_file) as data:
            self.assertEquals(data['a'], 1)
            self.assertEquals(data['b'], 2)
            self.assertEquals(data['dict']['value'], 5)
            self.assertEquals(data['list'], ["hello", "world"])

    def test_export_all(self):
        self.set_time(0)
        self.run_watch('start', 'run1')
        self.set_time(2)
        self.run_watch('stop', 'run1')

        dump = self.run_watch('show', 'run1')

        data = self.run_watch('export-all')
        self.run_watch('delete', 'run1')

        export_file = os.path.join(self.direc, 'export-dump.json')
        with open(export_file, 'w') as stream:
             stream.write(data)

        self.run_watch('import-all', export_file)
        self.assertEquals(self.run_watch('show', 'run1'), dump)


    def test_player(self):
        self.set_time(0)
        self.run_watch('start', 'run1', '-n', '1.0')
        self.set_time(2)
        self.run_watch('split', 'run1', '-n', '2.0')
        self.set_time(4)
        self.run_watch('split', 'run1', '-n', '3.0')
        self.set_time(6)
        self.run_watch('stop', 'run1')

        self.set_time(10)
        self.run_watch('start', 'run2', '-n', '10.0')
        self.set_time(11)
        self.run_watch('split', 'run2', '-n', '20.0')
        self.set_time(12.5)

        def get_lines():
            return buff.getvalue().splitlines()

        INITIAL_EXPECTED = [
                '0.0 1.0 10.0',
                '1.0 1.0 20.0',
                '2.0 2.0 20.0'
                ]

        buff = StringIO.StringIO()
        spawn(self.run_watch_streaming, buff, 'play', 'run1', 'run2')
        self.wait_for_value(get_lines, INITIAL_EXPECTED)

        self.set_time(14.1) #

        self.wait_for_value(lambda: len(get_lines()), 5)
        self.assertEquals(get_lines()[-2:], ['3.0 2.0 20.0', '4.0 3.0 20.0'])
        self.set_time(14.9) #
        self.run_watch('split', 'run2', '-n', '30.0')
        self.set_time(15.2)
        self.wait_for_value(lambda: len(get_lines()), 6)
        self.assertEquals(get_lines()[-1], '5.0 3.0 30.0')

    def wait_for_value(self, thunk, value):
        for _ in range(10):
            time.sleep(0.01)
            last_value = thunk()
            if last_value == value:
                break
        else:
            self.assertEquals(last_value, value)

# Utility functions
class FakeTime(object):
    def __init__(self):
        self._time = 0.0
        self._lock = threading.RLock()
        self._tick_events = []
        self._logger = logging.getLogger('FakeTime')

    def time(self):
        return self._time

    def set_time(self, value):
        with self._lock:
            self._time = value
            self._logger.debug('Set time to %r', value)
            self._tick()

    def incr_time(self, incr):
        with self._lock:
            self.set_time(self._time + incr)

    def _tick(self):
        for expiry, event in self._tick_events[:]:
            if self._time > expiry:
                self._logger.debug('Expiring %r', self._time)
                self._tick_events.remove((expiry, event))
                event.set()

    def sleep(self, delay):
        self._logger.debug('Sleeping for %r at %r', delay, self._time)
        event = threading.Event()
        with self._lock:
            start_time = self._time
            expiry = self._time + delay
            self._tick_events.append((expiry, event))
        event.wait()
        self._logger.debug('Sleep started at %r for %r expired', start_time, delay)

def spawn(f, *args, **kwargs):
	thread = threading.Thread(target=f, args=args, kwargs=kwargs)
	thread.setDaemon(True)
	thread.start()
	return thread
