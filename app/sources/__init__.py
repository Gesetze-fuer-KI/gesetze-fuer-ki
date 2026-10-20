"""One module per state portal; importing this package registers each in state_sync.SOURCES."""

from __future__ import annotations

from sources import by
from state_sync import SOURCES

SOURCES["by"] = by.BySource
