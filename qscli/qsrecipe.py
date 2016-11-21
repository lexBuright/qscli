#!/usr/bin/python

"""
A command line utility to plan sequences of actions over time, e.g. recipes, chemical procedures, operations, checklists, training routines, daily routines, exercise plans.

Modify these sequences, keep track of old versions, automatically prompt each of the step, record when steps are finished.

This is a command line utility, you may want to bind commands to keybindings in your window manager etc.
"""

import argparse
import contextlib
import datetime
import itertools
import json
import logging
import os
import sys
import threading
import time
import unittest

import fasteners

LOGGER = logging.getLogger()

UNIT_PERIODS = {
    's': datetime.timedelta(seconds=1),
    'm': datetime.timedelta(seconds=60),
    'h': datetime.timedelta(seconds=3600),
    'd': datetime.timedelta(days=1),
}

def parse_time(time_string):
    if time_string.startswith('+'):
        unit = time_string[-1]
        return UNIT_PERIODS[unit] * int(time_string[1:-1])
    else:
        raise ValueError(time_string)

def parse_absolute_time(time_string):
    return parse_time('+' + time_string).total_seconds()

DEFAULT_CONFIG_DIR = os.path.join(os.environ['HOME'], '.config', 'qsrecipe')

PARSER = argparse.ArgumentParser(description='Plan a sequence of activities')
PARSER.add_argument('--debug', action='store_true', help='Print debug output')
PARSER.add_argument('--config-dir', type=str, default=DEFAULT_CONFIG_DIR)
parsers = PARSER.add_subparsers(dest='command')

add_parser = parsers.add_parser('add', help='Add an action to a recipe')
add_parser.add_argument('recipe', type=str, help='Recipe to add a step to')
add_parser.add_argument('step', type=str, help='Recipe step')
add_parser.add_argument('--time', type=parse_time, help='Time delay before this step')

edit_parser = parsers.add_parser('edit', help='Edit an action in a recipe')
edit_parser.add_argument('recipe', type=str, help='Recipe to add a step to')
edit_parser.add_argument('--index', '-i', type=int, help='Operate on the action with this index')
edit_parser.add_argument('--after', '-a', type=parse_absolute_time, help='Time after this event before next action')
edit_parser.add_argument('--before', '-b', type=parse_absolute_time, help='Time before this event before next action')
edit_parser.add_argument('--text', '-n', type=str, help='Change the text of this step')

history_parser = parsers.add_parser('history', help='Show the history of playbacks')
history_parser.add_argument('name', type=str, nargs='?')

status_parser = parsers.add_parser('status', help='Show the status of a playback')
status_parser.add_argument('playback', type=str, help='Name of the playback')
status_parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')

playing_parser = parsers.add_parser('playing', help='Show the status of a playback')

stop_parser = parsers.add_parser('stop', help='Stop a current playback')
stop_parser.add_argument('playback', type=str, help='Playback that you want to stop')

list_parser = parsers.add_parser('list', help='Add an action to a recipe')

delete_parser = parsers.add_parser('delete', help='Add an action to a recipe')
delete_parser.add_argument('recipes', type=str, nargs='*')

parsers.add_parser('test', help='Run the tests')
show_parser = parsers.add_parser('show', help='Show a recipe')
show_parser.add_argument('recipe', type=str)
show_parser.add_argument('--json', action='store_true', help='Output data as machine-readable json')

parsers.add_parser('playbacks', help='List historic playbacks')

play_parser = parsers.add_parser('play', help='Play a recipe with steps in order')
play_parser.add_argument('recipe', help='Which recipe to replay', default='DEFAULT')
play_parser.add_argument('--name', help='Name of the playback (allows for restarting etc)')
play_parser.add_argument(
    '--poll-period', '-p', type=float,
    help='How long to wait before checking if we have stopped',
    default=5)
play_parser.add_argument(
    '--error-keep',
    action='store_true',
    help='Do not delete the playback on error')
play_parser.add_argument(
    '--multiplier', '-m',
    type=float,
    default=1.0,
    help='Play faster or slower')

play_note_parser = parsers.add_parser('playnote', help='Record a note on the current playback')
play_note_parser.add_argument('playback', type=str)
play_note_parser.add_argument('note', type=str, help='Note to record - to read from stdin')

play_notes_parser = parsers.add_parser('playnotes', help='List the notes for a current playback')
play_notes_parser.add_argument('playback', type=str)

abandon_parser = parsers.add_parser('abandon', help='Abandon the current activity')
abandon_parser.add_argument('playback', type=str)

skip_parser = parsers.add_parser('skip', help='Skip the current activity in a playback (not started)')
skip_parser.add_argument('playback', type=str)

