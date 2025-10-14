from datetime import datetime, date, timedelta, timezone
from dateutil.relativedelta import relativedelta
from functools import lru_cache
from hashlib import sha256
from html import escape
from html.parser import HTMLParser
import os
import re
import time
from typing import List
from zoneinfo import ZoneInfo

import icalendar as ical
import recurring_ical_events
import requests
from bs4 import BeautifulSoup

CAL_URL = "https://calendar.google.com/calendar/ical/seattlebluesdancecollective%40gmail.com/public/basic.ics"
CAL_FILE = "bluescal.ics"
CAL_CACHE_TTL_SECONDS = 10 # don't refresh if refreshed in the last X seconds

MAPS_API_KEY = os.getenv("MAPS_API_KEY")

EVENTS_DB = {}
NEIGHBORHOODS_DB = {}

def refresh(logger=None):
    global MAPS_API_KEY
    if not MAPS_API_KEY:
        MAPS_API_KEY = os.getenv("MAPS_API_KEY")
    try:
        if os.path.exists(CAL_FILE):
            if logger:
                logger.info("Calendar file exists")
            if os.path.getmtime(CAL_FILE) > time.time() - CAL_CACHE_TTL_SECONDS:
                if logger:
                    logger.info("Using cached calendar file")
                with open(CAL_FILE, "r") as f:
                    return ical.Calendar.from_ical(f.read())
            else:
                if logger:
                    logger.info("Calendar file is outdated; fetching new copy")
        if logger:
            logger.info("Fetching calendar from %s", CAL_URL)
        response = requests.get(CAL_URL)
        if response.status_code == 200 and len(response.text) > 0 and len(response.text) < 1_048_576 * 4: # 4MiB
            if logger:
                logger.info("Successfully fetched calendar (%d bytes)", len(response.text))
            with open(CAL_FILE, "w") as f:
                f.write(response.text)
            calendar = ical.Calendar.from_ical(response.text)
            return calendar
    except Exception as e:
        if logger:
            logger.error("Error fetching calendar: %s", e)
    if logger:
        logger.error("Failed to fetch calendar from %s", CAL_URL)
    return None

