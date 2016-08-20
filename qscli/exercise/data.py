import contextlib
import copy
import datetime
import json
import os
import time

import fasteners

from . import const, counter, scorer

DATA_DIR =  os.path.join(os.environ['HOME'], '.config', 'exercise-track')
if not os.path.isdir(DATA_DIR):
    os.mkdir(DATA_DIR)

DATA_FILE = os.path.join(DATA_DIR, 'data')

class ClientCache(object):
    def __init__(self, Client):
        self._Client = Client
        self._instance = None

    def get(self):
        if self._instance is None:
            self._instance = self._Client()
            self._instance.initialize()
        return self._instance

class Data(object):
    @staticmethod
    def get_rep_exercises(days_ago=None):
        if days_ago is not None:
            counters = COUNTER.get().run(['list', '--days-ago', str(days_ago)]).splitlines()
        else:
            counters = COUNTER.get().run(['list']).splitlines()

        exercises = [x.split('.', 1)[1]
            for x in counters if x.startswith('exercise.')]
        return exercises

    @staticmethod
    def set_endurance_exercise(exercise):
        with with_data(DATA_FILE) as data:
            data['endurance_exercise'] = exercise

    @staticmethod
    def set_rep_exercise(exercise):
        with with_data(DATA_FILE) as data:
            data['rep_exercise'] = exercise

    @staticmethod
    def get_rep_exercise():
        with with_data(DATA_FILE) as data:
            return data['rep_exercise']

    @staticmethod
    def get_endurance_exercise(default=const.MISSING):
        with with_data(DATA_FILE) as data:
            if default != const.MISSING:
                return data.get('endurance_exercise', default)
            else:
                return data['endurance_exercise']

    @staticmethod
    def get_endurance_scores(days_ago):
        data = json.loads(SCORER.get().run(['log', '--regex', '^exercise\\.endurance\\.', '--days-ago', str(days_ago), '--json']))
        data = [dict(metric=entry['metric'], value=entry['value'], time=entry['time']) for entry in data]
        return EnduranceScores(data)

    @staticmethod
    def get_exercise_scores():
        with with_data(DATA_FILE) as data:
            return {k: ScoreTimeSeries(v) for (k, v) in data.get('rep.scores.by.exercise', {}).items()}

    @staticmethod
    def get_endurance_exercises():
        return [x.split('.', 2)[2] for x in SCORER.get().run(['list']).splitlines() if x.startswith('exercise.endurance.')]

    @staticmethod
    def get_endurance_results(days_ago):
        pass

    @staticmethod
    def get_score_exercises():
        return [x.split('.', 1)[1] for x in SCORER.get().run(['list']).splitlines() if x.startswith('exercise.')]

    @staticmethod
    def set_exercise_score(exercise, score):
        with with_data(DATA_FILE) as data:
            by_exercise_scores = data.setdefault('rep.scores.by.exercise', {})
            exercise_scores = by_exercise_scores.setdefault(exercise, [])
            exercise_scores.append((time.time(), score))

    @staticmethod
    def get_to_ignore():
        with with_data(DATA_FILE) as data:
            ignore_date = data.get('versus.rep.ignore.date')
            ignore_date = ignore_date and datetime.date(*ignore_date)

            if ignore_date == datetime.date.today():
                return data.get('versus.rep.ignore', [])
            else:
                return []

    @staticmethod
    def set_to_ignore(ignore_list):
        with with_data(DATA_FILE) as data:
            today = datetime.date.today()
            data['versus.rep.ignore'] = ignore_list
            data['versus.rep.ignore.date'] = [today.year, today.month, today.day]

    @staticmethod
    def get_exercise_counts(days_ago):
        data = json.loads(COUNTER.get().run([
            'summary',
            '--days-ago',
            str(days_ago),
            '--json']))

        return [
            dict_replace(x, name=x['name'].split('.', 1)[1]) for x in data['counts'] if x['name'].startswith('exercise.')]

    @staticmethod
    def get_versus_days_ago():
        with with_data(DATA_FILE) as data:
            return data.get('versus_days', 1)

    @staticmethod
    def set_versus_days_ago(days_ago):
        with with_data(DATA_FILE) as data:
            data['versus_days'] = days_ago

    @staticmethod
    def incr_versus_days_ago(incr):
        with with_data(DATA_FILE) as data:
            data['versus_days'] = data.get('versus_days', 1) + incr



def dict_replace(dict_, **kwargs):
    updated = copy.copy(dict_)
    for key, value in kwargs.items():
        updated[key] = value
    return updated

@contextlib.contextmanager
def with_data(data_file):
    "Read from a json file, write back to it when we are finished"
    with fasteners.InterProcessLock(data_file + '.lck'):
        data = read_json(data_file)
        yield data
        output_data = json.dumps(data)

        with open(data_file, 'w') as stream:
            stream.write(output_data)

class EnduranceScores(object):
    def __init__(self, scores):
        self._scores = scores

    def num_types(self):
        return len(set(score['metric'] for score in self._scores))

    def total_seconds(self):
        return sum(score['value'] for score in self._scores)

    def by_exercise(self):
        result = dict()
        for score in self._scores:
            metric_dict = result.setdefault(score['metric'], dict())
            metric_dict['total_seconds'] = metric_dict.get('total_seconds', 0) + score['value']
            metric_dict.setdefault('values', list()).append(score['value'])

        for key in result:
            result[key]['values'].sort()

        return result

class ScoreTimeSeries(object):
    def __init__(self, time_series):
        self.time_series = time_series

    def last_value(self):
        return self.time_series[-1][1]

def read_json(filename):
    if os.path.exists(filename):
        with open(filename) as stream:
            return json.loads(stream.read())
    else:
        return dict()

COUNTER = ClientCache(counter.Counter)
SCORER = ClientCache(scorer.Scorer)
