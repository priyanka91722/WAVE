import streamlit as st

CSS = """
<style>
footer {visibility: hidden;}
.block-container {padding-top: 2rem; max-width: 1200px;}
h1 {font-weight: 800; letter-spacing: -0.5px;}
[data-testid="stMetric"] {
    background: rgba(128,128,128,0.08);
    border: 1px solid rgba(128,128,128,0.25);
    border-radius: 12px;
    padding: 14px 16px;
    text-align: center;
}
[data-testid="stMetricLabel"], [data-testid="stMetricValue"] {justify-content: center;}
[data-testid="stMetricLabel"] > div {justify-content: center;}
.stButton > button, .stFormSubmitButton > button {
    border-radius: 10px; font-weight: 600; padding: 0.5rem 1.4rem;
}
[data-testid="stSidebar"] {border-right: 1px solid rgba(128,128,128,0.25);}
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)