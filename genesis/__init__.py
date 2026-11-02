"""Project GENESIS: a deterministic, programmable civilization simulation.

Modules, by responsibility:

- ``models``       plain data types shared by every layer
- ``world``        authoritative world state and world creation
- ``agents``       the agent decision interface and built-in policies
- ``economy``      production, consumption, order validation, market clearing
- ``simulation``   the daily loop that turns agent proposals into state changes
- ``invariants``   accounting and consistency checks
- ``persistence``  versioned SQLite save files
- ``reporting``    text summaries and JSON/CSV experiment reports
- ``cli``          the command-line interface
"""

__version__ = "0.1.0"
