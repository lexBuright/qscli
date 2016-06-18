import argparse

class PersonalBestTracker(object):
    def __init__(self, get_after, storer):
        self.get_after = get_after
        self.storer = storer

    def update(self):
        with self.storer:
            best, best_id = self.storer['last_best'], self.storer['last_best_id']
            now = datetime.datetime.now()
            for value_id, value in self.get_after(now):
                if value > best:
                    best = value
                    best_id = value_id
            self.storer['last_best'] = best
            self.storer['last_best_id'] = best_id
            return best, best_id

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

    def __exit__(self, *args):
        self.with_data.__exit__(*args)
        self.with_data = None
        self.data = None

def get_blocks_after(after):
    for start, speed, duration in walking.get_time_blocks(datetime.datetime.fromtimestamp(after).date()):
        end = start + duration
        if end > after_unix:
            continue
        else:
            new_start = max(after, start)
            yield new_start, speed, end - new_start

def period_align_blocks(blocks, period):
    for start, speed, duration in blocks:

def get_distance_travelled(after, period):
    # These should be deques

    block_starts = list()
    block_speeds = list()
    for start, speed, duration in get_blocks_after(after):
        end = start + duration
        if not block_starts:
            block_starts.append(start)
            block_speeds.append(speed)
            continue
        if end - block_starts[0] > period:
            block_end = block
            yield start, calculate_distance(block_starts, block_ends + , block_speeds + [speed])

if args.action == 'five':
    storer = BestStorer('five')
    PersonalBestTracker(storer
