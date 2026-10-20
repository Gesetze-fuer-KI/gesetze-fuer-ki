"""One module per state portal, and SOURCES: each state's source, keyed by lower-case state code."""

from __future__ import annotations

from collections.abc import Callable

from sources.bb import BbSource
from sources.by import BySource
from sources.nw import NwSource
from sources.sn import SnSource
from state_sync import Source

SOURCES: dict[str, Callable[[], Source]] = {"bb": BbSource, "by": BySource, "nw": NwSource, "sn": SnSource}
