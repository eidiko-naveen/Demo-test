"""Interactive Streamlit operations console for the OCP monitoring agent."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

# Streamlit executes this file as a script and prepends agent/ to sys.path.
# That makes agent/agent.py shadow the agent package unless the repository root
# is explicitly placed first.
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT in sys.path:
    sys.path.remove(_PROJECT_ROOT)
sys.path.insert(0, _PROJECT_ROOT)

import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy import desc
from sqlalchemy.orm import joinedload

from agent.config import get_settings
from agent.db import get_session, health_check
from agent.models import AgentRun, Failure, Incident, RemediationRequest
from agent.remediation import RemediationError, create_request, decide_request


cfg = get_settings()
st.set_page_config(
    page_title=f"OCP Command Center · {cfg.cluster_name}",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  .stApp { background: radial-gradient(circle at 12% 4%, #172554 0, #070b16 34%, #050814 100%); }
  [data-testid="stSidebar"] { background: linear-gradient(180deg,#0f172a,#080d1c); border-right:1px solid #24324d; }
  [data-testid="stHeader"] { background:rgba(5,8,20,.72); }
  .block-container { max-width:1500px; padding-top:1.6rem; padding-bottom:4rem; }
  h1,h2,h3 { color:#f8fafc!important; letter-spacing:-.025em; }
  p,label,[data-testid="stMarkdownContainer"] { color:#b8c5da; }
  [data-testid="stMetric"] { background:linear-gradient(145deg,rgba(30,41,65,.92),rgba(10,16,31,.94)); border:1px solid #263653; border-radius:16px; padding:18px; box-shadow:0 14px 38px rgba(0,0,0,.25); }
  [data-testid="stMetricLabel"] { color:#91a4c3; }
  [data-testid="stMetricValue"] { color:#f8fafc; }
  .hero { padding:30px 34px; border-radius:20px; border:1px solid rgba(125,211,252,.2); background:linear-gradient(120deg,rgba(37,99,235,.36),rgba(124,58,237,.30),rgba(8,145,178,.20)); box-shadow:0 22px 65px rgba(0,0,0,.3); margin-bottom:20px; }
  .hero small { color:#7dd3fc; letter-spacing:.14em; font-weight:700; }
  .hero h1 { margin:.4rem 0; font-size:2.35rem; }
  .hero p { max-width:760px; margin:0; color:#d2dded; }
  .status-pill { display:inline-block; padding:6px 12px; border-radius:999px; background:#064e3b; color:#6ee7b7; font-weight:700; margin-top:14px; }
  .panel-title { color:#7dd3fc; font-size:.75rem; font-weight:700; letter-spacing:.12em; text-transform:uppercase; margin:8px 0 12px; }
  div[data-testid="stDataFrame"] { border:1px solid #263653; border-radius:14px; overflow:hidden; }
  .issue { border-left:4px solid #f43f5e; border-radius:10px; background:rgba(30,41,59,.72); padding:14px 16px; margin:10px 0; }
  .issue.warning { border-left-color:#f59e0b; }
  .muted { color:#7f91ad; font-size:.82rem; }
  .stTabs [data-baseweb="tab-list"] { gap:8px; }
  .stTabs [data-baseweb="tab"] { background:#111a2e; border-radius:10px; padding:8px 16px; }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=20)
def load_runs(hours: int, limit: int = 250) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    with get_session() as session:
        runs = (
            session.query(AgentRun)
            .filter(AgentRun.started_at >= since)
            .order_by(desc(AgentRun.started_at)).limit(limit).all()
        )
        return [{
            "id": str(r.id), "cluster": r.cluster_name, "started": r.started_at,
            "completed": r.completed_at, "status": r.status,
            "failures": r.failure_count, "summary": r.summary or "",
            "email": r.email_sent, "errors": r.collection_errors or {},
            "duration": (r.completed_at-r.started_at).total_seconds() if r.completed_at else None,
            "snapshot": r.raw_snapshot or {},
        } for r in runs]


@st.cache_data(ttl=20)
def load_failures(run_id: str) -> list[dict]:
    with get_session() as session:
        items = session.query(Failure).options(joinedload(Failure.resolution)).filter(Failure.run_id == run_id).all()
        return [{
            "ref": f.failure_ref, "component": f.component, "resource": f.resource_name or "—",
            "severity": f.severity, "message": f.message, "detected": f.detected_at,
            "root_cause": f.resolution.root_cause if f.resolution else "",
            "steps": f.resolution.steps or [] if f.resolution else [],
            "commands": f.resolution.commands or [] if f.resolution else [],
            "docs": f.resolution.docs_ref or "" if f.resolution else "",
        } for f in items]


@st.cache_data(ttl=30)
def load_incidents(limit: int = 200) -> list[dict]:
    with get_session() as session:
        items = session.query(Incident).order_by(desc(Incident.created_at)).limit(limit).all()
        return [{"id": i.incident_id, "title": i.title, "component": i.component,
                 "severity": i.severity, "indexed": i.indexed, "created": i.created_at,
                 "description": i.description, "root_cause": i.root_cause or ""} for i in items]


@st.cache_data(ttl=10)
def load_remediations(limit: int = 100) -> list[dict]:
    with get_session() as session:
        items = (
            session.query(RemediationRequest)
            .order_by(desc(RemediationRequest.created_at)).limit(limit).all()
        )
        return [{
            "id": str(item.id), "target": f"{item.namespace}/{item.resource_name}",
            "action": item.action, "reason": item.reason, "status": item.status,
            "mode": item.execution_mode, "requested_by": item.requested_by,
            "approver": item.approver_email or "", "decision": item.decision_reason or "",
            "result": item.result_message or "", "created": item.created_at,
            "decided": item.decided_at, "executed": item.executed_at,
            "pre_state": item.pre_state or {}, "post_state": item.post_state or {},
            "audit": item.audit_trail or [],
        } for item in items]


with st.sidebar:
    st.markdown("## ◈ OCP Command Center")
    st.caption(cfg.cluster_name)
    page = st.radio(
        "Workspace",
        ["Overview", "Run Explorer", "Cluster Inventory", "Incidents", "Remediation approvals"],
        label_visibility="collapsed",
    )
    st.divider()
    hours = st.select_slider("History window", options=[6, 12, 24, 48, 72, 168], value=24, format_func=lambda x: f"{x} hours" if x < 168 else "7 days")
    auto_refresh = st.toggle("Auto refresh (30s)", value=True)
    if st.button("↻ Refresh now", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    st.success("Database connected" if health_check() else "Database unavailable")
    st.caption(f"Monitor interval · {cfg.interval_minutes} min")

if auto_refresh:
    @st.fragment(run_every=30)
    def refresh_clock():
        st.caption(f"Live · refreshed {datetime.now().strftime('%H:%M:%S')}")
    refresh_clock()

runs = load_runs(hours)
latest = runs[0] if runs else None

st.markdown(f"""
<section class="hero">
  <small>AI-POWERED OPENSHIFT OPERATIONS</small>
  <h1>{page}</h1>
  <p>Real-time health, incident intelligence, and remediation context for {cfg.cluster_name}.</p>
  <span class="status-pill">● {latest['status'] if latest else 'AWAITING DATA'}</span>
