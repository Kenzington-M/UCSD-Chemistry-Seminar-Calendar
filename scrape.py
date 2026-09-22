#!/usr/bin/env python3
"""Scrape https://chemistry.ucsd.edu/seminars into subscribable .ics feeds.

Outputs (in docs/, served by GitHub Pages):
  all.ics            every seminar
  <type-slug>.ics    one feed per seminar type
  events.json        archive, so past seminars stay on the calendar after
                     they drop off the page
"""
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

URL = "https://chemistry.ucsd.edu/seminars"
OUT = Path("docs")
DB = OUT / "events.json"
TZ = ZoneInfo("America/Los_Angeles")
DURATION = timedelta(hours=1)  # the page lists start times only

DATE_RE = re.compile(
    r"Date:\s*(\d{2}/\d{2}/\d{4}).*?(\d{1,2}:\d{2}\s*[AP]M)\s*Location:\s*(.*)",
    re.I | re.S,
)
DETAIL_RE = re.compile(
    r"Speaker:?\s*(.*?)\s*Title:\s*(.*?)\s*Hosted by:\s*(.*)", re.I | re.S
)


def clean(s):
    return re.sub(r"\s+", " ", s).strip()


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def utc_stamp(dt):
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def parse(html):
    soup = BeautifulSoup(html, "html.parser")
    events = {}
    for row in soup.select("table tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue  # header row or unrelated table
        when = DATE_RE.search(cells[0].get_text(" ", strip=True))
        info = DETAIL_RE.search(cells[2].get_text(" ", strip=True))
        if not when or not info:
            print("Skipping unparsed row:", clean(row.get_text(" ")), file=sys.stderr)
            continue
        date, time, location = when.groups()
        speaker, title, host = map(clean, info.groups())
        start = datetime.strptime(
            f"{date} {clean(time)}", "%m/%d/%Y %I:%M %p"
        ).replace(tzinfo=TZ)
        # UID keyed on date + speaker: a title change (e.g. TBA -> real title)
        # updates the existing event instead of creating a duplicate.
        uid = hashlib.sha1(f"{date}|{speaker}".encode()).hexdigest()[:16]
        uid += "@ucsd-chem-seminars"
        events[uid] = {
            "uid": uid,
            "start": start.isoformat(),
            "location": clean(location),
            "type": clean(cells[1].get_text(" ", strip=True)),
            "speaker": speaker,
            "title": title,
            "host": host,
        }
    return events


def merge(scraped, now):
    old = json.loads(DB.read_text()) if DB.exists() else {}
    merged = {}
    for uid, ev in old.items():
        if uid in scraped:
            continue
        # Past seminars are kept after the page drops them. Future seminars
        # that vanish from the page are treated as cancelled/rescheduled.
        if datetime.fromisoformat(ev["start"]) < now:
            merged[uid] = ev
    for uid, ev in scraped.items():
        prev = old.get(uid)
        unchanged = prev and all(prev.get(k) == v for k, v in ev.items())
        ev["updated"] = prev["updated"] if unchanged else utc_stamp(now)
        merged[uid] = ev
    return merged


def esc(s):
    return (s.replace("\\", "\\\\").replace(";", "\\;")
             .replace(",", "\\,").replace("\n", "\\n"))


def fold(line):
    """RFC 5545: fold lines at 75 octets without splitting UTF-8 characters."""
    b = line.encode()
    parts = []
    while len(b) > (75 if not parts else 74):
        cut = 75 if not parts else 74
        while (b[cut] & 0xC0) == 0x80:
            cut -= 1
        parts.append(b[:cut].decode())
        b = b[cut:]
    parts.append(b.decode())
    return "\r\n ".join(parts)


def write_ics(path, name, events):
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//ucsd-chem-seminars//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{esc(name)}",
        "X-WR-TIMEZONE:America/Los_Angeles",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
    ]
    for ev in sorted(events, key=lambda e: e["start"]):
        start = datetime.fromisoformat(ev["start"])
        known_title = ev["title"].lower() not in ("tba", "tbd", "")
        summary = (f"{ev['speaker']}: {ev['title']}" if known_title
                   else f"{ev['speaker']} ({ev['type']})")
        desc = (f"{ev['type']}\nSpeaker: {ev['speaker']}\nTitle: {ev['title']}\n"
                f"Hosted by: {ev['host']}\n{URL}")
        lines += [
            "BEGIN:VEVENT",
            f"UID:{ev['uid']}",
            f"DTSTAMP:{ev['updated']}",
            f"LAST-MODIFIED:{ev['updated']}",
            f"DTSTART:{utc_stamp(start)}",
            f"DTEND:{utc_stamp(start + DURATION)}",
            f"SUMMARY:{esc(summary)}",
            f"LOCATION:{esc(ev['location'])}",
            f"DESCRIPTION:{esc(desc)}",
            f"CATEGORIES:{esc(ev['type'])}",
            f"URL:{URL}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    path.write_text("\r\n".join(fold(l) for l in lines) + "\r\n", newline="")


def write_index(feeds):
    items = "\n".join(f'<li><a href="{f}">{n}</a></li>' for f, (n, _) in feeds.items())
    (OUT / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><title>UCSD Chemistry Seminar Feeds</title>"
        "<h1>UCSD Chemistry Seminar Feeds</h1>"
        "<p>Copy a link and add it in Google Calendar via Other calendars &rarr; + &rarr; From URL.</p>"
        f"<ul>\n{items}\n</ul>\n"
    )


def main():
    now = datetime.now(TZ)
    resp = requests.get(URL, timeout=30,
                        headers={"User-Agent": "seminar-ics-feed (calendar sync)"})
    resp.raise_for_status()
    scraped = parse(resp.text)
    if not scraped:
        # Fail loudly (GitHub emails you) rather than publish an empty feed.
        sys.exit("No seminars parsed; page layout may have changed. Feed left unchanged.")

    events = merge(scraped, now)
    OUT.mkdir(exist_ok=True)
    (OUT / ".nojekyll").touch()
    DB.write_text(json.dumps(events, indent=2, sort_keys=True) + "\n")

    evs = list(events.values())
    feeds = {"all.ics": ("UCSD Chemistry Seminars", evs)}
    for t in sorted({e["type"] for e in evs}):
        feeds[f"{slug(t)}.ics"] = (f"UCSD Chem: {t}", [e for e in evs if e["type"] == t])
    for fname, (name, subset) in feeds.items():
        write_ics(OUT / fname, name, subset)
    write_index(feeds)
    print(f"{len(scraped)} seminars on page, {len(evs)} in archive, {len(feeds)} feeds written")


if __name__ == "__main__":
    main()
