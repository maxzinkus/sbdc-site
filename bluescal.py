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

def refresh(logger=None):
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

def process_events(calendar: ical.Calendar):
    events = []
    for i, cal_event in enumerate(sorted(filter(lambda x: x.get("DTSTART"), calendar.events), key=lambda x: x["DTSTART"].dt)):
        event = {}
        event["id"] = str(i)
        event["uid"] = sha256(str(cal_event.get("UID", str(cal_event))).encode("utf-8")).hexdigest()
        event["title"] = cal_event.get("SUMMARY", "")
        
        # Parse the iCalendar date strings into datetime objects
        dtstart = cal_event.get("DTSTART")
        dtend = cal_event.get("DTEND")
        utc_start = dtstart.dt.replace(tzinfo=timezone.utc)
        local_start = utc_start.astimezone(ZoneInfo("America/Los_Angeles"))

        # TODO: there's some UTC/PT stuff going on here
        if dtend:
            utc_end = dtend.dt.replace(tzinfo=timezone.utc)
            local_end = utc_end.astimezone(ZoneInfo("America/Los_Angeles"))
        else:
            local_end = local_start

        event["date"] = local_start.date().strftime("%Y-%m-%d")
        if local_start != local_end:
            event["time"] = local_start.strftime("%-I:%M %p") + " - " + local_end.strftime("%-I:%M %p")
        else:
            event["time"] = local_start.strftime("%-I:%M %p")

        # TODO: get neighborhood from location: Maps? https://stackoverflow.com/questions/13488759/is-it-possible-to-get-the-neighborhood-of-an-address-using-google-maps-api-or-bi
        # TODO use the database as well
        event["location"] = cal_event.get("LOCATION", "")
        # TODO normalize location with maps
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
        events.append(event)
    return events

if __name__ == "__main__":
    calendar = refresh()
    print("\n".join([str(event["SUMMARY"]) for event in calendar.events]))
