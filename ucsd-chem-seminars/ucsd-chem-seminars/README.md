# UCSD Chemistry Seminar Calendar Feed

Scrapes https://chemistry.ucsd.edu/seminars once a day and publishes
subscribable `.ics` feeds via GitHub Pages.

## Setup
1. Create a **public** GitHub repo and upload these files, keeping the
   `.github/workflows/` folder structure.
2. **Actions** tab → enable workflows if prompted → *Update seminar feed* →
   **Run workflow**. This creates the `docs/` folder.
3. **Settings → Pages** → Source: *Deploy from a branch* → Branch: `main`,
   folder: `/docs` → Save.
4. After a minute or two, open `https://<username>.github.io/<repo>/`
   for the list of feed links.

## Subscribe (Google Calendar, desktop)
Other calendars → **+** → **From URL** → paste e.g.
`https://<username>.github.io/<repo>/all.ics`

Per-type feeds (e.g. `inorganic-chemistry.ics`) are listed on the index page.

## Notes
- Event length is set to 1 hour (the page gives start times only);
  change `DURATION` in `scrape.py` if needed.
- Past seminars stay in the feed after the page removes them.
  Future seminars that disappear from the page are dropped (cancelled or rescheduled).
- If the page layout changes and nothing parses, the run fails without
  overwriting the feed, and GitHub emails you.
- GitHub pauses scheduled workflows after 60 days with no repo activity
  and emails a warning; one click re-enables it.
