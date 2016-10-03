"Functions to construct ids, for example for particular times"

import datetime
import itertools


def date_series(start, step):
    # Yes function does nothing
    #   but the name deserves to exist
    return itertools.count(start, step)

def iso_date_series(start, period):
    start_day = datetime.datetime.strptime(start, '%Y-%m-%d')
    for day in date_series(start_day, datetime.timedelta(days=period)):
        yield day.strftime('%Y-%m-%d')

def iso_hours_series(start, period):
    start_hour = datetime.datetime.strptime(start, '%Y-%m-%dT%H:%M:%S')
    for dt in date_series(start_hour, datetime.timedelta(hours=period)):
        yield dt.strftime('%Y-%m-%dT%H:%M:%S')

def iso_minutes_series(start, period):
    start_hour = datetime.datetime.strptime(start, '%Y-%m-%dT%H:%M:%S')
    for dt in date_series(start_hour, datetime.timedelta(seconds=-period * 60)):
        yield dt.strftime('%Y-%m-%dT%H:%M:%S')

def current_isodate(period, dt):
    # Start counting at the unix epoch
    count_start = datetime.date(1970, 1, 1)
    days = (dt.date() - count_start).total_seconds() / 86400
    result = count_start + datetime.timedelta(days=days // period * period)
    return result.isoformat()

def current_isohour(period, dt):
    # start counting from the beginning of the day
    count_start = dt.replace(hours=0, minutes=0, seconds=0, milliseconds=0)
    hours = (dt - count_start).total_seconds() / 3600
    result = count_start + datetime.timedelta(hours=hours // period * period)
    return result.isoformat()

def current_isominute(period, dt):
    count_start = dt.replace(hours=0, minutes=0, seconds=0, milliseconds=0)
    minutes = (dt - count_start).total_seconds() / 60
    result = count_start + datetime.timedelta(minutes=minutes // period * period)
    return result.isoformat()

# Return ids at a given time
TIME_ID_FUNC = {
    'isodate': current_isodate,
    'isohour': current_isohour,
    'isominute': current_isominute
}

# Produce a series of ids
ID_SERIES = {
    'isohour': iso_hours_series,
    'isodate': iso_date_series,
    'isominute': iso_minutes_series,
}




