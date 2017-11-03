"Scores associated with key-value-pair sets"

import collections
import json
import re


class DictScorer(object):
    def __init__(self, scorer, prefix):
        self._scorer = scorer
        self._prefix = prefix

    def update(self, d, v):
        path = self._dict_path(d)
        self._scorer.run(['update', path, str(v)])

    def store(self, d, v):
        path = self._dict_path(d)
        self._scorer.run(['store', path, '0'])

    def summary(self, d):
        path = self._dict_path(d)
        return self._scorer.run(['summary', path])

    def _dict_path(self, d):
        path = self._prefix.rstrip('.')
        for key, value in sorted(d.items()):
            # This is a bit icky...
            encoded_value = str(value).replace(',', '.')
            encoded_key = str(key).replace(',', '.')
            path += '.' + encoded_key + ':' + encoded_value
        return path

    def all_scores(self):
        records = json.loads(self._scorer.run(['log', '--regex', '^' + re.escape(self._prefix), '--json']))
        for record in records:
            settings = self._parse_settings(record['metric'])
            yield Score(time=record['time'], value=record['value'], settings=settings)

    def _parse_settings(self, name):
        if not name.startswith(self._prefix):
            raise Exception('Name does not start with prefix {!r} {!r}'.format(self._prefix, name))

        settings = dict()
        for pair_string in name[len(self._prefix):].split('.'):
            pair_string.split(':')
            print pair_string
        return settings


Score = collections.namedtuple('Score', 'time value settings')
