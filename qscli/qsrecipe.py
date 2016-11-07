#!/usr/bin/python

"""
A command line utility to plan sequences of actions over time, e.g. recipes, chemical procedures, operations, checklists, training routines, daily routines, exercise plans.

Modify these sequences, keep track of old versions, automatically prompt each of the step, record when steps are finished.

This is a command line utility, you may want to bind commands to keybindings in your window manager etc.
"""

import argparse
import contextlib
import datetime
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

status_parser = parsers.add_parser('status', help='Show the status of a playback')
status_parser.add_argument('name', type=str, help='Name of the playback')

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

play_parser = parsers.add_parser('play', help='Play a recipe with steps in order')
play_parser.add_argument('recipe', help='Which recipe to replay', default='DEFAULT')
play_parser.add_argument('--name', help='Name of the playback (allows for restarting etc)')
play_parser.add_argument(
    '--error-keep',
    action='store_true',
    help='Do not delete the playback on error')

status = parsers.add_parser('status', help='Show the current status of playback')
status.add_argument('playback', type=str)

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

def start_playing(data_path, recipe, name):
    with with_data(data_path) as data:
        playbacks = data.setdefault('playbacks', {})
        if name in playbacks:
            raise Exception('There is a already a player called {}. Use a different name'.format(name))

        playbacks[name] = dict(start=time.time())
        recipe = get_recipe(data, recipe)
        return recipe

def play(data_path, recipe_name, name, error_keep):
    # If you change the recipe under me you are
    #    a terrible human being
    if name is None:
        name = recipe_name

    recipe = start_playing(data_path, recipe_name, name)

    try:
        start_time = time.time()
        for index, step in enumerate(recipe['steps']):
            step_start = start_time + step['start_time']
            time.sleep(max(step_start - start_time, 0))
            print step['text']

            duration = step_duration(recipe, index)

            with with_data(data_path) as data:
                stored_step = step.copy()
                stored_step['started_at'] = time.time()
                stored_step['duration'] = duration
                data['playbacks'][name]['step'] = stored_step

        stop(data, name)

        with with_data(data_path) as data:
            stop(data, name)
    except:
        if not error_keep:
            with with_data(data_path) as data:
                stop(data, name)
        raise

def stop(data, playback):
    del data['playbacks'][playback]

def playback_status(data, playback):
    playing_step = data['playbacks'][playback]['step']
    progress = time.time() - playing_step['started_at']
    duration = playing_step['duration']
    percent_progress = float(progress) / playing_step['duration'] * 100
    return '{:.0f}s/{:.0f}s ({:.0f}%) {}'.format(progress, duration, percent_progress, playing_step['text'])

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
        return play(data_path, options.recipe, options.name, options.error_keep)

    with with_data(data_path) as data:
        if options.command == 'add':
            return add(data, options.recipe, options.step, options.time)
        elif options.command == 'playing':
            return playing(data)
        elif options.command == 'status':
            return playback_status(data, options.playback)
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
        else:
            raise ValueError(options.command)

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
        last_step_time = recipe['steps'][-1]['start_time']


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
            step['start_time'] += shift

    if after:
        shift = after - step_duration(recipe, index)
        LOGGER.debug('Shifting after by %r', shift)
        for step in recipe['steps'][index + 1:]:
            step['start_time'] += shift

def find_step(recipe, index):
    return recipe['steps'][index]

def step_time(recipe, index):
    if index < 0:
        return 0
    else:
       return recipe['steps'][index]['start_time']

def step_duration(recipe, index):
    return (step_time(recipe, index + 1) - step_time(recipe, index))

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
                start_time=step['start_time']
            ))
        return json.dumps(result)
    else:
        result = []
        for step in recipe['steps']:
            result.append((format_seconds(step['start_time']), step['text']))

        time_column_width = max(len(r[0]) for r in result) + 2
        output = []
        for time_string, text in result:
            time_string += ' ' * (time_column_width - len(time_string))
            output.append('{}{}'.format(time_string, text))

        return '\n'.join(output)

def main():
    args = PARSER.parse_args()
    if args.command == 'test':
        sys.argv = sys.argv[1:]
        unittest.main()
    else:
        result = run(sys.argv[1:])
        if result is not None :
            print result


if __name__ == '__main__':
    main()
