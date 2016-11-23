"Code related to playing back recipes"

import contextlib
import itertools
import logging
import time

from . import data
from . import history

LOGGER = logging.getLogger('playback')

class Player(object):
    def __init__(self, data_path, poll_period, recipe_name, error_keep, multiplier, name=None):
        self._data_path = data_path
        self._name = name or recipe_name
        self._poll_period = poll_period
        self._recipe_name = recipe_name
        self._error_keep = error_keep
        self._multiplier = multiplier

    def play(self):
        # If you change the recipe under me you are
        #    a terrible human being
        recipe = self.start_playing()

        try:
            step_start = time.time()
            for index, next_step in enumerate(recipe['steps']):
                next_step['skipped'] = False
                next_step['index'] = index
                next_step['abandoned_at'] = None
                next_step['notes'] = []
                next_step['finished'] = False

                step_start = step_start + next_step['start_offset'] / self._multiplier
                try:
                    LOGGER.debug('Waiting for something to happen...')
                    self.wait_until(step_start)
                except (SkippedStep, AbandonedStep) as ex:
                    LOGGER.debug('Step skipped or abanadoned %r', ex)
                except AbandonRecipe:
                    break

                next_step['started_at'] = time.time()


                LOGGER.debug('Setting step %r', next_step['text'])
                self.next_step(next_step)
                print next_step['text']
                del next_step

            with data.with_data(self._data_path) as app_data:
                stop(app_data, self._name, False)
        except:
            if not self._error_keep:
                with data.with_data(self._data_path) as app_data:
                    stop(app_data, self._name, False)
            raise

    def store_recipe(self, recipe):
        with self.with_playback_data() as playback_data:
            playback_data['recipe'] = recipe

    @contextlib.contextmanager
    def with_playback_data(self):
        with data.with_data(self._data_path) as app_data:
            yield app_data['playbacks'].setdefault(self._name, dict(name=self._name))

    @contextlib.contextmanager
    def with_current_step(self):
        with self.with_playback_data() as playback_data:
            yield playback_data['step']

    def record_step(self, step, duration=None, skipped=None):
        with self.with_playback_data() as playback_data:
            stored_step = step.copy()
            stored_step['started_at'] = time.time()
            if duration is not None:
                stored_step['duration'] = duration
            if skipped is not None:
                stored_step['skipped'] = skipped
            playback_data['step'] = stored_step

    def next_step(self, next_step):
        with self.with_playback_data() as playback_data:
            old_step = playback_data.get('step', None)
            if old_step:
                playback_data.setdefault('steps', [])
                playback_data['steps'].append(old_step)
            next_step['duration'] = data.step_duration(playback_data['recipe'], next_step['index'])
            playback_data['step'] = next_step

    def start_playing(self):
        with data.with_data(self._data_path) as app_data:
            playbacks = app_data.setdefault('playbacks', {})
            if self._name in playbacks:
                raise Exception('There is a already a player called {}. Use a different name'.format(self._name))

            with data.with_recipe(app_data, self._recipe_name) as recipe:
                playbacks[self._name] = dict(
                    start=time.time(),
                    step=None,
                    steps=[],
                    recipe=recipe,
                    name=self._name,
                    recipe_name=self._recipe_name)
                return recipe

    def wait_until(self, step_start):
        while time.time() < step_start:
            sleep_period = min(max(step_start - time.time(), 0), self._poll_period)
            time.sleep(sleep_period)
            with data.with_data(self._data_path) as app_data:
                if self._name not in app_data['playbacks']:
                    raise AbandonRecipe()
                else:
                    playback_data = app_data['playbacks'][self._name]
                    if playback_data['step']['skipped']:
                        raise SkippedStep()
                    elif playback_data['step']['abandoned_at'] is not None:
                        raise AbandonedStep()

        with self.with_playback_data() as playback_data:
            if playback_data['step'] is not None:
                playback_data['step']['finished'] = True

class SkippedStep(Exception):
    "Current step was skipped"

class AbandonRecipe(Exception):
    "Current recipe is abandoned"

class AbandonedStep(Exception):
    """Abandon the current step after it was started"""

def stop(app_data, playback, error=True):
    app_data.setdefault('past_playbacks', dict())

    if not error:
        if playback not in app_data['playbacks']:
            return

    if playback in app_data['playbacks']:
        playback_data = app_data['playbacks'][playback].copy()
        playback_data['id'] = time.time()
        for i in itertools.count(1):
            save_name = '{}-{}'.format(playback_data['name'], i)
            if save_name not in app_data['past_playbacks']:
                break

        app_data['past_playbacks'][save_name] = playback_data


    app_data['playbacks'].pop(playback)

def playback_status(app_data, playback, verbose):
    if not verbose:
        playing_step = app_data['playbacks'][playback]['step']
        progress = time.time() - playing_step['started_at']
        duration = playing_step['duration']
        percent_progress = float(progress) / playing_step['duration'] * 100
        return '{:.0f}s/{:.0f}s ({:.0f}%) {}'.format(progress, duration, percent_progress, playing_step['text'])
    else:
        history.display_full_playback(app_data['playbacks'][playback])

def skip_step(app_data, playback):
    playback_data = app_data['playbacks'][playback]
    playback_data['step']['skipped'] = True

def abandon_step(app_data, playback):
    playback_data = app_data['playbacks'][playback]
    playback_data['step']['abandoned_at'] = time.time()