</section>
""", unsafe_allow_html=True)

if not runs:
    st.info("No monitoring runs are available in this time window.")
    st.stop()

df = pd.DataFrame(runs)

if page == "Overview":
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Current status", latest["status"])
    c2.metric("Runs", len(df))
    c3.metric("Healthy", int((df.status == "HEALTHY").sum()))
    c4.metric("Open issues", int(df.failures.sum()))
    c5.metric("Email delivery", f"{int(df.email.sum())}/{len(df)}")

    left, right = st.columns([1.8, 1], gap="large")
    with left:
        st.markdown('<div class="panel-title">Health timeline</div>', unsafe_allow_html=True)
        chart_df = df.sort_values("started").copy()
        chart_df["health_score"] = chart_df.status.map({"HEALTHY": 100, "WARNING": 60, "ERROR": 35, "CRITICAL": 10}).fillna(50)
        chart = alt.Chart(chart_df).mark_line(point=True, strokeWidth=3).encode(
            x=alt.X("started:T", title=None), y=alt.Y("health_score:Q", title="Health score", scale=alt.Scale(domain=[0,100])),
            color=alt.Color("status:N", scale=alt.Scale(domain=["HEALTHY","WARNING","ERROR","CRITICAL"], range=["#34d399","#fbbf24","#a78bfa","#fb7185"])),
            tooltip=["started:T","status:N","failures:Q","duration:Q"]
        ).properties(height=310)
        st.altair_chart(chart, use_container_width=True)
    with right:
        st.markdown('<div class="panel-title">Status distribution</div>', unsafe_allow_html=True)
        counts = df.status.value_counts().rename_axis("status").reset_index(name="runs")
        donut = alt.Chart(counts).mark_arc(innerRadius=70, outerRadius=115).encode(
            theta="runs:Q", color=alt.Color("status:N", scale=alt.Scale(domain=["HEALTHY","WARNING","ERROR","CRITICAL"], range=["#34d399","#fbbf24","#a78bfa","#fb7185"])),
            tooltip=["status:N","runs:Q"]
        ).properties(height=310)
        st.altair_chart(donut, use_container_width=True)

    st.markdown('<div class="panel-title">Recent monitoring cycles</div>', unsafe_allow_html=True)
    st.dataframe(df[["started","status","failures","duration","email","summary"]].head(20), use_container_width=True, hide_index=True,
                 column_config={"started": st.column_config.DatetimeColumn("Started", format="DD MMM, HH:mm:ss"), "email": st.column_config.CheckboxColumn("Email"), "duration": st.column_config.NumberColumn("Duration", format="%.1f s")})

elif page == "Run Explorer":
    labels = {f"{r['started'].strftime('%d %b %H:%M')} · {r['status']} · {r['id'][:8]}": r for r in runs}
    selected = labels[st.selectbox("Select monitoring cycle", list(labels))]
    a,b,c,d = st.columns(4)
    a.metric("Status", selected["status"]); b.metric("Failures", selected["failures"])
    c.metric("Duration", f"{selected['duration'] or 0:.1f}s"); d.metric("Email", "Sent" if selected["email"] else "Not sent")
    st.info(selected["summary"] or "No summary available")
    failures = load_failures(selected["id"])
    details, telemetry, errors = st.tabs(["Issues & remediation", "Raw telemetry", "Collection errors"])
    with details:
        if not failures: st.success("No failures detected in this cycle.")
        for item in failures:
            css = "warning" if item["severity"] == "WARNING" else ""
            st.markdown(f'<div class="issue {css}"><b>{item["ref"]} · {item["severity"]}</b><br>{item["component"]} / {item["resource"]}<br><span class="muted">{item["message"]}</span></div>', unsafe_allow_html=True)
            with st.expander("Resolution runbook"):
                if item["root_cause"]: st.markdown(f"**Root cause:** {item['root_cause']}")
                for i, step in enumerate(item["steps"], 1): st.markdown(f"{i}. {step}")
                if item["commands"]: st.code("\n".join(item["commands"]), language="bash")
                if item["docs"]: st.link_button("Open documentation", item["docs"])
    with telemetry: st.json(selected["snapshot"], expanded=1)
    with errors:
        if selected["errors"]: st.json(selected["errors"])
        else: st.success("All telemetry collectors completed successfully.")

elif page == "Cluster Inventory":
    snapshot = latest["snapshot"]
    tabs = st.tabs(["Nodes", "Operators", "MachineConfigPools", "Pods", "PVCs", "Certificates", "etcd"])
    keys = ["nodes","operators","mcpools","pods","pvcs","certs","etcd"]
    for tab, key in zip(tabs, keys):
        with tab:
            value = snapshot.get(key, [] if key != "etcd" else {})
            if isinstance(value, list) and value: st.dataframe(pd.DataFrame(value), use_container_width=True, hide_index=True)
            elif value: st.json(value)
            else: st.success(f"No {key} issues reported.")

elif page == "Incidents":
    incidents = load_incidents()
    if not incidents: st.info("The incident knowledge base is empty.")
    else:
        idf = pd.DataFrame(incidents)
        c1,c2,c3 = st.columns(3)
        c1.metric("Knowledge records", len(idf)); c2.metric("Indexed", int(idf.indexed.sum())); c3.metric("Components", idf.component.nunique())
        components = sorted(x for x in idf.component.dropna().unique())
        chosen = st.multiselect("Filter components", components)
        if chosen: idf = idf[idf.component.isin(chosen)]
        st.dataframe(idf[["id","title","component","severity","indexed","created"]], use_container_width=True, hide_index=True)
        lookup = {f"{x['id']} · {x['title']}": x for x in incidents}
        item = lookup[st.selectbox("Inspect incident", list(lookup))]
        st.markdown(f"### {item['title']}")
        st.write(item["description"])
        if item["root_cause"]: st.warning(f"Root cause: {item['root_cause']}")

else:
    st.markdown('<div class="panel-title">Human-approved remediation</div>', unsafe_allow_html=True)
    if not cfg.hitl_enabled:
        st.warning("HITL remediation is disabled in configuration.")
        st.stop()

    if cfg.hitl_execution_enabled:
        st.error("LIVE MODE — an approved request can change the allowlisted OpenShift Deployment.")
    else:
        st.info("DRY-RUN MODE — approvals are audited, but OpenShift cannot be changed.")

    c1, c2, c3 = st.columns(3)
    c1.metric("Allowed namespace", cfg.hitl_allowed_namespace)
    c2.metric("Allowed Deployment", cfg.hitl_allowed_deployment)
    c3.metric("Allowed action", "Restart Deployment")

    with st.expander("Create remediation proposal", expanded=False):
        reason = st.text_area(
            "Why is a restart recommended?",
            placeholder="Describe the incident evidence and expected benefit.",
        )
        if st.button("Create approval request", type="primary", disabled=not reason.strip()):
            try:
                request_id = create_request(reason)
                st.cache_data.clear()
                st.success(f"Request {str(request_id)[:8]} is awaiting human approval.")
                st.rerun()
            except RemediationError as exc:
                st.error(str(exc))

    requests = load_remediations()
    pending = [item for item in requests if item["status"] == "PENDING_APPROVAL"]
    st.markdown(f"### Pending decisions ({len(pending)})")
    for item in pending:
        with st.container(border=True):
            st.markdown(f"**{item['target']} · Restart Deployment**")
            st.write(item["reason"])
            st.caption(f"Request {item['id']} · {item['mode']} · {item['created']}")
            approver = st.text_input(
                "Authorized approver email", key=f"approver-{item['id']}",
                placeholder=cfg.hitl_approver_email,
            )
            decision = st.text_input("Decision note", key=f"note-{item['id']}")
            approval_secret = ""
            if cfg.hitl_execution_enabled:
                approval_secret = st.text_input(
                    "Approval credential", type="password", key=f"secret-{item['id']}"
                )
            approve_col, reject_col = st.columns(2)
            if approve_col.button("Approve", key=f"approve-{item['id']}", type="primary"):
                try:
                    status = decide_request(
                        item["id"], approver, True, decision, approval_secret
                    )
                    st.cache_data.clear()
                    st.success(f"Decision saved: {status}")
                    st.rerun()
                except RemediationError as exc:
                    st.error(str(exc))
            if reject_col.button("Reject", key=f"reject-{item['id']}"):
                try:
                    status = decide_request(item["id"], approver, False, decision, approval_secret)
                    st.cache_data.clear()
                    st.success(f"Decision saved: {status}")
                    st.rerun()
                except RemediationError as exc:
                    st.error(str(exc))

    st.markdown("### Audit history")
    if not requests:
        st.info("No remediation requests have been created.")
    else:
        audit_df = pd.DataFrame(requests)
        st.dataframe(
            audit_df[["created", "target", "action", "mode", "status", "approver", "result"]],
            use_container_width=True, hide_index=True,
        )
        lookup = {f"{item['created']} · {item['status']} · {item['id'][:8]}": item for item in requests}
        selected_request = lookup[st.selectbox("Inspect audit record", list(lookup))]
        st.json({
            "request_id": selected_request["id"],
            "reason": selected_request["reason"],
            "decision_note": selected_request["decision"],
            "pre_state": selected_request["pre_state"],
            "post_state": selected_request["post_state"],
            "events": selected_request["audit"],
        })
