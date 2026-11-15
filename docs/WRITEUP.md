# FINN — covering note

**Live app:** https://finn-tawny-nine.vercel.app · **Code:** https://github.com/Devx228/finn
(README has a 3-minute walk-through) · **AI build history:**
https://github.com/Devx228/finn/tree/main/docs/build-log

An investor covering Indian listed companies loses most of the day to two things: wading through
exchange filings to find the few that matter, and checking whether management did what it said it
would. FINN does both on a phone, and adds the step investors actually take next: calling someone
who knows.

**Today (push).** Every filing from the portfolio is classified, scored and ranked into *Now*,
*Worth knowing* and *Buried*. Rules decide 79% of filings without a model. Event filings are scored
from their own text, not from the exchange's category: a pollution board ordering a plant shut goes
to the top; a ₹1.6 lakh telecom penalty is buried; an order win is sized against the company's own
revenue using the size band printed in the same filing. Results cards are computed from XBRL with
QoQ and YoY; management-change cards say who, which role, joining or leaving, and from when; every
card can explain why it is where it is. Alerts on volume, price and filing type are tuned by the
user and evaluated instantly.

**Research (pull): the Promise Ledger.** For any NSE company, FINN reads the last eight earnings
calls, extracts management's numeric guidance verbatim, chains it from first statement through
cuts, raises and verbal steers to the result, and scores it against the company's own reported
figure. The hero example is CreditAccess Grameen: FY26 loan growth *missed the preliminary 18–20%
outlook, met the lowered 14–18%, at the very bottom of the range*, after management told analysts
in October to expect the lower end. Every step opens the transcript at its page. A ticker FINN has
never seen can be researched from the phone: a job runs on a GitHub Actions runner and the report
arrives in about three minutes, marked as unreviewed.

**People (network).** Each card and research page answers "who can help?": contacts ranked by how
close they are to the company and how warm the relationship is, former employees before current
ones (who carry an insider warning), executives' careers exactly as their appointment filings
state them, and second-degree paths with the evidence for each link. The network is synthetic and
labelled so.

**What I optimised for: being right, visibly.** Code computes; models only read. A model-extracted
claim survives only if its quote is verbatim in the source; a model-written headline is dropped if
it contains a period or number the filing doesn't. A guidance claim is held to a year only if its
quote names the year. Where evidence is missing the app says so: *not scored*, *no year stated*,
*years not stated*, *not read yet*. I measured rather than assumed: 26 hand-listed guidance claims
and 25 deliberate traps across 8 transcripts (precision 23/23 on scored claims, recall 0.88, no
trap accepted), 124 labelled filings, and a ranking regression set built from the failures I found.

**What went wrong, and what it taught me.** The first unreviewed live report (Polycab) showed four
"delivered" verdicts; all four were wrong, scored from achievements, a revenue-mix target and a
segment figure. The rules that caught them now apply to every company, which cut my own hero's
resolved count from five to three. A filter scoring whole exchange categories hid a plant closure
behind a generic label; checking one "moved with no disclosure" alert exposed it. Each fix became a
general rule and a regression test, never a special case.

**Constraints.** Zero spend: free model tiers and a local model (₹0 actual; the cost screen shows
what the same work would cost at paid rates), free hosting, a read path with no model calls and a
bundled snapshot when the API is asleep. Exchange data is fetched politely and minimally, cached,
never re-hosted, and linked to its source; NSE refused my campus network, and I stopped until a
different connection was confirmed to work rather than working around the block.

**Deliberate cuts:** no open-ended chat, no balance-sheet or cash-quality sections, no native app
or intraday exchange feed, and no login. Thin and correct seemed better than broad and wrong.

---

# Writeup notes (source material)

## Data access

All market filings, annual reports, earnings-call transcripts and quarterly results come from
the National Stock Exchange of India's public website, and end-of-day prices from Yahoo
Finance. NSE's terms of use do not permit systematic automated collection or republishing
without permission; we accessed it only because the brief directs candidates to exchange
filings, and only for this personal, non-commercial evaluation prototype. To keep the footprint
minimal, FINN makes one request at a time at no more than one per second, caches every
response, never downloads the same document twice, and fetches only the demo companies and
tickers a user explicitly asks about — no crawling. It does not re-host any document: it keeps
extracted text for analysis, shows short cited quotes and computed numbers, and links back to
the original filing on NSE, which is credited as the source throughout the app. A production
deployment would replace all of this with a licensed exchange data feed.
