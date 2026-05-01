# src/biopipe/core/pulse_engine.py
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Awaitable, Optional, Any
from datetime import datetime
from collections import deque
import uuid

class PulseState(Enum):
    IDLE = auto()
    GATHER = auto()
    ACTION = auto()
    VERIFY = auto()
    AUDIT = auto()
    PAUSED = auto()
    COMPLETE = auto()
    ERROR = auto()

class PulseEvent(Enum):
    START = auto()
    INPUT_READY = auto()
    EXECUTE = auto()
    RESULT_READY = auto()
    VERIFY_SUCCESS = auto()
    VERIFY_FAILURE = auto()
    PAUSE = auto()
    RESUME = auto()
    RESET = auto()
    ABORT = auto()
    RETRY = auto()

@dataclass
class PulseContext:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = field(default_factory=datetime.now)
    data: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def extend(self, **kwargs) -> "PulseContext":
        return PulseContext(
            id=self.id,
            timestamp=datetime.now(),
            data={**self.data, **kwargs.get("data", {})},
            metadata={**self.metadata, **kwargs.get("metadata", {})},
        )

class PulseObserver(ABC):
    @abstractmethod
    async def on_state_change(self, engine: "PulseEngine", old_state: PulseState, new_state: PulseState, context: PulseContext) -> None:
        pass

class AsyncQueueBridge:
    def __init__(self, maxsize: int = 100):
        self._queue = asyncio.Queue(maxsize=maxsize)
        self._subscribers = []

    async def emit(self, event: PulseEvent, context: PulseContext) -> None:
        try:
            self._queue.put_nowait((event, context))
        except asyncio.QueueFull:
            pass
        for queue in self._subscribers:
            try:
                queue.put_nowait((event, context))
            except asyncio.QueueFull:
                pass

class PulseEngine:
    def __init__(self):
        self._state = PulseState.IDLE
        self._previous_state = None
        self._context = PulseContext()
        self._observers = []
        self._bridge = AsyncQueueBridge()
        self._lock = asyncio.Lock()

    @property
    def state(self) -> PulseState:
        return self._state

    def add_observer(self, observer: PulseObserver) -> None:
        self._observers.append(observer)

    async def emit_event(self, event: PulseEvent, **context_updates) -> None:
        async with self._lock:
            old_state = self._state
            self._context = self._context.extend(**context_updates)
            new_state = self._resolve_transition(self._state, event)
            self._previous_state = self._state
            self._state = new_state
            if new_state != old_state:
                for obs in self._observers:
                    await obs.on_state_change(self, old_state, new_state, self._context)
            await self._bridge.emit(event, self._context)

    def _resolve_transition(self, current: PulseState, event: PulseEvent) -> PulseState:
        transitions = {
            (PulseState.IDLE, PulseEvent.START): PulseState.GATHER,
            (PulseState.GATHER, PulseEvent.INPUT_READY): PulseState.ACTION,
            (PulseState.ACTION, PulseEvent.RESULT_READY): PulseState.VERIFY,
            (PulseState.VERIFY, PulseEvent.VERIFY_SUCCESS): PulseState.AUDIT,
            (PulseState.AUDIT, PulseEvent.COMPLETE): PulseState.COMPLETE,
        }
        return transitions.get((current, event), current)
