"Store of steps in out recipe"

import datetime
import json
import logging
import re

from . import data
from . import errors
from ..symbol import Symbol

DELETE = Symbol('Delete')
SPLIT = Symbol('Split')
LOGGER = logging.getLogger('qsrecipe.recipe')

UNIT_PERIODS = {
    's': datetime.timedelta(seconds=1),
    'm': datetime.timedelta(seconds=60),
    'h': datetime.timedelta(seconds=3600),
    'd': datetime.timedelta(days=1),
}

def list_recipes(app_data, anon):
    result = []
    for name in sorted(app_data.get('recipes', {})):
        result.append(name)

    if anon:
        result.extend(app_data.get('all_recipes', {}))

    return '\n'.join(result)

def add(app_data, recipe_name, step, start_time, index, duration, step_commands, format_command):
    with data.with_recipe(app_data, recipe_name) as recipe:
        if not recipe['steps']:
            last_step_time = 0
        else:
            last_step_time = recipe['steps'][-1]['start_offset']

        if isinstance(start_time, datetime.timedelta):
            start_offset = last_step_time + start_time.total_seconds()
        elif start_time is None:
            if index is not None:
                start_offset = recipe['steps'][index]['start_offset']
            else:
                start_offset = last_step_time
        else:
            raise ValueError(start_time)

        step = dict(text=step, start_offset=start_offset)
        if index is None:
            recipe['steps'].append(step)
        else:
            recipe['steps'].insert(index, step)

        if duration:
            if index is None or index == len(recipe['steps']):
                raise Exception('Cannot set a duration on the last step')

            for step in recipe['steps'][index + 1:]:
                step['start_offset'] += duration

        step['commands'] = step_commands or []
        step['format_command'] = format_command or []

        sort_steps(recipe)

def sort_steps(recipe):
    recipe['steps'].sort(key=lambda s: s['start_offset'])

def diff(l):
    return [b - a for a, b in zip(l, l[1:])]

def move(app_data, recipe_name, old_index, new_index):
    literal_new_index = new_index.get_index(old_index)

    with data.with_recipe(app_data, recipe_name) as recipe:

        # There are two spaces: duration space
        #  and absolute offset space. This task is
        #  best suited for duration space

        durations = diff([s['start_offset'] for s in recipe['steps']])
        steps_and_durations = list(zip(durations + [0], recipe['steps']))
        moved = steps_and_durations.pop(old_index)

        steps_and_durations.insert(literal_new_index, moved)

        offset = 0
        new_steps = []
        for duration, step in steps_and_durations:
            step['start_offset'] = offset
            offset += duration
            new_steps.append(step)

        recipe['steps'] = new_steps

def update_step(step):
    "Bring step uptodate"
    step.setdefault('commands', [])

def find_step(recipe, index):
    return recipe['steps'][index]

def edit(
        app_data, recipe_name,
        index=None, text=None, before=None, after=None, exact_time=None,
        add_command=None, delete_command_index=None, clear_commands=None,
        format_command=None
        ):
    if exact_time:
        if (before is not None or after is not None) and exact_time is not None:
            raise Exception('exact_time cannot be used with either before or after')

    with data.with_recipe(app_data, recipe_name) as recipe:
        step = find_step(recipe, index=index)
        update_step(step)

        LOGGER.debug('Editing step %r', step)

        if text:
            step['text'] = text

        if exact_time is not None:
            LOGGER.debug('Moving to precisely %r', exact_time)
            step['start_offset'] = exact_time

        if before is not None:
            shift = before - data.step_duration(recipe, index - 1)
            LOGGER.debug('Shifting before by %r', shift)
            for step in recipe['steps'][index:]:
                step['start_offset'] += shift

        if after is not None:
            shift = after - data.step_duration(recipe, index)
            LOGGER.debug('Shifting after by %r', shift)
            for step in recipe['steps'][index + 1:]:
                step['start_offset'] += shift

        if add_command:
            for command in add_command:
                step['commands'].append(command)

        if delete_command_index is not None:
            step['commands'].pop(delete_command_index)

        if format_command is not None:
            if format_command == DELETE:
                step['format_command'] = None
            else:
                step['format_command'] = format_command

        if clear_commands:
            step['commands'] = []

        sort_steps(recipe)

