from datetime import datetime, date, timedelta, timezone
from functools import lru_cache
from hashlib import sha256
from html.parser import HTMLParser
import os
import re
import time
from typing import List
from zoneinfo import ZoneInfo

import icalendar as ical
import requests
from bs4 import BeautifulSoup

CAL_URL = "https://calendar.google.com/calendar/ical/seattlebluesdancecollective%40gmail.com/public/basic.ics"
CAL_FILE = "bluescal.ics"

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
            if os.path.getmtime(CAL_FILE) > time.time() - 60:
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

def process_events(calendar: ical.Calendar, logger=None):
    global EVENTS_DB
    events = []
    if calendar is None:
        return events
    for cal_event in sorted(filter(lambda x: x.get("DTSTART"), calendar.events), key=lambda x: fix_datetime(x["DTSTART"])):
        event = {}
        uid_val = cal_event.get("UID", str(cal_event))
        event["uid"] = sha256(str(uid_val).encode("utf-8")).hexdigest()
        event["title"] = cal_event.get("SUMMARY", "")
        # already in cache
        if EVENTS_DB.get(event["uid"], []) and EVENTS_DB[event["uid"]][0]["title"] == event["title"]:
            if EVENTS_DB[event["uid"]][0]["location"] and EVENTS_DB[event["uid"]][0]["neighborhood"] == "":
                EVENTS_DB[event["uid"]][0]["neighborhood"] = get_neighborhood(EVENTS_DB[event["uid"]][0]["location"], logger)
            events.extend(EVENTS_DB[event["uid"]])
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
        if local_start != local_end:
            event["time"] = local_start.strftime("%-I:%M %p") + " - " + local_end.strftime("%-I:%M %p")
        else:
            event["time"] = local_start.strftime("%-I:%M %p")

        event["location"] = cal_event.get("LOCATION", "")
        if not event["location"]:
            event["neighborhood"] = ""
        else:
            event["neighborhood"] = get_neighborhood(event["location"], logger)

        features = set()
        if ("live music" in str(cal_event.get("DESCRIPTION", "")).lower() or "live music" in str(cal_event.get("SUMMARY", "")).lower() or
            " band" in str(cal_event.get("DESCRIPTION", "")).lower() or " band" in str(cal_event.get("SUMMARY", "")).lower()):
            features.add("Live Music")
        if "lesson" in str(cal_event.get("DESCRIPTION", "")).lower() or "lesson" in str(cal_event.get("SUMMARY", "")).lower():
            features.add("Lesson")
        # TODO get features from an LLM and cache in database
        event["categories"] = list(features)

        description = str(cal_event.get("DESCRIPTION", ""))
        if description:
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
                event["description"] = description
        try:
            cal_event.get("DTSTART").dt.time()
        except AttributeError:
            event["time"] = "All Day"
        sequence = handle_recurring_event(event, event["dtstart"], cal_event.get("RRULE"), logger)
        EVENTS_DB[event["uid"]] = sequence
        events.extend(sequence)
    return events

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

def handle_recurring_event(event: dict, start_date: datetime, rrule: ical.prop.vRecur, logger=None):
    # takes an event with rrules and returns a list of events
    events = [event]
    if not rrule:
        return events
    until = rrule.get("UNTIL", [start_date + timedelta(days=180)])
    if not until or not until[0]:
        return events
    until = fix_datetime(until[0])
    if rrule.get("FREQ") == ['MONTHLY'] and rrule.get("BYDAY"):
        if logger:
            logger.debug("Handling monthly recurring event %s", event["title"])
        byday = rrule["BYDAY"][0]
        next_date = find_next_monthly(start_date, byday)
        i = 1
        while next_date < until:
            next_event = event.copy()
            next_event["date"] = next_date.strftime("%Y-%m-%d")
            next_event["uid"] = sha256(str(event["uid"]+f"-{i}").encode("utf-8")).hexdigest()
            events.append(next_event)
            next_date = find_next_monthly(next_date, byday)
            i += 1
    elif rrule.get("FREQ") == ['WEEKLY'] and rrule.get("BYDAY"):
        if logger:
            logger.debug("Handling weekly recurring event %s", event["title"])
        byday = rrule["BYDAY"][0]
        next_date = find_next_weekly(start_date, byday)
        i = 1
        while next_date < until:
            next_event = event.copy()
            next_event["date"] = next_date.strftime("%Y-%m-%d")
            next_event["uid"] = sha256(str(event["uid"]+f"-{i}").encode("utf-8")).hexdigest()
            events.append(next_event)
            next_date = find_next_weekly(next_date, byday)
            i += 1
    return events

def find_next_monthly(start_date: datetime, byday: str):
    # Parse the byday string (e.g. "3TH" -> 3rd Thursday)
    week = int(byday[:-2])
    dow = byday[-2:]
    if dow == "MO":
        dow = 0
    elif dow == "TU":
        dow = 1
    elif dow == "WE":
        dow = 2
    elif dow == "TH":
        dow = 3
    elif dow == "FR":
        dow = 4
    elif dow == "SA":
        dow = 5
    elif dow == "SU":
        dow = 6
    # Get the first day of next month
    if start_date.month == 12:
        next_month = start_date.replace(year=start_date.year + 1, month=1, day=1)
    else:
        next_month = start_date.replace(month=start_date.month + 1, day=1)
    # Find the first occurrence of the target day of week
    first_day = next_month.weekday()
    days_to_add = (dow - first_day) % 7
    first_occurrence = next_month.replace(day=1 + days_to_add)
    # Add weeks to get to the nth occurrence
    target_date = first_occurrence.replace(day=first_occurrence.day + (week - 1) * 7)
    return target_date

def find_next_weekly(start_date: datetime, byday: str):
    # Parse the byday string (e.g. "MO" -> Monday)
    dow = byday
    if dow == "MO":
        dow = 0
    elif dow == "TU":
        dow = 1
    elif dow == "WE":
        dow = 2
    elif dow == "TH":
        dow = 3
    elif dow == "FR":
        dow = 4
    elif dow == "SA":
        dow = 5
    elif dow == "SU":
        dow = 6
    cur = start_date + timedelta(days=1)
    while cur.weekday() != dow:
        cur += timedelta(days=1)
    return cur

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
