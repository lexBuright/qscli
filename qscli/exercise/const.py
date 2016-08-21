
class Symbol(object):
    def __init__(self, name):
        self._name = name

    def __eq__(self, other):
        if isinstance(other, Symbol):
            return self._name == other._name
        else:
            return False

LAST = Symbol('LAST')
PROMPT = Symbol('PROMPT')
MISSING = object()
