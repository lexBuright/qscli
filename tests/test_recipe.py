
import json
import pprint
import shutil
import tempfile
import unittest

from qscli.qsrecipe import qsrecipe


class TestRecipes(unittest.TestCase):
    def setUp(self):
        self.direc = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.direc)

    def run_cli(self, args):
        new_args = ('--config-dir', self.direc) + tuple(args)
        return qsrecipe.run(new_args)

    def test_list(self):
        self.run_cli(['add', 'breakfast', 'eat'])
        self.run_cli(['add', 'work', 'do'])
        self.run_cli(['add', 'lunch', 'eat'])
        self.run_cli(['add', 'drinks', 'drink'])
        self.run_cli(['add', 'bed', 'sleep'])
        lines = self.run_cli(['list']).splitlines()
        self.assertTrue([l.startswith('breakfast') for l in lines])
        self.assertTrue([l.startswith('work') for l in lines])
        self.assertTrue([l.startswith('lunch') for l in lines])
        self.assertTrue([l.startswith('drinks') for l in lines])
        self.assertTrue([l.startswith('bed') for l in lines])

    def test_delete(self):
        self.run_cli(['add', 'recipe1', 'eat'])
        self.run_cli(['add', 'recipe2', 'do'])
        self.run_cli(['delete', 'recipe1'])
        result = self.run_cli(['list'])
        self.assertTrue('recipe1' not in result)
        self.assertTrue('recipe2' in result)

    def test_edit(self):
        self.run_cli(['add', 'recipe1', 'Step1'])
        self.run_cli(['add', 'recipe1', 'Step2', '--time', '+10s'])
        self.run_cli(['add', 'recipe1', 'Step3', '--time', '+10s'])

        self.run_cli(['edit', 'recipe1', '--index', '1', '--before', '5s', '--after', '15s', '--text', 'Step two'])

        recipe = json.loads(self.run_cli(['show', 'recipe1', '--json']))
        self.assertEquals(recipe['steps'][1]['start_offset'], 5)
        self.assertEquals(recipe['steps'][2]['start_offset'], 20)
        self.assertEquals(recipe['steps'][1]['text'], 'Step two')

    def test_edit_final(self):
        self.run_cli(['add', 'recipe1', 'Step1'])
        self.run_cli(['add', 'recipe1', 'Step2', '--time', '+10s'])
        self.run_cli(['add', 'recipe1', 'Step3', '--time', '+10s'])

        self.run_cli(['edit', 'recipe1', '--index', '2', '--before', '5s'])
        recipe = json.loads(self.run_cli(['show', 'recipe1', '--json']))
        self.assertEquals(recipe['steps'][-1]['start_offset'], 15)

    def test_show(self):
        self.run_cli(['add', 'omelete', 'break eggs'])
        self.run_cli(['add', 'omelete', 'Whisk', '--time', '+10s'])
        self.run_cli(['add', 'omelete', 'Add oil', '--time', '+5s'])
        self.run_cli(['add', 'omelete', 'Heat pan', '--time', '+5s'])
        self.run_cli(['add', 'omelete', 'Add eggs', '--time', '+2m'])
        self.run_cli(['add', 'omelete', 'Finished', '--time', '+3m'])

        expected = [
            dict(start_offset=0, text='break eggs'),
            dict(start_offset=10, text='Whisk'),
            dict(start_offset=15, text='Add oil'),
            dict(start_offset=20, text='Heat pan'),
            dict(start_offset=140, text='Add eggs'),
            dict(start_offset=320, text='Finished'),
        ]

        json_data = json.loads(self.run_cli(['show', 'omelete', '--json']))

        steps = [{k:step[k] for k in ("text", "start_offset")} for step in json_data['steps']]

        self.assertEquals(expected, steps)

    # def test_playback(self):
    #     self.run_cli(['add', 'recipe', 'start'])
    #     self.run_cli(['add', 'recipe', 'step 1', '--time', '+1s'])
    #     self.run_cli(['add', 'recipe', 'step 2', '--time', '+2s'])

    #     def read(it):
    #         return next(it)

    #     it = peak_iter(self.run_cli(['play', 'recipe']))
    #     self.assertEquals(read(it), 'start')
    #     self.set_time(1.1)
    #     self.assertEquals(read(it), 'step 1')
    #     self.set_time(2)
    #     self.assertEquals(read(it), None)
    #     self.set_time(3.1)
    #     self.assertEquals(read(it), 'step 2')


if __name__ == '__main__':
    unittest.main()
