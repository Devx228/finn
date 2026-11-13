"""Scan every commit in the git history for key-like strings. Prints commit, file and the kind of
match only, never the value. Run before making the repository public:

    python scripts/secret_scan_history.py
"""

import re
import subprocess
import sys

PATTERNS = {
    "google_api_key": r"AIza[0-9A-Za-z_\-]{30,}",
    "groq_key": r"gsk_[0-9A-Za-z]{20,}",
    "github_token": r"(?:ghp|gho|ghs|ghu)_[0-9A-Za-z]{30,}|github_pat_[0-9A-Za-z_]{30,}",
    "neon_password": r"npg_[0-9A-Za-z]{10,}",
    "postgres_url_with_password": r"postgres(?:ql)?://[^:\s/]+:(?!finn@)[^@\s]{6,}@[^\s'\"]+",
    "openai_like": r"\bsk-[0-9A-Za-z]{20,}",
    "private_key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
}


def main() -> int:
    log = subprocess.run(
        ["git", "log", "-p", "--all", "--no-color", "--format=@@commit %H"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    ).stdout
    commit = path = None
    hits = set()
    for line in log.splitlines():
        if line.startswith("@@commit "):
            commit = line[9:17]
        elif line.startswith("+++ b/"):
            path = line[6:]
        elif line.startswith("+") and not line.startswith("+++"):
            for name, rx in PATTERNS.items():
                if re.search(rx, line):
                    hits.add((commit, path, name))
    print(f"commits scanned: {log.count('@@commit ')} · hits: {len(hits)}")
    for h in sorted(hits):
        print("  ", *h)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
