import unittest
from datetime import date, datetime, time, timedelta

from models import Task
from planner import rescue_day, schedule_tasks


class ScheduleTasksTests(unittest.TestCase):
    def setUp(self):
        self.day = date(2026, 10, 18)

    def task(self, title, minutes, priority=2, deadline=None, **kwargs):
        return Task(
            title,
            minutes,
            priority,
            deadline or datetime.combine(self.day, time(18, 0)),
            **kwargs,
        )

    def test_schedules_by_deadline_then_priority_within_capacity(self):
        low = self.task("Low", 60, priority=3)
        urgent = self.task("Urgent", 30, priority=1, deadline=datetime.combine(self.day, time(10)))
        result = schedule_tasks([low, urgent], self.day, time(8), time(9, 20))

        self.assertEqual(result[1].start, datetime.combine(self.day, time(8)))
        self.assertFalse(result[0].scheduled)
        self.assertIn("free slot", result[0].reason)

    def test_fixed_task_and_break_are_respected(self):
        fixed = self.task("Class", 60, flexible=False, preferred_start=time(10))
        flexible = self.task("Study", 120)
        break_start = datetime.combine(self.day, time(11))
        break_end = datetime.combine(self.day, time(12))

        result = schedule_tasks(
            [fixed, flexible], self.day, time(9), time(14),
            breaks=[(break_start, break_end)],
        )

        self.assertEqual(result[0].start, datetime.combine(self.day, time(10)))
        self.assertEqual(result[1].start, datetime.combine(self.day, time(12)))

    def test_overdue_task_is_not_scheduled(self):
        task = self.task("Late", 20, deadline=datetime.combine(self.day, time(7)))
        result = schedule_tasks([task], self.day, time(8), time(12))
        self.assertFalse(result[0].scheduled)
        self.assertEqual(result[0].reason, "Deadline has already passed.")

    def test_cross_midnight_window(self):
        task = self.task(
            "Night work",
            60,
            deadline=datetime.combine(self.day + timedelta(days=1), time(2)),
        )
        result = schedule_tasks([task], self.day, time(23), time(2))
        self.assertEqual(result[0].start, datetime.combine(self.day, time(23)))
        self.assertEqual(result[0].end, datetime.combine(self.day + timedelta(days=1), time(0)))

    def test_equal_schedule_times_are_an_empty_window_not_an_overnight_window(self):
        task = self.task("Task", 30)
        result = schedule_tasks([task], self.day, time(10), time(10))

        self.assertFalse(result[0].scheduled)
        self.assertIn("window is empty", result[0].reason)

    def test_rescue_moves_pending_tasks_and_preserves_completed_tasks(self):
        done = self.task("Done", 30, completed=True)
        first = self.task("First", 60)
        second = self.task("Second", 60)
        old_schedule = schedule_tasks([first, second], self.day, time(8), time(11))

        result = rescue_day(
            [done, first, second],
            old_schedule,
            self.day,
            time(8),
            time(11),
            60,
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].start, datetime.combine(self.day, time(9)))
        self.assertIn("disruption", result[0].reason)
        self.assertTrue(result[1].scheduled)

    def test_rescue_disruption_consuming_entire_day_postpones_everything(self):
        task = self.task("Work", 60, deadline=datetime.combine(self.day, time(23, 59)))
        old_schedule = schedule_tasks([task], self.day, time(8), time(10))

        result = rescue_day(
            [task], old_schedule, self.day, time(8), time(10), 120,
            day_start_time=time(8),
        )

        self.assertEqual(len(result), 1)
        self.assertFalse(result[0].scheduled)
        self.assertIn("Postponed", result[0].reason)
        self.assertIn("no available time remains", result[0].reason)

    def test_rescue_with_one_minute_remaining_stays_inside_day(self):
        task = self.task("One minute task", 1, deadline=datetime.combine(self.day, time(23, 59)))
        old_schedule = schedule_tasks([task], self.day, time(8), time(10))

        result = rescue_day(
            [task], old_schedule, self.day, time(8), time(10), 119,
            day_start_time=time(8),
        )

        self.assertEqual(result[0].start, datetime.combine(self.day, time(9, 59)))
        self.assertEqual(result[0].end, datetime.combine(self.day, time(10)))

    def test_rescue_zero_and_negative_disruption_do_not_move_start_before_day(self):
        task = self.task("Work", 30, deadline=datetime.combine(self.day, time(23, 59)))
        old_schedule = schedule_tasks([task], self.day, time(8), time(10))

        for lost_minutes in (0, -30):
            with self.subTest(lost_minutes=lost_minutes):
                result = rescue_day(
                    [task], old_schedule, self.day, time(7), time(10), lost_minutes,
                    day_start_time=time(8),
                )

                self.assertEqual(result[0].start, datetime.combine(self.day, time(8)))
                self.assertLessEqual(result[0].end, datetime.combine(self.day, time(10)))

    def test_rescue_starting_at_end_of_day_has_no_available_time(self):
        task = self.task("Work", 30, deadline=datetime.combine(self.day, time(23, 59)))
        old_schedule = schedule_tasks([task], self.day, time(8), time(10))

        result = rescue_day(
            [task], old_schedule, self.day, time(10), time(10), 0,
            day_start_time=time(8),
        )

        self.assertFalse(result[0].scheduled)
        self.assertIn("no available time remains", result[0].reason)

    def test_rescue_does_not_schedule_after_overnight_window_end(self):
        overnight_end = datetime.combine(self.day + timedelta(days=1), time(2))
        task = self.task("Night work", 30, deadline=overnight_end)
        old_schedule = schedule_tasks([task], self.day, time(23), time(2))

        result = rescue_day(
            [task], old_schedule, self.day, time(1), time(2), 60,
            day_start_time=time(23),
        )

        self.assertFalse(result[0].scheduled)
        self.assertIn("no available time remains", result[0].reason)


if __name__ == "__main__":
    unittest.main()
