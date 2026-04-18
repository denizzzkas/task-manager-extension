"""Task Planner v1.0.0 · Task management with deadlines and reminders."""
from __future__ import annotations

import sys, os
_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _dir)

for _m in [k for k in sys.modules if k in (
    "app", "handlers_tasks", "skeleton", "panels",
)]:
    del sys.modules[_m]

from app import ext, chat  # noqa: F401
import handlers_tasks       # noqa: F401
import skeleton             # noqa: F401
import panels               # noqa: F401
