"""
Streamlit UI for the D-Invoice Pipeline.

Connects to the running FastAPI backend (default: http://localhost:8000)
and provides a rich, interactive dashboard for managing invoices.

Run:
    streamlit run streamlit_app.py

Make sure the FastAPI backend is running first:
    python main.py serve
"""
from __future__ import annotations

import time
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_BASE = st.sidebar.text_input(
    "API Base URL",
    value="http://localhost:8000",
    help="Base URL of the running FastAPI backend",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def api(path: str, method: str = "GET", **kwargs) -> dict | list | None:
    """Call the backend API and return parsed JSON, or None on failure."""
    url = f"{API_BASE}{path}"
    try:
        resp = requests.request(method, url, timeout=15, **kwargs)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        return None


def format_inr(value: float | None) -> str:
    """Format a number as Indian Rupee currency string."""
    if value is None:
        return "—"
    return f"₹{value:,.2f}"


def confidence_bar(conf: float | None) -> str:
    """Return a text representation of confidence."""
    if conf is None:
        return "—"
    pct = round(conf * 100)
    return f"{pct}%"


def status_color(status: str) -> str:
    """Map status to a Streamlit-friendly color."""
    return {
        "stored": "🟢",
        "needs_review": "🟡",
        "quarantined": "🔴",
    }.get(status, "⚪")


# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="D-Invoice Pipeline",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    /* Card styling */
    div[data-testid="stMetric"] {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 16px;
    }
    div[data-testid="stMetric"] label {
        color: #94a3b8 !important;
    }
    /* Header */
    .main-header {
        font-size: 1.8rem;
        font-weight: 700;
        margin-bottom: 0;
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .subtitle {
        font-size: 0.9rem;
        color: #94a3b8;
    }
    /* Status badges */
    .status-stored { color: #22c55e; font-weight: 600; }
    .status-needs_review { color: #f59e0b; font-weight: 600; }
    .status-quarantined { color: #ef4444; font-weight: 600; }
    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar: Health & Navigation
# ---------------------------------------------------------------------------
st.sidebar.markdown("## 🧾 D-Invoice Pipeline")
st.sidebar.divider()

# Health check
health = api("/api/health")
if health:
    st.sidebar.markdown("### System Health")
    col1, col2 = st.sidebar.columns(2)
    with col1:
        if health.get("openrouter"):
            st.success("LLM ✓", icon="🤖")
        else:
            st.error("LLM ✗", icon="🤖")
    with col2:
        if health.get("ocr"):
            st.success("OCR ✓", icon="📷")
        else:
            st.warning("OCR ✗", icon="📷")

    if health.get("processing"):
        st.sidebar.info("⏳ Pipeline is processing...", icon="⚙️")

    st.sidebar.caption(f"Model: `{health.get('model', 'unknown')}`")
else:
    st.sidebar.error("⚠️ Cannot reach backend API")
    st.sidebar.caption(f"Ensure the FastAPI server is running at `{API_BASE}`")

st.sidebar.divider()

# Navigation
page = st.sidebar.radio(
    "Navigate",
    ["📊 Dashboard", "📋 Invoices", "📤 Upload & Process", "🚫 Quarantine",
     "📜 Activity Log", "⚡ Performance"],
    label_visibility="collapsed",
)

# Auto-refresh toggle
auto_refresh = st.sidebar.toggle("Auto-refresh (10s)", value=False)
if auto_refresh:
    time.sleep(10)
    st.rerun()


# ===========================================================================
# 📊 DASHBOARD
# ===========================================================================
if page == "📊 Dashboard":
    st.markdown("# 📊 Dashboard")
    st.caption("Real-time overview of the invoice processing pipeline")
    st.divider()

    # Stats
    stats = api("/api/stats")
    if not stats:
        st.error("Could not load stats from backend.")
        st.stop()

    # KPI Cards
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📦 Stored Invoices", stats.get("stored", 0))
    with col2:
        st.metric("🔍 Needs Review", stats.get("needs_review", 0))
    with col3:
        st.metric("🚫 Quarantined", stats.get("quarantined", 0))
    with col4:
        st.metric("💰 Total Value", format_inr(stats.get("total_value", 0)))

    st.divider()

    # Last pipeline result
    last = stats.get("last_result")
    if last:
        st.markdown("### 🔄 Last Pipeline Run")
        if "error" in last:
            st.error(f"Error: {last['error']}")
        else:
            cols = st.columns(4)
            cols[0].metric("Stored", last.get("stored", 0))
            cols[1].metric("Quarantined", last.get("quarantined", 0))
            cols[2].metric("Skipped", last.get("skipped", 0))
            cols[3].metric("Errors", last.get("errors", 0))

    st.divider()

    # Recent invoices preview
    st.markdown("### 📋 Recent Invoices")
    invoices = api("/api/invoices?limit=10")
    if invoices:
        df = pd.DataFrame(invoices)
        if not df.empty:
            display_cols = ["id", "vendor_name", "invoice_number", "invoice_date",
                           "bill_amount", "confidence", "status"]
            available_cols = [c for c in display_cols if c in df.columns]
            df_display = df[available_cols].copy()
            if "bill_amount" in df_display.columns:
                df_display["bill_amount"] = df_display["bill_amount"].apply(
                    lambda x: format_inr(x) if x else "—"
                )
            if "confidence" in df_display.columns:
                df_display["confidence"] = df_display["confidence"].apply(
                    lambda x: f"{round(x * 100)}%" if x else "—"
                )
            if "status" in df_display.columns:
                df_display["status"] = df_display["status"].apply(
                    lambda x: f"{status_color(x)} {x}"
                )
            st.dataframe(df_display, use_container_width=True, hide_index=True)
        else:
            st.info("No invoices yet. Upload some files to get started!")
    else:
        st.warning("Could not load invoices.")

    # Recent activity preview
    st.markdown("### 📜 Recent Activity")
    logs = api("/api/logs?limit=5")
    if logs:
        for log in logs:
            outcome = log.get("outcome", "")
            icon = "✅" if outcome == "success" else "❌" if outcome == "error" else "⚠️"
            file_name = log.get("source_file", "unknown")
            stage = log.get("stage", "")
            detail = (log.get("detail") or "")[:100]
            created = (log.get("created_at") or "")[:19].replace("T", " ")
            st.markdown(
                f"  {icon} **{stage}** — `{file_name}` — {detail}  \n"
                f"  <small style='color: #94a3b8;'>{created}</small>",
                unsafe_allow_html=True
            )
    else:
        st.info("No activity logs yet.")


# ===========================================================================
# 📋 INVOICES
# ===========================================================================
elif page == "📋 Invoices":
    st.markdown("# 📋 Invoices")
    st.caption("Browse, filter, and manage all processed invoices")
    st.divider()

    # Filters
    filter_col1, filter_col2, filter_col3 = st.columns([2, 2, 1])
    with filter_col1:
        status_filter = st.selectbox(
            "Filter by Status",
            ["All", "stored", "needs_review"],
            index=0,
        )
    with filter_col2:
        limit = st.slider("Max results", 10, 500, 200)
    with filter_col3:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()

    # Fetch invoices
    params = f"?limit={limit}"
    if status_filter != "All":
        params += f"&status={status_filter}"
    invoices = api(f"/api/invoices{params}")

    if invoices is None:
        st.error("Could not load invoices from backend.")
        st.stop()

    if not invoices:
        st.info("No invoices found. Try uploading and processing some invoice files!")
        st.stop()

    # Build dataframe
    df = pd.DataFrame(invoices)

    # Search
    search = st.text_input("🔍 Search invoices", placeholder="Search by vendor, invoice number...")
    if search:
        mask = df.apply(
            lambda row: search.lower() in str(row.values).lower(), axis=1
        )
        df = df[mask]

    st.markdown(f"**{len(df)} invoice(s) found**")

    # Display table
    for _, inv in df.iterrows():
        with st.container():
            cols = st.columns([0.5, 2, 2, 1.5, 1.5, 1, 1, 1.5])
            cols[0].markdown(f"**#{inv.get('id', '')}**")
            cols[1].markdown(f"🏢 {inv.get('vendor_name', '—')}")
            cols[2].markdown(f"📄 `{inv.get('invoice_number', '—')}`")
            cols[3].markdown(f"📅 {inv.get('invoice_date', '—')}")
            cols[4].markdown(f"💰 {format_inr(inv.get('bill_amount'))}")
            conf = inv.get("confidence")
            if conf is not None:
                cols[5].progress(conf, text=f"{round(conf*100)}%")
            else:
                cols[5].markdown("—")
            status = inv.get("status", "")
            cols[6].markdown(f"{status_color(status)} {status}")

            # Actions
            invoice_id = inv.get("id")
            col_btns = cols[7]
            btn_cols = col_btns.columns(2)
            if btn_cols[0].button("👁️", key=f"view_{invoice_id}", help="View details"):
                st.session_state["view_invoice_id"] = invoice_id
            if status == "needs_review":
                if btn_cols[1].button("✅", key=f"approve_{invoice_id}", help="Approve"):
                    result = api(f"/api/invoices/{invoice_id}/approve", method="POST")
                    if result and result.get("ok"):
                        st.success(f"Invoice #{invoice_id} approved!")
                        st.rerun()
                    else:
                        st.error("Failed to approve invoice.")
            st.divider()

    # Invoice Detail Modal
    if "view_invoice_id" in st.session_state:
        inv_id = st.session_state["view_invoice_id"]
        inv_detail = api(f"/api/invoices/{inv_id}")
        if inv_detail:
            st.divider()
            st.markdown(f"## 📄 Invoice #{inv_id} — Details")

            # Header info
            detail_cols = st.columns(4)
            detail_cols[0].markdown(f"**Vendor**  \n{inv_detail.get('vendor_name', '—')}")
            detail_cols[1].markdown(f"**Invoice #**  \n`{inv_detail.get('invoice_number', '—')}`")
            detail_cols[2].markdown(f"**Date**  \n{inv_detail.get('invoice_date', '—')}")
            detail_cols[3].markdown(f"**Status**  \n{status_color(inv_detail.get('status', ''))} {inv_detail.get('status', '—')}")

            # More details
            more_cols = st.columns(4)
            more_cols[0].markdown(f"**Receiver**  \n{inv_detail.get('receiver_details') or '—'}")
            more_cols[1].markdown(f"**State**  \n{inv_detail.get('state') or '—'}")
            more_cols[2].markdown(f"**Broker**  \n{inv_detail.get('broker') or '—'}")
            more_cols[3].markdown(f"**Due Date**  \n{inv_detail.get('due_date') or '—'}")

            # Financial summary
            st.markdown("### 💰 Financial Summary")
            fin_cols = st.columns(3)
            fin_cols[0].metric("Bill Amount", format_inr(inv_detail.get("bill_amount")))
            conf = inv_detail.get("confidence")
            fin_cols[1].metric("Confidence", f"{round(conf * 100)}%" if conf else "—")
            fin_cols[2].metric("Source File", inv_detail.get("source_file") or "—")

            # Line items
            line_items = inv_detail.get("line_items", [])
            if line_items:
                st.markdown("### 📋 Line Items")
                li_df = pd.DataFrame(line_items)
                # Format amount column
                if "amount" in li_df.columns:
                    li_df["amount_formatted"] = li_df["amount"].apply(format_inr)
                if "rate" in li_df.columns:
                    li_df["rate_formatted"] = li_df["rate"].apply(format_inr)

                display_cols = []
                for c in ["description", "design_no", "color", "pcs", "rate_formatted", "amount_formatted"]:
                    if c in li_df.columns:
                        display_cols.append(c)

                column_rename = {
                    "description": "Description",
                    "design_no": "Design No",
                    "color": "Color",
                    "pcs": "Pcs",
                    "rate_formatted": "Rate",
                    "amount_formatted": "Amount",
                }
                li_display = li_df[display_cols].rename(columns=column_rename)
                st.dataframe(li_display, use_container_width=True, hide_index=True)

                # Total
                total_amount = sum(li.get("amount", 0) for li in line_items)
                st.markdown(f"**Line Items Total: {format_inr(total_amount)}**")
            else:
                st.info("No line items found for this invoice.")

            # Actions
            action_cols = st.columns(4)
            if inv_detail.get("status") == "needs_review":
                if action_cols[0].button("✅ Approve Invoice", key="detail_approve",
                                         type="primary"):
                    result = api(f"/api/invoices/{inv_id}/approve", method="POST")
                    if result and result.get("ok"):
                        st.success("Invoice approved!")
                        st.rerun()

            if action_cols[1].button("🗑️ Delete Invoice", key="detail_delete"):
                result = api(f"/api/invoices/{inv_id}", method="DELETE")
                if result and result.get("ok"):
                    st.success("Invoice deleted!")
                    del st.session_state["view_invoice_id"]
                    st.rerun()

            if action_cols[2].button("❌ Close", key="detail_close"):
                del st.session_state["view_invoice_id"]
                st.rerun()


# ===========================================================================
# 📤 UPLOAD & PROCESS
# ===========================================================================
elif page == "📤 Upload & Process":
    st.markdown("# 📤 Upload & Process")
    st.caption("Upload invoice files and trigger the processing pipeline")
    st.divider()

    # File Upload
    st.markdown("### 📁 Upload Invoice Files")
    uploaded_files = st.file_uploader(
        "Drop invoice files here",
        type=["txt", "pdf", "png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp", "md"],
        accept_multiple_files=True,
        help="Supported: PDF, images (PNG/JPG/TIFF/BMP/WebP), text files",
    )

    upload_col1, upload_col2 = st.columns(2)
    with upload_col1:
        process_after_upload = st.checkbox("Process immediately after upload", value=True)
    with upload_col2:
        pass

    if uploaded_files:
        if st.button("📤 Upload Files", type="primary", use_container_width=True):
            progress = st.progress(0)
            success_count = 0
            fail_count = 0

            for i, file in enumerate(uploaded_files):
                progress.progress((i + 1) / len(uploaded_files))
                try:
                    files_payload = {"file": (file.name, file.getvalue(), file.type or "application/octet-stream")}
                    data_payload = {"process": "true" if (process_after_upload and i == len(uploaded_files) - 1) else "false"}
                    resp = requests.post(
                        f"{API_BASE}/api/upload",
                        files=files_payload,
                        data=data_payload,
                        timeout=30,
                    )
                    if resp.status_code == 200:
                        success_count += 1
                    else:
                        fail_count += 1
                        st.warning(f"Failed to upload {file.name}: {resp.text}")
                except Exception as e:
                    fail_count += 1
                    st.error(f"Error uploading {file.name}: {e}")

            progress.empty()
            if success_count:
                st.success(f"✅ Successfully uploaded {success_count} file(s)!")
            if fail_count:
                st.error(f"❌ Failed to upload {fail_count} file(s)")

    st.divider()

    # Process Pipeline
    st.markdown("### ⚙️ Run Processing Pipeline")
    st.markdown(
        "Trigger the pipeline to process all files currently in the inbox. "
        "The pipeline will: **fetch → extract (LLM) → guardrails → store/quarantine**"
    )

    proc_col1, proc_col2 = st.columns(2)
    with proc_col1:
        if st.button("▶️ Process Inbox", type="primary", use_container_width=True):
            result = api("/api/process", method="POST")
            if result:
                if result.get("ok"):
                    st.success("🚀 Processing started! Check the Dashboard for results.")
                    st.balloons()
                else:
                    st.warning(result.get("message", "Processing may already be running."))
            else:
                st.error("Failed to start processing. Is the backend running?")

    with proc_col2:
        # Check if processing
        if health and health.get("processing"):
            st.info("⏳ Pipeline is currently processing...")
            with st.spinner("Waiting for processing to complete..."):
                pass

    st.divider()

    # Pipeline status
    st.markdown("### 📊 Current Stats")
    stats = api("/api/stats")
    if stats:
        stat_cols = st.columns(4)
        stat_cols[0].metric("Stored", stats.get("stored", 0))
        stat_cols[1].metric("Needs Review", stats.get("needs_review", 0))
        stat_cols[2].metric("Quarantined", stats.get("quarantined", 0))
        stat_cols[3].metric("Total Value", format_inr(stats.get("total_value", 0)))

        if stats.get("processing"):
            st.info("⏳ Pipeline is currently running...")


# ===========================================================================
# 🚫 QUARANTINE
# ===========================================================================
elif page == "🚫 Quarantine":
    st.markdown("# 🚫 Quarantine")
    st.caption("Files that failed guardrail checks and were quarantined")
    st.divider()

    quarantine = api("/api/quarantine")
    if quarantine is None:
        st.error("Could not load quarantine data.")
        st.stop()

    if not quarantine:
        st.success("✅ No quarantined files! All invoices passed guardrail checks.")
        st.stop()

    st.markdown(f"**{len(quarantine)} file(s) quarantined**")

    for q in quarantine:
        with st.expander(f"🚫 {q.get('file', 'Unknown')}",  expanded=False):
            # Violations
            violations = q.get("violations")
            if violations:
                st.error(f"**Violations:** {violations}")
            else:
                st.warning("Reason unknown")

            # Extracted data (if available)
            extracted = q.get("extracted")
            if extracted:
                st.markdown("#### Extracted Data (before quarantine)")
                ext_cols = st.columns(3)
                ext_cols[0].markdown(f"**Vendor:** {extracted.get('vendor_name', '—')}")
                ext_cols[1].markdown(f"**Invoice #:** {extracted.get('invoice_number', '—')}")
                ext_cols[2].markdown(f"**Bill Amount:** {format_inr(extracted.get('bill_amount'))}")

                # Show all extracted fields
                with st.expander("Full extracted data"):
                    st.json(extracted)


# ===========================================================================
# 📜 ACTIVITY LOG
# ===========================================================================
elif page == "📜 Activity Log":
    st.markdown("# 📜 Activity Log")
    st.caption("Audit trail of all pipeline processing events")
    st.divider()

    limit = st.slider("Number of entries", 10, 100, 50)
    logs = api(f"/api/logs?limit={limit}")

    if logs is None:
        st.error("Could not load activity logs.")
        st.stop()

    if not logs:
        st.info("No activity logs yet. Process some invoices to see logs here!")
        st.stop()

    # Summary counts
    outcomes = {}
    for log in logs:
        outcome = log.get("outcome", "unknown")
        outcomes[outcome] = outcomes.get(outcome, 0) + 1

    summary_cols = st.columns(len(outcomes))
    for i, (outcome, count) in enumerate(outcomes.items()):
        icon = "✅" if outcome == "success" else "❌" if outcome == "error" else "⚠️" if outcome == "quarantined" else "⏭️"
        summary_cols[i].metric(f"{icon} {outcome.title()}", count)

    st.divider()

    # Log table
    df_logs = pd.DataFrame(logs)
    if not df_logs.empty:
        # Add visual indicator
        def outcome_icon(outcome):
            return {
                "success": "✅",
                "error": "❌",
                "quarantined": "🚫",
                "skipped": "⏭️",
            }.get(outcome, "❓")

        df_logs[""] = df_logs["outcome"].apply(outcome_icon)
        display_cols = ["", "stage", "source_file", "outcome", "detail", "created_at"]
        available = [c for c in display_cols if c in df_logs.columns]
        df_display = df_logs[available].copy()
        if "created_at" in df_display.columns:
            df_display["created_at"] = df_display["created_at"].apply(
                lambda x: str(x)[:19].replace("T", " ") if x else "—"
            )
        if "detail" in df_display.columns:
            df_display["detail"] = df_display["detail"].apply(
                lambda x: str(x)[:120] if x else "—"
            )

        st.dataframe(
            df_display.rename(columns={
                "": "Status",
                "stage": "Stage",
                "source_file": "File",
                "outcome": "Outcome",
                "detail": "Detail",
                "created_at": "Timestamp",
            }),
            use_container_width=True,
            hide_index=True,
        )


# ===========================================================================
# ⚡ PERFORMANCE
# ===========================================================================
elif page == "⚡ Performance":
    st.markdown("# ⚡ Performance Metrics")
    st.caption("API response times and system performance")
    st.divider()

    perf = api("/api/performance")

    if perf is None:
        st.error("Could not load performance data.")
        st.stop()

    # KPI Cards
    kpi_cols = st.columns(4)
    kpi_cols[0].metric("Total Requests", perf.get("total_requests", 0))
    avg_ms = perf.get("avg_response_time_ms", 0)
    kpi_cols[1].metric("Avg Response", f"{avg_ms:.1f}ms")
    p95_ms = perf.get("p95_response_time_ms", 0)
    kpi_cols[2].metric("P95 Response", f"{p95_ms:.1f}ms")
    uptime = perf.get("uptime_seconds", 0)
    if uptime > 3600:
        kpi_cols[3].metric("Uptime", f"{uptime/3600:.1f}h")
    elif uptime > 60:
        kpi_cols[3].metric("Uptime", f"{uptime/60:.1f}m")
    else:
        kpi_cols[3].metric("Uptime", f"{uptime:.0f}s")

    st.divider()

    # Endpoint breakdown
    st.markdown("### 📊 Endpoint Breakdown")
    endpoints = perf.get("endpoints", [])
    if endpoints:
        df_ep = pd.DataFrame(endpoints)
        st.dataframe(
            df_ep.rename(columns={
                "endpoint": "Endpoint",
                "requests": "Requests",
                "avg_ms": "Avg (ms)",
                "min_ms": "Min (ms)",
                "max_ms": "Max (ms)",
                "p95_ms": "P95 (ms)",
            }),
            use_container_width=True,
            hide_index=True,
        )

        # Chart: avg response time per endpoint
        if len(df_ep) > 1:
            st.bar_chart(
                df_ep.set_index("endpoint")["avg_ms"],
                use_container_width=True,
            )
    else:
        st.info("No endpoint data yet. Make some API calls first!")

    st.divider()

    # Recent requests
    st.markdown("### 🕒 Recent Requests")
    recent = perf.get("recent", [])
    if recent:
        df_recent = pd.DataFrame(recent)
        if "timestamp" in df_recent.columns:
            df_recent["time"] = df_recent["timestamp"].apply(
                lambda x: datetime.fromtimestamp(x).strftime("%H:%M:%S") if x else "—"
            )
        display_cols = ["time", "method", "path", "status", "time_ms"]
        available = [c for c in display_cols if c in df_recent.columns]
        st.dataframe(
            df_recent[available].rename(columns={
                "time": "Time",
                "method": "Method",
                "path": "Path",
                "status": "HTTP Status",
                "time_ms": "Response (ms)",
            }),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No recent requests recorded yet.")

    # Min/Max stats
    st.divider()
    extra_cols = st.columns(2)
    extra_cols[0].metric("Min Response", f"{perf.get('min_response_time_ms', 0):.2f}ms")
    extra_cols[1].metric("Max Response", f"{perf.get('max_response_time_ms', 0):.2f}ms")
