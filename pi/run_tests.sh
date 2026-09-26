#!/bin/sh
# Pi-side receiver test suite. Standard library only — no pytest, no numpy.
#
# Run from anywhere:  sh pi/run_tests.sh
set -e
cd "$(dirname "$0")"
exec python3 -m unittest discover -s tests -t . "$@"
