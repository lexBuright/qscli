import os
import subprocess

def edit(filename, editors=None):
    if editors is None:
        editors = _get_default_editors()

    for editor in editors:
        if editor is None:
            continue

        try:
            _run([editor, filename])
        except ProgramFailed as e:
            if e.returncode == 127:
                continue
            else:
                raise
        else:
            return
    else:
        raise Exception('Could not find a working editor (maybe set EDITOR)')

def _run(command, stdin=None, shell=False):
    stdin = subprocess.PIPE if stdin is not None else None
    process = subprocess.Popen(command, shell=shell)
    result, _ = process.communicate(stdin)
    if process.returncode != 0:
        raise ProgramFailed(command, process.returncode)
    return result

class ProgramFailed(Exception):
    def __init__(self, command, returncode):
        Exception.__init__(self)
        self.command = command
        self.returncode = returncode

    def __str__(self):
        return '{!r} returned non-zero return code {!r}'.format(self.command, self.returncode)

def _get_default_editors():
    return [os.environ.get('VISUAL'), os.environ.get('EDITOR'), 'sensible-editor', 'vim', 'vi', 'nano', 'ed']
