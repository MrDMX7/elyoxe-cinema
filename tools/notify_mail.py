"""notify_mail.py — the laptop's notification road: one SES email to the owner (stdlib + boto3, ap-south-1).

run.sh's note() reaches the owner through the Fold's `notify` (termux-env.sh → a phone notification). On the
Windows laptop — the primary runner since 2026-10-01 — that function never exists, so every alert since then
only printed «notify (unavailable)» into the log: two multi-day freezes (10-01→10-09, 10-09→10-17) were
"alerted" that way and nobody saw them. note() now falls back to this script when `notify` is undefined and
the run is a real one (CINEMA_ENV_SH unset: the test sandbox always sets it, so a test never mails).

    python tools/notify_mail.py "<title>" "<body>"      exit 0 sent, 1 not sent (printed to stderr)

Sender hello@elyoxe.com (elyoxe.com is a verified SES identity, production access on), recipient the
owner's own Gmail (also a verified identity). No retries: alerts.py already makes a standing condition
notify once, and the next run tries again if a send fails.
"""
from __future__ import annotations

import sys

REGION = "ap-south-1"
FROM = "سينما <hello@elyoxe.com>"
TO = ["dmxalkaabi@gmail.com"]


def send(title: str, body: str) -> None:
    import boto3

    ses = boto3.client("ses", region_name=REGION)
    ses.send_email(
        Source=FROM,
        Destination={"ToAddresses": TO},
        Message={"Subject": {"Data": f"[سينما] {title}", "Charset": "UTF-8"},
                 "Body": {"Text": {"Data": body + "\n\n— cinema-runner (اللابتوب)\n", "Charset": "UTF-8"}}},
    )


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: notify_mail.py <title> <body>", file=sys.stderr)
        return 2
    try:
        send(argv[0], argv[1])
    except Exception as e:  # noqa: BLE001 - a failed alert must never fail the run; the log keeps the text
        print(f"notify_mail: not sent: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
