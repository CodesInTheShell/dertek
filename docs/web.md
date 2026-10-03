# Local web app

Dertek's browser interface uses the same agent runtime as the CLI. Flask serves a Vue single page app from local files; no Node.js installation or frontend build is needed to run it.

## Start

From the source checkout:

```bash
uv run dertek web --port 8765
```

From an installed Dertek tool:

```bash
dertek web --port 8765
```

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). The server listens only on `127.0.0.1`. Leave its terminal open while using the browser app, and press Ctrl+C to stop it.

Choose an existing local folder to create a session. The Sessions sidebar opens saved conversations. The conversation page shows routing, model and tool events as they happen, followed by the complete answer. Shell commands that require approval appear in a card with their arguments; unanswered requests are denied after five minutes. Only one run can be active at a time.

The Settings page changes non-secret model, reasoning, routing, and approval values in `~/.dertek/settings.json`. Environment variables still have higher priority. Authentication status is visible there, but credentials are not exposed or edited in the browser.

For ChatGPT authentication, first run:

```bash
dertek auth login
```

For API-key mode, export `OPENAI_API_KEY` before starting `dertek web`. Export `TYPESAFE_API_KEY` to enable Jev; without it, the heuristic router remains available.

Saved conversation history survives a web-server restart. ChatGPT's provider replay buffer is process-local, so a resumed ChatGPT session starts fresh model context after restart. The app makes that visible before the next prompt.

## Architecture

Flask owns local API routes under `/api`, a server-sent event stream for each run, and the HTML shell for `/`, `/settings`, and `/sessions/<id>`. Browser JavaScript mounts one Vue app into `#app`; Vue Router changes views and Pinia holds UI state. The pinned browser libraries are served from Dertek's own static directory.
