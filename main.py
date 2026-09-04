"""Demo: schedule one semester week for a small IT school.

Run with:  python main.py
"""

from timetable import (
    Lecturer,
    NoFeasibleTimetableError,
    Room,
    Scheduler,
    Session,
    TimeSlot,
    build_week,
    render,
)


def main() -> int:
    week = build_week(start=9, end=17, block=2)

    rooms = [
        Room("PURPLE-12", 200),   # lecture theatre
        Room("ORANGE-3", 60),     # classroom
        Room("LAB-A", 30),        # computer lab
    ]

    lecturers = [
        Lecturer("KIM", "Dr Kim", (TimeSlot("MON", 9, 17), TimeSlot("TUE", 9, 17))),
        Lecturer("ALI", "Dr Ali", (TimeSlot("WED", 9, 17), TimeSlot("THU", 9, 17))),
        Lecturer("NGUYEN", "Ms Nguyen"),   # no stated restrictions
    ]

    sessions = [
        Session("HIT137-LEC", "HIT137", "KIM", 180, 2, "IT-Y1",
                preferred_slots=(TimeSlot("MON", 9, 13),)),
        Session("HIT137-LAB", "HIT137", "NGUYEN", 28, 2, "IT-Y1"),
        Session("PRT582-LEC", "PRT582", "ALI", 55, 2, "IT-Y2"),
        Session("PRT582-LAB", "PRT582", "NGUYEN", 25, 2, "IT-Y2"),
        Session("CDU101-LEC", "CDU101", "KIM", 150, 2, "IT-Y1"),
    ]

    prerequisites = {"PRT582": ["HIT137"]}

    scheduler = Scheduler(sessions, rooms, week, lecturers, prerequisites)

    try:
        timetable = scheduler.solve()
    except NoFeasibleTimetableError as err:
        print("Could not build a timetable:", err)
        print("\nWhere each session could go:")
        for session in sessions:
            print("  ", scheduler.explain(session.session_id))
        return 1

    print(f"Timetable found in {scheduler.steps} search steps\n")
    print(render(timetable))

    wanted = sum(1 for s in sessions if s.preferred_slots)
    print(f"\nPreferred-slot score: {timetable.preference_score()}/{wanted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
