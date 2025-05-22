import os
import re
import logging

from flask import Flask, render_template, flash
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from html.parser import HTMLParser

import bluescal

app = Flask(__name__)
app.secret_key = os.urandom(32)
app.logger.setLevel(logging.INFO)

@app.route('/')
def index():
    calendar = bluescal.refresh(app.logger) # TODO start using fly.io postgres
    if not calendar:
        flash("No events found; a sync error may have occurred.")
        app.logger.error("No events found; a sync error may have occurred.")
        return render_template('index.html', events=[])
    events = process_events(calendar)
    if not events:
        flash("No events found; a sync error may have occurred.")
        app.logger.error("No events found; a sync error may have occurred.")
    return render_template('index.html', events=events)

def process_events(calendar):
    events = []
    for i, cal_event in enumerate(sorted(filter(lambda x: x.get("DTSTART"), calendar.events), key=lambda x: x["DTSTART"].dt)):
        event = {}
        event["id"] = str(i)
        event["uid"] = str(cal_event.get("UID", str(hash(str(cal_event)))))
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

        # TODO: get neighborhood from location: Maps? LLM? -> cache; https://stackoverflow.com/questions/13488759/is-it-possible-to-get-the-neighborhood-of-an-address-using-google-maps-api-or-bi
        event["location"] = cal_event.get("LOCATION", "")
        features = set()
        if "live music" in cal_event.get("DESCRIPTION", "").lower():
            features.add("Live Music")
        if "lesson" in cal_event.get("DESCRIPTION", "").lower():
            features.add("Lesson")
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

@app.route('/donate')
def donate():
    return render_template('donate.html')

if __name__ == '__main__':
    app.run(debug=True)
