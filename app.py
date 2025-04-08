# app.py
import os
import logging
from flask import Flask, render_template, request, jsonify, send_from_directory, url_for
from redis import Redis
from rq import Queue
from rq.job import Job
from dotenv import load_dotenv

# Load environment variables from .env file for local development
load_dotenv()

# Import the task function
from tasks import run_gallery_dl, DOWNLOAD_DIR

# Configure logging (matches tasks.py)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

# --- Configuration ---
# Get Redis URL from environment variable, default to localhost
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
# Ensure DOWNLOAD_DIR exists (tasks.py also checks, but good practice here too)
if not os.path.exists(DOWNLOAD_DIR):
    try:
        os.makedirs(DOWNLOAD_DIR)
        logging.info(f"Created download directory: {DOWNLOAD_DIR}")
    except OSError as e:
        # Log error but don't crash the app start; task will handle failure
        logging.error(f"Could not create download directory {DOWNLOAD_DIR} on startup: {e}")


# --- RQ Setup ---
try:
    redis_conn = Redis.from_url(REDIS_URL)
    # Test connection
    redis_conn.ping()
    # Create RQ Queue
    q = Queue(connection=redis_conn)
    logging.info(f"Successfully connected to Redis at {REDIS_URL} and initialized RQ.")
except Exception as e:
    logging.error(f"Could not connect to Redis at {REDIS_URL}: {e}")
    # Depending on requirements, you might exit here or allow limited functionality
    q = None # Indicate RQ is unavailable


@app.route('/')
def index():
    """Render the main page."""
    return render_template('index.html')

@app.route('/start-download', methods=['POST'])
def start_download():
    """Queue the download task."""
    if not q:
        return jsonify({"status": "error", "message": "Backend queue service is unavailable."}), 503

    url = request.form.get('url')
    # --- !! SECURITY !! ---
    # Basic validation is in run_gallery_dl, but consider more here if needed.
    # Sanitize any *other* options passed from the form before sending to the task.
    # For simplicity, this example doesn't pass extra options, add carefully if needed.

    if not url:
        return jsonify({"status": "error", "message": "URL is required"}), 400

    try:
        # Enqueue the job. The function `run_gallery_dl` will be executed by an RQ worker.
        # We pass the URL. Add other sanitized arguments as needed.
        job = q.enqueue(run_gallery_dl, url, job_timeout=1850) # timeout slightly longer than subprocess
        logging.info(f"Enqueued job {job.id} for URL: {url}")
        return jsonify({
            "status": "queued",
            "job_id": job.id,
            "message": "Download task queued."
        })
    except Exception as e:
        logging.exception(f"Failed to enqueue job for URL {url}: {e}")
        return jsonify({"status": "error", "message": "Failed to queue download task."}), 500


@app.route('/status/<job_id>')
def job_status(job_id):
    """Get the status and result of an RQ job."""
    if not q:
        return jsonify({"status": "error", "message": "Backend queue service is unavailable."}), 503

    try:
        job = Job.fetch(job_id, connection=redis_conn)
    except Exception as e:
        logging.exception(f"Failed to fetch job {job_id}: {e}")
        return jsonify({"status": "error", "message": "Failed to fetch job status."}), 500

    if job is None:
        return jsonify({"status": "error", "message": "Job ID not found."}), 404

    job_status = job.get_status()
    response_data = {
        "job_id": job.id,
        "status": job_status,
    }

    if job.is_finished:
        # Job finished successfully
        result = job.result # The dict returned by run_gallery_dl
        response_data.update(result) # Add status, output, error_output from task result
        response_data["message"] = result.get("message", "Task finished.") # Use message from task
    elif job.is_queued:
        response_data["message"] = "Task is waiting in the queue."
    elif job.is_started:
        response_data["message"] = "Task is currently running."
    elif job.is_failed:
        response_data["message"] = "Task failed."
        # Optionally include failure reason if available (can be complex)
        # response_data["error_info"] = job.exc_info
        # For simplicity, we rely on the result dictionary if the task function
        # catches the error and returns it, otherwise status is 'failed'.
        if job.result: # If task returned error dict
            response_data.update(job.result)
    else: # Other states like 'deferred', 'stopped'
        response_data["message"] = f"Task is in state: {job_status}"

    return jsonify(response_data)


# --- File Serving (Optional & Basic Security) ---
# Disable if not needed or implement proper authentication/authorization!
ENABLE_FILE_SERVER = os.getenv('ENABLE_FILE_SERVER', 'false').lower() == 'true'

if ENABLE_FILE_SERVER:
    @app.route('/files/')
    @app.route('/files/<path:req_path>')
    def list_files(req_path='.'):
        """Serve files from the download directory. BASIC SECURITY ONLY."""
        target_path = os.path.join(DOWNLOAD_DIR, req_path)
        safe_base_path = os.path.abspath(DOWNLOAD_DIR)
        safe_target_path = os.path.abspath(target_path)

        # Prevent path traversal attacks
        if not safe_target_path.startswith(safe_base_path):
            logging.warning(f"Denied access attempt outside DOWNLOAD_DIR: {req_path}")
            return "Access denied", 403
        # Prevent listing hidden files/directories
        if os.path.basename(safe_target_path).startswith('.'):
            return "Access denied", 403

        if not os.path.exists(safe_target_path):
            return "Not Found", 404

        if os.path.isdir(safe_target_path):
            # Basic directory listing
            try:
                files = sorted(os.listdir(safe_target_path))
                items = []
                # Add parent directory link if not at the root
                if safe_target_path != safe_base_path:
                    parent_rel_path = os.path.relpath(os.path.dirname(safe_target_path), safe_base_path)
                    # Handle root case where parent is '.'
                    parent_url_path = parent_rel_path if parent_rel_path != '.' else ''
                    items.append({'name': '.. (Parent)', 'url': url_for('list_files', req_path=parent_url_path), 'is_dir': True})

                for f in files:
                    if f.startswith('.'): # Skip hidden files
                        continue
                    item_rel_path = os.path.join(req_path, f)
                    item_abs_path = os.path.join(safe_target_path, f)
                    items.append({
                        'name': f,
                        'url': url_for('list_files', req_path=item_rel_path),
                        'is_dir': os.path.isdir(item_abs_path)
                    })
                return render_template('file_browser.html', items=items, current_path=req_path)
            except OSError as e:
                logging.error(f"Error listing directory {safe_target_path}: {e}")
                return "Error listing directory", 500
        elif os.path.isfile(safe_target_path):
            # Serve the file
            try:
                return send_from_directory(os.path.dirname(safe_target_path), os.path.basename(safe_target_path))
            except Exception as e:
                logging.exception(f"Error serving file {safe_target_path}: {e}")
                return "Error serving file", 500
        else:
            return "Not Found", 404 # Should not happen if exists check passed


# --- Need template for file browser if enabled ---
if ENABLE_FILE_SERVER:
    # Create a simple file_browser.html template in the templates directory
    # Example content for templates/file_browser.html:
    """
<!DOCTYPE html>
<html><head><title>Files</title></head><body>
<h1>Files in /{{ current_path }}</h1>
<ul>
{% for item in items %}
<li><a href="{{ item.url }}">{{ item.name }}</a>{% if item.is_dir %}/{% endif %}</li>
{% endfor %}
</ul>
<hr><a href="/">Back to Downloader</a>
</body></html>
    """
    pass # Just to avoid syntax error, template should be created as a file

# Note: No app.run() here when using Gunicorn/Docker

