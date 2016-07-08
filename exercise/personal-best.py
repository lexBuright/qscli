import argparse
import contextlib
import copy
import datetime
import json
import os.path
import time

import fasteners

import blocks
import walking


class PersonalBestTracker(object):
    HORIZON = 4
    def __init__(self, get_after, storer):
        self.get_after = get_after
        self.storer = storer

    def update(self):
        with self.storer:
            last_updated = datetime.datetime.fromtimestamp(
                self.storer.get('last_updated', time.time() - self.HORIZON * 86400))
            best, best_start = self.storer.get('last_best', None), self.storer.get('last_best_start', None)
            for start, value in self.get_after(last_updated):
                if best is None or value > best:
                    best = value
                    best_start = start

            if best:
                self.storer['last_best'] = best

            if best_start:
                self.storer['last_best_start'] = time.mktime(best_start.timetuple()) + best_start.microsecond * 1.0e-6

            if best_start:
                self.storer['last_updated'] = time.mktime(start.timetuple()) + start.microsecond * 1.0e-6

            return best, best_start

    def get(self):
        with self.storer:
            best, best_id = self.storer['last_best'], self.storer['last_best_id']
            return best, best_id

PARSER = argparse.ArgumentParser(description='')
parsers = PARSER.add_subparsers(dest='action')
parsers.add_parser('five', help='Distance travelled in a five minute period')
args = PARSER.parse_args()

def read_json(filename):
    if os.path.exists(filename):
        with open(filename) as stream:
            return json.loads(stream.read())
    else:
        return dict()

@contextlib.contextmanager
def with_data(data_file):
    "Read from a json file, write back to it when we are finished"
    with fasteners.InterProcessLock(data_file + '.lck'):
        data = read_json(data_file)
        data_before = copy.deepcopy(data)
        yield data
        # Try to crash before overwritting the file
        output_data = json.dumps(data)

        with open(data_file, 'w') as stream:
            stream.write(output_data)

class BestStorer(object):
    "Store for personal bests"
    def __init__(self, name):
        self.with_data = None
        self.data = None

    def __enter__(self):
        self.with_data = with_data(DATA_FILE)
        self.data = self.with_data.__enter__()

    def __setitem__(self, key, value):
        bests = self.data.setdefault('bests', dict())
        bests[key] = value

    def __getitem__(self, key):
        bests = self.data.get('bests', dict())
        return bests[key]

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def __exit__(self, *args):
        self.with_data.__exit__(*args)
        self.with_data = None
        self.data = None

def get_blocks_after(after):
    after_unix = time.mktime(after.timetuple()) + after.microsecond * 1.0e-6

    day = after.date()
    while day < datetime.date.today():
        for start, end, speed in walking.get_time_blocks(day):
            if end > after_unix:
                continue
            else:
                new_start = max(after_unix, start)
                assert end > new_start
                yield new_start, end, speed
        day += datetime.timedelta(days=1)


def get_distance_travelled(after, period):
    blocks_after = list(get_blocks_after(after))
    for period_block in blocks.period_windows(blocks_after, period):
        if not period_block:
            continue
        start, _end, _speed = period_block[0]
        start_dt = datetime.datetime.fromtimestamp(start)
        import pdb; pdb.set_trace()    #XXX
        yield start_dt, sum((block_end - block_start) * float(block_speed) for block_start, block_end, block_speed in period_block)

DATA_DIR =  os.path.join(os.environ['HOME'], '.config', 'personal-best')
if not os.path.isdir(DATA_DIR):
   os.mkdir(DATA_DIR)

DATA_FILE = os.path.join(DATA_DIR, 'data')


if args.action == 'five':
    storer = BestStorer('five')
    getter = lambda after: get_distance_travelled(after, 300)
    print PersonalBestTracker(getter, storer).update()
