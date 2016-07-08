"Blocks of time with information associated with them. (start, end, info)"

import unittest

def blocks_duration(blocks):
    "Total time spent in blocks"
    duration = 0
    for start, end, _info in blocks:
        duration += end - start
    return duration

def blocks_interval_length(blocks):
    "Length of time covered by blocks"
    period_start = None
    for start, end, _info in blocks:
        if period_start is None:
            period_start = start
        period_end = end

    if period_start is None:
        return 0
    else:
        return period_end - period_start

# def split_block(block, left_length=None, right_length=None):
#     assert left_length is None or right_length is None
#     start, end, info = block

#     if left_length is not None:
#         assert left_length >= 0
#         if end - start <= left_length:
#             return (start, end, info), None
#         elif left_length < 0.00001:
#             return None, (start, end, info)
#         else:
#             return (start, start + left_length, info), (start + left_length, end, info)

#     elif right_length is not None:
#         assert right_length >= 0
#         if right_length < 0.00001 or end - start <= right_length:
#             return (start, end, info), None
#         else:
#             return (start, end - right_length, info), (end - right_length, end, info)

def split_block(block, split_point):
    start, end, info = block
    if split_point < start + EPSILON:
        return None, block
    elif split_point < end - EPSILON:
        return (start, split_point, info), (split_point, end, info)
    else:
        return (start, end, info), None

def interval_duration((start, end, _info)):
    return end - start

EPSILON = 0.0001

def remove_window_blocks(initial_window, new_start):
    window = list(initial_window)
    while window and blocks_start(window) < new_start:
        earliest_block = window.pop(0)
        _discard_block, kept_block = split_block(
            earliest_block, new_start)

        if kept_block:
            window.insert(0, kept_block)

    return window, initial_window if initial_window != window else None


def max_ignore_none(*args):
    return max(a for a in args if a is not None)

def min_ignore_none(*args):
    return min(a for a in args if a is not None)

def block_start((start, end, info)):
    return start

def blocks_start(blocks):
    assert blocks
    return block_start(blocks[0])

def period_windows(blocks, period):
    "Returns collections of blocks that span periods"
    window = []
    i = 0
    for block in blocks:
        while block:
            # Free up space until new blocks fit
            if window and block_start(block) - period < blocks_start(window):
                window, result = remove_window_blocks(window, new_start=block_start(block) - period)
                if result is not None:
                    yield result

            # ... now block now fits

            # Split up the block so it fits into the period
            split_point = min_ignore_none(blocks_start(window) + period if window else None, block_start(block) + period)
            inserted_block, remaining_block = split_block(block, split_point)

            if inserted_block:
                window.append(inserted_block)
                block = remaining_block
                continue
            else:
                # Push new blocks into the window
                new_start = min(block_end(window[0]) if window else None, block_end(block) - period)
                window, result = remove_window_blocks(window, new_start=new_start)
                if result is not None:
                    yield result

    yield list(window)

def block_duration((start, end, info)):
    assert end > start
    return end - start

def block_end((start, end, info)):
    assert end > start
    return end

class TestBlocks(unittest.TestCase):
    def test_contiguous_blocks(self):
        blocks = [
            (0.0, 0.5, 1),
            (0.5, 1.3, 2),
            (1.3, 2.8, 3),
            (2.8, 3.0, 3),
            (3.0, 3.2, 4),
        ]

        for block_set in period_windows(blocks, 1):
            self.assertAlmostEqual(blocks_interval_length(block_set), 1.0)

        start, end, _ = block_set[-1]
        self.assertAlmostEqual(end, 3.2)

    def test_period_window(self):
        blocks = [
            (0.0, 0.5, 1),
            (0.5, 1.3, 2),
            (1.3, 2.8, 3),
            (3.0, 3.2, 4),
        ]

        for block_set in period_windows(blocks, 1):
            if block_set[-1][1] != 2.8:
                self.assertAlmostEqual(blocks_interval_length(block_set), 1.0)

        start, end, _ = block_set[-1]

    def test_splitting(self):
        blocks = [(0.0, 5.2, 1)]
        self.assertEquals(
            list(period_windows(blocks, 1)),
            [[(0.0, 1.0, 1)], [(1.0, 2.0, 1)], [(2.0, 3.0, 1)], [(3.0, 4.0, 1)], [(4.0, 5.0, 1)], [(4.2, 5.0, 1), (5.0, 5.2, 1)]])


if __name__ == '__main__':
	unittest.main()
