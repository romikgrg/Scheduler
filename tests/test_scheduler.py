"""End-to-end tests for the Scheduler.

Group H - basic scheduling
Group I - every hard constraint holds in a finished timetable
Group J - invalid input and impossible problems

Group I is the important one. The rules were already tested in isolation
in test_constraints.py; these tests check that the search actually
applies them, by re-examining the finished timetable.
"""

import pytest

from timetable.exceptions import (
    NoFeasibleTimetableError,
    UnknownReferenceError,
    ValidationError,
)
from timetable.models import Lecturer, Room, Session, TimeSlot, Timetable, build_week
from timetable.scheduler import Scheduler, render


@pytest.fixture
def week():
    """Monday to Friday, 09:00-17:00, in two-hour blocks: 20 slots."""
    return build_week(start=9, end=17, block=2)


@pytest.fixture
def staff():
    return [Lecturer("L1", "Dr Kim"), Lecturer("L2", "Dr Ali")]


@pytest.fixture
def rooms():
    return [Room("R1", 40), Room("R2", 100)]


def make_session(sid, unit="PRT582", lect="L1", enrol=20, hours=2, group="G1", prefer=()):
    return Session(sid, unit, lect, enrol, hours, group, prefer)


def no_overlaps(slots):
    """True when no two slots in the list overlap each other."""
    for i, first in enumerate(slots):
        for second in slots[i + 1:]:
            if first.overlaps(second):
                return False
    return True


# --------------------------------------------------------------- Group H
# What is tested: the scheduler places every session it is given, using
#   only the slots it was offered.
# Why it is necessary: the most basic promise the system makes.
# Defect prevented: a session silently dropped, duplicated, or invented.

class TestBasicScheduling:
    def test_single_session_is_placed(self, week, staff, rooms):
        table = Scheduler([make_session("S1")], rooms, week, staff).solve()
        assert len(table) == 1
        assert table.assignments[0].session.session_id == "S1"

    def test_every_session_appears_exactly_once(self, week, staff, rooms):
        sessions = [make_session(f"S{i}", group=f"G{i}") for i in range(6)]
        table = Scheduler(sessions, rooms, week, staff).solve()
        ids = [a.session.session_id for a in table]
        assert sorted(ids) == sorted(s.session_id for s in sessions)
        assert len(ids) == len(set(ids))

    def test_result_slots_come_from_the_supplied_week(self, week, staff, rooms):
        table = Scheduler([make_session("S1")], rooms, week, staff).solve()
        assert table.assignments[0].slot in week

    def test_result_rooms_come_from_the_supplied_rooms(self, week, staff, rooms):
        table = Scheduler([make_session("S1")], rooms, week, staff).solve()
        assert table.assignments[0].room in rooms

    def test_render_produces_one_line_per_class(self, week, staff, rooms):
        sessions = [make_session("S1", group="G1"), make_session("S2", group="G2")]
        table = Scheduler(sessions, rooms, week, staff).solve()
        assert len(render(table).splitlines()) == 2

    def test_render_handles_an_empty_timetable(self):
        assert render(Timetable()) == "(empty timetable)"


# --------------------------------------------------------------- Group I
# What is tested: the finished timetable breaks no hard constraint.
# Why it is necessary: rules that are correct in isolation can still be
#   applied wrongly, skipped, or checked in the wrong order by the search.
# Defect prevented: a solver that reports success while returning an
#   unusable timetable.

