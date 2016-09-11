import subprocess
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

def _prompt_for_thing(prompt, parse):
    while True:
        p = subprocess.Popen(
            ['zenity', '--entry', '--text', prompt],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        reply, _ = p.communicate('')
        try:
            return parse(reply)
        except ValueError:
            # Give people time to press C-c
            time.sleep(0.5)

def float_prompt(prompt):
    return _prompt_for_thing(prompt, float)

def int_prompt(prompt):
    return _prompt_for_thing(prompt, int)
