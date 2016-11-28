"Code related to playing back recipes"

import contextlib
import itertools
import logging
import time

from . import data
from . import history

LOGGER = logging.getLogger('playback')

class Player(object):
    def __init__(self, data_path, poll_period, recipe_name, error_keep, multiplier, name=None, dry_run=False):
        self._data_path = data_path
        self._name = name or recipe_name
        self._poll_period = poll_period
        self._recipe_name = recipe_name
        self._error_keep = error_keep
        self._multiplier = multiplier
        self._dry_run = dry_run
        self._current_delay = None

    @staticmethod
    def _initialize_step(index, next_step):
        next_step['skipped'] = False
        next_step['index'] = index
        next_step['abandoned_at'] = None
        next_step['notes'] = []
        next_step['finished'] = False
        next_step['delays'] = []

    def play(self):
        # If you change the recipe under me you are
        #    a terrible human being
        recipe = self.start_playing()
        recipe_finished = False

        try:
            step_start = time.time()
            for index, next_step in enumerate(recipe['steps']):
                self._initialize_step(index, next_step)


                step_start = step_start + next_step['start_offset'] / self._multiplier
                while True:
                    try:
                        LOGGER.debug('Waiting for something to happen or %r...', step_start - time.time())
                        self.wait_until(step_start)
                    except (SkippedStep, AbandonedStep) as ex:
                        LOGGER.debug('Step skipped or abanadoned %r', ex)
                        break
                    except DelayedStep as ex:
                        LOGGER.debug('Step delayed')
                        step_start = ex.end_time
                    except AbandonRecipe:
                        recipe_finished = True
                        break
                    else:
                        LOGGER.debug('Next step reached %r', next_step)
                        break

                if recipe_finished:
                    LOGGER.debug('Recipe finished')
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
            yield app_data['playbacks'][self._name]

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
            all_recipes = app_data.setdefault('all_recipes', {})

            if self._name in playbacks:
                raise Exception('There is a already a player called {}. Use a different name'.format(self._name))

            with data.with_recipe(app_data, self._recipe_name) as recipe:
                all_recipes[recipe['content_id']] = recipe
                playbacks[self._name] = dict(
                    start=time.time(),
                    step=None,
                    dry_run=self._dry_run,
                    steps=[],
                    recipe=recipe,
                    name=self._name,
                    recipe_name=self._recipe_name)
                return recipe

    def wait_until(self, step_start):
        while time.time() < step_start:
            time_left = max(step_start - time.time(), 0)
            sleep_period = min(time_left, self._poll_period)
            LOGGER.debug('Waiting %.1f for next poll (time left: %.1f)...', sleep_period, time_left)
            time.sleep(sleep_period)
            LOGGER.debug('Polling for event...')
            with data.with_data(self._data_path) as app_data:
                if self._name not in app_data['playbacks']:
                    raise AbandonRecipe()
                else:
                    playback_data = app_data['playbacks'][self._name]
                    if playback_data['step']['skipped']:
                        raise SkippedStep()
                    elif playback_data['step']['abandoned_at'] is not None:
                        raise AbandonedStep()
                    elif playback_data['step']['delays']:
                        delay = playback_data['step']['delays'][-1]
                        if delay != self._current_delay:
                            self._current_delay = delay
                            raise DelayedStep(delay['end_time'])

        with self.with_playback_data() as playback_data:
            if playback_data['step'] is not None:
                playback_data['step']['finished'] = True

class SkippedStep(Exception):
    "Current step was skipped"

class DelayedStep(Exception):
    "Current step was skipped"
    def __init__(self, end_time):
        self.end_time = end_time

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

        if not playback_data['dry_run']:
            app_data['past_playbacks'][save_name] = playback_data
    app_data['playbacks'].pop(playback)

def playback_status(app_data, playback, verbose):
    if not verbose:
        playing_step = app_data['playbacks'][playback]['step']

        if playing_step['delays']:
            last_delay = playing_step['delays'][-1]
            delay_until = last_delay['end_time']
            delay_reason = last_delay['reason']
        else:
            delay_until = None


        duration = playing_step['duration']

        if delay_until and time.time() < delay_until:
            relative_delay = delay_until - time.time()
            return 'DELAYED FOR {:.0f}s BECAUSE {}: {} {}'.format(relative_delay, delay_reason, duration, playing_step['text'])
        else:
            progress = time.time() - (delay_until or playing_step['started_at'])
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

def delay_step(app_data, playback, seconds, reason):
    playback_data = app_data['playbacks'][playback]
    playback_data['step']['delays'].append(dict(end_time=time.time() + seconds, reason=reason))