class TestConstraintsAreHonoured:
    def test_no_lecturer_is_double_booked(self, week, rooms):
        staff = [Lecturer("L1", "Dr Kim")]
        sessions = [make_session(f"S{i}", group=f"G{i}") for i in range(4)]
        table = Scheduler(sessions, rooms, week, staff).solve()
        assert no_overlaps([a.slot for a in table.for_lecturer("L1")])

    def test_no_room_is_double_booked(self, week, staff):
        rooms = [Room("R1", 50)]
        sessions = [
            make_session(f"S{i}", lect="L1" if i % 2 else "L2", group=f"G{i}")
            for i in range(4)
        ]
        table = Scheduler(sessions, rooms, week, staff).solve()
        assert no_overlaps([a.slot for a in table.for_room("R1")])

    def test_no_student_group_is_double_booked(self, week, staff, rooms):
        sessions = [
            make_session(f"S{i}", lect="L1" if i % 2 else "L2", group="G1")
            for i in range(4)
        ]
        table = Scheduler(sessions, rooms, week, staff).solve()
        assert no_overlaps([a.slot for a in table.for_group("G1")])

    def test_every_room_is_big_enough_for_its_class(self, week, staff):
        rooms = [Room("SMALL", 30), Room("BIG", 200)]
        sessions = [
            make_session("S1", enrol=25, lect="L1", group="G1"),
            make_session("S2", enrol=150, lect="L2", group="G2"),
        ]
        table = Scheduler(sessions, rooms, week, staff).solve()
        for a in table:
            assert a.room.capacity >= a.session.enrolment

    def test_large_class_gets_the_large_room(self, week, staff):
        rooms = [Room("SMALL", 30), Room("BIG", 200)]
        table = Scheduler([make_session("S1", enrol=150)], rooms, week, staff).solve()
        assert table.assignments[0].room.room_id == "BIG"

    def test_lecturer_availability_is_respected(self, week, rooms):
        staff = [Lecturer("L1", "Dr Kim", (TimeSlot("WED", 13, 17),))]
        table = Scheduler([make_session("S1")], rooms, week, staff).solve()
        assert table.assignments[0].slot.day == "WED"
        assert table.assignments[0].slot.start_hour >= 13

    def test_three_hour_session_only_fits_a_three_hour_block(self, staff, rooms):
        slots = [TimeSlot("MON", 9, 11), TimeSlot("MON", 11, 14)]
        table = Scheduler([make_session("S1", hours=3)], rooms, slots, staff).solve()
        assert table.assignments[0].slot.duration_hours == 3


# --------------------------------------------------------------- Group J
# What is tested: bad input and impossible problems fail loudly and early
#   with a message that names the offending item.
# Why it is necessary: a partial or silent result is worse than an error,
#   because the caller cannot tell success from failure.
# Defect prevented: unusable timetables accepted as valid; confusing
#   crashes deep inside the search.

class TestInvalidInputAndFailures:
    def test_no_sessions_is_rejected(self, week, staff, rooms):
        with pytest.raises(ValidationError):
            Scheduler([], rooms, week, staff)

    def test_no_rooms_is_rejected(self, week, staff):
        with pytest.raises(ValidationError):
            Scheduler([make_session("S1")], [], week, staff)

    def test_no_slots_is_rejected(self, staff, rooms):
        with pytest.raises(ValidationError):
            Scheduler([make_session("S1")], rooms, [], staff)

    def test_duplicate_session_ids_are_rejected(self, week, staff, rooms):
        with pytest.raises(ValidationError):
            Scheduler([make_session("S1"), make_session("S1")], rooms, week, staff)

    def test_duplicate_room_ids_are_rejected(self, week, staff):
        with pytest.raises(ValidationError):
            Scheduler([make_session("S1")], [Room("R1", 10), Room("R1", 20)], week, staff)

    def test_unknown_lecturer_is_rejected(self, week, staff, rooms):
        with pytest.raises(UnknownReferenceError):
            Scheduler([make_session("S1", lect="GHOST")], rooms, week, staff)

    def test_class_bigger_than_every_room_fails_with_a_clear_message(self, week, staff):
        rooms = [Room("R1", 10)]
        with pytest.raises(NoFeasibleTimetableError) as err:
            Scheduler([make_session("S1", enrol=500)], rooms, week, staff).solve()
        assert "S1" in str(err.value)

    def test_more_sessions_than_slots_fails(self, staff):
        slots = [TimeSlot("MON", 9, 11)]
        rooms = [Room("R1", 40)]
        sessions = [make_session("S1", group="G1"), make_session("S2", group="G2")]
        with pytest.raises(NoFeasibleTimetableError):
            Scheduler(sessions, rooms, slots, staff).solve()

    def test_impossible_lecturer_availability_fails(self, week, rooms):
        # A one-hour window cannot hold a two-hour class.
        staff = [Lecturer("L1", "Dr Kim", (TimeSlot("MON", 8, 9),))]
        with pytest.raises(NoFeasibleTimetableError):
            Scheduler([make_session("S1", hours=2)], rooms, week, staff).solve()


