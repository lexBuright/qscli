import json
import subprocess


class CliClient(object):
    """
    Protocol for communicating with a persistent
    server process over standard io

     Commands are sent as space separated words (with backslash escaping)
     (as for sh)
     """

    # Responses are json with the form {return_code: , output:, error:}
    def __init__(self, command):
        self._command = command
        self._proc = None

    def initialize(self):
        self._proc = subprocess.Popen(self._command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE)

    def run(self, command):
        command_string = ' '.join(map(escape_whitespace, command))
        self._proc.stdin.write(command_string + '\n')
        data = json.loads(self._proc.stdout.readline())
        if not data['return_code'] == 0:
            raise Exception('Command errored out {!r} {!r}'.format(command_string, data))
        return data['output']

    def stop(self):
        self._proc.stdin.close()
        self._proc.wait()

    def __del__(self):
        self.stop()

def escape_whitespace(command):
    return command.replace('\\', '\\\\').replace(' ', '\ ').replace('\n', '\\n')
