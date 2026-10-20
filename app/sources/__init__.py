"""One module per state portal, and SOURCES: each state's source, keyed by lower-case state code."""

from __future__ import annotations

from collections.abc import Callable

from sources.by import BySource
from sources.sn import SnSource
from state_sync import Source

SOURCES: dict[str, Callable[[], Source]] = {"by": BySource, "sn": SnSource}
