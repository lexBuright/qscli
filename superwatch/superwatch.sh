#!/bin/bash
set -o errexit
set -o nounset
set -o pipefail

here=$(dirname ${BASH_SOURCE[0]})
PYTHONPATH=${PYTHONPATH:-}:$here
export PYTHONPATH

python -m superwatch "$@"
