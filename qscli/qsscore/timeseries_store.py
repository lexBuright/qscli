"Store timeseries using qstimeseries"

import itertools
import json
import subprocess
import logging

from .generic_store import DataPoint, GenericTimeseriesStore
from .. import ipc

LOGGER = logging.getLogger('timeseries_store')

class TimeSeriesStore(GenericTimeseriesStore):
    def __init__(self, config_dir):
        self._config_dir = config_dir
        self._client = None

    @staticmethod
    def initialize(metric_data):
        del metric_data
        return

    def get_timeseries(self, metric_data):
        metric_name = metric_data['name']
        raw_result = self.timeseries('show', '--series', metric_name, '--json')
        LOGGER.debug('RAW RESULT %r', raw_result)
        series_entries = json.loads(raw_result)
        return [DataPoint(time=entry['time'], value=entry['value'], id=entry['id']) for entry in series_entries]

    def get_raw_values(self, metric_data):
        return [d.value for d in self.get_timeseries(metric_data)]

    def num_values(self, metric_data):
        return len(self.get_timeseries(metric_data))

    def _get_values(self, metric_data):
        return [d.value for d in self.get_timeseries(metric_data)]

    def store(self, metric_data, time, value):
        return self.timeseries('append', '--time', time, metric_data['name'], value)

    def check_if_empty(self, metric_data):
        values = self.get_timeseries(metric_data)
        return not bool(values)

    def get_value(self, metric_data, ident=None, index=None):
        if ident is not None and index is not None:
            raise ValueError((ident, index))

        if ident is None:
            index = -1

        if index:
            return json.loads(self.timeseries('show', '--series', metric_data['name'], '--index', index, '--json'))[0]['value']
        else:
            raw_json = self.timeseries('show', '--series', metric_data['name'], '--id', ident, '--json')
            print 'Raw result', raw_json
            return json.loads(raw_json)[0]['value']

    def timeseries(self, *args):
        if self._client is None:
            self._client = ipc.CliClient(['qstimeseries', '--config-dir', self._config_dir])
            self._client.initialize()
        self._client.run(map(str, args))

    def get_has_ids(self, metric_data):
        return any(not entry.id.startswith('internal--') for entry in self.get_timeseries(metric_data))

    def update(self, metric_data, value, ident, time=None):
        if time:
            time_args = ['--time', time]
        else:
            time_args = []

        self.timeseries('append', metric_data['name'], '--id', ident, '--update', value, *time_args)

    def update_ids(self, metric_data, values_by_id):
        for ident, value in values_by_id.items():
            LOGGER.debug('Setting %r %r %r', metric_data, value, ident)
            self.update(metric_data, value, ident)

    def delete_ids(self, metric_data, ids):
        id_args = list(itertools.chain.from_iterable([('--id', ident) for ident in ids]))
        print 'ID_ARGS', id_args, ids
        self.timeseries('show', '--series', metric_data['name'], '--delete',  *id_args)


def shell_collect(command):
    print 'running', ' '.join(command)
    process = subprocess.Popen(command, stdout=subprocess.PIPE)
    stdout, _ = process.communicate()
    if process.returncode != 0:
        raise ValueError(process.returncode)
    return stdout