# --------------------------------------------------------------- Group K
# What is tested: an early placement that looks fine must be undone when
#   it makes a later session impossible.
# Why it is necessary: greedy first-fit passed all 100 earlier tests, so
#   the whole suite gave a false sense of security. The gap was in the
#   tests, not only in the code.
# Defect prevented: the scheduler reporting "no timetable exists" for a
#   problem that has a perfectly good answer.

class TestBacktracking:
    def test_recovers_from_a_bad_first_choice(self, staff):
        """Two rooms, one slot, two classes.

        Taking the big room for the small class first leaves the large
        class homeless, even though swapping them works. The scheduler
        must be able to undo that first decision.
        """
        rooms = [Room("BIG", 100), Room("SMALL", 20)]
        slots = [TimeSlot("MON", 9, 11)]
        sessions = [
            make_session("SMALL_CLASS", enrol=15, lect="L1", group="G1"),
            make_session("BIG_CLASS", enrol=80, lect="L2", group="G2"),
        ]
        table = Scheduler(sessions, rooms, slots, staff).solve()
        placement = {a.session.session_id: a.room.room_id for a in table}
        assert placement["BIG_CLASS"] == "BIG"
        assert placement["SMALL_CLASS"] == "SMALL"

    def test_recovers_from_a_bad_time_choice(self, staff):
        """The same trap, but with time rather than rooms.

        Dr Kim is free all Monday; Dr Ali only 11:00-13:00. If Dr Kim's
        class takes the 11:00 slot first, Dr Ali has nowhere to teach.
        """
        rooms = [Room("R1", 40)]
        slots = [TimeSlot("MON", 9, 11), TimeSlot("MON", 11, 13)]
        staff = [
            Lecturer("L1", "Dr Kim"),
            Lecturer("L2", "Dr Ali", (TimeSlot("MON", 11, 13),)),
        ]
        sessions = [
            make_session("KIM", lect="L1", group="G1"),
            make_session("ALI", lect="L2", group="G2"),
        ]
        table = Scheduler(sessions, rooms, slots, staff).solve()
        assert len(table) == 2
        slot_of = {a.session.session_id: a.slot for a in table}
        assert slot_of["ALI"].start_hour == 11
        assert slot_of["KIM"].start_hour == 9

    def test_a_genuinely_impossible_problem_still_fails(self, staff):
        """Backtracking must not turn into an infinite hunt: when there
        really is no answer, the error must still be raised."""
        rooms = [Room("SMALL", 20)]
        slots = [TimeSlot("MON", 9, 11)]
        sessions = [
            make_session("S1", enrol=15, lect="L1", group="G1"),
            make_session("S2", enrol=18, lect="L2", group="G2"),
        ]
        with pytest.raises(NoFeasibleTimetableError):
            Scheduler(sessions, rooms, slots, staff).solve()


# --------------------------------------------------------------- Group M
# What is tested: the scheduler applies prerequisite ordering, and
#   rejects a prerequisite chain that cannot possibly be satisfied.
# Why it is necessary: ordering interacts with the search, which is where
#   rules that look correct in isolation tend to come apart.
# Defect prevented: a unit scheduled before its prerequisite; an
#   impossible chain causing a long pointless search.

