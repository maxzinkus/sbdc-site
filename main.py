import os
import logging

from flask import Flask, render_template, flash
from datetime import datetime

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
    for i, cal_event in enumerate(calendar.events):
        event = {}
        event["id"] = str(i)
        event["title"] = cal_event.get("SUMMARY", "")
        
        # Parse the iCalendar date strings into datetime objects
        dtstart = cal_event.get("DTSTART")
        dtend = cal_event.get("DTEND")
        if not dtstart or not dtend:
            continue

        # TODO: get neighborhood from location: Maps? LLM? -> cache; https://stackoverflow.com/questions/13488759/is-it-possible-to-get-the-neighborhood-of-an-address-using-google-maps-api-or-bi
        # TODO: get features for categories (Live Music, No Cover, Beginner Lesson): LLM -> cache
        # TODO: convert from UTC and don't use 24-hour time: easy

        event["date"] = dtstart.dt.date().strftime("%Y-%m-%d")
        event["time"] = dtstart.dt.strftime("%H:%M") + " - " + dtend.dt.strftime("%H:%M")
        event["location"] = cal_event.get("LOCATION", "")
        event["features"] = cal_event.get("CATEGORIES", [])
        event["description"] = cal_event.get("DESCRIPTION", "")
        events.append(event)
    if not events:
        flash("No events found; a sync error may have occurred.")
        app.logger.error("No events found; a sync error may have occurred.")
    return render_template('index.html', events=events)

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

@app.route('/login')
def login():
    return render_template('login.html')


if __name__ == '__main__':
    app.run(debug=True)
