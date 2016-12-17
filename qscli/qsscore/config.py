"Configuration of qsscore as a whole and particular metrics"

from . import ts_store

def get_metric_data(data, metric):
    metrics = data.setdefault('metrics', dict())
    metric_data = metrics.setdefault(metric, dict() )
    metric_data['name'] = metric
    ts_store.init(metric_data)
    return metric_data

def config(metric_data, ident_type, ident_period):
    if ident_type is not None:
        metric_data['ident_type'] = ident_type
    if ident_period is not None:
        metric_data['ident_period'] = ident_period
    return ''
