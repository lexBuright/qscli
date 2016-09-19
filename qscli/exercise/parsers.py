from . import const

def days_ago_option(parser):
    parser.add_argument(
        'days_ago',
        type=int,
        help='How many days ago to compare to',
        nargs='?')

def exercise_prompt(parser, required=True):
    exercise = parser.add_mutually_exclusive_group(required=required)
    exercise.add_argument('--exercise', type=str)
    exercise.add_argument('--prompt-for-exercise', dest='exercise', action='store_const', const=const.PROMPT, help='Prompt for the exercise with a graphical pop up')
