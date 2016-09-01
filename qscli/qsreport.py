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
#    this mostly comes down to making easy things easy again: you want to be able to quickly
#    look at various reports without interrupting your other activities

#    - Reuseability! This script represents a way of doing things; by creating it, I create a way
#    of spreading these ideas

#    - A combined interface for use and editing. There is a frictional cost to changing things when you
#    notice they could be improved. You have to stop what you are doing, open a new window, or
#    disrupt your existing windows and possible lose your place, and then actually locate
#    the thing that needs to be changed. These things get in your way, and can have a cumulative
#    effect similar to the broken window effect, tools simply go unused, information, simply
#    goes unlooked at.


DATA_DIR = os.path.join(os.environ['HOME'], '.config', 'qsreport')
if not os.path.isdir(DATA_DIR):
   os.mkdir(DATA_DIR)

REPORT_DIR = os.path.join(DATA_DIR, 'reports')
if not os.path.isdir(DATA_DIR):
   os.mkdir(REPORT_DIR)

DATA_FILE = os.path.join(DATA_DIR, 'data.json')


LAST = Symbol('last')
PROMPT = Symbol('prompt')

PARSER = argparse.ArgumentParser(description=__doc__)
PARSER.add_argument('--debug', action='store_true', help='Print debug output')
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

    if args.command in ('new', 'edit'):
        new(args.name, args.editor)
    elif args.command == 'show':
        show(args.name, args.prompt_for_name)
    elif args.command == 'path':
        path(args.name)
    elif args.command == 'blah':
        raise NotImplementedError()
    elif args.command == 'random':
        show(random.choice(get_reports()), False)
    elif args.command == 'delete':
        delete(args.name)
    else:
        raise ValueError(args.command)

def get_reports():
    return [x for x in os.listdir(REPORT_DIR) if not x.endswith('~')]

def get_default_editors():
    return [os.environ.get('VISUAL'), os.environ.get('EDITOR'), 'sensible-editor', 'vim', 'vi', 'nano', 'ed']

def new(name, editor):
    if name == LAST:
        name = Data.get_last()
    elif name is None:
        name = guiutils.combo_prompt('Report name', get_reports())

    editors = [editor] if editor else None
    report_path = os.path.join(REPORT_DIR, name)
    edit.edit(report_path, editors=editors)
    os.chmod(report_path, os.stat(report_path).st_mode | stat.S_IEXEC)

def delete(name):
    report_path = os.path.join(REPORT_DIR, name)
    os.unlink(report_path)

def show(name, prompt_for_name):
    if name is not None and prompt_for_name:
        raise Exception('You must either use --prompt-for-name or specify a report, not both')

    if prompt_for_name:
        name = guiutils.combo_prompt('Report name', get_reports())
    LOGGER.debug('Showing %s', name)
    Data.set_last(name)
    print name
    report_path = os.path.join(REPORT_DIR, name)
    subprocess.check_call([report_path])

def path(name):
    if name == LAST:
        name = Data.get_last()
    print os.path.join(REPORT_DIR, name)

class Data(object):
    @staticmethod
    def get_last():
        with with_data(DATA_FILE) as data:
            return data['last']

    @staticmethod
    def set_last(last):
        with with_data(DATA_FILE) as data:
            data['last'] = last


if __name__ == '__main__':
    main()
