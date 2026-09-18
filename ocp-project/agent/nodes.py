"""
nodes.py — LangGraph node functions for the OCP monitoring pipeline.

Each function:
  - Accepts the full ClusterState dict
  - Performs exactly ONE unit of work
  - Returns a PARTIAL dict containing only the keys it updates
  - Never raises — all errors are captured and written into state

Node inventory:
  ── Collection (7) ──────────────────────────────────────────────────────────
  collect_nodes_node()      → state["nodes"]
  collect_operators_node()  → state["operators"]
  collect_mcp_node()        → state["mcpools"]
  collect_etcd_node()       → state["etcd"]
  collect_pvcs_node()       → state["pvcs"]
  collect_pods_node()       → state["pods"]
  collect_certs_node()      → state["certs"]
  collect_cp4i_node()       → state["cp4i_endpoints"]

  ── Processing (5) ──────────────────────────────────────────────────────────
  aggregate_node()          → state["collected_at"], state["collection_errors"]
  analyze_node()            → state["failures"], state["summary"]
  resolve_node()            → state["resolutions"]
  rag_node()                → state["rag_results"]
  build_report_node()       → state["report_html"]
  escalate_node()           → state["escalations"], state["meeting_scheduled"]
  propose_remediation_node() → state["remediation_requests"]
  save_run_node()           → state["run_id"]
  send_email_node()         → state["email_sent"]
"""

from __future__ import annotations
import json
from agent.db import get_session
from agent.models import Incident
from agent.rag import index_new_incidents
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from agent.config import get_settings
from agent.logger import get_logger
from agent.state import ClusterState
from agent.tools import (
    check_cp4i_endpoints,
    get_cluster_operators,
    get_etcd_health,
    get_expiring_certs,
    get_failing_pods,
    get_machine_config_pools,
    get_node_status,
    get_pvc_issues,
)

log = get_logger(__name__)
cfg = get_settings()


# ──────────────────────────────────────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────────────────────────────────────

def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_error_response(data: Any) -> bool:
    """True if a tool returned an error dict/list instead of real data."""
    if isinstance(data, list) and len(data) == 1 and "error" in data[0]:
        return True
    if isinstance(data, dict) and "error" in data:
        return True
    return False


def _extract_error(data: Any) -> str:
    if isinstance(data, list) and data:
        return data[0].get("error", "unknown error")
    if isinstance(data, dict):
        return data.get("error", "unknown error")
    return "unknown error"


# ──────────────────────────────────────────────────────────────────────────────
# Collection Nodes (7 + 1 CP4I)
# ──────────────────────────────────────────────────────────────────────────────

def collect_nodes_node(state: ClusterState) -> Dict:
    log.info("node_start", node="collect_nodes")
    try:
        result = get_node_status.invoke({})
        log.info("node_done", node="collect_nodes", count=len(result))
        return {"nodes": result}
    except Exception as exc:
        log.error("node_error", node="collect_nodes", error=str(exc))
        return {"nodes": [{"error": str(exc)}]}


def collect_operators_node(state: ClusterState) -> Dict:
    log.info("node_start", node="collect_operators")
    try:
        result = get_cluster_operators.invoke({})
        log.info("node_done", node="collect_operators", count=len(result))
        return {"operators": result}
    except Exception as exc:
        log.error("node_error", node="collect_operators", error=str(exc))
        return {"operators": [{"error": str(exc)}]}


def collect_mcp_node(state: ClusterState) -> Dict:
    log.info("node_start", node="collect_mcp")
    try:
        result = get_machine_config_pools.invoke({})
        log.info("node_done", node="collect_mcp", count=len(result))
        return {"mcpools": result}
    except Exception as exc:
        log.error("node_error", node="collect_mcp", error=str(exc))
        return {"mcpools": [{"error": str(exc)}]}


def collect_etcd_node(state: ClusterState) -> Dict:
    log.info("node_start", node="collect_etcd")
    try:
        result = get_etcd_health.invoke({})
        log.info("node_done", node="collect_etcd", healthy=result.get("healthy"))
        return {"etcd": result}
    except Exception as exc:
        log.error("node_error", node="collect_etcd", error=str(exc))
        return {"etcd": {"error": str(exc)}}


