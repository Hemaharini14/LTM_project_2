"""
Curated facts for well-known scholarships that fund study across many
universities, not any single institution this app already holds data
for — Chevening funds a UK master's at whichever university accepts
you, for example, so it has no home in the per-university corpus.

Award amounts and deadlines shift every cycle, so none are stated here.
Only facts that stay true year over year are — what a scholarship
covers in kind, who funds it, the broad shape of eligibility — and the
official page is always given for the current figure. This mirrors how
ADMISSION_SYSTEMS in recommender.py explains a country's admission
system instead of inventing a number nobody reports.
"""

SCHOLARSHIPS = {
    "chevening": {
        "name": "Chevening Scholarship",
        "funder": "UK Government (Foreign, Commonwealth & Development Office)",
        "covers": (
            "Full tuition, a living allowance, and economy travel to and "
            "from the UK, for a one-year master's degree at any UK "
            "university that admits the candidate."
        ),
        "eligibility": (
            "Citizens of a Chevening-eligible country (most countries "
            "outside the UK and US), with at least two years of work "
            "experience and an undergraduate degree that qualifies them "
            "for a UK master's, who commit to returning to their home "
            "country for at least two years afterward."
        ),
        "notes": (
            "Chevening funds the degree; it does not grant admission — "
            "candidates must separately apply to and be accepted by a UK "
            "university."
        ),
        "official_url": "https://www.chevening.org",
        "aliases": ["chevening"]
    },
    "fulbright": {
        "name": "Fulbright Program",
        "funder": (
            "US Government (Bureau of Educational and Cultural Affairs), "
            "jointly with partner countries"
        ),
        "covers": (
            "Tuition, a living stipend, travel and health insurance for "
            "graduate study, research or teaching — in the US for "
            "international students, or abroad for US citizens — "
            "typically for one academic year."
        ),
        "eligibility": (
            "Varies by the roughly 160 participating countries, but "
            "generally requires a completed bachelor's degree and "
            "citizenship of a participating country. Applications go "
            "through the Fulbright Commission or US Embassy in the "
            "applicant's home country, not a single central office."
        ),
        "notes": None,
        "official_url": "https://foreign.fulbrightonline.org",
        "aliases": ["fulbright"]
    },
    "commonwealth": {
        "name": "Commonwealth Scholarship",
        "funder": "UK Government, for citizens of other Commonwealth countries",
        "covers": (
            "Full tuition, living allowance and travel for master's or "
            "PhD study at a UK university, under schemes aimed mainly at "
            "students from low- and middle-income Commonwealth countries."
        ),
        "eligibility": (
            "Citizens of a Commonwealth country other than the UK, "
            "normally with a first degree classed at least upper-second "
            "class or equivalent; the exact scheme (shared, split-site, "
            "distance learning) and its criteria depend on the "
            "applicant's home country."
        ),
        "notes": None,
        "official_url": "https://cscuk.fcdo.gov.uk",
        "aliases": ["commonwealth scholarship", "commonwealth scholarships"]
    },
    "daad": {
        "name": "DAAD Scholarship",
        "funder": "German Academic Exchange Service (Deutscher Akademischer Austauschdienst)",
        "covers": (
            "A monthly stipend, travel allowance, and health insurance "
            "for study or research in Germany, with the specific "
            "programme (and whether tuition is included) depending on "
            "which DAAD scheme the applicant applies through — German "
            "public universities themselves charge little to no tuition "
            "regardless."
        ),
        "eligibility": (
            "Varies by programme and home country; most require a "
            "relevant degree already completed and are applied for "
            "directly through the specific DAAD programme, not a single "
            "general pool."
        ),
        "notes": None,
        "official_url": "https://www.daad.de/en",
        "aliases": ["daad"]
    },
    "erasmus mundus": {
        "name": "Erasmus Mundus Joint Master's Scholarship",
        "funder": "European Union",
        "covers": (
            "Tuition, a monthly living allowance, travel and insurance "
            "for a joint master's degree studied across at least two "
            "European universities participating in the chosen Erasmus "
            "Mundus programme."
        ),
        "eligibility": (
            "Open to students worldwide; eligibility and selection are "
            "set by each individual Erasmus Mundus joint programme, not "
            "centrally, so requirements vary by the specific degree "
            "applied to."
        ),
        "notes": None,
        "official_url": "https://erasmus-plus.ec.europa.eu",
        "aliases": ["erasmus mundus", "erasmus scholarship"]
    },
    "rhodes": {
        "name": "Rhodes Scholarship",
        "funder": "Rhodes Trust",
        "covers": (
            "Full tuition and fees at the University of Oxford, plus a "
            "living stipend, for a two- or three-year postgraduate "
            "degree."
        ),
        "eligibility": (
            "Open to candidates from a defined set of countries and "
            "constituencies (each with its own selection committee and "
            "quota), normally aged 18-25 with a strong academic record "
            "and demonstrated leadership and service."
        ),
        "notes": "One of the oldest international scholarships, funding study at Oxford specifically.",
        "official_url": "https://www.rhodeshouse.ox.ac.uk",
        "aliases": ["rhodes scholarship"]
    },
    "gates cambridge": {
        "name": "Gates Cambridge Scholarship",
        "funder": "Bill & Melinda Gates Foundation",
        "covers": (
            "Full tuition and fees at the University of Cambridge, a "
            "living allowance, and additional funding such as airfare, "
            "for a full-time postgraduate degree there."
        ),
        "eligibility": (
            "Open to citizens of any country outside the UK applying "
            "for a full-time postgraduate course at Cambridge; "
            "candidates must first apply to and be admitted by Cambridge "
            "before being considered."
        ),
        "notes": None,
        "official_url": "https://www.gatescambridge.org",
        "aliases": ["gates cambridge", "gates scholarship"]
    },
    "schwarzman": {
        "name": "Schwarzman Scholars",
        "funder": "Schwarzman Scholars program, funded by private donors",
        "covers": (
            "Full tuition, room and board, travel and a stipend for a "
            "one-year master's in global affairs at Tsinghua University "
            "in Beijing."
        ),
        "eligibility": (
            "Open to candidates worldwide, typically aged 18-29 with a "
            "bachelor's degree; the programme is taught in English and "
            "does not require Chinese language ability."
        ),
        "notes": None,
        "official_url": "https://www.schwarzmanscholars.org",
        "aliases": ["schwarzman scholars", "schwarzman scholarship"]
    },
    "knight-hennessy": {
        "name": "Knight-Hennessy Scholars",
        "funder": "Knight-Hennessy Scholars program at Stanford University",
        "covers": (
            "Full tuition and a living stipend for up to three years of "
            "graduate study in any of Stanford's graduate degree "
            "programs."
        ),
        "eligibility": (
            "Open to candidates worldwide who are applying to or already "
            "admitted to a Stanford graduate program; selection is "
            "separate from, and in addition to, Stanford's own admission "
            "decision."
        ),
        "notes": None,
        "official_url": "https://knight-hennessy.stanford.edu",
        "aliases": ["knight-hennessy", "knight hennessy"]
    },
    "rotary peace fellowship": {
        "name": "Rotary Peace Fellowship",
        "funder": "The Rotary Foundation",
        "covers": (
            "Tuition, housing, travel and internship or field-study "
            "expenses for a master's degree or a professional "
            "development certificate at one of a small set of partner "
            "Rotary Peace Centers."
        ),
        "eligibility": (
            "Open to candidates worldwide with relevant work or "
            "volunteer experience in peace and development; applications "
            "go through Rotary districts and clubs, not a single central "
            "portal."
        ),
        "notes": None,
        "official_url": "https://www.rotary.org/en/our-programs/peace-fellowships",
        "aliases": ["rotary peace fellowship", "rotary peace scholarship"]
    },
}


def find_scholarship(question):
    """
    The curated scholarship this question names, if any — matched by
    alias so "chevening", "Chevening Scholarship" and "the Chevening"
    all resolve to the same entry.
    """

    lowered = question.lower()

    for info in SCHOLARSHIPS.values():
        if any(alias in lowered for alias in info["aliases"]):
            return info

    return None


def describe_scholarship(info):
    """One grounded paragraph a chat answer can quote from directly,
    deliberately withholding any amount or date that goes stale."""

    parts = [
        f"{info['name']}, funded by {info['funder']}.",
        f"What it covers: {info['covers']}",
        f"Eligibility: {info['eligibility']}",
    ]

    if info.get("notes"):
        parts.append(info["notes"])

    parts.append(
        f"This record deliberately omits exact award amounts and "
        f"deadlines, since they change every cycle — the current figures "
        f"are published at {info['official_url']}."
    )

    return " ".join(parts)