def delete_recipes(app_data, recipes):
    for recipe in recipes:
        app_data.get('recipes', {}).pop(recipe)

def delete_step(app_data, recipe_name, index):
    if index is None:
        # We might later support different search criteria
        raise Exception('Must specify and index')

    with data.with_recipe(app_data, recipe_name) as recipe:
        deleted_step_offset = recipe['steps'][index]['start_offset']
        recipe['steps'].pop(index)
        shift = None
        for step in recipe['steps'][index:]:
            shift = shift if shift is not None else deleted_step_offset - step['start_offset']
            step['start_offset'] -= shift

def show(app_data, recipe_name, is_json):
    with data.read_recipe(app_data, recipe_name) as recipe:
        map(update_step, recipe['steps'])
        if is_json:
            result = dict(steps=[])
            for index, step in enumerate(recipe['steps']):
                step.setdefault('format_command', None)
                # Add an indirection layer between
                #   external and internal format
                result['steps'].append(dict(
                    index=index,
                    format_command=step['format_command'],
                    commands=step['commands'],
                    text=step['text'],
                    start_offset=step['start_offset']
                ))
            return json.dumps(result)
        else:
            result = []
            for step, next_step in zip(recipe['steps'], recipe['steps'][1:] + [None]):
                if next_step:
                    duration = format_seconds(next_step['start_offset'] - step['start_offset'])
                else:
                    duration = '0s'
                result.append((format_seconds(step['start_offset']), duration, step['text'], step['commands']))

            time_column_width = max(len(r[0]) for r in result) + 2
            duration_column_width = max(len(r[1]) for r in result) + 2
            output = []
            for index, (time_string, duration_string, text, commands) in enumerate(result):
                time_string += ' ' * (time_column_width - len(time_string))
                duration_string += ' ' * (duration_column_width - len(duration_string))
                command_string = '; '.join(' '.join(command) for command in commands)
                output.append('{} {}{}{} {}'.format(index, time_string, duration_string, text, command_string))

            return '\n'.join(output)


def format_seconds(seconds):
    seconds = int(seconds)
    minutes, seconds = seconds // 60, seconds % 60
    hours, minutes = minutes // 60, minutes % 60

    result = '{}s'.format(seconds)
    if minutes:
        result = '{}m {}'.format(minutes, result)
    if hours:
        result = '{}h {}'.format(hours, result)
    return result

