import streamlit as st
import requests
import os

from src.frontend.streamlit.style import custom_css, auth_css

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
LOGO_PATH = os.path.join(ASSETS_DIR, "fea_copilot_logo.png")


def login_dialog_box():
    st.markdown(custom_css, unsafe_allow_html=True)
    st.markdown(auth_css, unsafe_allow_html=True)
    
    submission = None

    with st.container(key="auth_brand"):
        st.image(LOGO_PATH)
        st.markdown("Your agentic co-pilot for Abaqus/CAE")

    with st.container(key="auth_card"):
        login_tab, signup_tab = st.tabs(["Log in", "Sign up"])

        with login_tab:
            st.markdown("### Welcome back")
            st.caption("Sign in to pick up where you left off.")

            with st.form("login_form", border=False):
                username = st.text_input("Username", placeholder="your.username")
                password = st.text_input("Password", type="password", placeholder="••••••••")
                remember = st.checkbox("Keep me signed in")
                if st.form_submit_button("Log in", type="primary", width="stretch"):
                    if not username or not password:
                        st.error("Enter your username and password.")
                    else:
                        url = 
                        requests.post())
                        submission = {
                            "action": "login",
                            "username": username.strip(),
                            "password": password,
                            "remember": remember,
                        }

        with signup_tab:
            st.markdown("### Create your account")
            st.caption("Set up FEA Copilot in under a minute.")

            with st.form("signup_form", border=False):
                first_col, last_col = st.columns(2)
                first_name = first_col.text_input("First name", placeholder="Ada")
                last_name = last_col.text_input("Last name", placeholder="Lovelace")
                email = st.text_input("Email", placeholder="you@company.com")
                new_username = st.text_input("Username", placeholder="Pick a username")
                new_password = st.text_input("Password", type="password", placeholder="At least 8 characters")
                confirm_password = st.text_input("Confirm password", type="password", placeholder="Repeat password")

                if st.form_submit_button("Create account", type="primary", width="stretch"):
                    if not all([first_name, last_name, email, new_username, new_password]):
                        st.error("Please fill in every field.")
                    elif new_password != confirm_password:
                        st.error("Passwords don't match.")
                    else:
                        submission = {
                            "action": "signup",
                            "first_name": first_name.strip(),
                            "last_name": last_name.strip(),
                            "email": email.strip(),
                            "username": new_username.strip(),
                            "password": new_password,
                        }

    with st.container(key="auth_footer"):
        st.markdown("FEA Copilot · Built for engineers by engineers")

    return submission
