# RePlan AI

RePlan AI is a beginner-friendly, local daily planner built with Python, Streamlit, and Plotly. It uses a transparent scheduling heuristic and does not require an AI API or send planner data over the network.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

Tasks are stored in the current Streamlit session. They are not persisted after the app session ends.

## Run scheduler tests

```powershell
python -m unittest discover -s tests
```

## Scheduling behavior

Fixed-time tasks are placed first. Flexible tasks are then considered by earliest deadline, higher priority, and longer duration, and are assigned to the earliest contiguous free slot that meets both the deadline and the day's available hours. Breaks and fixed tasks are unavailable blocks. An end time earlier than the start time represents an overnight window; equal start and end times represent an empty window. When work cannot fit, the task stays visible with a reason instead of being silently dropped.

**Rescue My Day** applies the reported time loss without scheduling beyond the selected window, keeps completed tasks out of rescheduling, and rebuilds the remaining day. If the disruption consumes all available time, pending tasks are shown as postponed with an explanation. A new unexpected task can be added during rescue. The schedule explains whether work stayed put, moved, or had to be postponed.
