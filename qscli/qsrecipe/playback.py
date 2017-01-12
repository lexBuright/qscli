"Code related to playing back recipes"

import contextlib
import itertools
import logging
import time

from . import data, history
from .. import os_utils

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
    def _initialize_step(index, next_step, recipe):
        next_step['finished_early'] = False
        next_step['skipped'] = False
        next_step['index'] = index
        next_step['abandoned_at'] = None
        next_step['notes'] = []
        next_step['finished'] = False
        next_step['delays'] = []
        next_step['duration'] = data.step_duration(recipe, next_step['index'])

    def _play_step(self, step_duration):
        step_start = time.time() + step_duration / self._multiplier
        while True:
            try:
                LOGGER.debug('Waiting for something to happen or %r...', step_start - time.time())
                self.wait_until(step_start)
            except DelayedStep as ex:
                LOGGER.debug('Step delayed')
                step_start = ex.end_time + step_duration
            except AbandonRecipe:
                return True
            except (SkippedStep, FinishedStep, AbandonedStep) as ex:
                LOGGER.debug('Step skipped, abanadoned or finished %r', ex)
                return False
            else:
                LOGGER.debug('Next step reached')
                return False

    def play(self):
        # If you change the recipe under me you are
        #    a terrible human being
        recipe = self.start_playing()

        try:
            step_duration = 0
            for index, next_step in enumerate(recipe['steps']):
                self._initialize_step(index, next_step, recipe)

                if self._play_step(step_duration):
                    LOGGER.debug('Recipe finished')
                    break

                next_step['started_at'] = time.time()
                self.next_step(next_step)
                self._run_commands()
                with self.with_current_step() as current_step:
                    print format_step(self._name, current_step)
                step_duration = next_step['duration']
                del next_step

            self._finish_current_step()

            with data.with_data(self._data_path) as app_data:
                stop(app_data, self._name, False)
        except:
            if not self._error_keep:
                with data.with_data(self._data_path) as app_data:
                    stop(app_data, self._name, False)
            raise

    def _run_commands(self):
        with self.with_current_step() as step:
            if step is None:
                return
            for command in step['commands']:
                print _run_command(command, _command_info(self._name, step))

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
            playback_data['step'].setdefault('commands', [])
            playback_data['step'].setdefault('format_command', [])
            yield playback_data['step']

    def record_step(self, step, duration=None, skipped=None, finished_early=None):
        with self.with_playback_data() as playback_data:
            stored_step = step.copy()
            stored_step['started_at'] = time.time()
            if duration is not None:
                stored_step['duration'] = duration
            if skipped is not None:
                stored_step['skipped'] = skipped
            if finished_early is not None:
                stored_step['finished_early'] = finished_early
            playback_data['step'] = stored_step

    def next_step(self, next_step):
        LOGGER.debug('Setting step %r', next_step['text'])
        with self.with_playback_data() as playback_data:
            old_step = playback_data.get('step', None)
            if old_step:
                playback_data.setdefault('steps', [])
                playback_data['steps'].append(old_step)
            playback_data['step'] = next_step

    def start_playing(self):
        with data.with_data(self._data_path) as app_data:
            playbacks = app_data.setdefault('playbacks', {})
            all_recipes = app_data.setdefault('all_recipes', {})

            LOGGER.debug('Playbacks %r', playbacks)
            if self._name in playbacks:
                raise Exception('There is already a player called {}. Use a different name'.format(self._name))

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
                    if playback_data['step']['finished_early']:
                        raise FinishedStep()
                    elif playback_data['step']['abandoned_at'] is not None:
                        raise AbandonedStep()
                    elif playback_data['step']['delays']:
                        delay = playback_data['step']['delays'][-1]
                        if delay != self._current_delay:
                            self._current_delay = delay
                            raise DelayedStep(delay['end_time'])
        self._finish_current_step()

    def _finish_current_step(self):
        with self.with_playback_data() as playback_data:
            if playback_data['step'] is not None:
                playback_data['step']['finished'] = True

class SkippedStep(Exception):
    "Current step was skipped"

class FinishedStep(Exception):
    "Current step is finished"

class DelayedStep(Exception):
    "Delay the start of this step for a while"
    def __init__(self, end_time):
        self.end_time = end_time

class AbandonRecipe(Exception):
    "Current recipe is abandoned"

class AbandonedStep(Exception):
    """Abandon the current step after it was started"""

def stop(app_data, playback, error=True):
    LOGGER.debug('Stopping %r', playback)
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
        LOGGER.debug('Step %r', playing_step)
        if playing_step['delays']:
            last_delay = playing_step['delays'][-1]
            delay_until = last_delay['end_time']
            delay_reason = last_delay['reason']
        else:
            delay_until = None

        duration = playing_step['duration']

        text = format_step(playback, playing_step)

        if delay_until and time.time() < delay_until:
            relative_delay = delay_until - time.time()
            return 'DELAYED FOR {:.0f}s BECAUSE {}: {} {}'.format(relative_delay, delay_reason, duration, text)
        else:
            progress = time.time() - (delay_until or playing_step['started_at'])
            percent_progress = float(progress) / playing_step['duration'] * 100
            return '{:.0f}s/{:.0f}s ({:.0f}%) {}'.format(progress, duration, percent_progress, text)
    else:
        history.display_full_playback(app_data['playbacks'][playback])

def skip_step(app_data, playback):
    playback_data = app_data['playbacks'][playback]
    playback_data['step']['skipped'] = True

def abandon_step(app_data, playback):
    playback_data = app_data['playbacks'][playback]
    playback_data['step']['abandoned_at'] = time.time()

def finish_step(app_data, playback):
    playback_data = app_data['playbacks'][playback]
    playback_data['step']['finished_early'] = True
    playback_data['step']['finished_at'] = time.time()

def delay_step(app_data, playback, seconds, reason):
    playback_data = app_data['playbacks'][playback]
    playback_data['step']['delays'].append(dict(end_time=time.time() + seconds, reason=reason))

def format_step(name, step):
    if step is None:
        return
    elif step['format_command']:
        return _run_command(step['format_command'], _command_info(name, step))
    else:
        return step['text']

def _run_command(command, info):
    command = [c.format(**info) for c in command]
    return os_utils.backticks(command).strip().strip('\n')


def _command_info(name, step):
    return dict(
        name=name,
        text=step['text']
        )
