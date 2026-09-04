"""Tests for the hard constraints, each checked on its own.

Group F - room capacity and session duration
Group G - clash detection (lecturer, room, student cohort)

These tests never run the scheduler. Each rule is called directly with a
hand-built list of already-placed assignments, so a failure identifies
the broken rule immediately rather than pointing at the search.
"""

import pytest

from timetable import constraints as c
from timetable.models import Assignment, Lecturer, Room, Session, TimeSlot

MON_9 = TimeSlot("MON", 9, 11)
MON_11 = TimeSlot("MON", 11, 13)
MON_10 = TimeSlot("MON", 10, 12)
TUE_9 = TimeSlot("TUE", 9, 11)


def session(sid="S1", unit="PRT582", lect="L1", enrol=20, hours=2, group="G1"):
    """Build a session, overriding only what a test cares about."""
    return Session(sid, unit, lect, enrol, hours, group)


def placed(sess, slot, room):
    """A one-item list of already-placed assignments."""
    return [Assignment(sess, slot, room)]


# --------------------------------------------------------------- Group F
# What is tested: a session fits its room and exactly fills its slot.
# Why it is necessary: both are strict comparisons, and both are easy to
#   get subtly wrong in a way that still produces a plausible timetable.
# Defect prevented: overcrowded rooms; a three-hour lab silently squeezed
#   into a two-hour block.

class TestRoomCapacity:
    def test_room_with_spare_seats_is_fine(self):
        assert c.room_is_big_enough(session(enrol=20), Room("R1", 30))

    def test_exactly_full_is_fine(self):
        assert c.room_is_big_enough(session(enrol=30), Room("R1", 30))

    def test_one_over_is_not(self):
        assert not c.room_is_big_enough(session(enrol=31), Room("R1", 30))


class TestDuration:
    def test_matching_duration_passes(self):
        assert c.duration_matches_slot(session(hours=2), MON_9)

    def test_longer_session_fails(self):
        assert not c.duration_matches_slot(session(hours=3), MON_9)

    def test_shorter_session_fails(self):
        # A one-hour class is NOT allowed to occupy a two-hour block,
        # because the leftover hour would be silently wasted.
        assert not c.duration_matches_slot(session(hours=1), MON_9)


class TestLecturerAvailabilityRule:
    def test_available_lecturer_passes(self):
        lect = Lecturer("L1", "Dr Kim", (TimeSlot("MON", 9, 17),))
        assert c.lecturer_is_available(lect, MON_9)

    def test_unavailable_lecturer_fails(self):
        lect = Lecturer("L1", "Dr Kim", (TimeSlot("TUE", 9, 17),))
        assert not c.lecturer_is_available(lect, MON_9)

    def test_unrestricted_lecturer_always_passes(self):
        assert c.lecturer_is_available(Lecturer("L1", "Dr Kim"), MON_9)


# --------------------------------------------------------------- Group G
# What is tested: no lecturer, room or student cohort is double booked,
#   and legal back-to-back teaching is not mistaken for a clash.
# Why it is necessary: double booking is the single most common
#   timetabling defect, and the "not a clash" cases are just as important
#   as the clash cases.
# Defect prevented: a timetable that looks successful but is impossible
#   to actually run; or a valid timetable wrongly reported as impossible.

class TestLecturerClash:
    def test_lecturer_cannot_teach_two_classes_at_once(self):
        already = placed(session("S1"), MON_9, Room("R1", 30))
        assert not c.lecturer_is_free(already, session("S2"), MON_9)

    def test_partial_overlap_is_still_a_clash(self):
        already = placed(session("S1"), MON_9, Room("R1", 30))
        assert not c.lecturer_is_free(already, session("S2"), MON_10)

    def test_lecturer_can_teach_back_to_back(self):
        already = placed(session("S1"), MON_9, Room("R1", 30))
        assert c.lecturer_is_free(already, session("S2"), MON_11)

    def test_same_time_on_another_day_is_fine(self):
        already = placed(session("S1"), MON_9, Room("R1", 30))
        assert c.lecturer_is_free(already, session("S2"), TUE_9)

    def test_different_lecturers_never_clash(self):
        already = placed(session("S1", lect="L1"), MON_9, Room("R1", 30))
        assert c.lecturer_is_free(already, session("S2", lect="L2"), MON_9)

    def test_nothing_placed_yet_means_free(self):
        assert c.lecturer_is_free([], session("S1"), MON_9)


