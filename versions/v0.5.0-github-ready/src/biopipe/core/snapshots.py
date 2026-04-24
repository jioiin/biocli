"""Time-Travel State Snapshots.

Allows the user (or Critic Agent) to rewind the SessionManager's history
to a specific iteration, throwing away hallucinated or erroneous tool calls
and retrying from a clean slate.
"""

from __future__ import annotations

import collections
import copy
from typing import Any

from .session import SessionManager


class TimeTravelDebugger:
    """Manages state snapshots for an ongoing agent session."""

    def __init__(self, session: SessionManager) -> None:
        self._session = session
        # iteration_number -> snapshot JSON
        self._snapshots: dict[int, dict[str, Any]] = {}
        # Simple ring buffer to prevent infinite memory usage if loop runs 1000s of times
        self._max_snapshots = 50

    def take_snapshot(self, iteration: int) -> None:
        """Serialize current session and store it for this iteration."""
        state = self._session.export()
        # Deep copy to ensure no reference leakage
        self._snapshots[iteration] = copy.deepcopy(state)

        # Evict oldest if exceeding limit
        if len(self._snapshots) > self._max_snapshots:
            oldest = min(self._snapshots.keys())
            del self._snapshots[oldest]

    def can_rewind(self, target_iteration: int) -> bool:
        """Check if a snapshot exists for the target iteration."""
        return target_iteration in self._snapshots

    def rewind(self, target_iteration: int) -> None:
        """Restore the session to the exact state it was at target_iteration."""
        if not self.can_rewind(target_iteration):
            raise ValueError(f"No snapshot found for iteration {target_iteration}")

        snapshot = self._snapshots[target_iteration]
        
        # In-place restore of the session manager
        restored_session = SessionManager.restore(snapshot)
        
        # Replace messages in the original session
        self._session._messages = list(restored_session.messages())
        
        # Delete future snapshots since we altered the timeline
        to_delete = [it for it in self._snapshots if it > target_iteration]
        for it in to_delete:
            del self._snapshots[it]
    
    def list_snapshots(self) -> list[int]:
        """Return available rewind points."""
        return sorted(list(self._snapshots.keys()))
