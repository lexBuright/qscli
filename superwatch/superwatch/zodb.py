"""Interact with zodb object graph store

ZODB is probably bad for big amounts of data and broad interfaces
to your data. But for our current use case it allows us to
keep data in a json'y form. This is useful because we want to be
able to talk json to clients

"""


import contextlib
import json

import fasteners
import persistent.list
import persistent.mapping
import transaction
import ZODB.FileStorage

def new_list(base=None):
    base = base or []
    return persistent.list.PersistentList(base)

def new_dict(base=None):
    base = base or dict()
    return persistent.mapping.PersistentMapping(base)


class ZODBJsonEncoder(json.JSONEncoder):
    """Encode a ZODB object graph to json (deals with PersistentMapping and PersistentList)"""
    def default(self, o):
        if isinstance(o, persistent.list.PersistentList):
            return list(o)
        elif isinstance(o, persistent.mapping.PersistentMapping):
            return dict(o)
        else:
            return json.JSONEncoder.default(self, o)

def _zodb_json_object_hook(input_dict):
    d = input_dict.copy()

    for k in list(d.keys()):
        if isinstance(d[k], list):
            d[k] = persistent.list.PersistentList(d[k])
    result = persistent.mapping.PersistentMapping(d)
    return result

JSON_DECODER = json.JSONDecoder(object_hook=_zodb_json_object_hook)
JSON_ENCODER = ZODBJsonEncoder()

def json_dumps(obj):
    return ZODBJsonEncoder().encode(obj)

def json_loads(string):
    return ZODB_JSON_DECODER.decode(string)

@contextlib.contextmanager
def with_data(data_file):
    """Open a zodb database, yield the root note, and commit when done"""
    # for simplicity / access from different processes
    with fasteners.InterProcessLock(data_file + '.lck'):
        db = ZODB.DB(ZODB.FileStorage.FileStorage(data_file))
        connection = db.open()
        try:
            root = connection.root()
            yield root
            transaction.get().commit()
        except:
            transaction.get().abort()
            raise
        finally:
            connection.close()
            db.close()
