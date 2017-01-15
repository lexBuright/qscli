#!/usr/bin/python

"""
qssettings show # prompt for a setting name and print it
qssettings set # prompt for a setting name and print it
"""

import argparse
import json
import logging
import os.path
import subprocess
import sys

from . import guiutils
from .symbol import Symbol

LOGGER = logging.getLogger()


PROMPT = Symbol('prompt')

def name_setting(parser):
    parser.add_argument('--name', '-n', default=PROMPT)

def value_setting(parser):
    parser.add_argument('--value', '-v', default=PROMPT)

DEFAULT_CONFIG_DIR = os.path.join(os.environ['HOME'], '.config', 'qssettings')

PARSER = argparse.ArgumentParser(description='Store and update settings')
PARSER.add_argument('--config-dir', '-C', help='Directory to store configuration and data', default=DEFAULT_CONFIG_DIR)
PARSER.add_argument('--prefix', '-P', help='Prefix for settings in qstimeseries', default='')
PARSER.add_argument('--debug', action='store_true', help='Print debug output')

parsers = PARSER.add_subparsers(dest='action')
show_parser = parsers.add_parser('list', help='List all settings')
show_parser = parsers.add_parser('show', help='Show a setting')
name_setting(show_parser)
update_parser = parsers.add_parser('update', help='Update a setting')
name_setting(update_parser)
value_setting(update_parser)

delete_parser = pa.add_parser('delete', help='Delete a setting')
name_setting(delete_parser)

timeseries_parser = parsers.add_parser('timeseries', help='Update a setting')
timeseries_parser.add_argument('arguments', nargs='*', help='Arguments to pass to timeseries')


def main():
    result = run(guiutils, sys.argv[1:])
    if result is not None:
        print result
        sys.stdout.flush()

def run(prompter, args):
    args = PARSER.parse_args(args)
    store = ValueStore(args.config_dir, args.prefix)

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    if args.action == 'list':
        return list_settings(store)
    elif args.action == 'show':
        return show_setting(store, prompter, args.name)
    elif args.action == 'update':
        return update_setting(store, prompter, args.name, args.value)
    elif args.action == 'delete':
        return delete_setting(store, prompt, args.name)
    elif args.action == 'timeseries':
        return shell_collect(['qstimeseries', '--config-dir', args.config_dir] + args.arguments)
    else:
        raise ValueError(args.action)

class ValueStore(object):
    def __init__(self, config_dir, prefix):
        self._config_dir = config_dir
        self._prefix = prefix.strip('.') + '.' if prefix else ''

    def get_current(self, name):
        data = json.loads(
            shell_collect([
                'qstimeseries',
                '--config-dir',
                self._config_dir,
                'show',
                '--series', self._prefix + name,
                '--json']))
        data.sort(key=lambda x: x['time'])

        LOGGER.debug('Values %r', data)
        if data:
            return data[-1]['value']
        else:
            raise IndexError

    def delete(self, name):
        self.timeseries(['show', '--series', name, '--delete'])

    def get_setting_names(self):
        result = json.loads(self.timeseries(['series', '--json']))
        return [x['name'][len(self._prefix):]
                    for x in result['series']
                    if x['name'].startswith(self._prefix)]

    def update(self, name, value):
        if self._prefix:
            name = self._prefix + name

        LOGGER.debug('Storing %r %r', name, value)
        return self.timeseries(['append', name, str(value)])

    def timeseries(self, command):
        return shell_collect(['qstimeseries', '--config-dir', self._config_dir] + command)

def list_settings(store):
    result = []
    for name in store.get_setting_names():
        result.append('{} {}'.format(name, store.get_current(name)))
    return '\n'.join(result)

def show_setting(store, prompter, name):
    if name == PROMPT:
        name = prompt_for_name(prompter, store)

    return str(store.get_current(name))

def prompt_for_name(prompter, store):
    return prompter.combo_prompt('Which setting:', choices=store.get_setting_names())

def prompt_for_value(prompter, store, default):
    return prompter.float_prompt('Value:', default=default)

def update_setting(store, prompter, name, value):
    if name == PROMPT:
        name = prompt_for_name(prompter, store)

    if value == PROMPT:
        try:
            old = store.get_current(name)
        except IndexError:
            old = None

        value = prompt_for_value(prompter, store, default=old)

    store.update(name, value)

def delete_setting(store, prompter, name):
    if name == PROMPT:
        name = prompt_for_name(prompter, store)

    store.delete(name)

def shell_collect(command):
	process = subprocess.Popen(command, stdout=subprocess.PIPE)
	stdout, _ = process.communicate()
	if process.returncode != 0:
		raise ValueError(process.returncode)
	return stdout

if __name__ == '__main__':
    main()
