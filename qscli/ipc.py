"""
Protocol for communicating with a persistent
server process over standard io

Commands are sent as space separated words (with backslash escaping)
(as for sh)

"""


import json
import sys
import traceback
import logging
import subprocess

LOGGER = logging.getLogger('ipc')

def run_server(parser, run_function, debug=True):
    """Start a server, and handle requests. `parser` is an `argparse` parse, `run_function` is a function
    that takes the options returned by this parser and returns a string - often json.
    """

    if debug:
        print >>sys.stderr, 'Running'

    while True:
        command_string = sys.stdin.readline()
        if command_string == '':
            break

        if debug:
            print >>sys.stderr, 'Read command {!r}'.format(command_string)

        command = _tokenize_command(command_string.strip('\n'))
        try:
            options = parser.parse_args(command)

            if debug:
                print >>sys.stderr, 'Running command'

            result_list = run_function(options)

            if debug:
                print >>sys.stderr, 'Finished running'

            result = ''.join(result_list) if result_list is not None else ''
        except BaseException:
            print json.dumps(dict(return_code=1, output='', error=traceback.format_exc()))
        else:
            if debug:
                print >>sys.stderr, 'Dumping'

            print json.dumps(dict(return_code=0, output=result))
            sys.stdout.flush()
            if debug:
                print >>sys.stderr, 'Finished dumping'

def _tokenize_command(command_string):
    escaping = False
    words = []
    buff = []
    for c in command_string:
        if escaping:
            buff.append(c)
            escaping = False
        else:
            if c == '\\':
                escaping = True
            elif c == ' ':
                words.append(''.join(buff))
                buff[:] = []
            else:
                buff.append(c)


    words.append(''.join(buff))
    return words

class CliClient(object):
    "Client"
    # Responses are json with the form {return_code: , output:, error:}
    def __init__(self, command):
        self._command = command
        self._proc = None

    def initialize(self):
        LOGGER.debug('Spawning process %r', self._command)
        self._proc = subprocess.Popen(self._command, stdout=subprocess.PIPE, stdin=subprocess.PIPE)

    def run(self, command):
        command_string = ' '.join(map(_escape_whitespaced, command))
        LOGGER.debug('Sending command %r %r', self, command_string)
        if self._proc.poll() is not None:
            raise Exception('Process has died %r', self._command)
        self._proc.stdin.write(command_string + '\n')
        self._proc.stdin.flush()
        reply = self._proc.stdout.readline()
        LOGGER.debug('Got reply %r', reply)
        data = json.loads(reply)
        if not data['return_code'] == 0:
            raise Exception('Command errored out {!r} {!r}'.format(command_string, data))
        return data['output']

    def shutdown(self):
        self._proc.stdin.close()
        self._proc.wait()

    def __del__(self):
        self.shutdown()

    def __enter__(self):
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_info, tb):
        self.shutdown()

def _escape_whitespaced(command):
    return command.replace('\\', '\\\\').replace(' ', '\ ').replace('\n', '\\n')
