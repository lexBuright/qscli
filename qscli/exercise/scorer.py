from qscli.ipc import CliClient

class Scorer(CliClient):
    def __init__(self):
        CliClient.__init__(self, ['qsscore', 'daemon'])
