import datetime
import json
import time

from . import data

def show_history_item(app_data, name, is_json):
    playback = app_data['past_playbacks'][name]
    if not is_json:
        display_full_playback(playback)
    else:
        raise NotImplementedError()

def sorted_past_playbacks(app_data):
    def sort_key((k, v)):
        return v['start']

    return sorted(app_data['past_playbacks'].items(), key=sort_key)

def show_history(app_data, is_json):
    app_data.setdefault('past_playbacks', dict())
    result = []
    json_entries = []
    for name, playback_data in sorted_past_playbacks(app_data):
        start_time = playback_data['start']
        start_datetime = datetime.datetime.fromtimestamp(start_time).isoformat()
        start_date = datetime.datetime.fromtimestamp(start_time).date().isoformat()

        if playback_data['steps']:
            last_step = playback_data['steps'][-1]
            end_time = last_step['started_at'] + last_step['duration']
        else:
            end_time = None

        duration = 0 if end_time is None else end_time - start_time
        long_content_id = playback_data['recipe'].get('content_id')
        short_content_id = long_content_id[:10]
        recipe_name = playback_data['recipe_name']
        result.append('{} {} {} {}'.format(name, recipe_name, short_content_id, start_date))
        json_entries.append(dict(
            name=name,
            recipe_name=recipe_name,
            content_id=long_content_id,
            start_time=start_time,
            ended_time=end_time,
            duration=duration,
            date=start_datetime,
            ))
    if is_json:
        print json.dumps(dict(result=json_entries))
    else:
        print '\n'.join(result)

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
