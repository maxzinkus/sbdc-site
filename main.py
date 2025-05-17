import os
import logging

from flask import Flask, render_template, flash
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import bluescal

app = Flask(__name__)
app.secret_key = os.urandom(32)
app.logger.setLevel(logging.INFO)

@app.route('/')
def index():
    calendar = bluescal.refresh(app.logger)
    if not calendar:
        flash("No events found; a sync error may have occurred.")
        app.logger.error("No events found; a sync error may have occurred.")
        return render_template('index.html', events=[])
    events = []
    for i, cal_event in enumerate(sorted(filter(lambda x: x.get("DTSTART"), calendar.events), key=lambda x: x["DTSTART"].dt)):
        event = {}
        event["id"] = str(i)
        event["uid"] = str(cal_event.get("UID", str(hash(str(cal_event)))))
        event["title"] = cal_event.get("SUMMARY", "")
        
        # Parse the iCalendar date strings into datetime objects
        dtstart = cal_event.get("DTSTART")
        dtend = cal_event.get("DTEND")

        # TODO: get neighborhood from location: Maps? LLM? -> cache; https://stackoverflow.com/questions/13488759/is-it-possible-to-get-the-neighborhood-of-an-address-using-google-maps-api-or-bi

        utc_start = dtstart.dt.replace(tzinfo=timezone.utc)
        local_start = utc_start.astimezone(ZoneInfo("America/Los_Angeles"))

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
        event["location"] = cal_event.get("LOCATION", "")
        features = set()
        if "live music" in cal_event.get("DESCRIPTION", "").lower():
            features.add("Live Music")
        if "lesson" in cal_event.get("DESCRIPTION", "").lower():
            features.add("Lesson")
        event["features"] = list(features)
        event["description"] = cal_event.get("DESCRIPTION", "")
        events.append(event)
    if not events:
        flash("No events found; a sync error may have occurred.")
        app.logger.error("No events found; a sync error may have occurred.")
    return render_template('index.html', events=events)

@app.route('/recurring-events')
def recurring_events():
    return render_template('recurring_events.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/instructors')
def instructors():
    return render_template('instructors.html')

@app.route('/gallery')
def gallery():
    return render_template('gallery.html')

@app.route('/history')
def history():
    return render_template('history.html')

@app.route('/music')
def music():
    return render_template('music.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/donate')
def donate():
    return render_template('donate.html')

if __name__ == '__main__':
    app.run(debug=True)
