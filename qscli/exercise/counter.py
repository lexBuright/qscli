from qscli.ipc import CliClient

class Counter(CliClient):
    def __init__(self):
        CliClient.__init__(self, ['qscount', 'daemon'])
