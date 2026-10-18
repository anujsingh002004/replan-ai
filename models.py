"""Small, beginner-friendly data model for planner tasks."""

from dataclasses import dataclass
from datetime import datetime, time
from uuid import uuid4


PRIORITY_LABELS = {1: "High", 2: "Medium", 3: "Low"}


@dataclass
class Task:
    title: str
    duration_minutes: int
    priority: int
    deadline: datetime
    flexible: bool = True
    preferred_start: time | None = None
    completed: bool = False
    task_id: str = ""

    def __post_init__(self) -> None:
        if not self.task_id:
            self.task_id = str(uuid4())

    def validate(self) -> list[str]:
        errors = []
        if not self.title.strip():
            errors.append("Task title cannot be empty.")
        if self.duration_minutes <= 0:
            errors.append("Duration must be greater than zero.")
        if self.priority not in PRIORITY_LABELS:
            errors.append("Choose a valid priority.")
        if not self.flexible and self.preferred_start is None:
            errors.append("A fixed task needs a preferred start time.")
        return errors
