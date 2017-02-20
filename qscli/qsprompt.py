#!/usr/bin/python

""" Like zenity but higher level (and likely with fewer features)

Deals with things like retrying and validation and types.

qsprompt.py --prompt 'An integer' --type integer
qsprompt.py --prompt 'An integer' --type float
"""

import argparse
import re
import subprocess
import sys
import time

INTEGER = 'integer'
FLOAT = 'float'
STRING = 'string'
TYPES = (INTEGER, FLOAT, STRING)

PARSER = argparse.ArgumentParser(description='')
PARSER.add_argument('--type', choices=TYPES, default=STRING)
PARSER.add_argument('--prompt', type=str)

def main():
    args = PARSER.parse_args()
    
    prompt = args.prompt
    errored = False
    
    if args.type == INTEGER:
        validation_re = '^[0-9]+$'
    elif args.type == FLOAT:
        validation_re = '^[0-9]+(\\.[0-9]*)?$'
    else:
        validation_re = None


    while True:
        if args.type in (INTEGER, FLOAT, STRING):
            result = backticks(['zenity', '--entry'] + (['--text', prompt] if prompt else []))
        else:
            raise ValueError()

        if validation_re:
            if not re.search(validation_re, result):
                errored = True
                prompt = 'Not {}. '.format(args.type) + (prompt if prompt else ' ')
                time.sleep(0.5) # Give people time to press C-c
                continue
    
        break
    print result,

def backticks(command):
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()

    error_lines = [
        l for l in stderr.splitlines() if 'without a transient' not in l
    ]
    sys.stderr.write('\n'.join(error_lines))
    sys.stderr.flush()

    if process.returncode != 0:
        raise ValueError(process.returncode)
    return stdout

if __name__ == '__main__':
    main()