def collect_pvcs_node(state: ClusterState) -> Dict:
    log.info("node_start", node="collect_pvcs")
    try:
        result = get_pvc_issues.invoke({})
        log.info("node_done", node="collect_pvcs", problem_count=len(result))
        return {"pvcs": result}
    except Exception as exc:
        log.error("node_error", node="collect_pvcs", error=str(exc))
        return {"pvcs": [{"error": str(exc)}]}


def collect_pods_node(state: ClusterState) -> Dict:
    log.info("node_start", node="collect_pods")
    try:
        result = get_failing_pods.invoke({})
        log.info("node_done", node="collect_pods", failing_count=len(result))
        return {"pods": result}
    except Exception as exc:
        log.error("node_error", node="collect_pods", error=str(exc))
        return {"pods": [{"error": str(exc)}]}


def collect_certs_node(state: ClusterState) -> Dict:
    log.info("node_start", node="collect_certs")
    try:
        result = get_expiring_certs.invoke({})
        log.info("node_done", node="collect_certs", expiring_count=len(result))
        return {"certs": result}
    except Exception as exc:
        log.error("node_error", node="collect_certs", error=str(exc))
        return {"certs": [{"error": str(exc)}]}


def collect_cp4i_node(state: ClusterState) -> Dict:
    log.info("node_start", node="collect_cp4i")
    try:
        result = check_cp4i_endpoints.invoke({})
        healthy = sum(1 for r in result if r.get("healthy"))
        log.info("node_done", node="collect_cp4i", total=len(result), healthy=healthy)
        return {"cp4i_endpoints": result}
    except Exception as exc:
        log.error("node_error", node="collect_cp4i", error=str(exc))
        return {"cp4i_endpoints": [{"error": str(exc)}]}


# ──────────────────────────────────────────────────────────────────────────────
# aggregate_node — validate all collected data, stamp timestamp
# ──────────────────────────────────────────────────────────────────────────────

def aggregate_node(state: ClusterState) -> Dict:
    """
    Validate all collected data and stamp the collection timestamp.

    Walks every collected field and records any tool errors into
    collection_errors. The pipeline continues regardless — partial
    data is better than no report.
    """
    log.info("node_start", node="aggregate")

    collection_errors: Dict[str, str] = {}

    checks = {
        "nodes":         state.get("nodes", []),
        "operators":     state.get("operators", []),
        "mcpools":       state.get("mcpools", []),
        "etcd":          state.get("etcd", {}),
        "pvcs":          state.get("pvcs", []),
        "pods":          state.get("pods", []),
        "certs":         state.get("certs", []),
        "cp4i_endpoints": state.get("cp4i_endpoints", []),
    }

    for key, data in checks.items():
        if _is_error_response(data):
            err = _extract_error(data)
            collection_errors[key] = err
            log.warning("collection_error_recorded", key=key, error=err)

    collected_at = _now_utc()

    log.info(
        "node_done",
        node="aggregate",
        collection_errors=len(collection_errors),
        collected_at=collected_at,
    )

    return {
        "collected_at": collected_at,
        "collection_errors": collection_errors,
    }


# ──────────────────────────────────────────────────────────────────────────────
# analyze_node — LLM failure analysis
# ──────────────────────────────────────────────────────────────────────────────
def assign_severity(failure: Dict) -> str:
    text = str(failure).lower()

    if "crashloopbackoff" in text:
        return "CRITICAL"
    if "notready" in text:
        return "CRITICAL"
    if "etcd" in text:
        return "CRITICAL"

    if "pending" in text:
        return "WARNING"
    if "cert" in text:
        return "WARNING"

    return "INFO"


def analyze_node(state: ClusterState) -> Dict:
    """
    Send the full cluster snapshot to the LLM for failure analysis.

    Imports llm_chains lazily to avoid circular imports.
    Returns failures list and summary string.
    """
    log.info("node_start", node="analyze")
    try:
        from agent.llm_chains import run_analysis
        failures, summary = run_analysis(state)
        for f in failures:
            f["severity"] = assign_severity(f)
        log.info(
            "node_done",
            node="analyze",
            failure_count=len(failures),
            summary_preview=summary[:80],
        )
        return {"failures": failures, "summary": summary}
    except Exception as exc:
        log.error("node_error", node="analyze", error=str(exc), tb=traceback.format_exc())
        return {
            "failures": [],
            "summary": f"Analysis failed: {str(exc)}. Manual review required.",
        }


