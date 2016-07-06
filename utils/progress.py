#!/usr/bin/python
import argparse
import contextlib
import copy
import json
import logging
import os.path
import sys
import time

import fasteners

LOGGER = logging.getLogger()

PARSER = argparse.ArgumentParser(description='Command line tool to keep track of progress')
PARSER.add_argument('name', type=str, help='Name of the task that we are tracking')
PARSER.add_argument('progress', type=float, help='Progress')

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

DATA_DIR =  os.path.join(os.environ['HOME'], '.config', 'progress')
if not os.path.isdir(DATA_DIR):
    os.mkdir(DATA_DIR)

DATA_FILE = os.path.join(DATA_DIR, 'data.json')

def main():
    args = PARSER.parse_args()
    with with_data(DATA_FILE) as data:
        targets = data.setdefault('targets', {})
        starts = data.setdefault('starts', {})
        if not args.name in targets:
            targets[args.name] = args.progress
            starts[args.name] = time.time()
        else:

            targets[args.name] = max(targets[args.name], args.progress)

            remaining = args.progress / targets[args.name]
            done = 1 - remaining

            time_taken = time.time() - starts[args.name]
            time_remaining = time_taken * remaining / done
            total_time = time_taken + time_remaining

            sys.stderr.write('{:.2f} taken:{:.2f} estimate:{:.2f}'.format(done, time_taken, time_remaining))
if __name__ == '__main__':
	main()
