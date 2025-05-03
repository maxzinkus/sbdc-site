import icalendar as ical
import requests
import os
import time

CAL_URL = "https://calendar.google.com/calendar/ical/seattlebluesdancecollective%40gmail.com/public/basic.ics"
CAL_FILE = "bluescal.ics"

def refresh():
    if os.path.exists(CAL_FILE):
        if os.path.getmtime(CAL_FILE) > time.time() - 10:
            with open(CAL_FILE, "r") as f:
                return ical.Calendar.from_ical(f.read())
    response = requests.get(CAL_URL)
    if response.status_code == 200 and len(response.text) > 0 and len(response.text) < 1_048_576: # 1MiB
        with open(CAL_FILE, "w") as f:
            f.write(response.text)
        calendar = ical.Calendar.from_ical(response.text)
        return calendar
    return None

if __name__ == "__main__":
    calendar = refresh()
    print("\n".join([str(event["SUMMARY"]) for event in calendar.events]))