# ──────────────────────────────────────────────────────────────────────────────
# resolve_node — RAG-first, LLM-as-fallback remediation
# ──────────────────────────────────────────────────────────────────────────────

# Similarity score threshold — above this, RAG answer is used directly
# and the LLM is NOT called. Tune this value (0.0–1.0).
RAG_CONFIDENCE_THRESHOLD = 0.85


def _resolution_from_rag(failure: Dict, rag_hit: Dict) -> Dict:
    """Build a resolution dict from a RAG result (no LLM call needed)."""
    return {
        "failure_id":   failure.get("id", ""),
        "issue":        failure.get("message", ""),
        "severity":     failure.get("severity", "UNKNOWN"),
        "root_cause":   rag_hit.get("root_cause", "See similar incident"),
        "steps":        rag_hit.get("resolution_steps") or [],
        "commands":     rag_hit.get("commands") or [],
        "resource":     failure.get("resource_name", ""),
        "component":    failure.get("component", ""),
        "source":       "rag",          # tells reporter where this came from
        "rag_incident": rag_hit.get("incident_id", ""),
        "rag_score":    rag_hit.get("similarity_score"),
    }


def _save_incidents_and_index(failures: List[Dict], enriched: List[Dict]) -> None:
    """
    Persist new incidents to the incidents table and trigger RAG indexing.
    Only saves failures that came from LLM (source != 'rag') so we don't
    create duplicate incidents for known issues already in the vector store.
    """
    try:
        now = datetime.now(timezone.utc)
        incidents = []

        for f in failures:
            # Skip failures already resolved from RAG — they're already indexed
            res = next((r for r in enriched if r.get("failure_id") == f.get("id")), {})
            if res.get("source") == "rag":
                continue

            # Use a stable ID based on component+message hash to avoid duplicates
            import hashlib
            raw = f"{f.get('component', '')}:{f.get('message', '')}"
            stable_id = hashlib.md5(raw.encode()).hexdigest()[:12]

            incidents.append(Incident(
                incident_id=stable_id,
                title=f.get("message") or f.get("description", ""),
                component=f.get("component"),
                severity=f.get("severity"),
                description=(f.get("message") or f.get("description") or "No description available"),
                root_cause=res.get("root_cause", ""),
                resolution_steps=res.get("steps", []),
                commands=res.get("commands", []),
                occurred_at=now,
                indexed=False,
            ))

        if incidents:
            with get_session() as session:
                existing_ids = {i[0] for i in session.query(Incident.incident_id).all()}
                new_incidents = [i for i in incidents if i.incident_id not in existing_ids]
                session.add_all(new_incidents)
            log.info("incidents_created", count=len(new_incidents))

            # Index new incidents into vector store immediately
            indexed_count = index_new_incidents()
            log.info("rag_index_triggered", indexed=indexed_count)

    except Exception as e:
        log.error("incident_save_failed", error=str(e))


