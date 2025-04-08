# tasks.py
import os
import subprocess
import logging
from urllib.parse import urlparse

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configuration (consider moving sensitive parts or paths to env vars)
# Default download dir inside the container
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', '/app/downloads')
GALLERY_DL_PATH = "gallery-dl" # Assumes gallery-dl is in PATH

def validate_url(url):
    """Basic URL validation."""
    try:
        result = urlparse(url)
        # Check if scheme is http or https and netloc (domain) exists
        return all([result.scheme in ['http', 'https'], result.netloc])
    except ValueError:
        return False

def run_gallery_dl(url, extra_options=None):
    """
The RQ task function to run gallery-dl.
Captures output and handles success/failure.
Args:
url (str): The gallery URL to download.
extra_options (list): A list of additional command-line options for gallery-dl.
Returns:
dict: A dictionary containing status, output, and error messages.
    """
    if not validate_url(url):
        logging.error(f"Invalid URL received: {url}")
        return {"status": "error", "message": "Invalid URL format."}

    if not os.path.exists(DOWNLOAD_DIR):
        try:
            os.makedirs(DOWNLOAD_DIR)
            logging.info(f"Created download directory: {DOWNLOAD_DIR}")
        except OSError as e:
            logging.error(f"Failed to create download directory {DOWNLOAD_DIR}: {e}")
            return {"status": "error", "message": f"Server error: Cannot create download directory. {e}"}

    # --- SECURITY ---
    # Basic sanitization: Ensure options don't contain obviously malicious patterns.
    # A robust solution might involve strict allowlisting of options or more complex parsing.
    sanitized_options = []
    if extra_options:
        for opt in extra_options:
            # Example: Disallow options starting with '-' followed by chars that could cause issues,
            # or options containing shell metacharacters (;, &, |, etc.) - this is NOT exhaustive!
            if isinstance(opt, str) and not any(c in opt for c in ';|&`$()<>'):
                sanitized_options.append(opt)
            else:
                logging.warning(f"Skipping potentially unsafe option: {opt}")

    # Construct the command safely as a list
    command = [
        GALLERY_DL_PATH,
        '--verbose',
        '-o', f'base-directory={DOWNLOAD_DIR}', # Use configured download dir
        # Add other *sanitized* options here
        *sanitized_options,
        url # The validated URL comes last
    ]

    logging.info(f"Executing command: {' '.join(command)}") # Log the command for debugging

    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False, # Don't raise exception on non-zero exit code
            timeout=1800 # Timeout (e.g., 30 minutes) - adjust as needed
        )

        log_output = f"STDOUT:\n{process.stdout}\nSTDERR:\n{process.stderr}"
        logging.info(f"gallery-dl process completed for {url} with code {process.returncode}")
        # Log full output for debugging if needed, might be verbose
        # logging.debug(log_output)

        if process.returncode == 0:
            return {
                "status": "success",
                "message": f"Download complete for {url}.",
                "output": process.stdout,
                "error_output": process.stderr # Include stderr for info
            }
        else:
            return {
                "status": "error",
                "message": f"gallery-dl failed with exit code {process.returncode} for {url}.",
                "output": process.stdout,
                "error_output": process.stderr
            }

    except subprocess.TimeoutExpired:
        logging.error(f"gallery-dl timed out for {url}")
        return {
            "status": "error",
            "message": f"Download timed out for {url}.",
            "output": "Process took too long to complete.",
            "error_output": ""
        }
    except FileNotFoundError:
        logging.error(f"'{GALLERY_DL_PATH}' command not found. Is gallery-dl installed and in PATH?")
        return {
            "status": "error",
            "message": "Server configuration error: gallery-dl command not found.",
        }
    except Exception as e:
        logging.exception(f"An unexpected error occurred during gallery-dl execution for {url}: {e}")
        return {
            "status": "error",
            "message": f"An unexpected server error occurred: {e}",
        }