"""Store data in a simple json file

This is useful for debugging / readability, but becomes slow with large amounts of data
"""

import contextlib
import json
import os
import threading

import fasteners

DATA_FILE = 'superwatch.json'

def read_json(filename):
    if os.path.exists(filename):
        with open(filename) as stream:
            return json.loads(stream.read())
    else:
        return dict()


DATA_LOCK = threading.Lock()

@contextlib.contextmanager
def with_data(data_file):
    "Read from a json file, write back to it when we are finished"
    with fasteners.InterProcessLock(data_file + '.lck'):
        with DATA_LOCK:
            data = read_json(data_file)
            yield data

            output = json.dumps(data)
            with open(data_file, 'w') as stream:
                stream.write(output)

def new_list(lst=None):
    lst = lst or []
    return list(lst)

def new_dict(dct=None):
    dct = dct or dict()
    return dict(dct)

def json_dumps(item):
    return json.dumps(item)

def json_loads(string):
    return json.loads(string)
