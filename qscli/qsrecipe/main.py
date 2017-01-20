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
import logging
import os
import sys
import time
import unittest

from . import data, history, playback, recipe, errors

LOGGER = logging.getLogger()


DEFAULT_CONFIG_DIR = os.path.join(os.environ['HOME'], '.config', 'qsrecipe')

def build_parser():
    parser = argparse.ArgumentParser(description='Plan a sequence of activities')
    parser.add_argument('--debug', action='store_true', help='Print debug output')
    parser.add_argument('--config-dir', type=str, default=DEFAULT_CONFIG_DIR)
    parsers = parser.add_subparsers(dest='command')

    history_parser = parsers.add_parser('history', help='Show the history of playbacks')
    history_parser.add_argument('name', type=str, nargs='?')
    history_parser.add_argument('--json', '-j', action='store_true', help='Output machine-readable json')

    status_parser = parsers.add_parser('status', help='Show the status of a playback')
    status_parser.add_argument('playback', type=str, help='Name of the playback')
    status_parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')

    parsers.add_parser('playing', help='Show the status of a playback')

    stop_parser = parsers.add_parser('stop', help='Stop a current playback')
    stop_parser.add_argument('playback', type=str, help='Playback that you want to stop')

    parsers.add_parser('test', help='Run the tests')

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

    finish_parser = parsers.add_parser('finish', help='Finish the current step early')
    finish_parser.add_argument('playback', type=str)

    recipe.add_options(parsers)
    return parser

def ensure_config(config_dir):
    if not os.path.isdir(config_dir):
        os.mkdir(config_dir)

def playing(app_data):
    "Recipes that are currently playing"
    for name in sorted(app_data['playbacks']):
        print name

def run(args):
    parser = build_parser()
    options = parser.parse_args(args)
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
        try:
            return recipe.handle_command(app_data, options)
        except errors.NoCommand:
            pass

        if options.command == 'playing':
            return playing(app_data)
        elif options.command == 'status':
            return playback.playback_status(app_data, options.playback, options.verbose)
        elif options.command == 'stop':
            return playback.stop(app_data, options.playback)
        elif options.command == 'skip':
            playback.skip_step(app_data, options.playback)
        elif options.command == 'finish':
            playback.finish_step(app_data, options.playback)
        elif options.command == 'delay':
            playback.delay_step(app_data, options.playback, options.seconds, options.reason)
        elif options.command == 'abandon':
            playback.abandon_step(app_data, options.playback)
        elif options.command == 'playing':
            list_playbacks(app_data, options)
        elif options.command == 'playnote':
            add_play_note(app_data, options.playback, options.note)
        elif options.command == 'playnotes':
            show_play_notes(app_data, options.playback)
        elif options.command == 'history':
            if options.name:
                history.show_history_item(app_data, options.name, options.json)
            else:
                history.show_history(app_data, options.json)
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

def main():
    args = build_parser().parse_args()
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
