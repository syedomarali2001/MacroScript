MACROSCRIPT - QUICK START
=========================

From the folder containing app.py, run in PowerShell:

    python -m pip install -r requirements.txt
    python -m streamlit run app.py

Open the address shown in the terminal (usually http://localhost:8501).

The homepage has two paths: Today's Economy and Time Machine.
The five indicators and their charts are directly on those pages.
For a brief report on the recession warning experiments, use Research findings.
Light is the default theme. Dark Navy, Ocean Blue, Forest Green, and Burgundy Red
are available in the sidebar; the sidebar also links to MacroScript on GitHub.
Warning benchmarks are shown directly beneath the economic summary.

LIVE FRED / ALFRED REQUESTS: keep your personal FRED_API_KEY in a private .env
file beside app.py. Copy .env.example to .env and fill in your own key.
Never commit or share the .env file. This distributed ZIP deliberately omits it.

Time Machine saved month-end snapshots use local research/datasets files.
Other historical days require a FRED key and an ALFRED request.

To run backend tests:
    python -m pytest -q

The research inputs and economics calculations were preserved. No public
recession forecast is provided.
