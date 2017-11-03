"""
Display, manage and create simple text based reports.

# Create a new report called cpu and edit it in an editor
qsreport new cpu

# Show the report
qsreport show cpu

# Show a report (prompt for the report name)
qsreport show --prompt-for-name

# Edit a report
qsreport edit cpu --editor=emacs

"""

import argparse
import logging
import os
import random
import stat
import subprocess

from . import edit
from . import guiutils
from .data import with_data
from .symbol import Symbol

LOGGER = logging.getLogger()

# Q: Why not just put these reports in shell scripts on your path. of you need other freatures you can
#    probably just do this with wrapper scripts (e.g watch), if you want completion you can just
#    do it with some sort of prefix. If you want to edit them use vim $(which !:0))

# A: This is a compelling argument. I'd agree that care needs to be taken to pick the appropriate level of
#    generality when coding things, and if possible you should write specific tools rather than "frameworks".
#    There are a few counter arguments.

#    - My experience with completion and keybindings is that making common
#    tasks easy is worthwhile, not least in terms of making activities more enjoyable: this should not
#    be underestimated.

#    - Part of the purpose of this tool is for interaction with guis. I want to bind given commands to
#    various keybindings. It seems appropriate to put the window-manager agnostic code into
#    a single place. As to why one needs to be able to do this sort of thing from a window manager,
#    this mostly comes down to making easy things easy once again: you want to be able to quickly
#    look at various reports without interrupting your other activities

#    - Reuseability! This script represents a way of doing things; by creating it, I create a way
#    of spreading these ideas.

#    - A combined interface for use and editing. There is a frictional cost to changing things when you
#    notice they could be improved. You have to stop what you are doing, open a new window, or
#    disrupt your existing windows and possible lose your place, and then actually locate
#    the thing that needs to be changed. These things get in your way, and can have a cumulative
#    effect similar to the broken window effect, tools simply go unused, information, simply
#    goes unlooked at.


DEFAULT_CONFIG_DIR = os.path.join(os.environ['HOME'], '.config', 'qsreport')


LAST = Symbol('last')
PROMPT = Symbol('prompt')

PARSER = argparse.ArgumentParser(description=__doc__)
PARSER.add_argument('--debug', action='store_true', help='Print debug output')
PARSER.add_argument('--config-dir', '-C', type=str, help='Use this directory of configuration', default=DEFAULT_CONFIG_DIR)
parsers = PARSER.add_subparsers(dest='command')

path_command = parsers.add_parser('path', help='Show the path of a report')
path_command.add_argument('name', type=str, nargs='?', default=LAST)

new_command = parsers.add_parser('new', help='Create a new report')
new_command.add_argument('name', type=str, nargs='?')
new_command.add_argument('--editor', type=str)

edit_command = parsers.add_parser('edit', help='Create a new report')
edit_command.add_argument('name', type=str, nargs='?', default=LAST)
edit_command.add_argument('--editor', type=str)

show_command = parsers.add_parser('show', help='Show a new report')
show_command.add_argument('name', type=str, nargs='?')
show_command.add_argument('--prompt-for-name', action='store_true', help='Prompt for name using a gui pop-up')

delete_command = parsers.add_parser('delete', help='Show a new report')
delete_command.add_argument('name', type=str)

random_command = parsers.add_parser('random', help='Show a new report')

def main():
    args = PARSER.parse_args()
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    data = Data(args.config_dir)

    if args.command in ('new', 'edit'):
        new(data, args.name, args.editor)
    elif args.command == 'show':
        show(data, args.name, args.prompt_for_name)
    elif args.command == 'path':
        path(data, args.name)
    elif args.command == 'random':
        show(data, random.choice(data.get_reports()), False)
    elif args.command == 'delete':
        delete(data, args.name)
    else:
        raise ValueError(args.command)

def get_default_editors():
    return [os.environ.get('VISUAL'), os.environ.get('EDITOR'), 'sensible-editor', 'vim', 'vi', 'nano', 'ed']

def new(data, name, editor):
    if name == LAST:
        name = data.get_last()
    elif name is None:
        name = guiutils.combo_prompt('Report name', data.get_reports())

    editors = [editor] if editor else None
    report_path = data.get_report_path(name)
    edit.edit(report_path, editors=editors)
    os.chmod(report_path, os.stat(report_path).st_mode | stat.S_IEXEC)

def delete(data, name):
    os.unlink(data.get_report_path(name))

def show(data, name, prompt_for_name):
    if name is not None and prompt_for_name:
        raise Exception('You must either use --prompt-for-name or specify a report, not both')

    if prompt_for_name:
        name = guiutils.combo_prompt('Report name', data.get_reports())

    LOGGER.debug('Showing %s', name)
    data.set_last(name)
    print name
    subprocess.check_call([data.get_report_path(name)])

def path(data, name):
    if name == LAST:
        name = data.get_last()
    return data.get_report_path(name)

class Data(object):
    def __init__(self, config_dir):
        self._config_dir = config_dir
        self._data_file = os.path.join(config_dir, 'data.json')
        self._report_dir = os.path.join(config_dir, 'reports')

    def _init_config(self):
        if not os.path.isdir(self._config_dir):
            os.makedirs(self._config_dir)

        if not os.path.isdir(self._report_dir):
            os.makedirs(self._report_dir)

    def get_last(self):
        self._init_config()
        with with_data(self._data_file) as data:
            return data['last']

    def set_last(self, last):
        self._init_config()
        with with_data(self._data_file) as data:
            data['last'] = last

    def get_reports(self):
        self._init_config()
        return [x for x in os.listdir(self._report_dir) if not x.endswith('~')]

    def get_report_path(self, name):
        self._init_config()
        return os.path.join(self._report_dir, name)

if __name__ == '__main__':
    main()
