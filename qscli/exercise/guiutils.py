import subprocess
import time

def combo_prompt(prompt, choices):
    p = subprocess.Popen(
        ['rofi', '-dmenu', '-p', prompt],
        stdout=subprocess.PIPE, stdin=subprocess.PIPE)
    choice_string = '\n'.join(choices)
    reply, _ = p.communicate(choice_string)
    return reply.strip()

def float_prompt(prompt):
    while True:
        p = subprocess.Popen(
            ['zenity', '--entry', '--title', prompt],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        reply, _ = p.communicate('')
        try:
            return float(reply)
        except ValueError:
            # Give people time to press C-c
            time.sleep(0.5)
