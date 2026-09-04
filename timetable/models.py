"""Domain models for the intelligent timetable scheduler.

Design notes
------------
* A university week runs Monday to Friday.
* Teaching happens between DAY_START (08:00) and DAY_END (20:00).
* Times are whole hours. Half-hour teaching is out of scope.
"""

from dataclasses import dataclass, field

from .exceptions import ValidationError

DAYS: tuple[str, ...] = ("MON", "TUE", "WED", "THU", "FRI")
DAY_START = 8
DAY_END = 20


def _require_id(value: object, field_name: str) -> str:
    """Return a clean identifier string or raise ValidationError.

    Shared by Room, Lecturer and Session so that the rules for what
    counts as a valid identifier live in exactly one place.
    """
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string, got {type(value).__name__}")
    cleaned = value.strip()
    if not cleaned:
        raise ValidationError(f"{field_name} must not be empty")
    return cleaned


@dataclass(frozen=True)
class TimeSlot:
    """A period of teaching time on one day, e.g. MON 09:00-11:00."""

    day: str
    start_hour: int
    end_hour: int

    def __post_init__(self) -> None:
        # frozen=True blocks normal assignment, so validated values are
        # written back with object.__setattr__.
        day = self.day.strip().upper() if isinstance(self.day, str) else self.day
        if day not in DAYS:
            raise ValidationError(f"day must be one of {DAYS}, got {self.day!r}")
        object.__setattr__(self, "day", day)

        for name, value in (("start_hour", self.start_hour), ("end_hour", self.end_hour)):
            # bool is a subclass of int in Python, so True would otherwise
            # sneak through as hour 1. Reject it explicitly.
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValidationError(f"{name} must be a whole number, got {value!r}")

        if self.start_hour < DAY_START:
            raise ValidationError(f"start_hour must not be before {DAY_START}:00")
        if self.end_hour > DAY_END:
            raise ValidationError(f"end_hour must not be after {DAY_END}:00")
        if self.end_hour <= self.start_hour:
            raise ValidationError("end_hour must be later than start_hour")

    @property
    def duration_hours(self) -> int:
        return self.end_hour - self.start_hour

    @property
    def day_index(self) -> int:
        return DAYS.index(self.day)

    def overlaps(self, other: "TimeSlot") -> bool:
        """True when the two slots share at least one minute of the week.

        Slots that merely touch (09:00-11:00 and 11:00-13:00) do NOT
        overlap, because back-to-back teaching is legal. This is why the
        comparison is strictly less-than rather than less-than-or-equal.
        """
        if self.day != other.day:
            return False
        return self.start_hour < other.end_hour and other.start_hour < self.end_hour

    def contains(self, other: "TimeSlot") -> bool:
        """True when `other` fits completely inside this slot."""
        if self.day != other.day:
            return False
        return self.start_hour <= other.start_hour and other.end_hour <= self.end_hour

    def starts_before(self, other: "TimeSlot") -> bool:
        """Ordering across the week: earlier day wins, then earlier start."""
        return (self.day_index, self.start_hour) < (other.day_index, other.start_hour)

    def __str__(self) -> str:
        return f"{self.day} {self.start_hour:02d}:00-{self.end_hour:02d}:00"


@dataclass(frozen=True)
class Room:
    """A teaching room with a seat limit."""

    room_id: str
    capacity: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "room_id", _require_id(self.room_id, "room_id"))
        if isinstance(self.capacity, bool) or not isinstance(self.capacity, int):
            raise ValidationError("capacity must be a whole number")
        if self.capacity <= 0:
            raise ValidationError("capacity must be greater than zero")

    def can_seat(self, headcount: int) -> bool:
        """Inclusive: a class of exactly `capacity` students fits."""
        return headcount <= self.capacity


