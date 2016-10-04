import datetime
import re

def regexp_option(parser):
    parser.add_argument('--regex', '-x', type=re.compile, help='Only return entries whose metric name match this regexp')

def fuzzy_date(string):
    m = re.search(r'^(\d+)([mhsd])$', string)
    if m:
        count, unit = m.groups()
        if unit == 'd':
            round_now = datetime.datetime.now().replace(hour=0, second=0, microsecond=0)
        else:
            round_now = datetime.datetime.now()
        return round_now - int(count) * UNIT_SIZE[unit]
    elif re.search(r'^\d\d\d\d-\d\d-\d\d$', string):
        return datetime.datetime.strptime(string, '%Y-%m-%d').replace(hour=0, second=0, microsecond=0)
    else:
        # Ugg, ignore timezones
        return datetime.datetime.strptime(string, '%Y-%m-%dT%H:%M:%S')
