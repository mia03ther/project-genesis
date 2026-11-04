"""The GENESIS Security Lab: playable missions on top of the scenario harness.

- ``policies``  the validation strategies a player can choose (fixed, server-side)
- ``content``   mission content: briefing, evidence, hints, choices
- ``session``   the mission state machine: investigate, choose, replay, reset
- ``api``       a FastAPI application exposing only predefined mission actions
- ``__main__``  ``python -m genesis.lab``: serve the API (and the built frontend)

The harness stays the authoritative execution engine: the lab never talks to
the chain except through ``genesis.harness``. Requires the optional ``lab``
extra (FastAPI and uvicorn) for the API; everything else is standard library.
"""
