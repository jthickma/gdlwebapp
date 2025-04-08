// static/script.js
const form = document.getElementById('download-form');
const resultsDiv = document.getElementById('results');
const urlInput = document.getElementById('url');
const loadingIndicator = document.getElementById('loading');

const POLLING_INTERVAL = 3000; // Poll every 3 seconds
let activePolls = new Map(); // Keep track of intervals for active jobs {jobId: intervalId}

function displayJobStatus(jobData) {
    let jobElement = document.getElementById(`job-${jobData.job_id}`);
    if (!jobElement) {
        // Create element if it doesn't exist
        jobElement = document.createElement('div');
        jobElement.id = `job-${jobData.job_id}`;
        jobElement.classList.add('job-item');
        // Prepend new jobs to the top
        resultsDiv.insertBefore(jobElement, resultsDiv.firstChild);
    }

    // Clear previous content and apply status class
    jobElement.innerHTML = '';
    jobElement.className = 'job-item'; // Reset classes
    jobElement.classList.add(`status-${jobData.status}`); // Add current status class

    // Display Job ID and Status
    const statusLine = document.createElement('p');
    statusLine.innerHTML = `<strong>Job ID:</strong> ${jobData.job_id} | <strong>Status:</strong> ${jobData.status}`;
    jobElement.appendChild(statusLine);

    // Display Message
    if (jobData.message) {
        const messageLine = document.createElement('p');
        messageLine.textContent = jobData.message;
        jobElement.appendChild(messageLine);
    }

    // Display Output (if available)
    if (jobData.output) {
        const outputHeader = document.createElement('h4');
        outputHeader.textContent = 'Output:';
        jobElement.appendChild(outputHeader);
        const outputPre = document.createElement('pre');
        outputPre.textContent = jobData.output;
        jobElement.appendChild(outputPre);
    }

    // Display Error Output (if available)
    if (jobData.error_output) {
        const errorHeader = document.createElement('h4');
        errorHeader.textContent = 'Error Output:';
        jobElement.appendChild(errorHeader);
        const errorPre = document.createElement('pre');
        errorPre.textContent = jobData.error_output;
        jobElement.appendChild(errorPre);
    }

    // Stop polling if the job is finished or failed
    if (jobData.status === 'finished' || jobData.status === 'failed') {
        stopPolling(jobData.job_id);
    }
}

function pollJobStatus(jobId) {
    // Don't start polling if already polling for this job
    if (activePolls.has(jobId)) return;

    const intervalId = setInterval(async () => {
        try {
            const response = await fetch(`/status/${jobId}`);
            if (!response.ok) {
                 // Handle server errors during polling differently?
                 console.error(`Failed to fetch status for job ${jobId}: ${response.status}`);
                 // Optionally display an error within the job element
                 stopPolling(jobId); // Stop polling on fetch error
                 return;
            }
            const data = await response.json();
            displayJobStatus(data); // Update the UI

            // Redundant check, displayJobStatus should also stop it
            if (data.status === 'finished' || data.status === 'failed') {
                stopPolling(jobId);
            }
        } catch (error) {
            console.error('Error polling job status:', error);
            // Optionally display network error in UI
            stopPolling(jobId); // Stop polling on network error
        }
    }, POLLING_INTERVAL);

    activePolls.set(jobId, intervalId);
    console.log(`Started polling for job ${jobId} with interval ID ${intervalId}`);
}

function stopPolling(jobId) {
    if (activePolls.has(jobId)) {
        clearInterval(activePolls.get(jobId));
        activePolls.delete(jobId);
        console.log(`Stopped polling for job ${jobId}`);
    }
}

form.addEventListener('submit', async (event) => {
    event.preventDefault();
    loadingIndicator.style.display = 'inline'; // Show loading

    const formData = new FormData(form);

    try {
        const response = await fetch('/start-download', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        // Create a temporary status display while waiting for first poll
        const initialJobData = {
            job_id: result.job_id || 'N/A',
            status: response.ok ? result.status : 'error', // Use status from response
            message: result.message || (response.ok ? 'Queued...' : 'Failed to queue task')
        };
        displayJobStatus(initialJobData);


        if (response.ok && result.status === 'queued' && result.job_id) {
            pollJobStatus(result.job_id); // Start polling for the new job
            urlInput.value = ''; // Clear input field on success
        } else {
             // Handle queueing errors - already displayed by displayJobStatus
             console.error("Failed to queue job:", result.message);
        }

    } catch (error) {
        console.error('Form submission error:', error);
        // Display a general error if fetch itself failed
        displayJobStatus({ job_id: 'N/A', status: 'error', message: 'Failed to send request to server.' });
    } finally {
        loadingIndicator.style.display = 'none'; // Hide loading
    }
});

// Optional: If there are jobs already displayed on page load (e.g., from server-side rendering),
// you could initiate polling for them here if they are in an active state.
// document.querySelectorAll('.job-item[data-status="queued"], .job-item[data-status="started"]').forEach(item => {
//    const jobId = item.id.replace('job-', '');
//    if(jobId) pollJobStatus(jobId);
// });