def ensure_config(config_dir):
    if not os.path.isdir(config_dir):
       os.mkdir(config_dir)

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
                    LOGGER.debug('Step skipped or abanadoned {}'.format(ex))
                except AbandonRecipe:
                    break

                next_step['started_at'] = time.time()


                LOGGER.debug('Setting step %r', next_step['text'])
                self.next_step(next_step)
                print next_step['text']
                del next_step

            with with_data(self._data_path) as data:
                stop(data, self._name, False)
        except:
            if not self._error_keep:
                with with_data(self._data_path) as data:
                    stop(data, self._name, False)
            raise

    def store_recipe(self, recipe):
        with self.with_playback_data() as playback_data:
            playback_data['recipe'] = recipe

    @contextlib.contextmanager
    def with_playback_data(self):
        with with_data(self._data_path) as data:
            yield data['playbacks'].setdefault(self._name, dict(name=self._name))

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
            next_step['duration'] = step_duration(playback_data['recipe'], next_step['index'])
            playback_data['step'] = next_step

    def start_playing(self):
        with with_data(self._data_path) as data:
            playbacks = data.setdefault('playbacks', {})
            if self._name in playbacks:
                raise Exception('There is a already a player called {}. Use a different name'.format(self._name))

            recipe = get_recipe(data, self._recipe_name)
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
            with with_data(self._data_path) as data:
                if self._name not in data['playbacks']:
                    raise AbandonRecipe()
                else:
                    playback_data = data['playbacks'][self._name]
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

def stop(data, playback, error=True):
    data.setdefault('past_playbacks', dict())

    if not error:
        if playback not in data['playbacks']:
            return

    if playback in data['playbacks']:
        playback_data = data['playbacks'][playback].copy()
        playback_data['id'] = time.time()
        for i in itertools.count(1):
            save_name = '{}-{}'.format(playback_data['name'], i)
            if save_name not in data['past_playbacks']:
                break

        data['past_playbacks'][save_name] = playback_data


    data['playbacks'].pop(playback)

def playback_status(data, playback, verbose):
    if not verbose:
        playing_step = data['playbacks'][playback]['step']
        progress = time.time() - playing_step['started_at']
        duration = playing_step['duration']
        percent_progress = float(progress) / playing_step['duration'] * 100
        return '{:.0f}s/{:.0f}s ({:.0f}%) {}'.format(progress, duration, percent_progress, playing_step['text'])
    else:
        display_full_playback(data['playbacks'][playback])


def playing(data):
    "Recipes that are currently playing"
    for name in data['playbacks']:
        print name

def run(args):
    options = PARSER.parse_args(args)
    del args
    ensure_config(options.config_dir)

    data_path = os.path.join(options.config_dir, 'data.json')

    if options.command == 'play':
        # Long-running: can't lock data
        player = Player(
            data_path=data_path,
            recipe_name=options.recipe,
            name=options.name,
           error_keep=options.error_keep, poll_period=options.poll_period, multiplier=options.multiplier)
        return player.play()

    with with_data(data_path) as data:
        if options.command == 'add':
            return add(data, options.recipe, options.step, options.time)
        elif options.command == 'playing':
            return playing(data)
        elif options.command == 'status':
            return playback_status(data, options.playback, options.verbose)
        elif options.command == 'stop':
            return stop(data, options.playback)
        elif options.command == 'edit':
            return edit(
                data, options.recipe,
                index=options.index,
                after=options.after,
                before=options.before,
                text=options.text)
        elif options.command == 'list':
            return list_recipes(data)
        elif options.command == 'delete':
            return delete_recipes(data, options.recipes)
        elif options.command == 'show':
            return show(data, options.recipe, options.json)
        elif options.command == 'playbacks':
            list_playbacks(data, options)
        elif options.command == 'playnote':
            add_play_note(data, options.playback, options.note)
        elif options.command == 'playnotes':
            show_play_notes(data, options.playback)
        elif options.command == 'skip':
            skip_step(data, options.playback)
        elif options.command == 'abandon':
            abandon_step(data, options.playback)
        elif options.command == 'history':
            if options.name:
                show_history_item(data, options.name)
            else:
                show_history(data)
        else:
            raise ValueError(options.command)

def show_history(data):
    data.setdefault('past_playbacks', dict())
    for name, playback in data['past_playbacks'].items():
        print name, playback['recipe_name']

def show_history_item(data, name):
    playback = data['past_playbacks'][name]
    display_full_playback(playback)

def display_full_playback(playback):
    print 'Recipe', playback['recipe_name']
    print 'Started', datetime.datetime.fromtimestamp(playback['start'])

    if playback['step']:
        playback_steps = playback['steps'] + [playback['step']]
    else:
        playback_steps = playback['steps']

    recipe_steps = [x.copy() for x in playback['recipe']['steps']]

    for i, (playback_step, recipe_step) in enumerate(zip(playback_steps + [None] * len(recipe_steps), recipe_steps)):
        recipe_step['duration'] = step_duration(playback['recipe'], i)
        display_step(playback_step or recipe_step)