class TestRoomClash:
    def test_room_cannot_host_two_classes_at_once(self):
        room = Room("R1", 30)
        already = placed(session("S1"), MON_9, room)
        assert not c.room_is_free(already, room, MON_9)

    def test_room_can_be_reused_back_to_back(self):
        room = Room("R1", 30)
        already = placed(session("S1"), MON_9, room)
        assert c.room_is_free(already, room, MON_11)

    def test_a_different_room_is_free(self):
        already = placed(session("S1"), MON_9, Room("R1", 30))
        assert c.room_is_free(already, Room("R2", 30), MON_9)

    def test_rooms_are_matched_by_id_not_object_identity(self):
        # Two Room objects with the same id are the same physical room.
        already = placed(session("S1"), MON_9, Room("R1", 30))
        assert not c.room_is_free(already, Room("R1", 30), MON_9)


class TestGroupClash:
    def test_student_group_cannot_be_in_two_places(self):
        already = placed(session("S1", group="G1"), MON_9, Room("R1", 30))
        assert not c.group_is_free(already, session("S2", group="G1"), MON_9)

    def test_group_can_have_back_to_back_classes(self):
        already = placed(session("S1", group="G1"), MON_9, Room("R1", 30))
        assert c.group_is_free(already, session("S2", group="G1"), MON_11)

    def test_other_group_is_unaffected(self):
        already = placed(session("S1", group="G1"), MON_9, Room("R1", 30))
        assert c.group_is_free(already, session("S2", group="G2"), MON_9)


class TestClashesAcrossManyPlacements:
    def test_a_clash_is_found_anywhere_in_the_list(self):
        # The clashing item is last: the rule must check every placement,
        # not just the most recent one.
        already = [
            Assignment(session("S1"), TUE_9, Room("R1", 30)),
            Assignment(session("S2"), MON_11, Room("R1", 30)),
            Assignment(session("S3"), MON_9, Room("R1", 30)),
        ]
        assert not c.lecturer_is_free(already, session("S4"), MON_9)

    def test_no_clash_when_every_placement_is_elsewhere(self):
        already = [
            Assignment(session("S1"), TUE_9, Room("R1", 30)),
            Assignment(session("S2"), MON_11, Room("R1", 30)),
        ]
        assert c.lecturer_is_free(already, session("S3"), MON_9)


# --------------------------------------------------------------- Group L
# What is tested: a unit is taught later in the week than every unit
#   listed as its prerequisite.
# Why it is necessary: it is the only rule that compares two sessions by
#   position in the week rather than by overlap, so it needs its own
#   notion of "earlier".
# Defect prevented: a unit taught before the material it depends on.

class TestPrerequisiteOrdering:
    prereqs = {"PRT582": ["HIT137"]}

    def test_prerequisite_earlier_in_week_is_allowed(self):
        already = placed(session("S1", unit="HIT137"), MON_9, Room("R1", 30))
        assert c.prerequisites_respected(already, session("S2"), TUE_9, self.prereqs)

    def test_prerequisite_later_in_week_is_refused(self):
        already = placed(session("S1", unit="HIT137"), TUE_9, Room("R1", 30))
        assert not c.prerequisites_respected(already, session("S2"), MON_9, self.prereqs)

    def test_prerequisite_later_on_the_same_day_is_refused(self):
        already = placed(session("S1", unit="HIT137"), MON_11, Room("R1", 30))
        assert not c.prerequisites_respected(already, session("S2"), MON_9, self.prereqs)

    def test_same_start_time_is_refused(self):
        # Simultaneous is not "after", so this must be rejected.
        already = placed(session("S1", unit="HIT137"), MON_9, Room("R1", 30))
        assert not c.prerequisites_respected(already, session("S2"), MON_9, self.prereqs)

    def test_unrelated_units_are_unaffected(self):
        already = placed(session("S1", unit="CDU100"), TUE_9, Room("R1", 30))
        assert c.prerequisites_respected(already, session("S2"), MON_9, self.prereqs)

    def test_empty_prerequisite_map_allows_anything(self):
        already = placed(session("S1", unit="HIT137"), TUE_9, Room("R1", 30))
        assert c.prerequisites_respected(already, session("S2"), MON_9, {})

    def test_nothing_placed_yet_is_allowed(self):
        assert c.prerequisites_respected([], session("S1"), MON_9, self.prereqs)
