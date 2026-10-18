"""Deterministic scheduling and day-rescue logic; no network or AI calls."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from models import PRIORITY_LABELS, Task


@dataclass
class ScheduleItem:
    task: Task
    start: datetime | None
    end: datetime | None
    reason: str

    @property
    def scheduled(self) -> bool:
        return self.start is not None and self.end is not None


def _day_window(day: date, start_time: time, end_time: time) -> tuple[datetime, datetime]:
    start = datetime.combine(day, start_time)
    end_day = day + timedelta(days=1) if end_time < start_time else day
    return start, datetime.combine(end_day, end_time)


def _fits_before_deadline(task: Task, start: datetime, end: datetime) -> bool:
    return task.deadline >= end


def _find_gap(
    duration: timedelta,
    earliest: datetime,
    latest_end: datetime,
    busy: list[tuple[datetime, datetime]],
) -> tuple[datetime, datetime] | None:
    cursor = earliest
    for busy_start, busy_end in sorted(busy):
        if busy_end <= cursor:
            continue
        candidate_end = cursor + duration
        if candidate_end <= busy_start and candidate_end <= latest_end:
            return cursor, candidate_end
        if busy_start < candidate_end:
            cursor = max(cursor, busy_end)
        if cursor + duration > latest_end:
            return None
    candidate_end = cursor + duration
    if candidate_end <= latest_end:
        return cursor, candidate_end
    return None


def schedule_tasks(
    tasks: list[Task],
    day: date,
    start_time: time,
    end_time: time,
    breaks: list[tuple[datetime, datetime]] | None = None,
) -> list[ScheduleItem]:
    """Place fixed tasks first, then fit flexible tasks by deadline and priority."""
    window_start, window_end = _day_window(day, start_time, end_time)
    busy = [
        (max(start, window_start), min(end, window_end))
        for start, end in (breaks or [])
        if start < window_end and end > window_start and start < end
    ]
    items: dict[str, ScheduleItem] = {}
    pending = [task for task in tasks if not task.completed]

    for task in pending:
        errors = task.validate()
        if errors:
            items[task.task_id] = ScheduleItem(task, None, None, errors[0])
        elif task.deadline < window_start:
            items[task.task_id] = ScheduleItem(task, None, None, "Deadline has already passed.")

    if window_start == window_end:
        for task in pending:
            items.setdefault(
                task.task_id,
                ScheduleItem(task, None, None, "The available time window is empty."),
            )
        return [items[task.task_id] for task in pending]

    fixed_tasks = [
        task for task in pending
        if task.task_id not in items and not task.flexible
    ]
    fixed_tasks.sort(key=lambda task: (task.preferred_start or start_time, task.deadline, task.priority))
    for task in fixed_tasks:
        task_start = datetime.combine(day, task.preferred_start)
        if task_start < window_start:
            task_start += timedelta(days=1)
        task_end = task_start + timedelta(minutes=task.duration_minutes)
        if task_start < window_start or task_end > window_end:
            items[task.task_id] = ScheduleItem(task, None, None, "Fixed time is outside the available day.")
        elif not _fits_before_deadline(task, task_start, task_end):
            items[task.task_id] = ScheduleItem(task, None, None, "Cannot finish before its deadline at the fixed time.")
        elif any(task_start < busy_end and task_end > busy_start for busy_start, busy_end in busy):
            items[task.task_id] = ScheduleItem(task, None, None, "Fixed time overlaps a break or another fixed task.")
        else:
            items[task.task_id] = ScheduleItem(task, task_start, task_end, "Kept at its fixed time.")
            busy.append((task_start, task_end))

    flexible_tasks = [
        task for task in pending
        if task.task_id not in items and task.flexible
    ]
    flexible_tasks.sort(
        key=lambda task: (
            task.deadline,
            task.priority,
            -task.duration_minutes,
            task.title.casefold(),
            task.task_id,
        )
    )
    for task in flexible_tasks:
        latest_end = min(window_end, task.deadline)
        slot = _find_gap(
            timedelta(minutes=task.duration_minutes),
            window_start,
            latest_end,
            busy,
        )
        if slot is None:
            reason = (
                "No available time remains."
                if not busy and window_start + timedelta(minutes=task.duration_minutes) > latest_end
                else "No contiguous free slot fits before the deadline."
            )
            items[task.task_id] = ScheduleItem(task, None, None, reason)
        else:
            task_start, task_end = slot
            busy.append((task_start, task_end))
            items[task.task_id] = ScheduleItem(
                task,
                task_start,
                task_end,
                f"Scheduled by {PRIORITY_LABELS[task.priority].lower()} priority and deadline.",
            )

    return [items[task.task_id] for task in pending]


def rescue_day(
    tasks: list[Task],
    previous_schedule: list[ScheduleItem],
    day: date,
    new_start_time: time,
    end_time: time,
    lost_minutes: int,
    breaks: list[tuple[datetime, datetime]] | None = None,
    unexpected_task: Task | None = None,
    day_start_time: time | None = None,
) -> list[ScheduleItem]:
    """Rebuild the remaining day and explain each move or postponement."""
    window_start_time = day_start_time or new_start_time
    window_start, window_end = _day_window(day, window_start_time, end_time)
    disruption_start = datetime.combine(day, new_start_time)
    if window_end.date() > day and new_start_time < window_start_time:
        disruption_start += timedelta(days=1)
    disruption_start = min(max(disruption_start, window_start), window_end)
    rescue_start = min(
        disruption_start + timedelta(minutes=max(0, lost_minutes)),
        window_end,
    )

    remaining = [task for task in tasks if not task.completed]
    if unexpected_task is not None and not unexpected_task.completed:
        remaining = [
            task for task in remaining if task.task_id != unexpected_task.task_id
        ]
        remaining.append(unexpected_task)

    if rescue_start >= window_end:
        old_by_id = {item.task.task_id: item for item in previous_schedule}
        return [
            ScheduleItem(
                task,
                None,
                None,
                (
                    "Postponed after the disruption: no available time remains in the day."
                    if old_by_id.get(task.task_id) is not None
                    and old_by_id[task.task_id].scheduled
                    else "No available time remains in the day after the disruption."
                ),
            )
            for task in remaining
        ]

    results = schedule_tasks(
        remaining,
        rescue_start.date(),
        rescue_start.time(),
        end_time,
        breaks=breaks,
    )
    old_by_id = {item.task.task_id: item for item in previous_schedule}
    has_unexpected = unexpected_task is not None

    for item in results:
        old = old_by_id.get(item.task.task_id)
        if not item.scheduled:
            if old is not None and old.scheduled:
                item.reason = f"Postponed after the disruption: {item.reason}"
            continue
        if has_unexpected and item.task.task_id == unexpected_task.task_id:
            item.reason = "Added as an unexpected task during rescue."
        elif old is not None and old.scheduled and item.start == old.start:
            item.reason = "Kept at its original time."
        elif old is not None and old.scheduled and old.start < rescue_start:
            item.reason = "Moved because the disruption removed its original time slot."
        elif old is not None and old.scheduled and item.start > old.start:
            item.reason = "Moved later to fit the remaining time after the disruption."
        elif old is not None and old.scheduled:
            item.reason = "Moved earlier to fit around the remaining schedule."
    return results