def resolve_node(state: ClusterState) -> Dict:
    """
    RAG-first resolution:
      1. For each failure, query RAG for a similar past incident.
      2. If similarity score >= RAG_CONFIDENCE_THRESHOLD → use RAG answer directly.
         LLM is NOT called for this failure. Zero tokens spent.
      3. If RAG score is low or no match → call LLM for a fresh resolution.
      4. LLM resolutions are saved back to the incidents table and indexed
         into the vector store so future identical failures hit RAG instead.

    Over time the vector store grows and the LLM gets called less and less.
    """
    failures = state.get("failures", [])

    log.info("node_start", node="resolve", failure_count=len(failures))

    if not failures:
        log.info("node_skip", node="resolve", reason="no_failures")
        return {"resolutions": []}

    try:
        from agent.rag import query_similar_incidents

        enriched: List[Dict] = []
        llm_failures: List[Dict] = []   # failures that need LLM resolution

        # ── Step 1: Check RAG for each failure ───────────────────────────────
        for failure in failures:
            fid        = failure.get("id", "")
            query_text = f"{failure.get('component', '')} {failure.get('message', '')}"

            similar = query_similar_incidents(query_text, top_k=1)

            if similar:
                top_hit = similar[0]
                score   = top_hit.get("similarity_score") or 0.0

                if score >= RAG_CONFIDENCE_THRESHOLD:
                    # ✅ High confidence — use RAG answer, skip LLM
                    resolution = _resolution_from_rag(failure, top_hit)
                    enriched.append(resolution)
                    log.info(
                        "resolve_rag_hit",
                        failure_id=fid,
                        score=score,
                        incident=top_hit.get("incident_id", ""),
                    )
                    continue

            # Low/no RAG match — queue for LLM
            llm_failures.append(failure)
            log.info("resolve_llm_needed", failure_id=fid)

        # ── Step 2: Call LLM only for unresolved failures ────────────────────
        if llm_failures:
            from agent.llm_chains import run_resolution

            log.info("resolve_llm_call", failure_count=len(llm_failures))
            llm_resolutions = run_resolution(llm_failures)

            if not isinstance(llm_resolutions, list):
                llm_resolutions = []

            for r in llm_resolutions:
                enriched.append({
                    "failure_id": r.get("failure_id"),
                    "issue":      r.get("issue", ""),
                    "severity":   r.get("severity", "UNKNOWN"),
                    "root_cause": r.get("root_cause", "Unknown"),
                    "steps":      r.get("steps", []),
                    "commands":   r.get("commands", []),
                    "resource":   r.get("resource", ""),
                    "component":  r.get("component", ""),
                    "source":     "llm",
                })

        # ── Step 3: Save LLM resolutions to DB + index for future RAG hits ───
        _save_incidents_and_index(failures, enriched)

        rag_count = sum(1 for r in enriched if r.get("source") == "rag")
        llm_count = sum(1 for r in enriched if r.get("source") == "llm")
        log.info(
            "node_done",
            node="resolve",
            total=len(enriched),
            from_rag=rag_count,
            from_llm=llm_count,
        )
        return {"resolutions": enriched}

    except Exception as exc:
        log.error("node_error", node="resolve", error=str(exc), tb=traceback.format_exc())

        # Fallback — never leave failures without a resolution
        fallback = []
        for f in failures:
            fallback.append({
                "failure_id": f.get("id"),
                "issue":      f.get("message", ""),
                "severity":   f.get("severity", "UNKNOWN"),
                "root_cause": "Resolution generation failed",
                "steps":      ["Check logs manually", "Verify configuration", "Restart affected component"],
                "commands":   [
                    f"oc describe {f.get('component', 'pod')} {f.get('resource_name', '')}",
                    f"oc logs {f.get('resource_name', '')}",
                ],
                "resource":   f.get("resource_name", ""),
                "component":  f.get("component", ""),
                "source":     "fallback",
            })
        return {"resolutions": fallback}



# ──────────────────────────────────────────────────────────────────────────────
# rag_node — LlamaIndex historical incident search
# ──────────────────────────────────────────────────────────────────────────────

def rag_node(state: ClusterState) -> Dict:
    """
    Query the LlamaIndex vector store for similar historical incidents.

    For each detected failure, retrieve the top-K most similar past
    incidents and attach them to rag_results keyed by failure id.

    Skips gracefully if no failures or if the RAG index is unavailable.
    """
    failures = state.get("failures", [])
    if not failures:
        log.info("node_skip", node="rag", reason="no failures")
        return {"rag_results": {}}

    log.info("node_start", node="rag", failure_count=len(failures))
    try:
        from agent.rag import query_similar_incidents
        rag_results: Dict[str, List] = {}
        for failure in failures:
            fid = failure.get("id", "unknown")
            query_text = f"{failure.get('component','')} {failure.get('message','')}"
            similar = query_similar_incidents(query_text)
            rag_results[fid] = similar
            log.debug("rag_query", failure_id=fid, similar_count=len(similar))

        log.info("node_done", node="rag", queried=len(rag_results))
        return {"rag_results": rag_results}

    except Exception as exc:
        log.warning("node_error", node="rag", error=str(exc))
        # RAG failure is non-fatal — report continues without historical context
        return {"rag_results": {}}


