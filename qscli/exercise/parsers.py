def days_ago_option(parser):
    parser.add_argument(
        'days_ago',
        type=int,
        help='How many days ago to compare to',
        nargs='?')
