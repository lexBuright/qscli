"Keep track of the activity that we are doing"

import json
import subprocess
import uuid

from . import data

class AlreadyStarted(Exception):
    pass

def get_activities():
    return data.Data.get_activities()

def start(name, info): # Only one activity with a name can be done at a time
    ident = str(uuid.uuid1())
    activity = dict(name=name, info=info, ident=ident)
    activities = data.Data.get_activities()
    if name in activities:
        raise AlreadyStarted()

    activities[name] = activity
    data.Data.set_activities(activities)
    subprocess.check_call(['qstimeseries', 'append', 'exercise.activity.start.event', '--string', json.dumps(activity), '--id', ident + ':start'])

def stop(name):
    activities = data.Data.get_activities()
    if name not in activities:
        # Silent ignoring errors in bad
        #   but being able to get your program
        #   in a pointless broken state is worse
        return


    activity = activities[name]
    ident = activity['ident']
    activities.pop(name)
    data.Data.set_activities(activities)
    subprocess.check_call(['qstimeseries', 'append', 'exercise.activity.stop.event', '--string', json.dumps(activity), '--id', ident + ':stop'])

def stop_all():
    activities = data.Data.get_activities()
    for name in activities:
        stop(name)
