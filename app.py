import os
import time
import logging
from multiprocessing import Process, Queue, freeze_support

from flask import Flask, render_template, flash

import bluescal

app = Flask(__name__)
app.secret_key = os.urandom(32)
app.logger.setLevel(logging.INFO)

# Remove the global ipc queue
cached_calendar = None  # Initialize as None, will be set in main

def refresh_calendar(ipc, logger=None):
    while True:
        try:
            calendar = bluescal.refresh(logger)
            ipc.put(calendar)
        except Exception as e:
            if logger:
                logger.error("Error refreshing calendar: %s", e)
        time.sleep(60)

@app.route('/')
def index():
    global cached_calendar
    # Get the queue from the current process
    ipc = app.config.get('IPC_QUEUE')
    if not ipc:
        app.config['IPC_QUEUE'] = Queue()
        ipc = app.config['IPC_QUEUE']
        calendar = cached_calendar
        if not calendar:
            calendar = bluescal.refresh(app.logger)
    else:
        try:
            calendar = ipc.get_nowait() if not ipc.empty() else cached_calendar
            if calendar:
                cached_calendar = calendar
        except:
            calendar = cached_calendar
            if not calendar:
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
    freeze_support()
    # Create the queue inside the main block
    ipc = Queue()
    app.config['IPC_QUEUE'] = ipc  # Store in app config for access in routes
    
    # Initial calendar fetch
    cached_calendar = bluescal.refresh(app.logger)
    
    app.logger.info("Starting refresher")
    refresher = Process(target=refresh_calendar, args=(ipc,), daemon=True)
    refresher.start()
    app.logger.info("Starting server")
    try:
        app.run(debug=False, host='0.0.0.0', port=8080)
    except KeyboardInterrupt:
        app.logger.info("Shutting down gracefully...")
        # First terminate the process
        refresher.terminate()
        refresher.join(timeout=5)  # Wait up to 5 seconds for clean shutdown
        if refresher.is_alive():
            app.logger.warning("Refresher process did not terminate cleanly, forcing...")
            refresher.kill()  # Force kill if still alive
        # Clear the queue before closing
        while not ipc.empty():
            try:
                ipc.get_nowait()
            except:
                pass
        ipc.close()
        ipc.join_thread()  # Wait for the queue's feeder thread to finish
        del app.config['IPC_QUEUE']  # Remove from app config
        exit(0)
    except Exception as e:
        app.logger.error("Server error: %s", e)
        # Same cleanup as above
        refresher.terminate()
        refresher.join(timeout=5)
        if refresher.is_alive():
            refresher.kill()
        while not ipc.empty():
            try:
                ipc.get_nowait()
            except:
                pass
        ipc.close()
        ipc.join_thread()
        del app.config['IPC_QUEUE']  # Remove from app config
        exit(1)
