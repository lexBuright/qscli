"""Store data in a jsdb database

This should have reasonable performance. `json_backend` is better for debugability.

"""

import contextlib
import json
import threading

import fasteners

import jsdb
import jsdb.python_copy

DATA_FILE = 'superwatch.jsdb'
DATA_LOCK = threading.Lock()

@contextlib.contextmanager
def with_data(data_file):
    "Read from a json file, write back to it when we are finished"
    with fasteners.InterProcessLock(data_file + '.lck'):
        #with DATA_LOCK:
        db = jsdb.Jsdb(data_file)
        try:
            yield db
        except:
            db.rollback()
            raise
        else:
            db.commit()
        finally:
            db.close()


def new_list(lst=None):
    lst = lst or []
    return list(lst)

def new_dict(dct=None):
    dct = dct or dict()
    return dict(dct)

def json_dumps(item):
    return json.dumps(jsdb.python_copy.copy(item))

def json_loads(string):
    return json.loads(string)

def deep_copy(item):
    return jsdb.python_copy.copy(item)
