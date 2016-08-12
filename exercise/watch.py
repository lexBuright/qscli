from ipc import CliClient

class Watch(CliClient):
    def __init__(self):
        CliClient.__init__(self, ['superwatch.sh', 'daemon'])
