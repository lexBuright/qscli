import abc
import collections
import itertools

DataPoint = collections.namedtuple('DataPoint', 'time value id')


class GenericTimeseriesStore(object):
    __metaclass__ = abc.ABCMeta
    @abc.abstractmethod
    def get_has_ids(self, metric_data):
        raise NotImplementedError()

    @abc.abstractmethod
    def get_timeseries(self, metric_data):
        pass

    def get_last_values(self, metric_data, num, ident=None, id_series=None, ident_period=None, index=None):
        if index < 0:
            raise ValueError(index)

        has_ids = self.get_has_ids(metric_data)

        negative_index = -1 - index

        if has_ids:
            if ident is None:
                id_entries = sorted(self.get_timeseries(metric_data), key=lambda x: x.id)
                entries = id_entries[negative_index:negative_index - num:-1]
            else:
                before_id_entries = sorted([x for x in self.get_timeseries(metric_data) if x.id <= ident], key=lambda x: x.id)
                entries = before_id_entries[negative_index:negative_index - num:-1]
        else:
            if ident is not None:
                raise ValueError(ident)
            else:
                entries = self.get_timeseries(metric_data)[negative_index:negative_index - num:-1]

        if not has_ids and id_series:
            raise Exception('Can only use an ids_before_func when we have ids')

        if id_series:
            series = id_series(ident or entries[0]['id'], -ident_period)
            idents = itertools.islice(series, num)
            values_by_id = {e.id: e.value for e in entries}
            result = [values_by_id.get(ident, 0) for ident in idents]
            return result
        else:
            result = [e.value for e in entries]
            return result