class TestPrerequisites:
    def test_prerequisite_unit_is_scheduled_first(self, week, staff):
        rooms = [Room("BIG", 100), Room("SMALL", 30)]
        sessions = [
            make_session("S_DEP", unit="PRT582", lect="L1", enrol=90, group="G1"),
            make_session("S_PRE", unit="HIT137", lect="L2", enrol=20, group="G2"),
        ]
        sched = Scheduler(sessions, rooms, week, staff,
                          prerequisites={"PRT582": ["HIT137"]})
        table = sched.solve()
        slot_of = {a.session.session_id: a.slot for a in table}
        assert slot_of["S_PRE"].starts_before(slot_of["S_DEP"])

    def test_unit_codes_are_case_insensitive(self, week, staff):
        rooms = [Room("BIG", 100), Room("SMALL", 30)]
        sessions = [
            make_session("S_DEP", unit="PRT582", lect="L1", enrol=90, group="G1"),
            make_session("S_PRE", unit="HIT137", lect="L2", enrol=20, group="G2"),
        ]
        sched = Scheduler(sessions, rooms, week, staff,
                          prerequisites={"prt582": ["hit137"]})
        table = sched.solve()
        slot_of = {a.session.session_id: a.slot for a in table}
        assert slot_of["S_PRE"].starts_before(slot_of["S_DEP"])

    def test_no_prerequisites_behaves_normally(self, week, staff, rooms):
        sessions = [make_session("S1", group="G1"), make_session("S2", group="G2")]
        assert len(Scheduler(sessions, rooms, week, staff).solve()) == 2

    def test_circular_prerequisites_are_rejected(self, week, staff, rooms):
        # A before B before A can never be satisfied, so it is a broken
        # input rather than an impossible timetable.
        with pytest.raises(ValidationError):
            Scheduler([make_session("S1")], rooms, week, staff,
                      prerequisites={"A": ["B"], "B": ["A"]})

    def test_self_prerequisite_is_rejected(self, week, staff, rooms):
        with pytest.raises(ValidationError):
            Scheduler([make_session("S1")], rooms, week, staff,
                      prerequisites={"A": ["A"]})

    def test_a_long_chain_is_allowed(self, week, staff, rooms):
        # A -> B -> C is not a cycle and must be accepted.
        Scheduler([make_session("S1")], rooms, week, staff,
                  prerequisites={"C": ["B"], "B": ["A"]})


# --------------------------------------------------------------- Group N
# What is tested: the two soft constraints - preferred time slots, and
#   using the smallest room that fits.
# Why it is necessary: soft constraints improve the timetable but must
#   never win against a hard rule, which is easy to get backwards.
# Defect prevented: a preference forcing an illegal placement; a small
#   tutorial occupying the only lecture theatre and blocking a lecture.

class TestPreferences:
    def test_preferred_slot_is_used_when_it_is_free(self, week, staff, rooms):
        wanted = TimeSlot("THU", 13, 15)
        table = Scheduler([make_session("S1", prefer=(wanted,))], rooms, week, staff).solve()
        assert table.assignments[0].slot == wanted

    def test_preference_score_counts_satisfied_requests(self, week, staff, rooms):
        wanted = TimeSlot("THU", 13, 15)
        table = Scheduler([make_session("S1", prefer=(wanted,))], rooms, week, staff).solve()
        assert table.preference_score() == 1

    def test_score_is_zero_when_nobody_asked_for_anything(self, week, staff, rooms):
        table = Scheduler([make_session("S1")], rooms, week, staff).solve()
        assert table.preference_score() == 0

    def test_preference_is_soft_and_can_be_dropped(self, week, staff):
        # Both sessions want the same slot and share a room, so only one
        # can have it. The other must still be scheduled somewhere.
        wanted = TimeSlot("THU", 13, 15)
        sessions = [
            make_session("S1", lect="L1", group="G1", prefer=(wanted,)),
            make_session("S2", lect="L2", group="G2", prefer=(wanted,)),
        ]
        table = Scheduler(sessions, [Room("R1", 40)], week, staff).solve()
        assert len(table) == 2
        assert table.preference_score() == 1

    def test_preference_never_beats_a_hard_constraint(self, week, staff):
        # S2 wants the same slot, but only the big room can hold it.
        rooms = [Room("SMALL", 20), Room("BIG", 200)]
        wanted = TimeSlot("MON", 9, 11)
        sessions = [
            make_session("S1", enrol=10, lect="L1", group="G1", prefer=(wanted,)),
            make_session("S2", enrol=150, lect="L2", group="G2", prefer=(wanted,)),
        ]
        table = Scheduler(sessions, rooms, week, staff).solve()
        for a in table:
            assert a.room.capacity >= a.session.enrolment

    def test_a_preference_that_can_never_be_met_is_ignored(self, week, staff, rooms):
        # Nobody teaches at 19:00, so the request is simply not honoured
        # rather than making the timetable fail.
        impossible = TimeSlot("MON", 19, 20)
        table = Scheduler([make_session("S1", prefer=(impossible,))], rooms, week, staff).solve()
        assert len(table) == 1
        assert table.preference_score() == 0


