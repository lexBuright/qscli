"""
Ask questions with random interviews.

qsask new actions --period 100 --question "What are you doing?"
qsask new happiness --period 30 --question "How happy are you?"
qsask run # Daemon process that periodically asks questions
qsask log happiness # Show readings for happiness

"""

STRING, FLOAT = 'string', 'float'

import argparse
import contextlib
import json
import logging
import os
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

import fasteners

from . import guiutils

DEFAULT_CONFIG_DIR = os.path.join(os.environ['HOME'], '.config', 'qsask')

PARSER = argparse.ArgumentParser(description='Periodically prompt for answers to questions')
PARSER.add_argument('--config-dir', '-C', type=str, help='', default=DEFAULT_CONFIG_DIR)
PARSER.add_argument('--debug', action='store_true', help='Include debug output (to stderr)')

parsers = PARSER.add_subparsers(dest='command')
test = parsers.add_parser('test', help='Run the tests')

new = parsers.add_parser('new', help='Create a new question')
new.add_argument('name', type=str)
new.add_argument('--period', type=float, help='Average about of time between asking question', default=3600)
new.add_argument('--type', type=str, choices=(STRING, FLOAT), help='The type of answer to record', default=STRING)
new.add_argument('--prompt', type=str, help='Prompt message', default='')

edit = parsers.add_parser('edit', help='Change properties of a question')
edit.add_argument('name', type=str)
edit.add_argument('--period', type=float, help='Average about of time between asking question')
edit.add_argument('--type', type=str, choices=(STRING, FLOAT), help='The type of answer to record')
edit.add_argument('--prompt', type=str, help='Prompt message')

show = parsers.add_parser('show', help='Show information about a question')
show.add_argument('name', type=str)

log = parsers.add_parser('log', help='Show timeseries of record questions')

daemon = parsers.add_parser('daemon', help='Process that asks questions')
daemon.add_argument('--dry-run', '-n', action='store_true', help='Print out actions rather than carrying them out')
daemon.add_argument('--multiplier', '-m', type=float, help='Ask questions more quickly', default=1.0)

list_parser = parsers.add_parser('list', help='List the questions')

delete_parser = parsers.add_parser('delete', help='Delete a question')
delete_parser.add_argument('name', type=str)

LOGGER = logging.getLogger()

def main():
    args = PARSER.parse_args()
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    if args.command == 'test':
        sys.argv.remove('test')
        if '--debug' in sys.argv:
            sys.argv.remove('--debug')
        unittest.main()
    else:
        result = run(sys.argv[1:])
        if result is not None:
            sys.stdout.write(result)
            sys.stdout.flush()

def backticks(command, stdin=None, shell=False):
    stdin = subprocess.PIPE if stdin is not None else None

    process = subprocess.Popen(command, stdout=subprocess.PIPE, stdin=stdin, shell=shell)
    result, _ = process.communicate(stdin)
    if process.returncode != 0:
        raise Exception('{!r} returned non-zero return code {!r}'.format(command, process.returncode))
    return result

def timeseries_run(data_dir, command):
    # Where possible use pre-existing or general
    #   command line tools.
    direc = os.path.join(data_dir, 'timeseries')
    if not os.path.isdir(direc):
        os.mkdir(direc)

    return backticks(['qstimeseries', '--config-dir', direc] + command)

def log(data_dir):
    return timeseries_run(data_dir, ['show'])

def store_answer(data_dir, name, answer):
    return timeseries_run(data_dir, ['append', name, str(answer)])

def run(args):
    LOGGER.debug('Running with args %r', args)
    options = PARSER.parse_args(args)
    del args
    data_file = os.path.join(options.config_dir, 'data.json')
    LOGGER.debug('Question file %r', data_file)
    if options.command == 'daemon':
        return run_daemon(options.config_dir, data_file, options.multiplier)

    with with_data(data_file) as data:
        init_data(data)
        if options.command == 'new':
            verify_new(data, options.name)
            return edit_question(data, options.name, period=options.period, prompt=options.prompt, type=options.type)
        elif options.command == 'edit':
            return edit_question(data, options.name, period=options.period, prompt=options.prompt, type=options.type)
        elif options.command == 'show':
            return show_question(data, options.name)
        elif options.command == 'log':
            return log(options.config_dir)
        elif options.command == 'list':
            return list_questions(data)
        elif options.command == 'delete':
            return delete_question(data, options.name)
        else:
            raise ValueError(options.command)

