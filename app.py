"""RePlan AI: a local, API-free daily planner."""

from datetime import date, datetime, time, timedelta

import plotly.express as px
import pandas as pd
import streamlit as st

from models import PRIORITY_LABELS, Task
from planner import ScheduleItem, rescue_day, schedule_tasks


st.set_page_config(page_title="RePlan AI", page_icon="🗓️", layout="wide")
st.title("RePlan AI")
st.caption("The self-repairing day — plan calmly, then adapt when life happens.")

if "tasks" not in st.session_state:
    st.session_state.tasks = []
if "schedule" not in st.session_state:
    st.session_state.schedule = []
if "schedule_day" not in st.session_state:
    st.session_state.schedule_day = date.today()
if "has_schedule" not in st.session_state:
    st.session_state.has_schedule = False


def clear_schedule() -> None:
    st.session_state.schedule = []
    st.session_state.has_schedule = False


def task_form_fields(key: str, task: Task | None = None) -> dict:
    task = task or Task("", 30, 2, datetime.combine(date.today(), time(17, 0)))
    title = st.text_input("Task", value=task.title, key=f"{key}_title")
    duration = st.number_input(
        "Duration (minutes)", min_value=1, max_value=1440,
        value=max(1, task.duration_minutes), step=5, key=f"{key}_duration",
    )
    priority_name = st.selectbox(
        "Priority",
        options=["High", "Medium", "Low"],
        index={1: 0, 2: 1, 3: 2}.get(task.priority, 1),
        key=f"{key}_priority",
    )
    deadline_date = st.date_input(
        "Deadline date", value=task.deadline.date(), key=f"{key}_deadline_date"
    )
    deadline_time = st.time_input(
        "Deadline time", value=task.deadline.time(), key=f"{key}_deadline_time"
    )
    flexible = st.checkbox(
        "Flexible (uncheck to reserve a fixed time)",
        value=task.flexible,
        key=f"{key}_flexible",
    )
    preferred_start = None
    if not flexible:
        preferred_start = st.time_input(
            "Fixed start time",
            value=task.preferred_start or time(9, 0),
            key=f"{key}_fixed_start",
        )
    return {
        "title": title,
        "duration_minutes": int(duration),
        "priority": {"High": 1, "Medium": 2, "Low": 3}[priority_name],
        "deadline": datetime.combine(deadline_date, deadline_time),
        "flexible": flexible,
        "preferred_start": preferred_start,
    }


def save_task(values: dict, existing: Task | None = None) -> Task:
    task = Task(**values, task_id=existing.task_id if existing else "")
    errors = task.validate()
    if errors:
        raise ValueError(" ".join(errors))
    return task


with st.sidebar:
    st.header("Your day")
    planning_day = st.date_input("Plan date", value=date.today())
    day_start = st.time_input("Day starts", value=time(8, 0))
    day_end = st.time_input("Day ends", value=time(21, 0))
    use_break = st.checkbox("Add a break")
    break_start = break_end = None
    if use_break:
        break_start = st.time_input("Break starts", value=time(12, 0))
        break_end = st.time_input("Break ends", value=time(13, 0))
    if st.button("Create my schedule", type="primary", use_container_width=True):
        if day_start == day_end:
            st.error("Choose different start and end times.")
        elif use_break and break_start == break_end:
            st.error("Choose different break start and end times.")
        else:
            breaks = []
            if use_break:
                b_start = datetime.combine(planning_day, break_start)
                b_end_day = planning_day + timedelta(days=1) if break_end <= break_start else planning_day
                breaks = [(b_start, datetime.combine(b_end_day, break_end))]
            st.session_state.schedule = schedule_tasks(
                st.session_state.tasks, planning_day, day_start, day_end, breaks
            )
            st.session_state.schedule_day = planning_day
            st.session_state.has_schedule = True
            st.session_state.breaks = breaks
            st.session_state.day_end = day_end
            st.session_state.day_start = day_start
            st.rerun()

left, right = st.columns([1, 1])
with left:
    st.subheader("Add a task")
    with st.form("add_task_form", clear_on_submit=True):
        new_values = task_form_fields("new")
        if st.form_submit_button("Add task"):
            try:
                st.session_state.tasks.append(save_task(new_values))
                clear_schedule()
                st.rerun()
            except ValueError as error:
                st.error(str(error))

