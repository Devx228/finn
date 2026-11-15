# FINN submission runbook

The authoritative source is `docs/brief.pdf` (identical to the original root PDF). It requires a
mobile-first working prototype, a public GitHub repository, AI build history and a short covering
note. The PDF gives the date **15 November 2026** but no time or timezone; submit as soon as the
checks below are green rather than assuming an end-of-day cutoff.

## Final checks before sending

- [ ] `https://finn-tawny-nine.vercel.app` opens without login on a phone.
- [ ] Today, Research and People each complete one end-to-end workflow.
- [ ] Android/desktop: Settings → Enable alerts → Send test alert; tapping it opens the card.
- [ ] `bash scripts/verify.sh` ends `OK: all checks green`.
- [ ] `python scripts/secret_scan_history.py` reports zero hits.
- [ ] Git working tree is clean and the final commit is pushed.
- [ ] GitHub repository visibility is **Public** and its logged-out URL opens.
- [ ] `docs/build-log/README.md` and its five sanitized session exports open on GitHub.

## What to send

Send one email—no separate form is named in the brief.

- **To:** `assessment@enam.com`
- **Subject (copy exactly):** `IIT Kanpur – Founding AI Engineer - 2027`
- **Body:** paste the covering note from `docs/WRITEUP.md`, stopping at the `---` before “Writeup
  notes”. Keep the links clickable.
- **Required links near the top:**
  - Live app: `https://finn-tawny-nine.vercel.app`
  - Public repository: `https://github.com/Devx228/finn`
  - AI build history: `https://github.com/Devx228/finn/tree/main/docs/build-log`
- State explicitly that the investor network is synthetic and labelled, and that a real deployment
  would ingest consented connections/CRM data with tenant isolation and access control.
- A short screen recording is optional, not required by the PDF. If there is time, use the README's
  3-minute route; do not delay the required email for extra polish.

Do not email environment files, database dumps, cached source documents, API keys or a private-key
file. The repository link is the code deliverable; a zip is unnecessary unless ENAM asks for one.

## Immediately after sending

1. Confirm the sent email shows the exact recipient, subject and three working links.
2. Open each link from a private/incognito window.
3. Keep Vercel, Render and Neon running and do not rotate VAPID/model/database keys during review.
4. Save the sent-email timestamp and a screenshot/PDF of the sent message as submission evidence.