def propose_remediation_node(state: ClusterState) -> Dict:
    """Open one approval request for a critical pod in the allowlisted Deployment."""
    if not cfg.hitl_enabled:
        return {"remediation_requests": []}

    pods = {
        str(pod.get("name", "")): pod
        for pod in state.get("pods", [])
        if pod.get("name")
    }
    resolutions = {
        str(item.get("failure_id", "")): item
        for item in state.get("resolutions", [])
    }

    for failure in state.get("failures", []):
        if str(failure.get("severity", "")).upper() != "CRITICAL":
            continue
        pod = pods.get(str(failure.get("resource_name", "")))
        if not pod:
            continue
        if (
            pod.get("namespace") != cfg.hitl_allowed_namespace
            or pod.get("deployment") != cfg.hitl_allowed_deployment
        ):
            continue

        resolution = resolutions.get(str(failure.get("id", "")), {})
        reason_parts = [
            f"Critical monitor finding: {failure.get('message', '')}",
            f"Pod: {pod.get('name')} ({pod.get('phase', 'unknown')})",
        ]
        if resolution.get("root_cause"):
            reason_parts.append(f"AI root-cause assessment: {resolution['root_cause']}")
        if resolution.get("steps"):
            reason_parts.append(
                "Recommended plan: " + "; ".join(str(step) for step in resolution["steps"][:3])
            )

        try:
            from agent.remediation import create_request

            request_id = create_request("\n".join(reason_parts), requested_by="monitoring-agent")
            log.info(
                "remediation_proposal_created",
                request_id=str(request_id), pod=pod.get("name"),
            )
            return {"remediation_requests": [{
                "request_id": str(request_id),
                "failure_id": failure.get("id", ""),
                "namespace": pod.get("namespace", ""),
                "deployment": pod.get("deployment", ""),
                "status": "PENDING_APPROVAL",
            }]}
        except Exception as exc:
            log.error("remediation_proposal_failed", error=str(exc))
            return {"remediation_requests": []}

    return {"remediation_requests": []}

# ──────────────────────────────────────────────────────────────────────────────
# build_report_node — render HTML report
# ──────────────────────────────────────────────────────────────────────────────

def build_report_node(state: ClusterState) -> Dict:
    log.info("node_start", node="build_report")
    try:
        from agent.reporter import build_html_report
        html = build_html_report(state)
        log.info("node_done", node="build_report", html_bytes=len(html))
        return {"report_html": html}
    except Exception as exc:
        log.error("node_error", node="build_report", error=str(exc), tb=traceback.format_exc())
        # Fallback minimal report so email can still be sent
        fallback = (
            f"<html><body><h1>Report Generation Failed</h1>"
            f"<p>{str(exc)}</p></body></html>"
        )
        return {"report_html": fallback}


# ─────────────────────────────────────────────────────────────────────────────
# Google Meet escalation
# ─────────────────────────────────────────────────────────────────────────────

def _failure_haystack(failure: Dict[str, Any], namespace: str = "") -> str:
    return " ".join(
        [
            str(failure.get("component", "")),
            str(failure.get("resource_name", "")),
            namespace,
        ]
    ).lower()


def _build_pod_namespace_lookup(state: ClusterState) -> Dict[str, str]:
    return {
        str(pod["name"]): str(pod["namespace"])
        for pod in state.get("pods", [])
        if pod.get("name") and pod.get("namespace")
    }


def _is_escalation_candidate(failure: Dict[str, Any], namespace: str = "") -> bool:
    if str(failure.get("severity", "")).upper() != "CRITICAL":
        return False
    haystack = _failure_haystack(failure, namespace)
    return any(value in haystack for value in cfg.escalation_components_list)


