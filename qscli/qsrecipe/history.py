import datetime
import time

from . import data

def show_history_item(app_data, name):
    playback = app_data['past_playbacks'][name]
    display_full_playback(playback)

def display_full_playback(playback):
    print 'Recipe', playback['recipe_name']
    print 'Started', datetime.datetime.fromtimestamp(playback['start'])

    if playback['step']:
        playback_steps = playback['steps'] + [playback['step']]
    else:
        playback_steps = playback['steps']

    recipe_steps = [x.copy() for x in playback['recipe']['steps']]

    for i, (playback_step, recipe_step) in enumerate(zip(playback_steps + [None] * len(recipe_steps), recipe_steps)):
        recipe_step['duration'] = data.step_duration(playback['recipe'], i)
        display_step(playback_step or recipe_step)

def display_step(step):
    if not step.get('started_at'):
        print '    NOT STARTED {} {}s'.format(step['text'], step['duration'])
        return

    if step['skipped']:
        print '   ', step['text'], 'SKIPPED'
    elif step['abandoned_at'] is not None:
        completed_time = step['abandoned_at'] - step['started_at']
        percent_completed = step['duration'] and completed_time / step['duration'] * 100
        print '   ', step['text'], 'ABANDONED', '{:.0f}/{:.0f}({:.0f}%)'.format(
            completed_time, step['duration'], percent_completed)

    elif step['finished']:
        print '   ', step['text'], 'FINISHED', step['duration']
    else:
        elapsed = time.time() - step['started_at']
        percent_complete = step['duration'] and float(elapsed) / float(step['duration']) * 100
        print '    {} IN PROGRESS {:.1f}s/{:.1f}s ({:.0f}%)'.format(
            step['text'], elapsed, step['duration'], percent_complete)

    for note in step['notes']:
        note_offset = note['time'] - step['started_at']
        print '        {:.1f} {}'.format(note_offset, note['note'])
