class Histogram(object):
    def __init__(self, counts):
        self.counts = counts

    @classmethod
    def _inner_subtract(cls, pairs, other_pairs):
        # This is O(n**2) without yieldfrom
        if not other_pairs:
            for x in pairs:
                yield x
        elif not pairs:
            return
        elif pairs[0][1] == 0:
            for x in cls._inner_subtract(pairs[1:], other_pairs):
                yield x
        elif other_pairs[0][1] == 0:
            for x in cls._inner_subtract(pairs, other_pairs[1:]):
                yield x
        elif other_pairs[0] >= pairs[0]:
            new_pair = (pairs[0][0], max(0, pairs[0][1] - other_pairs[0][1]))
            new_other_pair = (other_pairs[0][0], max(0, other_pairs[0][1] - pairs[0][1]))
            for pair in cls._inner_subtract([new_pair] + pairs[1:], [new_other_pair] + other_pairs[1:]):
                yield pair
        else:
            yield pairs[0]
            for pair in cls._inner_subtract(pairs[1:], other_pairs):
                yield pair

    def subtract(self, histogram):
        "Histogram for time where we weren't travelling at a faster speed"
        pairs = sorted(self.counts.items(), reverse=True)
        other_pairs = sorted(histogram.counts.items(), reverse=True)
        return type(self)(dict(self._inner_subtract(pairs, other_pairs)))

    def quantile_at_value(self, target_value):
        cumsum = 0
        last_value, bottom_quantile = None, 0.0
        total = self.total()
        for value, count in sorted(self.counts.items()):
            cumsum += count
            top_quantile = float(cumsum) / total

            if value >= target_value:
                if last_value is None:
                    return 0.0
                else:
                    weight = float(target_value - value) / float(value - last_value)
                    return (1 - weight) * bottom_quantile + top_quantile * weight

            last_value = value
            bottom_quantile = top_quantile
        return 1.0

    def value_at_quantile(self, target_quantile):
        assert 0 <= target_quantile <= 1.0
        total = sum(self.counts.values())
        cumsum = 0.0
        bottom_quantile = 0.0
        if not self.counts:
            raise Exception('No data')
        for value, count in sorted(self.counts.items()):
            cumsum += count
            top_quantile = float(cumsum) / total

            if target_quantile >= bottom_quantile and target_quantile <= top_quantile:
                return value
        return value

    def empty(self):
        return not bool(self.counts)

    def values_at_quantiles(self, quantiles):
        return [self.value_at_quantile(quantile) for quantile in quantiles]

    def total(self):
        return sum(self.counts.values())

    def update(self, counts):
        for value, count in counts.items():
            if value not in self.counts:
                self.counts[value] = 0

            self.counts[value] += count