def display_step(step):
    if not step.get('started_at'):
        print '    NOT STARTED {} {}s'.format(step['text'], step['duration'])
        return

    if step['skipped']:
        print '   ', step['text'], 'SKIPPED'
    elif step['abandoned_at'] is not None:
        completed_time = step['abandoned_at'] - step['started_at']
        percent_completed = step['duration'] and completed_time / step['duration'] * 100

        print '   ', step['text'], 'ABANDONED', '{:.0f}/{:.0f}({:.0f}%)'.format(completed_time, step['duration'], percent_completed)

    elif step['finished']:
        print '   ', step['text'], 'FINISHED',  step['duration']
    else:
        elapsed = time.time() - step['started_at']
        percent_complete = step['duration'] and float(elapsed) / float(step['duration']) * 100
        print '    {} IN PROGRESS {:.1f}s/{:.1f}s ({:.0f}%)'.format(step['text'], elapsed, step['duration'], percent_complete)


    for note in step['notes']:
        note_offset = note['time'] - step['started_at']
        print '        {:.1f} {}'.format(note_offset, note['note'])


def skip_step(data, playback):
    playback_data = data['playbacks'][playback]
    playback_data['step']['skipped'] = True

def abandon_step(data, playback):
    playback_data = data['playbacks'][playback]
    playback_data['step']['abandoned_at'] = time.time()

def list_playbacks(data, options):
    playbacks = data.get('finished_playbacks', [])
    for playback in playbacks:
        print playback

def add_play_note(data, playback, note):
    if note == '-':
        note = sys.stdin.read()

    step = data['playbacks'][playback]['step']
    step.setdefault('notes', []).append(dict(note=note, time=time.time()))

def show_play_notes(data, playback):
    playback_data = data['playbacks'][playback]
    for step in playback_data['steps']:
        for note in step.get('notes', []):
            print note

    if playback_data['step']:
        for note in playback_data['step'].get('notes', []):
            print note

def delete_recipes(data, recipes):
    for recipe in recipes:
        data.get('recipes', {}).pop(recipe)

def list_recipes(data):
    result = []
    for name in sorted(data.get('recipes', {})):
        result.append(name)
    return '\n'.join(result)

def get_recipe(data, recipe):
    recipes = data.setdefault('recipes', {})
    recipe = recipes.setdefault(recipe, {})
    steps = recipe.setdefault('steps', [])
    return recipe

def add(data, recipe, step, start_time):
    recipe = get_recipe(data, recipe)

    if not recipe['steps']:
        last_step_time = 0
    else:
        last_step_time = recipe['steps'][-1]['start_offset']

    if isinstance(start_time, datetime.timedelta):
        start_offset = last_step_time + start_time.total_seconds()
    elif start_time is None:
        start_offset = last_step_time
    else:
        raise ValueError(start_time)

    recipe['steps'].append(dict(text=step, start_offset=start_offset))

def edit(data, recipe_name, index=None, text=None, before=None, after=None):
    recipe = get_recipe(data, recipe_name)
    step = find_step(recipe, index=index)
    step_index = recipe['steps'].index(step)

    if text:
        step['text'] = text

    if before:
        shift = before - step_duration(recipe, index - 1)
        LOGGER.debug('Shifting before by %r', shift)
        for step in recipe['steps'][index:]:
            step['start_offset'] += shift

    if after:
        shift = after - step_duration(recipe, index)
        LOGGER.debug('Shifting after by %r', shift)
        for step in recipe['steps'][index + 1:]:
            step['start_offset'] += shift

def find_step(recipe, index):
    return recipe['steps'][index]

def step_time(recipe, index):
    if index < 0:
        return 0
    elif index >= len(recipe['steps']):
        return recipe['steps'][-1]['start_offset']
    else:
       return recipe['steps'][index]['start_offset']

def step_duration(recipe, index):
    next_step_time = step_time(recipe, index + 1)
    current_step_time = step_time(recipe, index)
    return next_step_time - current_step_time

def format_seconds(seconds):
    seconds = int(seconds)
    minutes, seconds = seconds // 60, seconds % 60
    hours, minutes  = minutes // 60, minutes % 60

    result = '{}s'.format(seconds)
    if minutes:
        result = '{}m {}'.format(minutes, result)
    if hours:
        result = '{}h {}'.format(hours, result)
    return result

def show(data, recipe, is_json):
    recipe = get_recipe(data, recipe)

    if is_json:
        result = dict(steps=[])
        for step in recipe['steps']:
            # Add an indirection layer between
            #   external and internal format
            result['steps'].append(dict(
                text=step['text'],
                start_offset=step['start_offset']
            ))
        return json.dumps(result)
    else:
        result = []
        for step in recipe['steps']:
            result.append((format_seconds(step['start_offset']), step['text']))

        time_column_width = max(len(r[0]) for r in result) + 2
        output = []
        for time_string, text in result:
            time_string += ' ' * (time_column_width - len(time_string))
            output.append('{}{}'.format(time_string, text))

        return '\n'.join(output)

def main():
    args = PARSER.parse_args()
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    LOGGER.debug('Starting')

    if args.command == 'test':
        sys.argv = sys.argv[1:]
        unittest.main()
    else:
        result = run(sys.argv[1:])
        if result is not None :
            print result


if __name__ == '__main__':
    main()
