import re

import streamlit as st


st.set_page_config(
    page_title="Estate Records",
    page_icon="🏡",
    layout="wide",
    initial_sidebar_state="collapsed",
)


st.markdown(
    """
    <style>
    :root {
        --ink: #172b2a;
        --muted: #61716d;
        --green: #176b52;
        --line: #e4ebe7;
        --paper: #f6f8f5;
    }
    html, body, [class*="css"] {
        font-family: 'DM Sans', 'Segoe UI', sans-serif;
        color: var(--ink);
    }
    .stApp { background: var(--paper); }
    [data-testid="stHeader"] { background: transparent; }
    .block-container { max-width: 1180px; padding-top: 1.4rem; padding-bottom: 3rem; }
    .brand { font-family: 'Manrope', 'Segoe UI', sans-serif; font-size: 1.2rem; font-weight: 800; letter-spacing: -0.04em; }
    .brand-mark {
        display: inline-grid; place-items: center; width: 2rem; height: 2rem; margin-right: .55rem;
        color: white; background: var(--green); border-radius: .65rem; vertical-align: middle;
    }
    .eyebrow { color: var(--green); font-size: .76rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
    .hero-title {
        max-width: 690px; margin: .75rem 0 1rem; color: var(--ink);
        font-family: 'Manrope', 'Segoe UI', sans-serif; font-size: clamp(2.5rem, 5vw, 4.35rem);
        font-weight: 800; letter-spacing: -.065em; line-height: 1.05;
    }
    .hero-copy { max-width: 560px; color: var(--muted); font-size: 1.08rem; line-height: 1.75; }
    .hero-card {
        min-height: 360px; padding: 2rem; color: white; border-radius: 1.25rem;
        background: linear-gradient(145deg, #163d35 0%, #176b52 60%, #74a887 150%);
        display: flex; flex-direction: column; justify-content: space-between;
    }
    .hero-card-label { color: #c8e3d3; font-size: .78rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
    .hero-card-title { max-width: 360px; font-family: 'Manrope', 'Segoe UI', sans-serif; font-size: 2rem; font-weight: 700; line-height: 1.2; }
    .hero-card-copy { max-width: 340px; color: #d6e8dc; line-height: 1.65; }
    .hero-stat { display: inline-block; margin-right: 2rem; }
    .hero-stat strong { display: block; font-size: 1.35rem; }
    .hero-stat span { color: #d6e8dc; font-size: .8rem; }
    .section-title { margin: 2rem 0 .35rem; font-family: 'Manrope', 'Segoe UI', sans-serif; font-size: 1.55rem; font-weight: 800; letter-spacing: -.04em; }
    .section-copy { margin-bottom: 1rem; color: var(--muted); }
    .feature-card {
        height: 100%; min-height: 150px; padding: 1.2rem; background: white;
        border: 1px solid var(--line); border-radius: .9rem;
    }
    .feature-icon { font-size: 1.35rem; }
    .feature-title { margin: .65rem 0 .3rem; font-family: 'Manrope', 'Segoe UI', sans-serif; font-weight: 700; }
    .feature-copy { color: var(--muted); font-size: .9rem; line-height: 1.55; }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: white; border-color: var(--line); border-radius: 1rem;
    }
    div.stButton > button[kind="primary"] {
        color: white; background: var(--green); border-color: var(--green);
        border-radius: .55rem; font-weight: 700;
    }
    div.stButton > button[kind="primary"]:hover { background: #10553f; border-color: #10553f; }
    footer { visibility: hidden; }
    </style>
    """,
    unsafe_allow_html=True,
)


def valid_email(email: str) -> bool:
    """Perform basic form-level email validation before database integration."""
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()))


def render_login_form() -> None:
    with st.form("login_form", clear_on_submit=False):
        email = st.text_input("Email address", placeholder="you@example.com")
        password = st.text_input("Password", type="password", placeholder="Your password")
        submitted = st.form_submit_button("Log in", type="primary", use_container_width=True)

    if submitted:
        if not valid_email(email):
            st.error("Enter a valid email address.")
        elif not password:
            st.error("Enter your password.")
        else:
            st.info(
                "Login is a UI placeholder. Connect the MySQL database and implement "
                "credential verification before enabling sign-in."
            )


def render_register_form() -> None:
    with st.form("register_form", clear_on_submit=False):
        name = st.text_input("Full name", placeholder="Your name")
        email = st.text_input("Email address", placeholder="you@example.com")
        password = st.text_input("Create password", type="password", placeholder="At least 8 characters")
        confirm_password = st.text_input("Confirm password", type="password")
        submitted = st.form_submit_button("Create account", type="primary", use_container_width=True)

    if submitted:
        if not name.strip():
            st.error("Enter your name.")
        elif not valid_email(email):
            st.error("Enter a valid email address.")
        elif len(password) < 8:
            st.error("Choose a password with at least 8 characters.")
        elif password != confirm_password:
            st.error("The passwords do not match.")
        else:
            st.info(
                "Registration is a UI placeholder. Connect the MySQL database and implement "
                "secure password hashing and account creation before enabling registration."
            )


st.markdown(
    '<div class="brand"><span class="brand-mark">E</span>Estate Records</div>',
    unsafe_allow_html=True,
)
st.write("")

hero, account = st.columns([1.15, 0.85], gap="large", vertical_alignment="center")

with hero:
    st.markdown('<div class="eyebrow">A clearer view of property</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-title">Real estate records, all in one place.</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="hero-copy">Explore property information, find the records that matter, '
        'and keep your searches close at hand. A focused workspace for better-informed decisions.</div>',
        unsafe_allow_html=True,
    )
    st.write("")
    st.markdown(
        """
        <div class="hero-card">
            <div class="hero-card-label">Your property workspace</div>
            <div>
                <div class="hero-card-title">From first search to saved shortlist.</div>
                <div class="hero-card-copy">Search, review, and organise property records with one simple workflow.</div>
            </div>
            <div>
                <div class="hero-stat"><strong>Search</strong><span>Find relevant records</span></div>
                <div class="hero-stat"><strong>Save</strong><span>Return to searches</span></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with account:
    with st.container(border=True):
        st.markdown("### Welcome")
        st.caption("Log in or create an account to get started.")
        login_tab, register_tab = st.tabs(["Log in", "Create account"])
        with login_tab:
            render_login_form()
        with register_tab:
            render_register_form()
        st.caption("Authentication and account storage will be enabled after database setup.")

st.markdown('<div class="section-title">Everything you need to stay organised</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="section-copy">The workspace is ready for the core tools in your project.</div>',
    unsafe_allow_html=True,
)

features = [
    ("⌕", "Search & filter", "Narrow property records by the details that matter to you."),
    ("▤", "Manage records", "Create, review, update, and remove records from one workspace."),
    ("☆", "Saved searches", "Keep useful search criteria ready for your next visit."),
]
feature_columns = st.columns(3, gap="medium")
for column, (icon, title, description) in zip(feature_columns, features):
    with column:
        st.markdown(
            f"""
            <div class="feature-card">
                <div class="feature-icon">{icon}</div>
                <div class="feature-title">{title}</div>
                <div class="feature-copy">{description}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.write("")
st.caption(
    "Database integration: MySQL for relational account and property data; "
    "MongoDB for document-oriented saved-search data."
)
