import os
import logging

from flask import Flask, render_template, flash

import bluescal

app = Flask(__name__)
app.secret_key = os.urandom(32)
app.logger.setLevel(logging.INFO)

@app.route('/')
def index():
    # TODO start using fly.io postgres
    calendar = bluescal.refresh(app.logger)
    # TODO start supporting date ranges so that we don't have to fetch the full calendar every time
    if not calendar:
        flash("No events found; a sync error may have occurred.")
        app.logger.error("No events found; a sync error may have occurred.")
        return render_template('index.html', events=[])
    events = bluescal.process_events(calendar, app.logger)
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

@app.route('/donate')
def donate():
    return render_template('donate.html')

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=8080)
