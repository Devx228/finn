"""Stage 1 classifier: exchange category + subject/text patterns → reference category.

Categories are the reference document's 17, unchanged. Sub-types are FINN's judgment (spec §8.1).
Returns None when the rules cannot place a filing; those go to the batched model (stage 2).
Every decision carries a short reason so "Why is this here?" can show it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CATEGORIES = (
    "results",
    "M&A",
    "fund_raise",
    "management_change",
    "litigation",
    "insider_trading",
    "earnings_call",
    "investor_meetings",
    "credit_rating",
    "dividend",
    "bonus_split",
    "capex",
    "press_release",
    "postal_ballot",
    "agm_egm",
    "pledging",
    "unclassified",
)


@dataclass(frozen=True)
class Classified:
    category: str
    sub_type: str | None
    base: int  # 0–60 base score (spec §8.6); materiality for the model stage
    reason: str
    decided_by: str = "rules"


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p, re.I)


TOP_ROLE = _rx(
    r"\b(chief executive|ceo\b|chief financial|cfo\b|managing director|whole[- ]?time director"
    r"|executive director|chief operating|coo\b)"
)
CS_SMP = _rx(
    r"\b(company secretary|compliance officer|senior management|smp\b|chief (risk|technology"
    r"|human|marketing|information|digital|compliance)|head of)"
)
INDEP = _rx(r"\b(independent director|non[- ]executive|nominee director|additional director)")
REAPPOINT = _rx(r"\bre-?appoint")
RESULTS = _rx(r"\b(financial results?|unaudited results|audited results|quarterly results)")
DIVIDEND = _rx(r"\bdividend")
BONUS_SPLIT = _rx(r"\b(bonus|split|sub-?division of)")
TRANSCRIPT = _rx(r"\btranscript")
RECORDING = _rx(r"\b(audio|video|recording|webcast)")
CALL_NOTICE = _rx(r"\b(earnings call|conference call|con\.? call|analysts? call|investor call)")
MEET = _rx(
    r"\b(analyst|investor|institutional|fund|conference|roadshow|non[- ]deal|one[- ]on[- ]one|"
    r"group meeting|meet)"
)
UPGRADE = _rx(
    r"\b(upgrad|downgrad|revis(ed|ion) (in|of) (the )?(rating|outlook)|outlook (to|changed)"
    r"|placed on (rating )?watch|credit watch)"
)
REAFFIRM = _rx(r"\b(reaffirm|re-affirm|affirm)")
DEBT = _rx(r"\b(commercial paper|non[- ]convertible|ncds?\b|debentures?|bonds?\b)")
EQUITY_RAISE = _rx(r"\b(qualified institutional|qip\b|preferential|rights issue|buy-?back|warrants)")
ESOP = _rx(r"\b(esop|esos|esps|stock option|employee stock|restricted stock)")
SUBSIDIARY_ROUTINE = _rx(
    r"\b(incorporat\w+ (of )?(a )?(wholly[- ]owned )?(step[- ]down )?subsidiary"
    r"|wholly[- ]owned subsidiary.{0,40}(incorporat|capital|infusion|subscri))"
)
CAPEX = _rx(
    r"\b(capex|capital expenditure|capacity (expansion|addition)|new (plant|facility|unit)"
    r"|greenfield|brownfield|commission(ed|ing) of|commencement of commercial production)"
)
MNA = _rx(
    r"\b(acqui(re|sition)|merger|amalgamat|demerger|scheme of arrangement|joint venture"
    r"|stake (sale|purchase)|divest|disinvest|sale of (business|undertaking|stake))"
)
ORDER = _rx(r"\b(order|contract)s? (win|received|bagged|worth|valued|aggregating)|bagging|receipt of orders?")
LITIGATION = _rx(
    r"\b(penalt|show cause|demand order|tax demand|assessment order|nclt|insolvency|court"
    r"|tribunal|sebi order|regulatory action|search|investigation|litigation|dispute)"
)
AUDITOR_EXIT = _rx(
    r"\b(resign\w*|cessation|removal)\b.{0,80}\b(statutory )?auditor|auditor\w*.{0,80}"
    r"\b(resign|cessation)"
)
QUALIFIED = _rx(r"\b(qualified opinion|adverse opinion|disclaimer of opinion|modified opinion)")
ROUTINE = _rx(
    r"\b(loss of share certificate|duplicate share certificate|trading window|closure of"
    r"|reg(ulation)?\.? ?74 ?\(5\)|investor grievance|newspaper|publication|e-?voting"
    r"|book closure|transfer of shares to iepf|iepf|change in (registered )?address)"
)

# Exchange category → (category, sub_type, base, reason) for unambiguous cases.
DIRECT: dict[str, tuple[str, str | None, int, str]] = {
    "copy of newspaper publication": ("unclassified", "newspaper_copy", 2, "newspaper copy"),
    "esop/esos/esps": ("unclassified", "esop", 4, "employee stock options"),
    "certificate under sebi (depositories and participants) regulations, 2018": (
        "unclassified",
        "reg74_certificate",
        1,
        "Reg 74(5) compliance certificate",
    ),
    "trading window": ("unclassified", "trading_window", 1, "trading-window closure"),
    "committee meeting updates": ("unclassified", "committee_meeting", 5, "committee meeting"),
    "monitoring agency report": ("unclassified", "monitoring_agency", 6, "monitoring agency report"),
    "statement of deviation(s) or variation(s) under reg. 32": (
        "unclassified",
        "use_of_proceeds",
        8,
        "use-of-proceeds statement",
    ),
    "giving guarantees/indemnity/ becoming a surety for third party": (
        "unclassified",
        "guarantee",
        12,
        "guarantee given",
    ),
    "options to purchase securities": ("unclassified", "esop", 4, "stock options"),
    "corrigendum": ("unclassified", "corrigendum", 5, "corrigendum"),
    "address change": ("unclassified", "admin", 1, "address change"),
    "amendment to aoa/moa": ("unclassified", "admin", 6, "articles/memorandum amendment"),
    "related party transactions": ("unclassified", "related_party", 18, "related-party transaction"),
    "investor presentation": ("investor_meetings", "presentation", 18, "investor presentation"),
    "pendency of litigation(s)/dispute(s) or the outcome impacting the company": (
        "litigation",
        None,
        40,
        "litigation update",
    ),
    "rumour verification - regulation 30(11)": (
        "press_release",
        "rumour_clarification",
        52,
        "rumour clarification (promoted)",
    ),
    "news verification": ("press_release", "rumour_clarification", 48, "news verification (promoted)"),
    "bagging/receiving of orders/contracts": ("press_release", "order_win", 38, "order win"),
    "monthly business updates": ("press_release", "business_update", 30, "monthly business update"),
    "product launch": ("press_release", "product_partnership", 25, "product launch"),
    "adoption of new line(s) of business": ("press_release", "new_business", 42, "new line of business"),
    "acquisition": ("M&A", None, 50, "acquisition"),
    "amalgamation/merger": ("M&A", None, 50, "merger / amalgamation"),
    "scheme of arrangement": ("M&A", None, 48, "scheme of arrangement"),
    "sale or disposal": ("M&A", "divestment", 45, "sale or disposal"),
    "diversification/disinvestment": ("M&A", "divestment", 45, "diversification / disinvestment"),
    "commencement of commercial production/operations": (
        "capex",
        "commissioning",
        42,
        "commercial production started",
    ),
    "capacity addition": ("capex", None, 45, "capacity addition"),
    "qualified institutional placement": ("fund_raise", "equity_raise", 58, "QIP"),
    "preferential issue": ("fund_raise", "equity_raise", 55, "preferential issue"),
    "disclosure under sebi takeover regulations": ("insider_trading", "sast", 35, "takeover-code disclosure"),
    "clarification - financial results": ("results", "clarification", 30, "results clarification"),
    "reply to clarification- financial results": ("results", "clarification", 30, "results clarification"),
}

MGMT = {
    "change in management",
    "appointment",
    "resignation",
    "cessation",
    "retirement",
    "change in director(s)",
    "resignation of director/kmp/smp",
}
LLM_CATEGORIES = {"general updates", "updates", "disclosure of material issue", "agreements"}


def classify(exch_category: str | None, subject: str | None, text: str | None = None) -> Classified | None:
    cat = (exch_category or "").strip().lower()
    subj = subject or ""
    blob = f"{subj} {(text or '')[:3000]}"

    # Promotions that override everything (spec §8.1 'unclassified' exception).
    auditor_change = "change in auditors" in cat and re.search(r"resign|cessation", blob, re.I)
    if AUDITOR_EXIT.search(blob) or auditor_change:
        return Classified(
            "unclassified", "auditor_resignation", 60, "statutory auditor leaving mid-term (promoted)"
        )
    if QUALIFIED.search(blob):
        return Classified("unclassified", "qualified_opinion", 60, "modified audit opinion (promoted)")

    if cat == "disclosure under sebi takeover regulations" and re.search(
        r"31\s*\(\s*[1-4]\s*\)|encumbr|pledg", blob, re.I
    ):
        return Classified(
            "pledging", "encumbrance_declaration", 12, "promoter encumbrance (pledge) declaration"
        )
    if cat in DIRECT:
        c, st, base, why = DIRECT[cat]
        if c == "M&A" and SUBSIDIARY_ROUTINE.search(subj):
            return Classified("M&A", "routine_subsidiary_infusion", 20, "routine subsidiary step")
        return Classified(c, st, base, why)

    if cat in MGMT:
        if TOP_ROLE.search(blob) and not REAPPOINT.search(subj):
            return Classified("management_change", "kmp_change", 58, "CEO/CFO/MD-level change")
        if REAPPOINT.search(blob) and not re.search(r"resign|cessation", blob, re.I):
            return Classified("management_change", "re_appointment", 10, "re-appointment")
        if INDEP.search(blob):
            return Classified(
                "management_change",
                "independent_director_rotation",
                30,
                "independent / non-executive director change",
            )
        if CS_SMP.search(blob):
            return Classified("management_change", "smp_change", 28, "company secretary / senior management")
        return None  # role not stated in the subject; needs the text or the model

    if cat == "change in auditors":
        return Classified("unclassified", "auditor_appointment", 8, "auditor appointment (routine)")

    if cat.startswith("credit rating"):
        if UPGRADE.search(blob):
            return Classified("credit_rating", "rating_action", 48, "rating upgrade/downgrade/outlook change")
        if REAFFIRM.search(blob):
            return Classified("credit_rating", "reaffirmation", 8, "rating reaffirmed")
        return Classified("credit_rating", "new_rating", 22, "rating assigned")

    if cat == "analysts/institutional investor meet/con. call updates":
        if TRANSCRIPT.search(subj):
            return Classified("earnings_call", "transcript", 32, "earnings-call transcript")
        if RECORDING.search(subj):
            return Classified("earnings_call", "recording", 6, "call recording link")
        if CALL_NOTICE.search(subj):
            return Classified("earnings_call", "call_notice", 12, "earnings-call notice")
        return Classified("investor_meetings", None, 6, "investor / analyst meeting schedule")

    if cat == "outcome of board meeting":
        if RESULTS.search(subj):
            return Classified("results", "results_filing", 55, "financial results")
        if DIVIDEND.search(subj):
            return Classified("dividend", None, 35, "dividend declared")
        if EQUITY_RAISE.search(subj):
            return Classified("fund_raise", "equity_raise", 55, "equity raise approved")
        return None

    if cat == "shareholders meeting":
        if re.search(r"postal ballot", blob, re.I):
            return Classified("postal_ballot", None, 6, "postal ballot")
        return Classified("agm_egm", None, 6, "general meeting")

    if cat in ("record date", "dividend"):
        if BONUS_SPLIT.search(blob):
            return Classified("bonus_split", None, 35, "bonus / split")
        if DIVIDEND.search(blob):
            return Classified("dividend", None, 35, "dividend record date")
        return Classified("unclassified", "record_date", 8, "record date")

    if cat in ("allotment of securities", "issue of securities"):
        if ESOP.search(blob):
            return Classified("unclassified", "esop", 4, "ESOP allotment")
        if DEBT.search(blob):
            return Classified("fund_raise", "routine_debt", 8, "debt issue / allotment")
        if EQUITY_RAISE.search(blob):
            return Classified("fund_raise", "equity_raise", 52, "equity issue")
        return None

    if cat == "action(s) taken or orders passed":
        return Classified("litigation", None, 34, "regulatory / tax action or order")

    if cat.startswith("press release"):
        if RESULTS.search(subj):
            return Classified("results", "press_release", 30, "results press release")
        return None

    if cat in LLM_CATEGORIES or not cat:
        # Patterns that are reliable even inside generic "Updates".
        if ROUTINE.search(subj):
            return Classified("unclassified", "routine", 2, "routine compliance")
        if CAPEX.search(subj):
            return Classified("capex", None, 42, "capacity / plant update")
        if SUBSIDIARY_ROUTINE.search(subj):
            return Classified("M&A", "routine_subsidiary_infusion", 20, "routine subsidiary step")
        return None

    return None