def process_events(calendar: ical.Calendar, month: int, year: int, logger=None):
    global EVENTS_DB
    events = []
    if calendar is None:
        return events
    month_start = fix_datetime(datetime(year, month, 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    month_end = fix_datetime(month_start + relativedelta(months=2)).replace(hour=0, minute=0, second=0, microsecond=0)
    for cal_event in sorted(filter(lambda x: x.get("DTSTART"), recurring_ical_events.of(calendar).between(month_start, month_end)),
                                   key=lambda x: fix_datetime(x["DTSTART"])):
        event = {}
        uid_val = cal_event.get("UID", str(cal_event)) + str(cal_event.get("RECURRENCE-ID", ""))
        event["uid"] = sha256(str(uid_val).encode("utf-8")).hexdigest()
        event["title"] = cal_event.get("SUMMARY", "")
        # already in cache
        if EVENTS_DB.get(event["uid"]) and EVENTS_DB[event["uid"]]["title"] == event["title"]:
            if EVENTS_DB[event["uid"]]["location"] and EVENTS_DB[event["uid"]]["neighborhood"] == "":
                EVENTS_DB[event["uid"]]["neighborhood"] = get_neighborhood(EVENTS_DB[event["uid"]]["location"], logger)
            events.append(EVENTS_DB[event["uid"]])
            continue

        # Parse the iCalendar date strings into datetime objects
        dtstart = fix_datetime(cal_event.get("DTSTART"))
        dtend = fix_datetime(cal_event.get("DTEND"))

        local_start = fix_datetime(dtstart)
        local_end = fix_datetime(dtend) if dtend else local_start
        if local_start is None:
            continue

        event["dtstart"] = local_start
        event["date"] = local_start.strftime("%Y-%m-%d")
        try:
            cal_event.get("DTSTART").dt.time()
            start_time = local_start.strftime("%-I:%M %p")
            end_time = local_end.strftime("%-I:%M %p")
            if event["date"] != local_end.strftime("%Y-%m-%d") or start_time != end_time:
                event["time"] = f"{start_time} - {end_time}"
            else:
                event["time"] = start_time
        except AttributeError:
            event["time"] = "All Day"
        event["location"] = cal_event.get("LOCATION", "")
        if not event["location"]:
            event["neighborhood"] = ""
        else:
            event["neighborhood"] = get_neighborhood(event["location"], logger)

        features = set()
        if ("live music" in str(cal_event.get("DESCRIPTION", "")).lower() or "live music" in str(cal_event.get("SUMMARY", "")).lower() or
            " band" in str(cal_event.get("DESCRIPTION", "")).lower() or " band" in str(cal_event.get("SUMMARY", "")).lower()):
            features.add("Live Music")
        lesson_strings = ["lesson", "dance class", "practica", "workshop", "instructor"]
        if any(s in str(cal_event.get("DESCRIPTION", "")).lower() or s in str(cal_event.get("SUMMARY", "")).lower() for s in lesson_strings):
            features.add("Lesson")
        # TODO get features from an LLM and cache in database
        event["categories"] = list(features)

        description = str(cal_event.get("DESCRIPTION", ""))
        try:
            # Convert plain text URLs to links
            url_pattern = re.compile(r'(?<![="\'])(https?://[^\s<>"\']+)(?![="\'])')
            description = url_pattern.sub(r'<a href="\1">\1</a>', description)
            soup = BeautifulSoup(description, 'html.parser')
            for link in soup.find_all('a'):
                link['target'] = '_blank'
                link['rel'] = 'noopener'
                if len(link.text) > 40 and link.text == link.get("href", "") and not '@' in link.text:
                    link.string = link.text[:40] + '[...]'
            event["description"] = str(soup)
        except HTMLParser.HTMLParseError as e:
            if logger:
                logger.error("HTML parsing error: %s", e)
            # If parsing fails, use the original description
            event["description"] = escape(description)
        EVENTS_DB[event["uid"]] = event
        events.append(event)
    return list(events)

def fix_datetime(vddd):
    if type(vddd) is ical.prop.vDDDTypes:
        dt = vddd.dt
    else:
        dt = vddd # either a date or a datetime
    if type(dt) is date:
        dt = datetime.combine(dt, datetime.min.time())
        dt = dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo("America/Los_Angeles"))
    if not dt.tzinfo:
        return dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo("America/Los_Angeles"))
    else:
        return dt.astimezone(ZoneInfo("America/Los_Angeles"))

def get_neighborhood(location: str, logger=None):
    global NEIGHBORHOODS_DB
    if NEIGHBORHOODS_DB.get(location):
        if logger:
            logger.info("Using cached neighborhood for %s", location)
        return NEIGHBORHOODS_DB[location]
    if not MAPS_API_KEY or not location:
        return ""
    response = requests.get(f"https://maps.googleapis.com/maps/api/geocode/json?address={requests.utils.quote(location)}&key={MAPS_API_KEY}")
    if response.status_code == 200:
        data = response.json()
        if data["status"] == "OK" and data["results"]:
            try:
                components = data["results"][0]["address_components"]
                for comp in components:
                    if "neighborhood" in comp["types"] and comp.get("long_name"):
                        NEIGHBORHOODS_DB[location] = str(comp["long_name"])
                        return NEIGHBORHOODS_DB[location]
            except (KeyError, TypeError) as e:
                if logger:
                    logger.error("Failed to get neighborhood for %s: %s (%s)", location, data["status"], e)
                return ""
        else:
            if logger:
                logger.error("Failed to get neighborhood for %s: %s", location, data["status"])
    else:
        if logger:
            logger.error("Failed to get neighborhood for %s: %s", location, response.text)
    return ""

if __name__ == "__main__":
    calendar = refresh()
    print("\n\n".join([str(event) for event in calendar.events]))
