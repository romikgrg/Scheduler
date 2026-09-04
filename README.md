# Intelligent Timetable Scheduler

PRT582 Software Engineering: Process and Tools — Software Unit Testing assignment.

Builds a weekly university timetable that satisfies room capacity, lecturer
availability, clash-free scheduling and prerequisite ordering, while trying
to honour preferred time slots and avoid wasting large rooms.

Developed test-first: for every feature the tests were written and watched
to fail before any implementation code existed.

## Requirements

Python 3.10 or newer. No runtime dependencies beyond the standard library.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
```

## Run

```bash
python main.py                                    # worked example
python -m pytest -v                               # full test suite
python -m pytest --cov=timetable --cov-report=term-missing
python -m pytest --cov=timetable --cov-report=html # then open htmlcov/index.html
```

## Layout

```
timetable/
    models.py       TimeSlot, Room, Lecturer, Session, Assignment, Timetable
    constraints.py  one function per hard rule
    scheduler.py    backtracking search
    exceptions.py   custom error types
tests/
    test_models.py       validation and boundary conditions
    test_constraints.py  each rule in isolation
    test_scheduler.py    end to end, failure cases, regressions
main.py             worked example
AI_LOG.md           development log
```

## Constraints

| Constraint | Type | Implemented in |
|---|---|---|
| Room capacity at least the enrolment | Hard | `room_is_big_enough` |
| Session length equals slot length | Hard | `duration_matches_slot` |
| Slot inside the lecturer's availability | Hard | `lecturer_is_available` |
| No lecturer double booking | Hard | `lecturer_is_free` |
| No room double booking | Hard | `room_is_free` |
| No student cohort double booking | Hard | `group_is_free` |
| Prerequisite unit taught earlier in the week | Hard | `prerequisites_respected` |
| Preferred time slots | Soft | candidate ordering in `Scheduler.candidates` |
| Smallest room that fits | Soft | candidate ordering in `Scheduler.candidates` |

Hard constraints filter out illegal placements. Soft constraints only change
the order options are tried, so an impossible preference is ignored rather
than making the timetable fail.

## Algorithm

Depth-first backtracking. Sessions are ordered by how few legal placements
they have, so the most constrained are placed first and dead ends are found
early. A step budget stops the search on problems that are too large.

An earlier greedy first-fit version passed all 100 tests that existed at the
time but could not undo a bad early choice; see `AI_LOG.md` for the defect
register.

## Testing

134 tests, 100% statement coverage of the `timetable` package.

## Author

Romik Gurung
S374535