def add_options(parsers):
    "Add those options for handling recipes to the main parser"

    def format_command(parser):
        parser.add_argument('--format-command', type=parse_command, help='Run this command to produce the text output', dest='format_command')
        parser.add_argument('--clear-format-command', action='store_const', help='Clear the format command', dest='format_command', const=DELETE)

    move_parser = parsers.add_parser('move', help='Move a step while keeping all durations the same')
    move_parser.add_argument('recipe', type=str, help='Recipe to add a step to')
    move_parser.add_argument('old_index', type=int, help='Step to move')
    move_parser.add_argument('new_index',
        type=IntegerCoord.parse,
        help='Index to which the step should be moved. Relative motions can be specified like +1 or -1')

    edit_parser = parsers.add_parser('edit', help='Edit an action in a recipe')
    edit_parser.add_argument('recipe', type=str, help='Recipe to add a step to')
    edit_parser.add_argument('--index', '-i', type=int, help='Operate on the action with this index')
    edit_parser.add_argument('--after', '-a', type=parse_absolute_time, help='Time after this event before next action')
    edit_parser.add_argument('--before', '-b', type=parse_absolute_time, help='Time before this event before next action')
    edit_parser.add_argument('--text', '-n', type=str, help='Change the text of this step')
    edit_parser.add_argument('--exact', '-x', type=parse_absolute_time, help='Exact time into the recipe for this step')
    edit_commands = edit_parser.add_mutually_exclusive_group()
    edit_commands.add_argument('--add-command', action='append', type=parse_command, help='Add a command to run when the step starts')
    edit_commands.add_argument('--clear-commands', action='store_true', help='Clear all commands')
    edit_commands.add_argument('--delete-command', metavar='INDEX', type=int, help='Delete a command at an index')
    format_command(edit_commands)

    list_parser = parsers.add_parser('list', help='Add an action to a recipe')
    list_parser.add_argument('--anon', '-a', action='store_true', help='Include anonymous recipes (old recipes)')

    delete_parser = parsers.add_parser('delete', help='Delete a recipes')
    delete_parser.add_argument('recipes', type=str, nargs='*')

    delete_step_parser = parsers.add_parser('delete-step', help='Delete a step in a recipe')
    delete_step_parser.add_argument('recipe', type=str)
    delete_step_parser.add_argument('--index', type=int, help='Index of step to delete')

    add_parser = parsers.add_parser('add', help='Add an action to a recipe')
    add_parser.add_argument('recipe', type=str, help='Recipe to add a step to')
    add_parser.add_argument('step', type=str, help='Recipe step')
    add_parser.add_argument('--time', type=parse_time, help='Time delay before this step')
    add_parser.add_argument('--index', type=int, help='Insert at this index. By default insert', default=None)
    add_parser.add_argument(
        '--duration', type=parse_absolute_time,
        help='How long the step should last. (Does not work for final argument)', default=None)
    add_parser.add_argument('--command', action='append', type=parse_command, help='Add a command to run when the step starts', dest='step_command')
    format_command(add_parser)


class IntegerCoord(object):
    def __init__(self, coord_type, value):
        self.type = coord_type
        self.value = value

    def get_index(self, old_index):
        if self.type == 'absolute':
            return self.value
        elif self.type == 'relative':
            return self.value + old_index
        else:
            raise ValueError(self.type)

    @classmethod
    def parse(cls, string):
        sign, digits = re.match(r'([+-])?(\d+)', string).groups()
        index_type = {'+':'relative', '-':'relative', None: 'absolute'}[sign]
        return cls(index_type, int(digits))


def parse_absolute_time(time_string):
    return parse_time('+' + time_string).total_seconds()

def parse_command(command_string):
    parts = backslash_unescape(command_string, {' ': SPLIT})
    return [''.join(w) for w in list_split(SPLIT, parts)]

def parse_time(time_string):
    if time_string.startswith('+'):
        unit = time_string[-1]
        return UNIT_PERIODS[unit] * int(time_string[1:-1])
    else:
        raise ValueError(time_string)

def backslash_unescape(string, mappings):
    "Unescape backslashes mapping some characters to values unless they are escaped"
    escaped = False
    for c in string:
        if c == '\\':
            escaped = True
        else:
            if escaped:
                yield c
            else:
                if c in mappings:
                    yield mappings[c]
                else:
                    yield c
            escaped = False

def list_split(split_item, lst):
    part = []
    for item in lst:
        if item == split_item:
            yield part
            part = []
        else:
            part.append(item)
    if part:
        yield part

def handle_command(app_data, options):
    if options.command == 'add':
        return add(
            app_data,
            options.recipe, options.step, options.time,
            options.index, options.duration,
            options.step_command, options.format_command)
    elif options.command == 'move':
        return move(app_data, options.recipe, options.old_index, options.new_index)
    elif options.command == 'edit':
        return edit(
            app_data, options.recipe,
            index=options.index,
            after=options.after,
            before=options.before,
            text=options.text,
            exact_time=options.exact,
            add_command=options.add_command,
            delete_command_index=options.delete_command,
            clear_commands=options.clear_commands,
            format_command=options.format_command,
            )
    elif options.command == 'list':
        return list_recipes(app_data, options.anon)
    elif options.command == 'delete':
        return delete_recipes(app_data, options.recipes)
    elif options.command == 'delete-step':
        return delete_step(app_data, options.recipe, options.index)
    elif options.command == 'show':
        return show(app_data, options.recipe, options.json)
    else:
        raise errors.NoCommand()
