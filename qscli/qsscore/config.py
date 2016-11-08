"Configuration of qsscore as a whole and particular metrics"

class Config(object):
    def __init__(self, ts_store):
        self._ts_store = ts_store

    def get_metric_data(self, data, metric_name):
        metrics = data.setdefault('metrics', dict())
        metric_data = metrics.setdefault(metric_name, dict(name=metric_name))
        self._ts_store.initialize(metric_data)
        return metric_data

    def config(self, metric_data, ident_type, ident_period):
        if ident_type is not None:
            metric_data['ident_type'] = ident_type
        if ident_period is not None:
            metric_data['ident_period'] = ident_period
        return ''
