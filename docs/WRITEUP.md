# Writeup notes

Collected while building; the covering email is assembled from these.

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