def _load_escalation_owners() -> Dict[str, List[str]]:
    configured_path = Path(cfg.escalation_owners_file)
    if not configured_path.is_absolute():
        configured_path = Path(__file__).resolve().parent.parent / configured_path
    try:
        raw = json.loads(configured_path.read_text(encoding="utf-8"))
        return {
            str(key).lower(): [str(value).strip() for value in values if str(value).strip()]
            for key, values in raw.items()
            if not str(key).startswith("_") and isinstance(values, list)
        }
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        log.error(
            "escalation_owners_load_failed", path=str(configured_path), error=str(exc)
        )
        return {}


def _resolve_escalation_attendees(
    failure: Dict[str, Any], namespace: str, owners: Dict[str, List[str]]
) -> List[str]:
    haystack = _failure_haystack(failure, namespace)
    # Prefer the most specific matching key, regardless of JSON key order.
    matches = [key for key in owners if key in haystack]
    selected = owners[max(matches, key=len)] if matches else cfg.escalation_fallback_owners_list
    return list(dict.fromkeys(selected))


def _build_escalation_description(
    state: ClusterState,
    failure: Dict[str, Any],
    namespace: str,
) -> str:
    """Build the human-readable explanation stored on the Calendar event."""
    failure_id = str(failure.get("id", ""))
    resolution = next(
        (
            item
            for item in state.get("resolutions", [])
            if str(item.get("failure_id", "")) == failure_id
        ),
        {},
    )

    component = str(failure.get("component", "unknown"))
    resource_name = str(failure.get("resource_name", "unknown"))
    summary = str(state.get("summary", "")).strip() or "No cluster summary was generated."

    lines = [
        "WHY THIS MEETING WAS CREATED",
        (
            f"A CRITICAL {component} incident matched the automatic escalation "
            f"scope and remained critical for {cfg.escalation_consecutive_cycles} "
            "consecutive monitoring cycles."
        ),
        "",
        "CLUSTER SUMMARY",
        summary,
        "",
        "INCIDENT DETAILS",
        f"Cluster: {state.get('cluster_name', cfg.cluster_name)}",
        f"Failure ID: {failure_id or 'n/a'}",
        f"Component: {component}",
        f"Resource: {resource_name}",
        f"Namespace: {namespace or 'n/a'}",
        f"Severity: {failure.get('severity', 'CRITICAL')}",
        f"Reason: {failure.get('message', '')}",
    ]

    if resolution:
        lines.extend(["", "AI REMEDIATION CONTEXT"])
        if resolution.get("root_cause"):
            lines.append(f"Likely root cause: {resolution['root_cause']}")
        steps = resolution.get("steps", []) or []
        if steps:
            lines.append("Recommended steps:")
            lines.extend(f"{index}. {step}" for index, step in enumerate(steps, 1))
        commands = resolution.get("commands", []) or []
        if commands:
            lines.append("Suggested commands:")
            lines.extend(f"- {command}" for command in commands)
        if resolution.get("docs_ref"):
            lines.append(f"Documentation: {resolution['docs_ref']}")

    lines.extend(
        [
            "",
            "AUTOMATION DETAILS",
            f"Cycle started: {state.get('timestamp', '')}",
            f"Meeting duration: {cfg.escalation_meeting_duration_minutes} minutes",
            "Created automatically by the OCP monitoring agent.",
        ]
    )
    return "\n".join(lines)


def _run_contains_same_critical(
    session, run_id: Any, component: str, resource_name: str
) -> bool:
    from agent.models import Failure

    query = session.query(Failure).filter(
        Failure.run_id == run_id,
        Failure.component == component,
        Failure.severity == "CRITICAL",
    )
    if resource_name:
        query = query.filter(Failure.resource_name == resource_name)
    return query.first() is not None


