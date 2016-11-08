"A store for timeseries that keeps data in the configuration file"

import time

from .generic_store import DataPoint, GenericTimeseriesStore

class NativeTimeSeriesStore(GenericTimeseriesStore):
    def __init__(self, config_dir):
        del config_dir

    @staticmethod
    def initialize(metric_data):
        metric_data.setdefault('values', [])

    @staticmethod
    def get_timeseries(metric_data):
        return [DataPoint(time=value['time'], value=value['value'], id=i) for i, value in enumerate(metric_data['values'])]

    @staticmethod
    def _get_values(metric_data):
        return metric_data['values']

    @staticmethod
    def get_raw_values(metric_data):
        return [entry['value'] for entry in metric_data['values']]

    @staticmethod
    def delete_ids(metric_data, ids):
        for index in sorted(ids, reverse=True):
            metric_data['values'].pop(index) # unnecessary O(n**2)

    @staticmethod
    def get_ids_values(metric_data):
        return [entry['id'] for entry in metric_data['values'] if entry['id'] is not None]

    @staticmethod
    def num_values(metric_data):
        return len(metric_data['values'])

    @staticmethod
    def get_has_ids(metric_data):
        return any(entry.get('id') for entry in metric_data['values'])

    @staticmethod
    def check_if_empty(metric_data):
        return metric_data['values']

    @classmethod
    def get_value(cls, metric_data, ident=None, index=0):
        values = cls.get_last_values(metric_data, 1, ident, index=index)
        return values[0] if values else None

    @staticmethod
    def store(metric_data, time, value):
        metric_data['values'].append(dict(time=time, value=value))

    @staticmethod
    def update_ids(metric_data, value_by_id):
        "Upsert values by id"
        updated = set()
        for entry in metric_data['values']:
            entry_id = entry.get('id')
            if entry_id is not None:
                if entry_id in value_by_id:
                    entry['value'] = float(value_by_id[entry_id])
                    entry['time'] = time.time()
                    updated.add(entry_id)

        for ident, value in value_by_id.items():
            if ident in updated:
                continue
            else:
                metric_data['values'].append(dict(time=time.time(), id=ident, value=float(value)))
        return ''

    @classmethod
    def update(cls, metric_data, value, ident):
        cls.initialize(metric_data)

        entry = dict(time=time.time(), value=value)
        if ident is not None:
            entry['id'] = ident

        metric_values = metric_data['values']

        if not metric_values:
            metric_values.append(entry)

        if ident is not None:
            ident_entries = [x for x in metric_values if x.get('id') == ident]
            if ident_entries:
                ident_entry, = ident_entries
                ident_entry['value'] = value
            else:
                metric_values.append(entry)
        else:
            metric_values[-1] = entry
        return ''