with right:
    st.subheader("Your tasks")
    if not st.session_state.tasks:
        st.info("Add a task to get started.")
    for task in list(st.session_state.tasks):
        status = "Done" if task.completed else "Overdue" if task.deadline < datetime.now() else "Pending"
        with st.expander(f"{'✅' if task.completed else '•'} {task.title} — {status}"):
            with st.form(f"edit_{task.task_id}"):
                values = task_form_fields(f"edit_{task.task_id}", task)
                submitted = st.form_submit_button("Save changes")
                if submitted:
                    try:
                        updated = save_task(values, task)
                        st.session_state.tasks = [
                            updated if existing.task_id == task.task_id else existing
                            for existing in st.session_state.tasks
                        ]
                        clear_schedule()
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))
            action_col, delete_col = st.columns(2)
            if action_col.button(
                "Mark pending" if task.completed else "Complete",
                key=f"complete_{task.task_id}",
            ):
                task.completed = not task.completed
                clear_schedule()
                st.rerun()
            if delete_col.button("Delete", key=f"delete_{task.task_id}"):
                st.session_state.tasks = [
                    existing for existing in st.session_state.tasks
                    if existing.task_id != task.task_id
                ]
                clear_schedule()
                st.rerun()
            st.caption(
                f"{task.duration_minutes} min · {PRIORITY_LABELS[task.priority]} priority · "
                f"Due {task.deadline:%b %d, %I:%M %p} · "
                f"{'Flexible' if task.flexible else 'Fixed'}"
            )

st.divider()
st.subheader("Today at a glance")
pending_tasks = [task for task in st.session_state.tasks if not task.completed]
overdue_count = sum(task.deadline < datetime.now() for task in pending_tasks)
scheduled_count = sum(item.scheduled for item in st.session_state.schedule)
metric_cols = st.columns(4)
metric_cols[0].metric("Tasks", len(st.session_state.tasks))
metric_cols[1].metric("Completed", sum(task.completed for task in st.session_state.tasks))
metric_cols[2].metric("Scheduled", scheduled_count)
metric_cols[3].metric("Overdue", overdue_count)
if overdue_count:
    st.warning(f"{overdue_count} pending task(s) are overdue.")

if st.session_state.has_schedule:
    st.subheader("Your schedule")
    scheduled = [item for item in st.session_state.schedule if item.scheduled]
    unscheduled = [item for item in st.session_state.schedule if not item.scheduled]
    if unscheduled:
        st.warning(f"{len(unscheduled)} task(s) do not fit in the available day.")
    if scheduled:
        chart_rows = [
            {
                "Task": item.task.title,
                "Start": item.start,
                "End": item.end,
                "Priority": PRIORITY_LABELS[item.task.priority],
                "Why": item.reason,
                "Kind": "Task",
            }
            for item in scheduled
        ]
        for break_start, break_end in getattr(st.session_state, "breaks", []):
            chart_rows.append(
                {
                    "Task": "Break",
                    "Start": break_start,
                    "End": break_end,
                    "Priority": "Break",
                    "Why": "Unavailable time",
                    "Kind": "Break",
                }
            )
        chart = px.timeline(
            pd.DataFrame(chart_rows),
            x_start="Start",
            x_end="End",
            y="Task",
            color="Priority",
            hover_data=["Why"],
            color_discrete_map={
                "High": "#e45756",
                "Medium": "#f2a541",
                "Low": "#4c9f70",
                "Break": "#9aa0a6",
            },
        )
        chart.update_yaxes(autorange="reversed")
        chart.update_layout(xaxis_title="Time", yaxis_title="", legend_title="Priority")
        st.plotly_chart(chart, use_container_width=True)
    else:
        st.info("No tasks could be scheduled. Check deadlines and available hours.")
    for item in st.session_state.schedule:
        if item.scheduled:
            st.write(f"**{item.start:%I:%M %p}–{item.end:%I:%M %p} · {item.task.title}** — {item.reason}")
        else:
            st.write(f"**Postponed · {item.task.title}** — {item.reason}")

    st.subheader("Rescue My Day")
    st.caption("Report a disruption and RePlan will rebuild the remaining schedule.")
    rescue_col1, rescue_col2 = st.columns(2)
    with rescue_col1:
        disruption_time = st.time_input(
            "Disruption starts at",
            value=max(time(0, 0), min(datetime.now().time().replace(second=0, microsecond=0), st.session_state.day_end)),
            key="rescue_time",
        )
        lost_minutes = st.number_input(
            "Time lost (minutes)", min_value=0, max_value=1440, value=30, step=5
        )
    with rescue_col2:
        add_unexpected = st.checkbox("Add an unexpected task", key="add_unexpected")
        unexpected_values = None
        if add_unexpected:
            unexpected_values = task_form_fields("unexpected")
    if st.button("Rescue My Day", type="primary"):
        unexpected = None
        try:
            if unexpected_values is not None:
                unexpected = save_task(unexpected_values)
                st.session_state.tasks.append(unexpected)
            st.session_state.schedule = rescue_day(
                st.session_state.tasks,
                st.session_state.schedule,
                st.session_state.schedule_day,
                disruption_time,
                st.session_state.day_end,
                int(lost_minutes),
                breaks=getattr(st.session_state, "breaks", []),
                unexpected_task=unexpected,
                day_start_time=st.session_state.day_start,
            )
            st.session_state.has_schedule = True
            st.rerun()
        except ValueError as error:
            st.error(str(error))
else:
    st.info("Set your available hours and select **Create my schedule** to see the visual plan.")
