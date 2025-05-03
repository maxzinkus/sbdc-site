import icalendar as ical
import requests
import os
import time

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

if __name__ == "__main__":
    calendar = refresh()
    print("\n".join([str(event["SUMMARY"]) for event in calendar.events]))
