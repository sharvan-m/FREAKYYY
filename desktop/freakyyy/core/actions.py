"""Structured actions and results shared by every part of Freakyyy Desktop."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class Outcome(str, Enum):
    COMPLETED = "COMPLETED"            # done and verified where possible
    OPENED = "OPENED"                  # a screen was opened; the user finishes it
    INFO = "INFO"
    NEEDS_PERMISSION = "NEEDS_PERMISSION"
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
    CLARIFY = "CLARIFY"                # Freakyyy needs one more detail
    UNKNOWN = "UNKNOWN"                # the request wasn't understood
    NOT_SUPPORTED = "NOT_SUPPORTED"
    FAILED = "FAILED"
    DEVICE_OFFLINE = "DEVICE_OFFLINE"


class Device(str, Enum):
    LAPTOP = "laptop"
    PHONE = "phone"
    BOTH = "both"


@dataclass
class Intent:
    """A parsed command: what to do, with which parameters, on which device."""
    name: str
    params: dict[str, Any] = field(default_factory=dict)
    device: Device = Device.LAPTOP
    text: str = ""                     # normalised command text (device phrase removed)

    @property
    def label(self) -> str:
        p = ", ".join(f"{k}={v}" for k, v in self.params.items() if v not in (None, ""))
        return f"{self.device.value.upper()} · {self.name}" + (f" ({p})" if p else "")


@dataclass
class Clarification:
    """A question with candidate answers; `resolve(answer_text)` returns a Result."""
    question: str
    options: list[str]
    resolve: Callable[[str], "Result | None"]


@dataclass
class Result:
    outcome: Outcome
    message: str
    spoken: str | None = None
    data: dict[str, Any] | None = None
    confirm: Callable[[], "Result"] | None = None   # runs on "yes"
    clarify: Clarification | None = None

    @property
    def speech(self) -> str:
        return self.spoken if self.spoken is not None else self.message


def done(msg: str, spoken: str | None = None, **data) -> Result:
    return Result(Outcome.COMPLETED, msg, spoken, data or None)


def opened(msg: str, spoken: str | None = None) -> Result:
    return Result(Outcome.OPENED, msg, spoken)


def info(msg: str, spoken: str | None = None, **data) -> Result:
    return Result(Outcome.INFO, msg, spoken, data or None)


def failed(msg: str, spoken: str | None = None) -> Result:
    return Result(Outcome.FAILED, msg, spoken)


def confirm(question: str, action: Callable[[], Result]) -> Result:
    return Result(Outcome.NEEDS_CONFIRMATION, question, confirm=action)


def clarify(question: str, options: list[str], resolve: Callable[[str], Result | None]) -> Result:
    return Result(Outcome.CLARIFY, question, clarify=Clarification(question, options, resolve))
