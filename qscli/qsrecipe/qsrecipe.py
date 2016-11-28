"""
A command line utility to plan sequences of actions over time, e.g. recipes,
chemical procedures, operations, checklists, training routines, daily routines,
exercise plans.

Modify these sequences, keep track of old versions, automatically prompt each of
the step, record when steps are finished.

This is a command line utility, you may want to bind commands to keybindings
in your window manager etc.
"""

import argparse
import datetime
import json
import logging
import os
import sys
import time
import unittest

from . import playback
from . import history
from . import data

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
add_parser.add_argument('--index', type=int, help='Insert at this index. By default insert', default=None)

edit_parser = parsers.add_parser('edit', help='Edit an action in a recipe')
edit_parser.add_argument('recipe', type=str, help='Recipe to add a step to')
edit_parser.add_argument('--index', '-i', type=int, help='Operate on the action with this index')
edit_parser.add_argument('--after', '-a', type=parse_absolute_time, help='Time after this event before next action')
edit_parser.add_argument('--before', '-b', type=parse_absolute_time, help='Time before this event before next action')
edit_parser.add_argument('--text', '-n', type=str, help='Change the text of this step')
edit_parser.add_argument('--exact', '-x', type=parse_absolute_time, help='Exact time into the recipe for this step')

history_parser = parsers.add_parser('history', help='Show the history of playbacks')
history_parser.add_argument('name', type=str, nargs='?')

status_parser = parsers.add_parser('status', help='Show the status of a playback')
status_parser.add_argument('playback', type=str, help='Name of the playback')
status_parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')

playing_parser = parsers.add_parser('playing', help='Show the status of a playback')

stop_parser = parsers.add_parser('stop', help='Stop a current playback')
stop_parser.add_argument('playback', type=str, help='Playback that you want to stop')

list_parser = parsers.add_parser('list', help='Add an action to a recipe')
list_parser.add_argument('--anon', '-a', action='store_true', help='Include anonymous recipes (old recipes)')

delete_parser = parsers.add_parser('delete', help='Delete a recipes')
delete_parser.add_argument('recipes', type=str, nargs='*')

delete_step_parser = parsers.add_parser('delete-step', help='Delete a step in a recipe')
delete_step_parser.add_argument('recipe', type=str)
delete_step_parser.add_argument('--index', type=int, help='Index of step to delete')

parsers.add_parser('test', help='Run the tests')
show_parser = parsers.add_parser('show', help='Show a recipe')
show_parser.add_argument('recipe', type=str)
show_parser.add_argument('--json', action='store_true', help='Output data as machine-readable json')

parsers.add_parser('playing', help='List historic playbacks')

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
play_parser.add_argument(
    '--dry-run', '-n',
    action='store_true',
    help='Play but do not record')

play_note_parser = parsers.add_parser('playnote', help='Record a note on the current playback')
play_note_parser.add_argument('playback', type=str)
play_note_parser.add_argument('note', type=str, help='Note to record - to read from stdin')

play_notes_parser = parsers.add_parser('playnotes', help='List the notes for a current playback')
play_notes_parser.add_argument('playback', type=str)

abandon_parser = parsers.add_parser('abandon', help='Abandon the current activity')
abandon_parser.add_argument('playback', type=str)

delay_parser = parsers.add_parser('delay', help='Delay the current step for a reason')
delay_parser.add_argument('playback', type=str)
delay_parser.add_argument('seconds', type=int, help='Number of seconds in the future before the step should start')
delay_parser.add_argument('--reason', type=str, help='Reason for the delay', default='Unknown')

skip_parser = parsers.add_parser('skip', help='Skip the current activity in a playback (not started)')
skip_parser.add_argument('playback', type=str)

def ensure_config(config_dir):
    if not os.path.isdir(config_dir):
        os.mkdir(config_dir)

def playing(app_data):
    "Recipes that are currently playing"
    for name in app_data['playbacks']:
        print name

def run(args):
    options = PARSER.parse_args(args)
    del args
    ensure_config(options.config_dir)

    data_path = os.path.join(options.config_dir, 'data.json')

    if options.command == 'play':
        # Long-running: can't lock data
        player = playback.Player(
            data_path=data_path,
            recipe_name=options.recipe,
            name=options.name,
            error_keep=options.error_keep,
            poll_period=options.poll_period,
            multiplier=options.multiplier,
            dry_run=options.dry_run)
        return player.play()

    with data.with_data(data_path) as app_data:
        if options.command == 'playing':
            return playing(app_data)
        elif options.command == 'status':
            return playback.playback_status(app_data, options.playback, options.verbose)
        elif options.command == 'stop':
            return playback.stop(app_data, options.playback)
        elif options.command == 'skip':
            playback.skip_step(app_data, options.playback)
        elif options.command == 'delay':
            playback.delay_step(app_data, options.playback, options.seconds, options.reason)
        elif options.command == 'abandon':
            playback.abandon_step(app_data, options.playback)
        elif options.command == 'add':
            return add(app_data, options.recipe, options.step, options.time, options.index)
        elif options.command == 'edit':
            return edit(
                app_data, options.recipe,
                index=options.index,
                after=options.after,
                before=options.before,
                text=options.text,
                exact_time=options.exact)
        elif options.command == 'list':
            return list_recipes(app_data, options.anon)
        elif options.command == 'delete':
            return delete_recipes(app_data, options.recipes)
        elif options.command == 'delete-step':
            return delete_step(app_data, options.recipe, options.index)
        elif options.command == 'show':
            return show(app_data, options.recipe, options.json)
        elif options.command == 'playing':
            list_playbacks(app_data, options)
        elif options.command == 'playnote':
            add_play_note(app_data, options.playback, options.note)
        elif options.command == 'playnotes':
            show_play_notes(app_data, options.playback)
        elif options.command == 'history':
            if options.name:
                history.show_history_item(app_data, options.name)
            else:
                history.show_history(app_data)
        else:
            raise ValueError(options.command)

