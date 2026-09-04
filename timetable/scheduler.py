"""The scheduling engine.

Algorithm: depth-first backtracking search.

The first version of this file used greedy first-fit: walk the sessions,
take the first legal spot, never look back. It passed every test at the
time, but it cannot undo a decision. Given one time slot, a big and a
small room, and a big and a small class, it gives the big room to
whichever class comes first and then declares the other one impossible.

Backtracking fixes that by trying an option, recursing, and undoing the
choice if the rest of the timetable cannot be completed.

Two heuristics keep the search small:

1. Sessions are ordered by how few legal placements they have, so the
   hardest ones are placed first. This is the "most constrained variable"
   heuristic: failing early means failing cheaply.
2. Sessions with no legal placement at all are detected before the search
   begins, so an impossible problem fails immediately with a useful
   message instead of after exhausting every combination.
"""

from typing import Sequence

from . import constraints as c
from .exceptions import NoFeasibleTimetableError, UnknownReferenceError, ValidationError
from .models import Assignment, Lecturer, Room, Session, TimeSlot, Timetable


class Scheduler:
    """Builds a clash-free timetable from sessions, rooms and time slots."""

    def __init__(
        self,
        sessions: Sequence[Session],
        rooms: Sequence[Room],
        slots: Sequence[TimeSlot],
        lecturers: Sequence[Lecturer],
        prerequisites=None,
        max_steps: int = 200_000,
    ) -> None:
        self.sessions = list(sessions)
        self.rooms = list(rooms)
        self.slots = list(slots)
        self.lecturers = {lect.lecturer_id: lect for lect in lecturers}
        # Unit codes are upper-cased on Session, so normalise here too and
        # callers can write them however they like.
        self.prerequisites = {
            unit.upper(): [p.upper() for p in parents]
            for unit, parents in (prerequisites or {}).items()
        }
        self.max_steps = max_steps
        self.steps = 0
        self._validate_inputs()

    # ------------------------------------------------------------------ setup

    def _validate_inputs(self) -> None:
        """Catch malformed problems before any searching happens."""
        if not self.sessions:
            raise ValidationError("at least one session is required")
        if not self.rooms:
            raise ValidationError("at least one room is required")
        if not self.slots:
            raise ValidationError("at least one time slot is required")
        if isinstance(self.max_steps, bool) or not isinstance(self.max_steps, int) \
                or self.max_steps <= 0:
            raise ValidationError("max_steps must be a whole number greater than zero")

        seen = set()
        for session in self.sessions:
            if session.session_id in seen:
                raise ValidationError(f"duplicate session_id {session.session_id!r}")
            seen.add(session.session_id)
            if session.lecturer_id not in self.lecturers:
                raise UnknownReferenceError(
                    f"session {session.session_id!r} refers to unknown lecturer "
                    f"{session.lecturer_id!r}"
                )

        room_ids = set()
        for room in self.rooms:
            if room.room_id in room_ids:
                raise ValidationError(f"duplicate room_id {room.room_id!r}")
            room_ids.add(room.room_id)

        self._check_prerequisite_cycles()

    def _check_prerequisite_cycles(self) -> None:
        """Depth-first cycle detection: A before B before A is impossible.

        A cycle is broken input rather than a hard timetable, so it is
        rejected before any searching starts.
        """
        visiting = set()   # units on the current path
        done = set()       # units already proven cycle-free

        def walk(unit, trail):
            if unit in visiting:
                raise ValidationError(
                    f"prerequisite cycle detected: {' -> '.join(trail + [unit])}"
                )
            if unit in done:
                return
            visiting.add(unit)
            for parent in self.prerequisites.get(unit, ()):
                walk(parent, trail + [unit])
            visiting.discard(unit)
            done.add(unit)

        for unit in list(self.prerequisites):
            walk(unit, [])

    # ------------------------------------------------------------- candidates

    def _is_legal(self, placed, session, slot, room) -> bool:
        """True when this placement breaks none of the hard rules."""
        lecturer = self.lecturers[session.lecturer_id]
        return (
            c.duration_matches_slot(session, slot)
            and c.room_is_big_enough(session, room)
            and c.lecturer_is_available(lecturer, slot)
            and c.lecturer_is_free(placed, session, slot)
            and c.room_is_free(placed, room, slot)
            and c.group_is_free(placed, session, slot)
            and c.prerequisites_respected(placed, session, slot, self.prerequisites)
        )

    def candidates(self, session: Session):
        """Every (slot, room) pair that suits this session in isolation.

        Clashes with other sessions are ignored here, because they depend
        on what has already been placed. They are checked during the
        search instead.
        """
        pairs = [
            (slot, room)
            for slot in self.slots
            for room in self.rooms
            if self._is_legal([], session, slot, room)
        ]

        # Soft constraints work by ORDER, not by filtering. Every pair
        # here is legal; better ones are simply tried first. If a
        # preferred option does not work out, the search moves on
        # without the timetable failing.
        #
        # Priority:
        #   1. slots the session asked for
        #   2. the smallest room that still fits, so lecture theatres
        #      stay free for the classes that actually need them
        #   3. earliest in the week, then room id, purely so the result
        #      is tidy and identical on every run
        pairs.sort(
            key=lambda p: (
                not session.prefers(p[0]),
                p[1].capacity,
                p[0].day_index,
                p[0].start_hour,
                p[1].room_id,
            )
        )
        return pairs

    # ----------------------------------------------------------------- search

    def solve(self) -> Timetable:
        """Return a timetable that satisfies every hard constraint."""
        # Hardest first: sessions with the fewest options are placed
        # earliest, so dead ends are reached sooner and cost less.
        order = sorted(self.sessions, key=lambda s: len(self.candidates(s)))

        for session in order:
            if not self.candidates(session):
                raise NoFeasibleTimetableError(
                    f"session {session.session_id!r} has no legal room and time at "
                    f"all: check enrolment against room capacity, session duration "
                    f"and lecturer availability"
                )

        # Reset before every search. Without this the count would carry
        # over and a second solve() on the same object would exhaust the
        # budget and wrongly report that no timetable exists.
        self.steps = 0

        placed = []
        if self._place(order, 0, placed):
            return Timetable(placed)
        raise NoFeasibleTimetableError(
            "no clash-free timetable exists for the given sessions, rooms and slots"
        )

    def _place(self, order, index: int, placed) -> bool:
        """Try to place order[index] onwards. True when all of them fit."""
        if index == len(order):
            return True

        session = order[index]
        for slot, room in self.candidates(session):
            self.steps += 1
            if self.steps > self.max_steps:
                raise NoFeasibleTimetableError(
                    f"search gave up after {self.max_steps} steps: the problem is "
                    f"too large or too tightly constrained"
                )
            if not self._is_legal(placed, session, slot, room):
                continue
            placed.append(Assignment(session, slot, room))
            if self._place(order, index + 1, placed):
                return True
            placed.pop()          # undo and try the next option
        return False


    def explain(self, session_id: str) -> str:
        """Describe where one session could possibly go.

        Useful when solve() fails: it narrows an unhelpful "no timetable
        exists" down to the session that has nowhere to be.
        """
        matches = [s for s in self.sessions if s.session_id == session_id]
        if not matches:
            raise UnknownReferenceError(f"no session with id {session_id!r}")

        options = self.candidates(matches[0])
        if not options:
            return f"{session_id}: no legal room and time combination"
        slot, room = options[0]
        return f"{session_id}: {len(options)} options, first is {slot} in {room.room_id}"


def render(timetable: Timetable) -> str:
    """Plain text timetable, one line per class."""
    if len(timetable) == 0:
        return "(empty timetable)"
    return "\n".join(
        f"{unit:<10} {when:<22} {room}" for unit, _day, when, room in timetable.as_rows()
    )
