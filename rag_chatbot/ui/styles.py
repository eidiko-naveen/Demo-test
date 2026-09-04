import streamlit as st


def apply_styles():

    st.markdown(
        """
<style>

@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');

:root {
    --ink: #102a43;
    --muted: #627d98;
    --line: #d9e2ec;
    --blue: #1476b8;
    --green: #73be44;
    --paper: #f7fafc;
}

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
    color: var(--ink);
}

.stApp {
    background: var(--paper);
    background-image: radial-gradient(#d9e2ec 0.7px, transparent 0.7px);
    background-size: 24px 24px;
}

.block-container {
    max-width: 1180px;
    padding-top: 2rem;
    padding-bottom: 5rem;
}

.hero {
    padding: 2.1rem 2.2rem;
    border: 1px solid #c9d8e5;
    border-radius: 4px;
    background: linear-gradient(112deg, #ffffff 0%, #eff7fb 100%);
    box-shadow: 0 12px 35px rgba(16, 42, 67, 0.07);
    margin-bottom: 1.5rem;
    position: relative;
    overflow: hidden;
}

.hero:after {
    content: '';
    position: absolute;
    width: 180px;
    height: 180px;
    right: 5%;
    top: -90px;
    border: 24px solid rgba(115, 190, 68, 0.15);
    border-radius: 50%;
}

.hero h1 {
    font-family: 'Space Grotesk', sans-serif;
    color: var(--ink);
    margin: 0;
    font-size: 2.15rem;
    letter-spacing: 0;
}

.hero p {
    color: var(--muted);
    margin-top: 0.4rem;
}

.brand-mark {
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 700;
    font-size: 1.55rem;
    letter-spacing: 0;
    color: var(--blue);
    margin-bottom: 1.8rem;
}

.brand-mark span {
    color: var(--green);
}

.eyebrow {
    color: var(--green);
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
}

.welcome-panel {
    padding: 2rem 0 1rem;
}

.welcome-panel h2 {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.8rem;
    margin: 0.3rem 0;
}

.welcome-panel p {
    color: var(--muted);
    max-width: 600px;
}

section[data-testid="stSidebar"] {
    background: #ffffff;
    border-right: 1px solid var(--line);
}

section[data-testid="stSidebar"] .block-container {
    padding: 1.6rem 1.2rem;
}

section[data-testid="stSidebar"] h3 {
    color: var(--ink);
    font-family: 'Space Grotesk', sans-serif;
}

.stButton > button, .stDownloadButton > button {
    border-radius: 3px;
    border: 1px solid #b8c9d8;
    font-weight: 600;
    color: var(--ink);
    min-height: 2.65rem;
}

.stButton > button[kind="primary"] {
    background: var(--blue);
    color: white;
    border-color: var(--blue);
}

.stChatMessage {
    border: 1px solid var(--line);
    border-radius: 4px;
    background: rgba(255, 255, 255, 0.82);
    margin: 0.7rem 0;
}

.stChatInput {
    background: white;
}

.source-card {
    padding: 0.9rem 1rem;
    border: 1px solid var(--line);
    border-left: 4px solid var(--green);
    background: #ffffff;
    border-radius: 3px;
    margin: 0.65rem 0;
}

.source-card strong { color: var(--ink); }
.source-card small { color: var(--muted); }

@media (max-width: 700px) {
    .block-container { padding: 1rem 0.8rem 4rem; }
    .hero { padding: 1.4rem; }
    .hero h1 { font-size: 1.65rem; }
}

</style>
""",
        unsafe_allow_html=True,
    )