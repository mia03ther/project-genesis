"""Run Project GENESIS from a source checkout: ``python main.py <command>``.

Equivalent to ``python -m genesis`` or, after ``pip install -e .``, ``genesis``.
Try ``python main.py demo`` for a 100-day demonstration.
"""

import sys

from genesis.cli import main

if __name__ == "__main__":
    sys.exit(main())
