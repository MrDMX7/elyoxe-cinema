# «صوّتوا مع الربع»: a group vote on 2–4 shows (2026-11-20)

**Asked:** the owner asked for a link you send to friends so they vote on a film and a time («يعني رابط؟ الواحد يطرشه لربعه ويصوتون…»). He approved the design and said «Yes, vote link».
**Replaces:** the backend-less `/v/` of 2026-09 (W3-P4), where the WhatsApp chat itself was the ballot box. Nothing in the app design links to it.

## The flow

1. **Collect shows.** In a ticket (film or cinema page), «+ للتصويت» adds that show to a tray kept on the phone (`cinema.vote`, at most 4). A bar above the tab bar says how many there are, with «أرسل للربع» and ×.
2. **Send.** With 2 or more shows, «أرسل للربع» asks the sender's name once (kept as `cinema.vname`) and creates the poll on the server. It opens the phone's share sheet with `https://cinema.elyoxe.com/v/?p=<id>`, or `/en/v/?p=` on the English site.
3. **Vote.** A friend opens the link. There is no account: a name once, then «أنا معكم» on each show that suits them, or «ما أقدر هالمرة», plus one optional line (60 characters). Votes can be changed. The page refreshes every 10 s while it is open.
4. **Result.** The show with the most votes is marked and gets «احجز» (the chain's own booking link) and «أضف للتقويم». The calendar entry comes as an `.ics` from the API for iPhone, and as a Google Calendar link otherwise.
5. **Expiry.** The poll is deleted the day after its last show (DynamoDB TTL).

**No chat on purpose:** the WhatsApp group is the chat. A chat here would need moderation and accounts.

## Backend

The backend sits on the counter stack's API (`elyoxe-cinema-counter`, `infra/counter/`). The site's CSP already allows that host, so the CloudFront stack is not touched.

- **Lambda:** `elyoxe-cinema-vote` (`lambdas/vote.py`).
- **Table:** `elyoxe-cinema-votes`. Its keys:
  - `id` and `k=poll`: the options and the sender.
  - `id` and `k=v#<pub>`: one voter.
  - `_day#<date>`: the daily count of new polls.
- **Routes:**

| Route | What it does |
|---|---|
| `POST /vote` | Creates a poll from 2–4 show keys `{city, date, cin, fid, time, hall}`. |
| `GET /vote/{id}` | The poll and its votes. |
| `POST /vote/{id}` | Casts or changes one voter's vote. |
| `GET /vote/{id}/ics` | The leading show as a calendar file. |

**Trust:**
- **Shows come from our own data.** The server never takes show details from the browser. It resolves each key against the site's own published `/data/<city>-<date>.json`, so a poll can only hold real shows with our booking links. That means no fake titles and no foreign links.
- **Nobody can edit another person's vote.** A voter proves who they are with a random secret kept on their phone (`vk`). The server stores and shows only `sha256(vk)[:12]`.
- **Caps:**
  - 300 new polls a day;
  - 40 voters a poll;
  - name ≤ 24 characters, note ≤ 60, plain text only.
- **Origin and kill switch:** only https://cinema.elyoxe.com may write. The SSM parameter `/elyoxe/cinema/counter/vote-off`, set to any value, stops new polls and votes.
- **Privacy:** like the rest of the stack, no IP is read or stored.
