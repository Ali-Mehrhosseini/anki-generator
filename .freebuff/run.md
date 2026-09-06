# Preview Runbook

## Reproduce artifacts

From a fresh checkout at `/Users/alimehhosseini/Anki`:

1. Create or reuse the project virtual environment:
   `python3 -m venv venv`
2. Install the dependencies with the project requirements file:
   `venv/bin/pip install -r requirements.txt`
3. Copy the local environment file from the main checkout into this worktree as `.env`; do not commit or document its values.

The Flask app reads API credentials at request time from the browser for the web generation flow, while `.env` is used by CLI workflows.

## Run server

From the project root, start the Flask app with:

`venv/bin/python app.py`

The default preview URL is `http://127.0.0.1:5001`. If port `5001` is occupied, use another free port by adapting the Flask startup configuration before launching the server. For the Freebuff preview, detach on macOS with:

`{ nohup venv/bin/python app.py > "/Users/alimehhosseini/Anki/.freebuff/preview-bc4a2869-f7c8-45f3-b038-92acaac81f7e.log" 2>&1 < /dev/null & echo "pid=$!"; disown; }`
