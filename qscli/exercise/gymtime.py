import json

from .data import WATCH, SCORER

def add_subparser(parser):
    sub = parser.add_subparsers(dest='gymtime_action')

    sub.add_parser('arrive', help='Record arrival at gym')
    sub.add_parser('leave', help='Record leaving the gym')
    sub.add_parser('toggle', help='Record arriving or leaving the gym')
    sub.add_parser('show', help='Show current amount of time at the gym')

def run(args):
    if args.gymtime_action == 'arrive':
        return arrive()
    elif args.gymtime_action == 'leave':
        return leave()
    elif args.gymtime_action == 'show':
        return show()
    elif args.gymtime_action == 'toggle':
        return toggle()
    else:
        raise ValueError(args.rep_action)

def update():
    duration = json.loads(WATCH.get().run(['show', 'exercise.gymtime', '--json']))['duration']
    SCORER.get().run(['update', 'exercise.score.gymtime', str(duration)])

def show():
    update()
    return SCORER.get().run(['summary', 'exercise.score.gymtime']).encode('utf8')

def arrive():
    WATCH.get().run(['start', 'exercise.gymtime'])
    SCORER.get().run(['store', 'exercise.score.gymtime', '0'])
    return 'Arrived at gym'

def leave():
    time_at_gym = json.loads(WATCH.get().run(['show', 'exercise.gymtime', '--json']))['duration']
    update()
    summary = SCORER.get().run(['summary', 'exercise.score.gymtime'])
    hours_at_gym = time_at_gym // 3600
    seconds_at_gym = time_at_gym % 3600

    WATCH.get().run(['stop', 'exercise.gymtime'])
    return u'Left gym: {}h {}s\n{}'.format(hours_at_gym, seconds_at_gym, summary).encode('utf8')

def timeseries():
    update()
    result = []
    entries = json.loads(SCORER.get().run(['log', '--regex', '^exercise.score.gymtime$', '--json']))
    for entry in reversed(entries):
        result.append('{:.1f}'.format(entry['value']))
    return ' '.join(result)
        

def toggle():
    data = json.loads(WATCH.get().run(['show', 'exercise.gymtime', '--json']))
    if data['running']:
        return leave()
    else:
        return arrive()
