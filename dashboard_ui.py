"""Presentation helpers for the school dashboard; no database writes."""

from html import escape
from pathlib import Path

import streamlit as st


SECTIONS = {
    "Overview": ["Overview"],
    "People & access": ["Students", "Teachers", "Departments", "Class Teachers", "Class Sections", "Logins"],
    "Teaching & learning": ["Subjects", "Timetable", "Exams"],
    "Nova & school information": ["Almanac", "Suggested Additions", "Learned Phrases", "Notices"],
    "Operations": ["System Status"],
}
DESCRIPTIONS = {
    "Overview": "School records and Nova, in one place.",
    "Students": "Manage student records, attendance and fee status.",
    "Teachers": "Manage staff profiles, departments and class assignments.",
    "Departments": "Organise teaching teams and department heads.",
    "Class Teachers": "Assign the class teacher responsible for each class.",
    "Class Sections": "Maintain the Boys and Girls class mappings used in reports.",
    "Logins": "Manage chatbot accounts and linked records.",
    "Subjects": "Maintain subjects and the grades that study them.",
    "Timetable": "Manage teaching periods and check allocation conflicts.",
    "Exams": "Manage exam schedules, subjects and classes.",
    "Almanac": "Update the school information Nova uses in its answers.",
    "Suggested Additions": "Review unanswered questions and add verified school information.",
    "Learned Phrases": "Review and approve new ways of asking existing questions.",
    "Notices": "Manage announcements and their audience.",
    "System Status": "Check chatbot availability and its toggle history.",
}


def apply_theme():
    css = Path(__file__).with_name("dashboard.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def login_header():
    st.markdown('<div class="login-brand"><span class="brand-mark">Y</span>'
                '<span>YaraBot <small>SCHOOL ADMINISTRATION</small></span></div>', unsafe_allow_html=True)
    st.title("Welcome back")
    st.caption("Sign in to manage school records and Nova’s knowledge.")


def navigation(username, cloud):
    with st.sidebar:
        st.markdown('<div class="sidebar-brand"><span class="brand-mark">Y</span>'
                    '<span>YaraBot<small>ADMIN WORKSPACE</small></span></div>', unsafe_allow_html=True)
        st.caption(f"Signed in as {username}")
        section = st.selectbox("Workspace", list(SECTIONS), key="dashboard_section")
        page = st.radio("Pages", SECTIONS[section], key=f"dashboard_page_{section}", label_visibility="collapsed")
        st.divider()
        st.caption("Current Aiven data" if cloud else "Local database")
        st.caption("Saved changes affect the connected chatbot.")
        if st.button("Sign out", key="dashboard_logout", width="stretch"):
            # Remove editor contents as well as authentication state.
            for key in list(st.session_state):
                del st.session_state[key]
            st.rerun()
    st.markdown(f'<div class="page-eyebrow">YARA INTERNATIONAL SCHOOL / {escape(section.upper())}</div>',
                unsafe_allow_html=True)
    st.title(page)
    st.caption(DESCRIPTIONS[page])
    return page


def searchable_table(frame, key):
    search = st.text_input("Search records", key=f"search_{key}", placeholder="Search any column…")
    filtered = frame
    if search.strip():
        mask = frame.fillna("").astype(str).apply(
            lambda column: column.str.contains(search.strip(), case=False, regex=False)
        ).any(axis=1)
        filtered = frame.loc[mask]
    st.caption(f"{len(filtered)} of {len(frame)} records")
    st.dataframe(filtered, hide_index=True, width="stretch")