def _persistence_threshold_reached(
    failure: Dict[str, Any], cluster_name: str, current_started_at: str
) -> bool:
    """True once, on the cycle where a consecutive-failure threshold is reached."""
    from agent.models import AgentRun

    required_prior_matches = cfg.escalation_consecutive_cycles - 1
    # One extra run tells us whether this incident was already escalated on the
    # preceding cycle. That prevents repeated invites for one ongoing incident.
    history_limit = max(required_prior_matches + 1, 1)
    try:
        started_at = datetime.fromisoformat(current_started_at)
    except (TypeError, ValueError):
        started_at = datetime.now(timezone.utc)

    with get_session() as session:
        prior_runs = (
            session.query(AgentRun)
            .filter(
                AgentRun.cluster_name == cluster_name,
                AgentRun.started_at < started_at,
            )
            .order_by(AgentRun.started_at.desc())
            .limit(history_limit)
            .all()
        )
        matches = [
            _run_contains_same_critical(
                session,
                run.id,
                str(failure.get("component", "")),
                str(failure.get("resource_name", "")),
            )
            for run in prior_runs
        ]

    if len(matches) < required_prior_matches:
        return False
    if required_prior_matches and not all(matches[:required_prior_matches]):
        return False
    # If the next older cycle also matched, the threshold was reached earlier.
    return len(matches) == required_prior_matches or not matches[required_prior_matches]


def escalate_node(state: ClusterState) -> Dict:
    """Schedule one Google Meet invite when a critical incident first persists."""
    if not cfg.escalation_enabled:
        return {"escalations": [], "meeting_scheduled": False}

    namespace_by_pod = _build_pod_namespace_lookup(state)
    candidates = []
    for failure in state.get("failures", []):
        namespace = namespace_by_pod.get(str(failure.get("resource_name", "")), "")
        if _is_escalation_candidate(failure, namespace):
            candidates.append((failure, namespace))

    owners = _load_escalation_owners()
    escalations: List[Dict[str, Any]] = []
    for failure, namespace in candidates:
        try:
            if not _persistence_threshold_reached(
                failure,
                state.get("cluster_name", cfg.cluster_name),
                state.get("timestamp", _now_utc()),
            ):
                continue

            attendees = _resolve_escalation_attendees(failure, namespace, owners)
            from agent.google_meet import schedule_meeting

            component = str(failure.get("component", "unknown"))
            resource_name = str(failure.get("resource_name", "unknown"))
            subject = (
                f"[{state.get('cluster_name', cfg.cluster_name)}] CRITICAL: "
                f"{component} / {resource_name}"
            )
            body = _build_escalation_description(state, failure, namespace)
            result = schedule_meeting(subject, body, attendees)
            escalations.append(
                {
                    "failure_id": failure.get("id", ""),
                    "component": component,
                    "resource_name": resource_name,
                    "attendees": attendees,
                    "event_id": result.get("event_id", ""),
                    "join_url": result.get("join_url", ""),
                    "summary": state.get("summary", ""),
                    "description": body,
                }
            )
        except Exception as exc:
            log.error(
                "escalation_meeting_failed",
                failure_id=failure.get("id", ""),
                error=str(exc),
            )

    log.info("node_done", node="escalate", scheduled_count=len(escalations))
    return {"escalations": escalations, "meeting_scheduled": bool(escalations)}


# ──────────────────────────────────────────────────────────────────────────────
# save_run_node — persist results to PostgreSQL
# ──────────────────────────────────────────────────────────────────────────────