def list_playbacks(app_data, options):
    del options
    playbacks = app_data.get('playbacks', [])
    for playback_name in playbacks:
        print playback_name

def add_play_note(app_data, playback_name, note):
    if note == '-':
        note = sys.stdin.read()
    step = app_data['playbacks'][playback_name]['step']
    step.setdefault('notes', []).append(dict(note=note, time=time.time()))

def show_play_notes(app_data, playback_name):
    playback_data = app_data['playbacks'][playback_name]
    for step in playback_data['steps']:
        for note in step.get('notes', []):
            print note

    if playback_data['step']:
        for note in playback_data['step'].get('notes', []):
            print note

def delete_recipes(app_data, recipes):
    for recipe in recipes:
        app_data.get('recipes', {}).pop(recipe)

def delete_step(app_data, recipe_name, index):
    if index is None:
        # We might later support different search criteria
        raise Exception('Must specify and index')

    with data.with_recipe(app_data, recipe_name) as recipe:
        deleted_step_offset = recipe['steps'][index]['start_offset']
        recipe['steps'].pop(index)
        shift = None
        for step in recipe['steps'][index:]:
            shift = deleted_step_offset - step['start_offset'] if shift is None else shift
            step['start_offset'] -= shift

def list_recipes(app_data, anon):
    result = []
    for name in sorted(app_data.get('recipes', {})):
        result.append(name)

    if anon:
        result.extend(app_data.get('all_recipes', {}))

    return '\n'.join(result)

def add(app_data, recipe_name, step, start_time, index):
    with data.with_recipe(app_data, recipe_name) as recipe:
        if not recipe['steps']:
            last_step_time = 0
        else:
            last_step_time = recipe['steps'][-1]['start_offset']

        if isinstance(start_time, datetime.timedelta):
            start_offset = last_step_time + start_time.total_seconds()
        elif start_time is None:
            if index is not None:
                start_offset = recipe['steps'][index]['start_offset']
            else:
                start_offset = last_step_time
        else:
            raise ValueError(start_time)

        step = dict(text=step, start_offset=start_offset)
        if index is None:
            recipe['steps'].append(step)
        else:
            recipe['steps'].insert(index, step)

        recipe['steps'].sort(key=lambda s: s['start_offset'])

def edit(app_data, recipe_name, index=None, text=None, before=None, after=None, exact_time=None):
    if exact_time:
        if (before is not None or after is not None) and exact_time is not None:
           raise Exception('exact_time cannot be used with either before or after')

    with data.with_recipe(app_data, recipe_name) as recipe:
        step = find_step(recipe, index=index)

        LOGGER.debug('Editing step %r', step)

        if text:
            step['text'] = text

        if exact_time is not None:
            LOGGER.debug('Moving to precisely %r', exact_time)
            step['start_offset'] = exact_time

        if before is not None:
            shift = before - data.step_duration(recipe, index - 1)
            LOGGER.debug('Shifting before by %r', shift)
            for step in recipe['steps'][index:]:
                step['start_offset'] += shift

        if after is not None:
            shift = after - data.step_duration(recipe, index)
            LOGGER.debug('Shifting after by %r', shift)
            for step in recipe['steps'][index + 1:]:
                step['start_offset'] += shift

        recipe['steps'].sort(key=lambda s: s['start_offset'])

def find_step(recipe, index):
    return recipe['steps'][index]

def format_seconds(seconds):
    seconds = int(seconds)
    minutes, seconds = seconds // 60, seconds % 60
    hours, minutes = minutes // 60, minutes % 60

    result = '{}s'.format(seconds)
    if minutes:
        result = '{}m {}'.format(minutes, result)
    if hours:
        result = '{}h {}'.format(hours, result)
    return result

def show(app_data, recipe_name, is_json):
    with data.read_recipe(app_data, recipe_name) as recipe:
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
            for step, next_step in zip(recipe['steps'], recipe['steps'][1:] + [None]):
                if next_step:
                    duration = format_seconds(next_step['start_offset'] - step['start_offset'])
                else:
                    duration = '0s'
                result.append((format_seconds(step['start_offset']), duration, step['text']))

            time_column_width = max(len(r[0]) for r in result) + 2
            duration_column_width = max(len(r[1]) for r in result) + 2
            output = []
            for index, (time_string, duration_string, text) in enumerate(result):
                time_string += ' ' * (time_column_width - len(time_string))
                duration_string += ' ' * (duration_column_width - len(duration_string))
                output.append('{} {}{}{}'.format(index, time_string, duration_string, text))

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
        if result is not None:
            print result
