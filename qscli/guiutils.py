import pipes
import subprocess
import tempfile
import time


def combo_prompt(prompt, choices):
    p = subprocess.Popen(
        ['rofi', '-dmenu', '-p', prompt],
        stdout=subprocess.PIPE, stdin=subprocess.PIPE)

    if isinstance(choices, dict):
        if any(' ' in v for v in choices):
            raise Exception('Choices cannot contain spaces')
        choice_string = '\n'.join(' '.join([key, str('' if value is None else value)]) for key, value in choices.items())
    else:
        choice_string = '\n'.join(choices)
    reply, _ = p.communicate(choice_string)

    if isinstance(choices, dict):
        return reply.strip().rsplit(' ', 1)[0]
    else:
        return reply.strip()

def _prompt_for_thing(prompt, parse, default):
    while True:
        command = ['zenity', '--entry', '--text', prompt]

        if default is not None:
            command += ['--entry-text', str(default)]

        p = subprocess.Popen(
            command,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        reply, _ = p.communicate('')
        try:
            return parse(reply)
        except ValueError:
            # Give people time to press C-c
            time.sleep(0.5)

def float_prompt(prompt, default=None):
    return _prompt_for_thing(prompt, float, default)

def int_prompt(prompt, default=None):
    return _prompt_for_thing(prompt, int, default)

def str_prompt(prompt, default=None):
    return _prompt_for_thing(prompt, str, default)

def run_in_window(command):
    "Run an interactive terminal command in a new window"
    with tempfile.NamedTemporaryFile(delete=False) as f:
        escaped_command = ' '.join(map(pipes.quote, command))
        escaped_command = 'sh -c "{} > {}; "'.format(escaped_command, f.name)
        subprocess.check_call(['mate-terminal', '-e', escaped_command])
        while True:
            f.seek(0)
            result = f.read()
            if result:
                return result
            else:
                time.sleep(0.2)

def confirmation_box(prompt):
    "Prompt and require action to confirm that it has been read"
    subprocess.check_call(['zenity', '--info', '--text', prompt])
