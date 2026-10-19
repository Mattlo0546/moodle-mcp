"""What's worth syncing for studying, and what's noise.

Students are enrolled in more than their courses: guidance hubs, the library's skills site, careers, department
noticeboards. Real courses also hold files nobody studies from: posters, handbooks, forms, timetables. A full sync
skips both, and says what it skipped so the student can bring a course back (see `choose`).
"""
from __future__ import annotations

import re

# A course code, e.g. EC100, MY452, LSE100, PHIL20069, COMS30030.
CODE = re.compile(r"(?<![A-Z0-9])[A-Z]{2,5}\s?\d{2,5}[A-Z]?(?![0-9])")

# Sites that aren't a course you take. A strong match means "not a course" even with a course code in the name
# (e.g. "EC100 Welcome hub"); a weak one only when there's no code ("Community Ecology BIOL20003" is a course).
NOT_A_COURSE_STRONG = re.compile(
    r"\b(guidance|induction|welcome|orientation|pre-?arrival|pre-?sessional|hub|careers?|employability|"
    r"handbook|sandbox|noticeboard|notice board|lse life|moodle help|blackboard help|help (and|&) support|"
    r"student (services|support|life|union|voice|information|centre|handbook|experience)|students'? union|"
    r"academic (skills|integrity|support|writing|advising|mentoring|conduct)|study skills|personal tutor|"
    r"(information|info) for (students|undergraduates|postgraduates)|getting started with|how to use)\b", re.I)
NOT_A_COURSE_WEAK = re.compile(
    r"\b(well-?being|mental health|training|test (course|site|area)|practice area|staff|community|society|"
    r"plagiarism|referencing|digital skills|it services|accommodation|international students?|exams? office|"
    r"library|graduate school|doctoral (school|college)|mentoring|peer|ambassadors?|volunteering|study abroad|"
    r"year abroad|erasmus|alumni|module (selection|choices?|options)|course (selection|choices?|options)|"
    r"department|programme|school of|faculty)\b", re.I)

# A site for a whole year group with no course code is a noticeboard, not a course.
CROWD = 1000

# Files that aren't for studying. Words that are also lecture topics ("induction", "consent", "privacy",
# "regulation", "survey") only count in an admin phrase.
NOT_STUDY_FILE = re.compile(
    r"\b(posters?|flyers?|leaflets?|brochures?|infographics?|banners?|handbook|timetables?|floor ?plans?|"
    r"campus map|consent forms?|privacy (notice|policy|statement)|gdpr|accessibility statement|cover ?sheets?|"
    r"(plagiarism|coursework|submission) declaration|extension request|mitigating|extenuating|deferrals?|"
    r"academic appeals?|appeals? (form|process|procedure)|code of conduct|health (and|&) safety|"
    r"fire (safety|evacuation)|safeguarding|well-?being|careers? (fair|event|service|guide|day)|internships?|"
    r"invitations?|newsletters?|certificates? of|(application|registration|feedback|request|booking|sign-?up) forms?|"
    r"(student|module|course|unit|feedback|satisfaction) surveys?|feedback questionnaires?|"
    r"welcome (pack|letter|guide|week|talk|event)|(induction|orientation) (week|pack|programme|guide|schedule|"
    r"session|event|day)|student guide|students' guide|guidance (for|on) students|student support|"
    r"disability (support|services|adjustments)|inclusion plan|terms (and|&) conditions|student charter|"
    r"(assessment|academic|exam|examination|school|university) regulations|academic integrity|"
    r"referencing guide|library guide|how to (use|access|log ?in|submit)|(moodle|blackboard|turnitin|zoom|teams|"
    r"it) guide)\b", re.I)

# Course sections that only hold admin and support material.
NOT_STUDY_SECTION = re.compile(
    r"^\s*(student support|support (and|&) wellbeing|well-?being|useful links|help|contacts?|administration|admin|"
    r"careers|library (resources|support)|announcements|forums?|news)\s*$", re.I)


def course_skip_reason(name: str, shortname: str = "", idnumber: str = "", students: int = 0) -> str:
    """Why a site isn't a course to sync ("" when it is one)."""
    text = f"{shortname} {name}"
    has_code = bool(CODE.search(f"{shortname} {name} {idnumber}".upper()))
    if NOT_A_COURSE_STRONG.search(text) or (not has_code and NOT_A_COURSE_WEAK.search(text)):
        return "looks like a guidance or information site, not a course"
    if not has_code and students >= CROWD:
        return f"a site for {students:,} students with no course code (likely a noticeboard)"
    return ""


def is_study_file(*texts: str | None) -> bool:
    """False for posters, handbooks, forms and the like. Pass the file name and the item/module title."""
    return not any(t and NOT_STUDY_FILE.search(re.sub(r"[_\-.]+", " ", t)) for t in texts)


def is_study_section(name: str | None) -> bool:
    return not (name and NOT_STUDY_SECTION.search(name))


def choose(courses: list[dict], prefs: dict) -> tuple[list[dict], list[dict]]:
    """Split courses (dicts with "id", "name", and the fields course_skip_reason takes) into (sync, skipped).

    `prefs` holds the student's own choices, {"include": [ids], "exclude": [ids]}, which beat the guesswork."""
    inc = {str(i) for i in prefs.get("include") or []}
    exc = {str(i) for i in prefs.get("exclude") or []}
    keep, skipped = [], []
    for c in courses:
        cid = str(c["id"])
        why = "you turned it off" if cid in exc else "" if cid in inc else course_skip_reason(
            c.get("name", ""), c.get("shortname", ""), c.get("idnumber", ""), c.get("students", 0))
        (skipped if why else keep).append({**c, "why": why} if why else c)
    return keep, skipped
