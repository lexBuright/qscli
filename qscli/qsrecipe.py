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
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest

import fasteners

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

DEFAULT_CONFIG_DIR = os.path.join(os.environ['HOME'], '.config', 'qsrecipe')

PARSER = argparse.ArgumentParser(description='Plan a sequence of activities')
PARSER.add_argument('--config-dir', type=str, default=DEFAULT_CONFIG_DIR)
parsers = PARSER.add_subparsers(dest='command')
add_parser = parsers.add_parser('add', help='Add an action to a recipe')
add_parser.add_argument('recipe', type=str, help='Recipe to add a step to')
add_parser.add_argument('step', type=str, help='Recipe step')
add_parser.add_argument('--time', type=parse_time, help='Time delay before this step')

list_parser = parsers.add_parser('list', help='Add an action to a recipe')

parsers.add_parser('test', help='Run the tests')
show_parser = parsers.add_parser('show', help='Show a recipe')
show_parser.add_argument('recipe', type=str)

play_parser = parsers.add_parser('play', help='Play a recipe with steps in order')
play_parser.add_argument('recipe', help='Which recipe to replay', default='DEFAULT')
play_parser.add_argument('--name', help='Name of the playback (allows for restarting etc)', default='DEFAULT')

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

def play(data_path, recipe, name):
    # If you change the recipe under me you are
    #    a terrible human being


    with with_data(data_path) as data:
        playbacks = data.setdefault('playbacks', {})

        if name in playbacks:
            raise Exception('There is a already a player called {}. Use a different name'.format(name))

        playbacks[name] = dict(start=time.time())

        recipe = get_recipe(data, recipe)
        players = recipe.setdefault('players', list())
        players.append(name)



def run(args):
    options = PARSER.parse_args(args)
    ensure_config(options.config_dir)

    data_path = os.path.join(options.config_dir, 'data.json')

    if options.command == 'play':
        # Long-running: can't lock data
        return play(data_path, options.recipe, options.name)

    with with_data(data_path) as data:

        if options.command == 'add':
            return add(data, options.recipe, options.step, options.time)
        elif options.command == 'list':
            return list_recipes(data)
        elif options.command == 'show':
            return show(data, options.recipe)
        else:
            raise ValueError(options.command)

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
        start_time = last_step_time + start_time.total_seconds()
    elif start_time is None:
        start_time = last_step_time
    else:
        raise ValueError(start_time)

    recipe['steps'].append(dict(text=step, start_time=start_time))

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

def show(data, recipe):
    recipe = get_recipe(data, recipe)
    result = []
    for step in recipe['steps']:
        result.append((format_seconds(step['start_time']), step['text']))

    time_column_width = max(len(r[0]) for r in result) + 2
    output = []
    for time_string, text in result:
        time_string += ' ' * (time_column_width - len(time_string))
        output.append('{}{}'.format(time_string, text))

    return '\n'.join(output)

class TestRecipes(unittest.TestCase):
    def setUp(self):
        self.direc = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.direc)

    def run_cli(self, args):
        new_args = ('--config-dir', self.direc) + tuple(args)
        return run(new_args)

    def test_list(self):
        self.run_cli(['add', 'breakfast', 'eat'])
        self.run_cli(['add', 'work', 'do'])
        self.run_cli(['add', 'lunch', 'eat'])
        self.run_cli(['add', 'drinks', 'drink'])
        self.run_cli(['add', 'bed', 'sleep'])
        lines = self.run_cli(['list']).splitlines()
        self.assertTrue([l.startswith('breakfast') for l in lines])
        self.assertTrue([l.startswith('work') for l in lines])
        self.assertTrue([l.startswith('lunch') for l in lines])
        self.assertTrue([l.startswith('drinks') for l in lines])
        self.assertTrue([l.startswith('bed') for l in lines])


    def test_show(self):
        self.run_cli(['add', 'omelete', 'break eggs'])
        self.run_cli(['add', 'omelete', 'Whisk', '--time', '+10s'])
        self.run_cli(['add', 'omelete', 'Add oil', '--time', '+5s'])
        self.run_cli(['add', 'omelete', 'Heat pan', '--time', '+5s'])
        self.run_cli(['add', 'omelete', 'Add eggs', '--time', '+2m'])
        self.run_cli(['add', 'omelete', 'Finished', '--time', '+3m'])

        expected = '''\
0s      break eggs
10s     Whisk
15s     Add oil
20s     Heat pan
2m 20s  Add eggs
5m 20s  Finished'''

        self.assertEquals(expected, self.run_cli(['show', 'omelete']))

    # def test_playback(self):
    #     self.run_cli(['add', 'recipe', 'start'])
    #     self.run_cli(['add', 'recipe', 'step 1', '--time', '+1s'])
    #     self.run_cli(['add', 'recipe', 'step 2', '--time', '+2s'])

    #     def read(it):
    #         return next(it)

    #     it = peak_iter(self.run_cli(['play', 'recipe']))
    #     self.assertEquals(read(it), 'start')
    #     self.set_time(1.1)
    #     self.assertEquals(read(it), 'step 1')
    #     self.set_time(2)
    #     self.assertEquals(read(it), None)
    #     self.set_time(3.1)
    #     self.assertEquals(read(it), 'step 2')


def main():
    args = PARSER.parse_args()
    if args.command == 'test':
        sys.argv = sys.argv[1:]
        unittest.main()
    else:
        run(sys.argv[1:])


if __name__ == '__main__':
    main()
