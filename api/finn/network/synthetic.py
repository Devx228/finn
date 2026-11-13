"""Synthetic investor network (spec §4.3). Deterministic (fixed seed); every person is fictional
and flagged is_synthetic. Real organisations appear as employers and alma maters — that is
public, organisational information, not personal data about a real individual.

What the investor "gives FINN": a connections export (name, company, position, connected-on),
a meeting log with their own notes, and their CV. The notes record the investor's OWN views and
questions — never words attributed to a real executive.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

TENANT = 1
SEED = 20261113
TODAY = date(2026, 11, 13)

FIRST = [
    "Aarav",
    "Vihaan",
    "Ishaan",
    "Kabir",
    "Arjun",
    "Reyansh",
    "Aditya",
    "Rohan",
    "Karan",
    "Nikhil",
    "Siddharth",
    "Varun",
    "Pranav",
    "Rahul",
    "Manish",
    "Gaurav",
    "Akash",
    "Dev",
    "Ananya",
    "Diya",
    "Ira",
    "Meera",
    "Riya",
    "Saanvi",
    "Tara",
    "Kavya",
    "Nisha",
    "Pooja",
    "Shreya",
    "Aditi",
    "Neha",
    "Priyanka",
    "Radhika",
    "Sneha",
    "Tanvi",
    "Zoya",
    "Farhan",
    "Imran",
    "Joseph",
    "Thomas",
    "Harpreet",
    "Gurpreet",
    "Venkat",
    "Lakshmi",
    "Suresh",
]
LAST = [
    "Agarwal",
    "Bhatia",
    "Chopra",
    "Desai",
    "Gokhale",
    "Iyer",
    "Joshi",
    "Kulkarni",
    "Menon",
    "Nair",
    "Pillai",
    "Rao",
    "Shetty",
    "Sinha",
    "Trivedi",
    "Varma",
    "Banerjee",
    "Chatterjee",
    "Dutta",
    "Ghosh",
    "Mukherjee",
    "Sengupta",
    "Kapadia",
    "Mistry",
    "Sethi",
    "Malhotra",
    "Khanna",
    "Saxena",
    "Tandon",
    "Fernandes",
    "D'Costa",
    "Qureshi",
    "Siddiqui",
    "Hegde",
    "Kamath",
    "Reddy",
    "Naidu",
    "Gill",
    "Sandhu",
    "Ahuja",
]
CITIES = [
    "Mumbai",
    "Mumbai",
    "Mumbai",
    "Bengaluru",
    "Bengaluru",
    "Delhi NCR",
    "Delhi NCR",
    "Pune",
    "Chennai",
    "Hyderabad",
    "Ahmedabad",
    "Kolkata",
    "Singapore",
    "London",
]

# Real institutions (alma maters).
INSTITUTIONS = [
    "IIM Ahmedabad",
    "IIM Bangalore",
    "IIM Calcutta",
    "IIT Bombay",
    "IIT Delhi",
    "IIT Madras",
    "Institute of Chartered Accountants of India",
    "XLRI Jamshedpur",
    "SRCC Delhi",
    "Jamnalal Bajaj Institute",
    "ISB Hyderabad",
    "NMIMS Mumbai",
]

# Real organisations by theme: portfolio/research companies first, then adjacent employers.
THEME_ORGS = {
    "banking": [
        "HDFC Bank Limited",
        "AU Small Finance Bank Limited",
        "ICICI Bank",
        "Axis Bank",
        "Kotak Mahindra Bank",
        "Reserve Bank of India",
        "State Bank of India",
    ],
    "rural lending": [
        "Bajaj Finance Limited",
        "CREDITACCESS GRAMEEN LIMITED",
        "Cholamandalam Investment and Finance",
        "Mahindra & Mahindra Financial Services",
        "Spandana Sphoorty",
        "Ujjivan Small Finance Bank",
    ],
    "IT services": [
        "Infosys Limited",
        "Persistent Systems Limited",
        "KPIT Technologies Limited",
        "HCLTech",
        "Tata Consultancy Services",
        "Wipro",
        "Nagarro",
    ],
    "specialty chemicals": [
        "Deepak Nitrite Limited",
        "PI Industries Limited",
        "SRF",
        "Aarti Industries",
        "Navin Fluorine International",
        "UPL",
    ],
    "semiconductors & electronics": [
        "Dixon Technologies (India) Limited",
        "Kaynes Technology India Limited",
        "CG Power and Industrial Solutions Limited",
        "Tata Electronics",
        "Amber Enterprises",
        "Foxconn India",
    ],
    "consumer": [
        "Titan Company Limited",
        "Trent Limited",
        "Varun Beverages Limited",
        "Hindustan Unilever",
        "Avenue Supermarts",
        "PepsiCo India",
    ],
    "pharma": ["Sun Pharmaceutical Industries Limited", "Dr. Reddy's Laboratories", "Cipla", "Lupin"],
    "industrials & infra": [
        "Larsen & Toubro Limited",
        "UltraTech Cement Limited",
        "Siemens India",
        "ACC",
        "Ambuja Cements",
    ],
    "metals & telecom": ["Tata Steel Limited", "Bharti Airtel Limited", "JSW Steel", "Vodafone Idea"],
    "autos": [
        "Mahindra & Mahindra Limited",
        "Maruti Suzuki India Limited",
        "Tata Motors",
        "Cummins India",
        "Bosch India",
    ],
    "markets": [
        "Kotak Institutional Equities",
        "Motilal Oswal",
        "Jefferies India",
        "HDFC Mutual Fund",
        "SBI Mutual Fund",
        "McKinsey & Company",
        "EY India",
    ],
}
FUNCTIONS = [
    "finance",
    "operations",
    "sales",
    "strategy",
    "legal-compliance",
    "R&D-technical",
    "treasury-credit",
    "IR",
    "HR",
    "general-management",
]
TITLES = {
    "finance": ["Senior Manager, Finance", "Head of FP&A", "Deputy CFO", "CFO"],
    "operations": ["Plant Head", "VP Operations", "Head of Supply Chain", "COO"],
    "sales": ["Regional Sales Head", "VP Sales", "Head of Key Accounts", "Chief Business Officer"],
    "strategy": ["Strategy Manager", "Head of Corporate Development", "VP Strategy & M&A"],
    "legal-compliance": ["Legal Counsel", "Head of Compliance", "General Counsel"],
    "R&D-technical": ["Principal Engineer", "Head of R&D", "Chief Technology Officer"],
    "treasury-credit": ["Credit Manager", "Head of Credit Risk", "Treasurer", "Chief Risk Officer"],
    "IR": ["IR Manager", "Head of Investor Relations"],
    "HR": ["HR Business Partner", "CHRO"],
    "general-management": ["Business Head", "President", "Managing Director"],
}
HOW_KNOWN = ["ex-colleague", "classmate", "met-as-management", "industry-friend", "personal", "introduced-by"]
# Two holdings left deliberately uncovered so the coverage-gap insight has something to show.
UNCOVERED = {"PI Industries Limited", "AU Small Finance Bank Limited"}


@dataclass
class Job:
    org: str
    title: str
    function: str
    seniority: int
    start: date
    end: date | None


@dataclass
class Contact:
    name: str
    city: str
    jobs: list[Job]
    edu: list[tuple[str, str, int, int]]  # institution, degree, start_y, end_y
    how_known: str
    since: date
    last_contact: date
    interactions_24m: int
    closeness: int
    themes: list[str] = field(default_factory=list)


def _ym(y: int, m: int) -> date:
    return date(y, m, 1)


def investor() -> dict:
    return {
        "name": "You (synthetic investor persona)",
        "alma_maters": [("IIM Ahmedabad", "MBA", 2008, 2010), ("IIT Bombay", "B.Tech", 2004, 2008)],
        "employers": [
            ("Kotak Institutional Equities", "Research Analyst", _ym(2010, 6), _ym(2014, 3)),
            # 2014–2019: overlaps Anup Bagchi's stated ICICI Bank ED years (2017–2023) by more than a
            # year whatever month in 2017 he started (the filing gives only the year)
            ("ICICI Bank", "Credit Analyst", _ym(2014, 4), _ym(2019, 6)),
            ("HDFC Mutual Fund", "Fund Manager", _ym(2019, 7), None),
        ],
        "city": "Mumbai",
        "covers": ["banking", "rural lending", "specialty chemicals", "IT services"],
    }


def _career(r: random.Random, theme: str, n_jobs: int, end_open: bool) -> list[Job]:
    orgs = [o for o in THEME_ORGS[theme] if o not in UNCOVERED]
    func = r.choice(FUNCTIONS)
    y = r.randint(2004, 2014)
    jobs = []
    for i in range(n_jobs):
        org = r.choice(orgs)
        span = r.randint(2, 7)
        start = _ym(y, r.randint(1, 12))
        last = i == n_jobs - 1
        end = None if (last and end_open) else _ym(min(y + span, 2026), r.randint(1, 12))
        level = min(4, 1 + i + (1 if span > 4 else 0))
        titles = TITLES[func]
        jobs.append(Job(org, titles[min(level - 1, len(titles) - 1)], func, level + 1, start, end))
        y = (end.year if end else 2026) + (0 if r.random() < 0.6 else 1)
        if y > 2025:
            break
    return jobs


def contacts() -> list[Contact]:
    r = random.Random(SEED)
    used: set[str] = set()
    out: list[Contact] = []
    themes = list(THEME_ORGS)
    for i in range(64):
        theme = themes[i % len(themes)]
        while True:
            name = f"{r.choice(FIRST)} {r.choice(LAST)}"
            if name not in used:
                used.add(name)
                break
        jobs = _career(r, theme, r.randint(1, 3), end_open=r.random() < 0.7)
        inst, deg = r.choice(
            [
                ("IIM Ahmedabad", "MBA"),
                ("IIM Bangalore", "MBA"),
                ("Institute of Chartered Accountants of India", "CA"),
                ("IIT Bombay", "B.Tech"),
                ("IIT Delhi", "B.Tech"),
                ("XLRI Jamshedpur", "PGDM"),
                ("SRCC Delhi", "B.Com"),
                ("ISB Hyderabad", "PGP"),
                ("NMIMS Mumbai", "MBA"),
                ("IIM Calcutta", "MBA"),
            ]
        )
        ey = jobs[0].start.year - r.randint(0, 2)
        edu = [(inst, deg, ey - 2, ey)]
        how = r.choices(HOW_KNOWN, weights=[3, 2, 4, 3, 1, 2])[0]
        since = _ym(r.randint(2011, 2024), r.randint(1, 12))
        cold = r.random() < 0.25
        last = TODAY - timedelta(days=r.randint(290, 700) if cold else r.randint(5, 250))
        out.append(
            Contact(
                name,
                r.choice(CITIES),
                jobs,
                edu,
                how,
                since,
                last,
                0 if cold else r.randint(1, 10),
                r.randint(1, 5),
                [theme],
            )
        )
    return out


# Meeting log: the investor's own views and open questions (never quotes from real people).
# Several are written so a real filing in the data later confirms or contradicts them.
MEETING_NOTES = [
    (
        "Deepak Nitrite Limited",
        _ym(
            2026,
            3,
        ),
        "My view after the plant visit: growth from existing "
        "capacity; I don't expect a large new project this year. Watch for any capex above ₹1,000 cr.",
        ["capex", "specialty chemicals"],
    ),
    (
        "HDFC Bank Limited",
        _ym(2026, 2),
        "Open question for me: leadership continuity at the top "
        "after the merger integration. Track any MD & CEO succession announcement.",
        ["management", "banking"],
    ),
    (
        "Tata Steel Limited",
        _ym(2026, 5),
        "My take: balance sheet first, so I expect no new "
        "greenfield capex this year. Re-check if NINL expansion is approved.",
        ["capex", "metals"],
    ),
    (
        "Persistent Systems Limited",
        _ym(2026, 4),
        "Note to self: inorganic growth is the swing "
        "factor. A large acquisition would change the margin story.",
        ["M&A", "IT services"],
    ),
    (
        "Infosys Limited",
        _ym(2026, 6),
        "Question to track: CEO transition planning, and whether guidance bands narrow.",
        ["management", "guidance"],
    ),
    (
        "Maruti Suzuki India Limited",
        _ym(2026, 1),
        "My view: new Gujarat capacity matters more than pricing this year; check commissioning dates.",
        ["capex", "autos"],
    ),
]


def meetings(cs: list[Contact]) -> list[tuple[str, date, list[str], str, list[str]]]:
    """~40 meetings: the six anchor notes above plus routine catch-ups with contacts."""
    r = random.Random(SEED + 1)
    out = []
    for org, d, note, tags in MEETING_NOTES:
        attendees = [c.name for c in cs if any(j.org == org for j in c.jobs)][:2]
        out.append((org, d, attendees, note, tags))
    for _ in range(34):
        c = cs[r.randrange(len(cs))]
        org = c.jobs[-1].org
        d = TODAY - timedelta(days=r.randint(20, 900))
        out.append(
            (
                org,
                d,
                [c.name],
                r.choice(
                    [
                        "Catch-up on industry demand and pricing; nothing company-specific.",
                        "Discussed hiring trends and wage inflation in the sector.",
                        "Talked about competitive intensity and new entrants.",
                        "Background on the industry's working-capital cycle.",
                        "Sector conference; general views on the demand outlook.",
                    ]
                ),
                ["catch-up"],
            )
        )
    return out