@dataclass(frozen=True)
class Lecturer:
    """A lecturer and the windows of time they are willing to teach in."""

    lecturer_id: str
    name: str
    availability: tuple[TimeSlot, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "lecturer_id", _require_id(self.lecturer_id, "lecturer_id"))
        object.__setattr__(self, "name", _require_id(self.name, "name"))
        slots = tuple(self.availability)
        for slot in slots:
            if not isinstance(slot, TimeSlot):
                raise ValidationError("availability must contain TimeSlot objects")
        object.__setattr__(self, "availability", slots)

    def is_available(self, slot: TimeSlot) -> bool:
        """A lecturer with no stated availability is treated as always free.

        Otherwise the slot must fit entirely inside one window; a class
        that starts inside a window but runs past its end is refused.
        """
        if not self.availability:
            return True
        return any(window.contains(slot) for window in self.availability)


@dataclass(frozen=True)
class Session:
    """One teaching event that must be placed on the timetable."""

    session_id: str
    unit_code: str
    lecturer_id: str
    enrolment: int
    duration_hours: int
    student_group: str
    preferred_slots: tuple[TimeSlot, ...] = ()

    def __post_init__(self) -> None:
        for name in ("session_id", "unit_code", "lecturer_id", "student_group"):
            object.__setattr__(self, name, _require_id(getattr(self, name), name))
        object.__setattr__(self, "unit_code", self.unit_code.upper())

        for name in ("enrolment", "duration_hours"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValidationError(f"{name} must be a whole number")
            if value <= 0:
                raise ValidationError(f"{name} must be greater than zero")

        if self.duration_hours > DAY_END - DAY_START:
            raise ValidationError(
                f"duration_hours cannot exceed the teaching day "
                f"({DAY_END - DAY_START} hours)"
            )
        object.__setattr__(self, "preferred_slots", tuple(self.preferred_slots))

    def prefers(self, slot: TimeSlot) -> bool:
        """True when the slot falls inside any preferred window.

        Containment, not equality: a session that prefers Monday morning
        is satisfied by any Monday morning slot.
        """
        return any(window.contains(slot) for window in self.preferred_slots)


@dataclass(frozen=True)
class Assignment:
    """A session placed in a particular room at a particular time.

    This is the unit the scheduler builds up: one line of the finished
    timetable.
    """

    session: Session
    slot: TimeSlot
    room: Room


@dataclass
class Timetable:
    """The finished schedule: a list of assignments plus some views on it."""

    assignments: list = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.assignments)

    def __iter__(self):
        return iter(self.assignments)

    def for_lecturer(self, lecturer_id: str) -> list:
        return [a for a in self.assignments if a.session.lecturer_id == lecturer_id]

    def for_room(self, room_id: str) -> list:
        return [a for a in self.assignments if a.room.room_id == room_id]

    def for_group(self, student_group: str) -> list:
        return [a for a in self.assignments if a.session.student_group == student_group]

    def preference_score(self) -> int:
        """How many sessions landed in a slot their owner asked for.

        A quality measure, not a correctness one: a low score is a less
        pleasant timetable, never an invalid one.
        """
        return sum(1 for a in self.assignments if a.session.prefers(a.slot))

    def as_rows(self) -> list:
        """Rows of (unit, day, time, room), sorted into week order."""
        rows = [
            (a.session.unit_code, a.slot.day, str(a.slot), a.room.room_id)
            for a in self.assignments
        ]
        return sorted(rows, key=lambda r: (DAYS.index(r[1]), r[2]))


def build_week(days=DAYS, start: int = 9, end: int = 17, block: int = 2) -> list:
    """Chop each day into equal teaching blocks.

    A partial block at the end of the day is discarded rather than
    offered as a short slot, because a session must exactly fill its
    slot.
    """
    if isinstance(block, bool) or not isinstance(block, int) or block <= 0:
        raise ValidationError("block must be a whole number greater than zero")

    slots = []
    for day in days:
        hour = start
        while hour + block <= end:
            slots.append(TimeSlot(day, hour, hour + block))
            hour += block
    return slots
