"""Streamlit dashboard for inventory, use-case facts, and screenings.

Run the API first, then from the repository root:

    .\\.venv\\Scripts\\python.exe -m streamlit run frontend/app.py
"""

import os

import streamlit as st

from frontend.client import ApiClient
from frontend.forms import NOTICE
from frontend.governance import render_audit, render_controls, render_reports, render_review
from frontend.views import render_inventory, render_screening, render_use_case

PAGES = ("Inventory", "Use case", "Screening", "Controls", "Review", "Audit", "Reports")


def main() -> None:
    """Draw the sidebar and the selected page."""
    st.set_page_config(page_title="AI governance", layout="wide")
    if "pending_page" in st.session_state:
        st.session_state["page"] = st.session_state.pop("pending_page")
    st.sidebar.markdown("**AI governance**")
    st.sidebar.caption(NOTICE)
    base_url = st.sidebar.text_input("API", os.environ.get("API_BASE_URL", "http://127.0.0.1:8000"))
    actor = st.sidebar.text_input("Your name", key="actor_name")
    page = st.sidebar.radio("Go to", PAGES, key="page")
    if st.sidebar.button("Register a new system"):
        st.session_state["system_id"] = None
        st.session_state["draft_for"] = None
        st.session_state["assessment_id"] = None
        st.session_state["pending_page"] = "Use case"
        st.rerun()
    selected = st.session_state.get("system_id")
    if selected:
        st.sidebar.caption(f"Open system {selected}")
    client = ApiClient(base_url, actor=actor)
    try:
        if page == "Inventory":
            render_inventory(client)
        elif page == "Use case":
            render_use_case(client)
        elif page == "Screening":
            render_screening(client)
        elif page == "Controls":
            render_controls(client)
        elif page == "Review":
            render_review(client)
        elif page == "Audit":
            render_audit(client)
        else:
            render_reports(client)
    finally:
        client.close()


if __name__ == "__main__":
    main()
