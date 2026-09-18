def get_eidiko_css() -> str:
    """Returns custom CSS injected for Eidiko Enterprise GitHub MCP Portal."""
    return """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }

    /* Main App Workspace Background */
    .stApp {
        background: radial-gradient(circle at top right, #0F172A 0%, #090D16 50%, #030712 100%);
        color: #F1F5F9;
    }

    /* Top Navigation Header Banner */
    .eidiko-banner {
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.85) 0%, rgba(30, 41, 59, 0.85) 100%);
        border: 1px solid rgba(56, 189, 248, 0.25);
        box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(16px);
        border-radius: 16px;
        padding: 24px 32px;
        margin-bottom: 28px;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }

    .eidiko-logo-text {
        font-size: 26px;
        font-weight: 800;
        letter-spacing: -0.5px;
        background: linear-gradient(90deg, #38BDF8 0%, #818CF8 50%, #C084FC 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }

    .eidiko-subtitle {
        font-size: 13px;
        color: #94A3B8;
        font-weight: 500;
        letter-spacing: 0.5px;
        margin-top: 4px;
    }

    /* Custom Form Cards */
    .action-card {
        background: rgba(15, 23, 42, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
        padding: 24px;
        margin-bottom: 20px;
        backdrop-filter: blur(12px);
        transition: all 0.25s ease-in-out;
    }

    .action-card:hover {
        border-color: rgba(56, 189, 248, 0.35);
        box-shadow: 0 8px 30px rgba(56, 189, 248, 0.08);
    }

    .action-card-header {
        font-size: 18px;
        font-weight: 700;
        color: #F8FAFC;
        margin-bottom: 6px;
        display: flex;
        align-items: center;
        gap: 10px;
    }

    .action-card-sub {
        font-size: 13px;
        color: #94A3B8;
        margin-bottom: 18px;
    }

    /* Status Badges */
    .status-badge-online {
        background: rgba(16, 185, 129, 0.12);
        color: #34D399;
        border: 1px solid rgba(16, 185, 129, 0.3);
        padding: 6px 14px;
        border-radius: 24px;
        font-size: 13px;
        font-weight: 600;
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }

    /* Tool Call Execution Badges */
    .tool-badge {
        background: rgba(56, 189, 248, 0.12);
        color: #38BDF8;
        border: 1px solid rgba(56, 189, 248, 0.3);
        padding: 4px 12px;
        border-radius: 6px;
        font-size: 12px;
        font-family: 'JetBrains Mono', monospace;
        font-weight: 600;
        margin-right: 6px;
        display: inline-block;
    }

    /* Modern Tabs Customization */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background: rgba(15, 23, 42, 0.6);
        padding: 6px;
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.06);
    }

    .stTabs [data-baseweb="tab"] {
        height: 44px;
        border-radius: 8px;
        color: #94A3B8;
        font-weight: 600;
        font-size: 14px;
        border: none !important;
        padding: 0 20px;
    }

    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #1E293B 0%, #334155 100%) !important;
        color: #38BDF8 !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
    }

    /* Styled Inputs & Forms */
    .stTextInput input, .stTextArea textarea, .stSelectbox select {
        background-color: rgba(15, 23, 42, 0.8) !important;
        color: #F8FAFC !important;
        border-radius: 10px !important;
        border: 1px solid rgba(255, 255, 255, 0.12) !important;
        font-size: 14px !important;
    }

    .stTextInput input:focus, .stTextArea textarea:focus {
        border-color: #38BDF8 !important;
        box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.2) !important;
    }

    /* Buttons Styling */
    .stButton > button {
        background: linear-gradient(135deg, #0284C7 0%, #0369A1 100%) !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        border: 1px solid rgba(56, 189, 248, 0.4) !important;
        border-radius: 10px !important;
        padding: 10px 22px !important;
        transition: all 0.2s ease !important;
        box-shadow: 0 4px 14px rgba(2, 132, 199, 0.25) !important;
    }

    .stButton > button:hover {
        background: linear-gradient(135deg, #0369A1 0%, #075985 100%) !important;
        box-shadow: 0 6px 20px rgba(2, 132, 199, 0.4) !important;
        transform: translateY(-1px) !important;
    }
    </style>
    """