class TestRoomEfficiency:
    def test_small_class_does_not_take_the_lecture_theatre(self, week, staff):
        rooms = [Room("THEATRE", 200), Room("TUTORIAL", 25)]
        table = Scheduler([make_session("S1", enrol=15)], rooms, week, staff).solve()
        assert table.assignments[0].room.room_id == "TUTORIAL"

    def test_class_still_gets_a_big_room_when_it_needs_one(self, week, staff):
        rooms = [Room("THEATRE", 200), Room("TUTORIAL", 25)]
        table = Scheduler([make_session("S1", enrol=150)], rooms, week, staff).solve()
        assert table.assignments[0].room.room_id == "THEATRE"

    def test_theatre_stays_free_for_the_class_that_needs_it(self, week, staff):
        # One slot only: the tutorial must give way to the lecture.
        rooms = [Room("THEATRE", 200), Room("TUTORIAL", 25)]
        slots = [TimeSlot("MON", 9, 11)]
        sessions = [
            make_session("TUT", enrol=15, lect="L1", group="G1"),
            make_session("LEC", enrol=150, lect="L2", group="G2"),
        ]
        table = Scheduler(sessions, rooms, slots, staff).solve()
        placement = {a.session.session_id: a.room.room_id for a in table}
        assert placement == {"TUT": "TUTORIAL", "LEC": "THEATRE"}


# --------------------------------------------------------------- Group O
# What is tested: the search gives up after a fixed budget, the same
#   input always gives the same timetable, and a single session can be
#   explained on its own.
# Why it is necessary: these cover NFR2, NFR3 and FR12, which have no
#   tests yet. A backtracking search on a hard problem can run for a very
#   long time, and a non-deterministic result makes every other test
#   unreliable.
# Defect prevented: an apparently frozen program; flaky tests; an
#   unhelpful "no timetable exists" with no way to find out why.

class TestSearchBudget:
    def test_max_steps_must_be_positive(self, week, staff, rooms):
        with pytest.raises(ValidationError):
            Scheduler([make_session("S1")], rooms, week, staff, max_steps=0)

    def test_solve_records_how_many_steps_it_took(self, week, staff, rooms):
        sched = Scheduler([make_session("S1")], rooms, week, staff)
        sched.solve()
        assert sched.steps > 0

    def test_search_budget_is_enforced(self, week, staff, rooms):
        sessions = [make_session(f"S{i}", group=f"G{i}") for i in range(8)]
        with pytest.raises(NoFeasibleTimetableError) as err:
            Scheduler(sessions, rooms, week, staff, max_steps=1).solve()
        assert "gave up" in str(err.value)

    def test_step_counter_resets_between_solves(self, week, staff, rooms):
        # Without a reset the count would accumulate, and a second solve()
        # on the same object would hit the budget and wrongly report that
        # no timetable exists.
        sched = Scheduler([make_session("S1")], rooms, week, staff)
        sched.solve()
        first = sched.steps
        sched.solve()
        assert sched.steps == first


class TestDeterminism:
    def test_solving_twice_gives_the_same_answer(self, week, staff, rooms):
        sessions = [make_session(f"S{i}", group=f"G{i}") for i in range(4)]
        sched = Scheduler(sessions, rooms, week, staff)
        assert sched.solve().as_rows() == sched.solve().as_rows()

    def test_two_identical_schedulers_agree(self, week, staff, rooms):
        def build():
            sessions = [make_session(f"S{i}", group=f"G{i}") for i in range(4)]
            return Scheduler(sessions, rooms, week, staff).solve()
        assert render(build()) == render(build())


class TestExplain:
    def test_describes_a_placeable_session(self, week, staff, rooms):
        sched = Scheduler([make_session("S1")], rooms, week, staff)
        assert "options" in sched.explain("S1")

    def test_reports_a_session_that_fits_nowhere(self, week, staff):
        sched = Scheduler([make_session("S1", enrol=999)], [Room("R1", 5)], week, staff)
        assert "no legal" in sched.explain("S1")

    def test_unknown_session_is_rejected(self, week, staff, rooms):
        sched = Scheduler([make_session("S1")], rooms, week, staff)
        with pytest.raises(UnknownReferenceError):
            sched.explain("NOPE")
