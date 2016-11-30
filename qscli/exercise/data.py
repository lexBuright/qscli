import contextlib
import copy
import datetime
import json
import os
import time

import fasteners

from . import const, counter, scorer, watch

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
        return sorted(exercises)

    @staticmethod
    def set_current_endurance_settings(settings):
        with with_data(DATA_FILE) as data:
            data['current_endurance_settings'] = settings

    @staticmethod
    def get_current_endurance_settings():
        with with_data(DATA_FILE) as data:
            return data['current_endurance_settings']

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
    def get_endurance_weight(exercise):
        with with_data(DATA_FILE) as data:
            weights = data.setdefault('endurance_weights', {})
            return weights.get(exercise, 0)


    @staticmethod
    def set_endurance_weight(exercise, score):
        with with_data(DATA_FILE) as data:
            weights = data.setdefault('endurance_weights', {})
            weights[exercise] = score

    @staticmethod
    def get_endurance_settings(exercise):
        with with_data(DATA_FILE) as data:
            settings = data.setdefault('endurance_settings', {})
            return settings.get(exercise)


    @staticmethod
    def set_endurance_settings(exercise, settings):
        with with_data(DATA_FILE) as data:
            endurance_settings = data.setdefault('endurance_settings', {})
            endurance_settings[exercise] = settings



    @staticmethod
    def get_endurance_weights():
        with with_data(DATA_FILE) as data:
            weights = data.setdefault('endurance_weights', {})
            weights = weights.copy()
            for exercise in Data.get_endurance_exercises():
                weights.setdefault(exercise, None)
            return weights

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
    def get_interval_exercises():
        return [x.split('.', 2)[2] for x in SCORER.get().run(['list']).splitlines() if x.startswith('exercise.interval.')]

    @staticmethod
    def get_interval_exercise():
        with with_data(DATA_FILE) as data:
            return data['interval_exercise']

    @staticmethod
    def get_interval_incline():
        with with_data(DATA_FILE) as data:
            return data['interval_incline']

    @staticmethod
    def get_interval_speed():
        with with_data(DATA_FILE) as data:
            return data['interval_speed']

    @staticmethod
    def set_interval_exercise(exercise):
        with with_data(DATA_FILE) as data:
            data['interval_exercise'] = exercise

    @staticmethod
    def set_interval_frontier_point(value):
        with with_data(DATA_FILE) as data:
            data['interval_frontier'] = value

    @staticmethod
    def get_interval_frontier_point():
        with with_data(DATA_FILE) as data:
            return data['interval_frontier']

    @staticmethod
    def set_interval_incline(incline):
        with with_data(DATA_FILE) as data:
            data['interval_incline'] = incline

    @staticmethod
    def set_interval_speed(speed):
        with with_data(DATA_FILE) as data:
            data['interval_speed'] = speed

    @staticmethod
    def set_interval_active(active):
        with with_data(DATA_FILE) as data:
            data['interval_active'] = active


    @staticmethod
    def get_interval_active():
        with with_data(DATA_FILE) as data:
            return data['interval_active']

    @staticmethod
    def set_interval_rest(resting):
        with with_data(DATA_FILE) as data:
            data['interval_rest'] = resting

    @staticmethod
    def get_interval_rest():
        with with_data(DATA_FILE) as data:
            return data['interval_rest']

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
    def get_current_notes():
        with with_data(DATA_FILE) as data:
            return data.get('notes', [''])[-1]

    @staticmethod
    def set_current_notes(notes):
        with with_data(DATA_FILE) as data:
            notes_store = data.setdefault('notes', list())
            notes_store.append(notes)

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

    @staticmethod
    def get_last_report():
        with with_data(DATA_FILE) as data:
            return data.get('last_report', None)

    @staticmethod
    def set_last_report(name):
        with with_data(DATA_FILE) as data:
            data['last_report'] = name

    @staticmethod
    def set_heart_rate_targetter(guid):
        with with_data(DATA_FILE) as data:
            data['heart.targeter'] = guid

    @staticmethod
    def get_heart_rate_targetter():
        with with_data(DATA_FILE) as data:
            return data['heart.targeter']

    @staticmethod
    def get_heart_multiplier():
        with with_data(DATA_FILE) as data:
            return data.get('heart.multiplier', 1.0)

    @staticmethod
    def get_heart_poll_period():
        with with_data(DATA_FILE) as data:
            return data.get('heart.poll_period')
    @staticmethod
    def set_heart_poll_period(period):
        with with_data(DATA_FILE) as data:
            data['heart.poll_period'] = period

    @staticmethod
    def get_heart_target_period():
        with with_data(DATA_FILE) as data:
            return data.get('heart.target_period')
    @staticmethod
    def set_heart_target_period(period):
        with with_data(DATA_FILE) as data:
            data['heart.target_period'] = period

    @staticmethod
    def set_heart_multiplier(multiplier):
        with with_data(DATA_FILE) as data:
            data['heart.multiplier'] = multiplier

    @staticmethod
    def set_heart_reading_delay(delay):
        with with_data(DATA_FILE) as data:
            data['heart.delay'] = delay

    @staticmethod
    def get_heart_reading_delay(delay):
        with with_data(DATA_FILE) as data:
            return data.get('heart.delay')



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
WATCH = ClientCache(watch.Watch)
