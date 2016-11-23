import contextlib
import hashlib
import json
import os
import threading

import fasteners


def step_duration(recipe, index):
    "Calculate how long a step lasts in a recipe"
    next_step_time = step_time(recipe, index + 1)
    current_step_time = step_time(recipe, index)
    return next_step_time - current_step_time

def step_time(recipe, index):
    if index < 0:
        return 0
    elif index >= len(recipe['steps']):
        return recipe['steps'][-1]['start_offset']
    else:
        return recipe['steps'][index]['start_offset']

DATA_LOCK = threading.Lock()
@contextlib.contextmanager
def with_data(data_file):
    "Read from a json file, write back to it when we are finished"
    with fasteners.InterProcessLock(data_file + '.lck'):
        with DATA_LOCK:
            app_data = read_json(data_file)
            yield app_data

            output = json.dumps(app_data)
            with open(data_file, 'w') as stream:
                stream.write(output)

def read_json(filename):
    if os.path.exists(filename):
        with open(filename) as stream:
            return json.loads(stream.read())
    else:
        return dict()

@contextlib.contextmanager
def with_recipe(app_data, recipe_name):
    recipes = app_data.setdefault('recipes', {})
    recipe = recipes.setdefault(recipe_name, {})
    recipe.setdefault('steps', [])
    yield recipe
    recipe['content_id'] = recipe_content_id(recipe)

def recipe_content_id(recipe):
    "Content addressable id for a recipe... because everythign must be git"
    recipe = recipe.copy()
    recipe['content_id'] = None
    return hashlib.sha256(json.dumps(tuple(sorted(recipe.items())))).hexdigest()
