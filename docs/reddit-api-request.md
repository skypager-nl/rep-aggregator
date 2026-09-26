# Reddit Data API access request

Form: Reddit Help → Data Access Request → "I'm a developer" → "…Reddit App that does not work in the Devvit ecosystem".
Account: u/-skypager-

---

## What benefit/purpose will the bot/app have for Redditors?

This is a personal, read-only tool, and I want to be upfront that it isn't a feature for other Redditors. It helps me, as a member of these communities, follow quality-control discussion that's spread across six subreddits and many years of threads. It posts nothing, votes on nothing and messages nobody, so it has no footprint on the communities or their users. The load on Reddit's API is small and steady, well within the free tier. If it's useful, I'm open to sharing aggregated, anonymised summaries back with the communities, with moderator approval.

## Provide a detailed description of what the Bot/App will be doing on the Reddit platform.

It's a private dashboard, for my own use only, that summarises community quality-control (QC) discussion about replica watches in the six subreddits listed below.

What it does, step by step:
1. Every ~30 minutes it fetches new posts and their comments from the six subreddits using a single OAuth "script" app on my account. Requests are sent one at a time.
2. For a limited time after setup, it slowly backfills recent history, only as far as the standard listings return.
3. It extracts structured opinions from each thread. For example:
   - A QC thread ("GL or RL? [watch model]") → the community's verdict (green light / red light), how many comments voted each way, and which parts of the watch were criticised (e.g. "bezel insert misaligned", "date font off").
   - A review post → per-aspect opinions such as "dial print crisp: positive" or "rotor noise after 6 months: negative".
4. It aggregates these into per-model summaries and trends over time, shown on a private web page on my home server, behind a login.

Read-only: it makes no posts, comments, votes, messages, reports or moderation actions.

Volume: a few requests per minute on average, never close to the 100 QPM free-tier limit. It backs off on any 429 response and follows rate-limit headers.

Data handling:
- Stored only on my private home server. It isn't published, shared, sold or redistributed.
- Deletions are respected: stored posts and comments are periodically re-checked, and anything deleted or removed is purged.
- Usernames are kept only to give more weight to long-standing contributors within the tool. They're never linked to identities outside Reddit, and nothing is inferred about users' personal or sensitive characteristics.
- Post text is sent to Anthropic's Claude API solely to extract the structured opinions described above. No Reddit data is used to train any AI/ML model, by me or by the API provider.

Not used for: commercial purposes, advertising, resale, AI/ML training, or any public-facing product.

I'm happy to adjust the scope if that would help, for example fewer subreddits or a lower polling frequency. Thanks for considering it.

## What is missing from Devvit that prevents building on that platform?

- **Installation:** Devvit apps are installed into a subreddit by its moderators. I'm not a moderator of these communities, and I need read-only access across all six without asking them to install anything.
- **Where it runs:** the tool is an off-platform personal dashboard. It aggregates data across subreddits and over several years, stores it for trend analysis, and shows it outside Reddit. It isn't an in-subreddit experience, which is what Devvit is built for.
- **Processing:** it needs long-running scheduled jobs and local storage/analysis on my own server, plus a call to an external text-processing API. A per-subreddit Devvit app isn't designed for that.

## Provide a link to source code or platform that will access the API.

[see note below]

## What subreddits do you intend to use the bot/app in?

r/RepTime, r/RepTimeQC, r/Rep_Watch_World, r/repbuilds, r/vintagerepwatches, r/retrotime (read-only)

## If applicable, what username will you be operating this Bot/App under?

-skypager-

---

## After approval

1. Go to https://www.reddit.com/prefs/apps, then "create another app…". Choose type **script** and set the redirect URI to `http://localhost:8080`.
2. Put the client ID, client secret and username into the Rep Index app's options in Home Assistant. Don't paste them into chat.
