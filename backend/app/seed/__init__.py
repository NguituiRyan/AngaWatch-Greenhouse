"""Demo seed + scripted demo for AngaWatch.

* :mod:`app.seed.constants` — the single source of truth for the demo dataset
  (org slug, Nakuru farm, GH-1, devices, users, the tomato crop). The simulator
  package keeps matching copies of a couple of these on purpose.
* :mod:`app.seed.seed` — ``python -m app.seed.seed``: idempotently create the
  whole demo hierarchy + ~36 h of NORMAL history via a sync session.
* :mod:`app.seed.demo` — ``python -m app.seed.demo``: the narrated, end-to-end
  hackathon story (detect → advise → act → resolve).
"""

from __future__ import annotations