def init_data(data):
    data.setdefault('questions', dict())

def show_question(data, name):
    question = data['questions'][name]
    result = []
    result.append('Prompt: {}'.format(question['prompt']))
    result.append('Period: {}'.format(question['period']))
    result.append('Type: {}'.format(question['type']))

    if result:
        return '\n'.join(result) + '\n'

def verify_new(data, name):
    if name in data['questions']:
        raise Exception('Already a question {!r}'.format(name))

def edit_question(data, name, period, prompt, type, choices=None):
    data['questions'].setdefault(name, {})

    if period is not None:
        data['questions'][name]['period'] = period

    if prompt is not None:
        data['questions'][name]['prompt'] = prompt

    if choices:
        data['question'][name].setdefault('choices', [])
        data['question'][name]['choices'].extend(choices)

    if type is not None:
        data['questions'][name]['type'] = type

def list_questions(data):
    result = []
    for name in data['questions']:
        result.append(name)

    if result:
        return '\n'.join(result) + '\n'

def delete_question(data, name):
    del data['questions'][name]

def calculate_ask_prob(question_period, poll_period):
    # As n -> infinity we want the proportion of
    #   success to be poll_period / question_period =: P

    #  I.e seek p such that
    #  \expectation X  / n -> P
    #  Where X ~ B(n, p)

    # now \expectation B(n, p) = np :),
    #   so this just becomse

    return float(poll_period) / float(question_period)

def run_daemon(data_dir, data_file, multiplier):
    period = 1
    while True:
        LOGGER.debug('Polling')
        with with_data(data_file) as data:
            init_data(data)
            data.setdefault('questions', {})

            if not data['questions']:
                LOGGER.debug('No questions to think about asking')


            for name, question in data['questions'].items():
                question['period']

                # Hooray for memorilessness
                ask_prob = calculate_ask_prob(question['period'], period)

                LOGGER.debug('Probability of asking %s: %s', name, ask_prob)
                if random.random() < ask_prob:
                    LOGGER.debug('Asking %s', name)
                    answer = ask_question(question)
                    store_answer(data_dir, name, answer)

        time.sleep(period / multiplier)


def ask_question(question):
    if question['type'] == STRING:
        return guiutils.str_prompt(question['prompt'])
    elif question['type'] == FLOAT:
        return guiutils.float_prompt(question['prompt'])
    else:
        raise ValueError(question['type'])

class FakePrompter(object):
    def str_prompt(self, prompt):
        return 'string'

    def float_prompt(self, prompt):
        return 17.0

# This is difficult to test, and I feel as if the
#   code would turn into inside out reimplementation
#   asyncrhonous glueness

# Stick to unit tests
class TestAsk(unittest.TestCase):
    def setUp(self):
        self.direc = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.direc)

    def run_cli(self, args):
        new_args = ('--config-dir', self.direc) + tuple(args)
        return run(new_args)

    def test_basic(self):
        self.run_cli(['new', 'test'])
        self.run_cli(['new', 'test2', '--period', '100'])

        result = self.run_cli(['list'])
        self.assertTrue('test\n' in result or 'test ' in result, result)
        self.assertTrue('test2\n' in result or 'test ' in result, result)

        self.run_cli(['delete', 'test2'])
        result = self.run_cli(['list'])
        self.assertTrue('test\n' in result or 'test ' in result, result)
        self.assertFalse('test2\n' in result or 'test2 ' in result, result)

    def test_prompt(self):
        self.run_cli(['new', 'test', '--prompt', 'This is a test'])
        result = self.run_cli(['show', 'test'])
        self.assertTrue('This is a test' in result, result)



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




if __name__ == '__main__':
	main()
