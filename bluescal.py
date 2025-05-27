import os
import re
import time
from hashlib import sha256
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from html.parser import HTMLParser

import requests
import icalendar as ical
from bs4 import BeautifulSoup

CAL_URL = "https://calendar.google.com/calendar/ical/seattlebluesdancecollective%40gmail.com/public/basic.ics"
CAL_FILE = "bluescal.ics"

MAPS_API_KEY = os.getenv("MAPS_API_KEY")

EVENTS_DB = {}

def refresh(logger=None):
    global MAPS_API_KEY
    if not MAPS_API_KEY:
        MAPS_API_KEY = os.getenv("MAPS_API_KEY")
    try:
        if os.path.exists(CAL_FILE):
            if logger:
                logger.info("Calendar file exists")
            if os.path.getmtime(CAL_FILE) > time.time() - 10:
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
        if response.status_code == 200 and len(response.text) > 0 and len(response.text) < 1_048_576: # 1MiB
            if logger:
                logger.info("Successfully fetched calendar (%d bytes)", len(response.text))
            with open(CAL_FILE, "w") as f:
                f.write(response.text)
            calendar = ical.Calendar.from_ical(response.text)
            return calendar
    except Exception as e:
        logger.error("Error fetching calendar: %s", e)
    if logger:
        logger.error("Failed to fetch calendar from %s", CAL_URL)
    return None

def process_events(calendar: ical.Calendar, logger=None):
    global EVENTS_DB
    events = []
    for i, cal_event in enumerate(sorted(filter(lambda x: x.get("DTSTART"), calendar.events), key=lambda x: x["DTSTART"].dt)):
        event = {}
        event["id"] = str(i)
        event["uid"] = sha256(str(cal_event.get("UID", str(cal_event))).encode("utf-8")).hexdigest()
        event["title"] = cal_event.get("SUMMARY", "")
        # already in cache
        if event["uid"] in EVENTS_DB and EVENTS_DB[event["uid"]]["title"] == event["title"] and EVENTS_DB[event["uid"]]["neighborhood"] != "":
            events.append(EVENTS_DB[event["uid"]])
            continue
        
        # Parse the iCalendar date strings into datetime objects
        dtstart = cal_event.get("DTSTART")
        dtend = cal_event.get("DTEND")
        
        def to_local_time(dt):
            if dt is None:
                return None
            if not dt.dt.tzinfo:
                # Case 1: No timezone info, assume UTC
                return dt.dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo("America/Los_Angeles"))
            elif dt.dt.tzinfo.key == "America/Los_Angeles":
                # Case 3: Already in Pacific time
                return dt.dt
            else:
                # Case 2: Has timezone info, convert to Pacific
                return dt.dt.astimezone(ZoneInfo("America/Los_Angeles"))

        local_start = to_local_time(dtstart)
        local_end = to_local_time(dtend) if dtend else local_start
        if local_start is None:
            continue

        event["date"] = local_start.date().strftime("%Y-%m-%d")
        if local_start != local_end:
            event["time"] = local_start.strftime("%-I:%M %p") + " - " + local_end.strftime("%-I:%M %p")
        else:
            event["time"] = local_start.strftime("%-I:%M %p")

        event["location"] = cal_event.get("LOCATION", "")
        event["neighborhood"] = get_neighborhood(event["location"], logger)
        
        features = set()
        if "live music" in cal_event.get("DESCRIPTION", "").lower():
            features.add("Live Music")
        if "lesson" in cal_event.get("DESCRIPTION", "").lower():
            features.add("Lesson")
        # TODO get features from an LLM and cache in database
        event["features"] = list(features)
        
        description = cal_event.get("DESCRIPTION", "")
        if description:
            try:
                # Convert plain text URLs to links
                url_pattern = re.compile(r'(?<!href=")(?<!src=")(https?://\S+)(?!")')
                description = url_pattern.sub(r'<a href="\1">\1</a>', description)
                soup = BeautifulSoup(description, 'html.parser')
                for link in soup.find_all('a'):
                    link['target'] = '_blank'
                    link['rel'] = 'noopener'
                    if len(link.text) > 40 and link.text == link.get("href", ""):
                        link.string = link.text[:40] + '[...]'
                event["description"] = str(soup)
            except HTMLParser.HTMLParseError as e:
                app.logger.error(f"HTML parsing error: {e}")
                # If parsing fails, use the original description
                event["description"] = description
        EVENTS_DB[event["uid"]] = event
        events.append(event)
    return events

def get_neighborhood(location: str, logger=None):
    if not MAPS_API_KEY or not location:
        return ""
    response = requests.get(f"https://maps.googleapis.com/maps/api/geocode/json?address={requests.utils.quote(location)}&key={MAPS_API_KEY}")
    if response.status_code == 200:
        data = response.json()
        if data["status"] == "OK" and data["results"]:
            components = data["results"][0]["address_components"]
            for comp in components:
                if "neighborhood" in comp["types"]:
                    return str(comp["long_name"])
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