def save_run_node(state: ClusterState) -> Dict:
    """
    Persist the completed cycle to PostgreSQL (AgentRun + Failures + Resolutions).

    Returns the run UUID so downstream nodes and the dashboard can reference it.
    """
    log.info("node_start", node="save_run")
    try:
        from agent.db import get_session
        from agent.models import AgentRun, Failure, Resolution

        failures = state.get("failures", [])
        resolutions_map = {
            r["failure_id"]: r
            for r in state.get("resolutions", [])
            if "failure_id" in r
        }

        # Determine overall run status
        severities = {f.get("severity", "").upper() for f in failures}
        if "CRITICAL" in severities:
            status = "CRITICAL"
        elif "WARNING" in severities:
            status = "WARNING"
        elif failures:
            status = "WARNING"
        else:
            status = "HEALTHY"

        collection_errors = state.get("collection_errors", {})
        if collection_errors:
            status = "ERROR" if status == "HEALTHY" else status

        with get_session() as session:
            run = AgentRun(
                cluster_name=state.get("cluster_name", cfg.cluster_name),
                started_at=datetime.fromisoformat(
                    state.get("timestamp", _now_utc())
                ),
                collected_at=datetime.fromisoformat(
                    state.get("collected_at", _now_utc())
                ) if state.get("collected_at") else None,
                completed_at=datetime.now(timezone.utc),
                status=status,
                failure_count=len(failures),
                summary=state.get("summary", ""),
                report_html=state.get("report_html", ""),
                # Email and escalation run before persistence, so their final
                # outcomes are captured in this run record.
                email_sent=state.get("email_sent", False),
                collection_errors=collection_errors or None,
                raw_snapshot={
                    k: state.get(k)
                    for k in ["nodes", "operators", "mcpools", "etcd",
                              "pvcs", "pods", "certs", "cp4i_endpoints",
                              "escalations", "meeting_scheduled",
                              "remediation_requests"]
                },
            )
            session.add(run)
            session.flush()  # get run.id before adding children

            for f_dict in failures:
                failure = Failure(
                    run_id=run.id,
                    failure_ref=f_dict.get("id", ""),
                    component=f_dict.get("component", "unknown"),
                    resource_name=f_dict.get("resource_name", ""),
                    severity=f_dict.get("severity", "INFO"),
                    message=f_dict.get("message", ""),
                    detected_at=datetime.fromisoformat(f_dict["detected_at"])
                    if f_dict.get("detected_at") else None,
                )
                session.add(failure)
                session.flush()

                res_dict = resolutions_map.get(f_dict.get("id", ""))
                if res_dict:
                    resolution = Resolution(
                        failure_id=failure.id,
                        root_cause=res_dict.get("root_cause", ""),
                        steps=res_dict.get("steps", []),
                        commands=res_dict.get("commands", []),
                        docs_ref=res_dict.get("docs_ref", ""),
                    )
                    session.add(resolution)

            run_id = str(run.id)

        log.info("node_done", node="save_run", run_id=run_id, status=status)
        return {"run_id": run_id}

    except Exception as exc:
        log.error("node_error", node="save_run", error=str(exc), tb=traceback.format_exc())
        return {"run_id": ""}


# ──────────────────────────────────────────────────────────────────────────────
# send_email_node — dispatch the HTML report via email
# ──────────────────────────────────────────────────────────────────────────────

def send_email_node(state: ClusterState) -> Dict:
    """
    Send the HTML report email via the configured backend (SMTP or SendGrid).

    Respects cfg.email_on_healthy — skips email when cluster is healthy
    and the setting is False.
    """
    failures = state.get("failures", [])
    collection_errors = state.get("collection_errors", {})
    is_healthy = len(failures) == 0

    if not cfg.email_enabled:
        log.info("node_skip", node="send_email", reason="email_disabled")
        return {"email_sent": False}

    if collection_errors and is_healthy and not cfg.email_on_collection_error:
        log.info(
            "node_skip",
            node="send_email",
            reason="collection_errors_without_cluster_failures",
            collection_errors=list(collection_errors),
        )
        return {"email_sent": False}

    if is_healthy and not cfg.email_on_healthy:
        log.info("node_skip", node="send_email", reason="healthy_and_suppressed")
        return {"email_sent": False}

    log.info("node_start", node="send_email", failure_count=len(failures))
    try:
        from agent.emailer import dispatch

        severities = {f.get("severity", "").upper() for f in failures}
        if "CRITICAL" in severities:
            status_label = "🔴 CRITICAL"
        elif "WARNING" in severities:
            status_label = "🟡 WARNING"
        elif failures:
            status_label = "🟡 WARNING"
        elif collection_errors:
            status_label = "🔴 COLLECTION ERROR"
        else:
            status_label = "🟢 HEALTHY"

        subject = (
            f"[{state.get('cluster_name', cfg.cluster_name)}] "
            f"OCP Health Report — {status_label} — "
            f"{state.get('timestamp', '')[:10]}"
        )

        dispatch(
            subject=subject,
            html_body=state.get("report_html", "<p>No report generated.</p>"),
        )

        log.info("node_done", node="send_email", recipients=cfg.email_recipients)
        return {"email_sent": True}

    except Exception as exc:
        log.error("node_error", node="send_email", error=str(exc))
        return {"email_sent": False}
