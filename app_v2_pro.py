"""Legacy Streamlit entrypoint.

This file intentionally delegates execution to app.py so that
older deployment settings that still point to app_v2_pro.py
always run the latest product workflow.
"""

from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).with_name("app.py")), run_name="__main__")
