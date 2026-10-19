import datetime
import urllib.parse
import requests
import streamlit as st

st.set_page_config(
    page_title="CampusMate",
    page_icon="🎓",
    layout="wide",
)

API_URL = "http://127.0.0.1:8000"

# ── Dark dashboard styling ────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .stApp {
        background-color: #000000;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] > div {
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        background-color: #0d0f17;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5);
    }
    div[data-testid="stMetric"] {
        background-color: #0d0f17;
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 14px 18px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🎓 CampusMate")
st.caption("Your University Life, Organized • Smart Deadline Reminders")

# ── Session state init ────────────────────────────────────────────────────────
if "upload_result" not in st.session_state:
    st.session_state["upload_result"] = None   # dict returned by POST /upload
if "uploader_key" not in st.session_state:
    st.session_state["uploader_key"] = 0       # increment to reset the file_uploader widget


# ── Helper: build ChatGPT URL ─────────────────────────────────────────────────
def _chatgpt_url(assignment: dict) -> str:
    """
    Build a chatgpt.com URL with a prefilled prompt.
    The ?q= parameter is supported by chat.openai.com/chat and chatgpt.com.

    Note: ChatGPT does NOT support automatic file attachment via URL.
    If the assignment has an uploaded document, the prompt includes the
    extracted text so ChatGPT can still reason about it.
    """
    title       = assignment.get("title", "")
    subject     = assignment.get("subject", "")
    deadline    = assignment.get("deadline", "")
    priority    = assignment.get("priority", "Medium")
    ext_text    = (assignment.get("extracted_text") or "").strip()
    attach_name = assignment.get("attachment_original_name") or ""

    prompt = (
        f"Help me plan and complete my university assignment:\n\n"
        f"• Title: {title}\n"
        f"• Subject: {subject}\n"
        f"• Due Date: {deadline}\n"
        f"• Priority: {priority}\n"
    )
    if attach_name:
        prompt += f"• Source document: {attach_name}\n"
    if ext_text:
        prompt += f"\n--- Extracted document text ---\n{ext_text[:1500]}\n--- End of document text ---\n"
    prompt += (
        "\nPlease explain the core concepts, identify common pitfalls, "
        "and provide a step-by-step strategy to complete this assignment."
    )
    return f"https://chatgpt.com/?q={urllib.parse.quote(prompt)}"


try:
    response = requests.get(f"{API_URL}/assignments", timeout=5)
    if response.status_code != 200:
        st.error(f"Backend error: Received status code {response.status_code}")
        st.stop()

    assignments = response.json()

    # ── Metric counts ─────────────────────────────────────────────────────────
    total_count     = len(assignments)
    completed_count = sum(1 for a in assignments if a.get("is_completed"))
    pending_count   = total_count - completed_count
    overdue_count   = sum(1 for a in assignments if a.get("urgency") == "Overdue")
    due_today_count = sum(1 for a in assignments if a.get("urgency") == "Due Today")
    due_soon_count  = sum(1 for a in assignments if a.get("urgency") == "Due Soon")
    urgent_total    = overdue_count + due_today_count + due_soon_count

    # ── Top metrics row ───────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total assignments", total_count)
    col2.metric("Pending tasks", pending_count)
    col3.metric(
        "Urgent / Due soon",
        urgent_total,
        delta=f"-{overdue_count} overdue" if overdue_count > 0 else (
            f"{due_today_count} due today" if due_today_count > 0 else None
        ),
        delta_color="inverse" if overdue_count > 0 else "normal",
    )
    col4.metric("Completed tasks", completed_count)

    # ── Progress bar ──────────────────────────────────────────────────────────
    pct = (completed_count / total_count) if total_count > 0 else 0.0
    st.progress(pct, text=f"Progress: {int(pct * 100)}% completed ({completed_count}/{total_count} tasks)")

    # ── Alert banner ──────────────────────────────────────────────────────────
    if overdue_count > 0:
        st.error(
            f"You have **{overdue_count} overdue assignment(s)** requiring immediate attention!",
            icon=":material/warning:",
        )
    elif due_today_count > 0:
        st.warning(
            f"You have **{due_today_count} assignment(s) due today**! Stay focused and submit on time.",
            icon=":material/alarm:",
        )
    elif due_soon_count > 0:
        st.info(
            f"You have **{due_soon_count} assignment(s) due within the next 3 days**.",
            icon=":material/info:",
        )

    st.divider()

    # ── Upcoming deadlines spotlight ──────────────────────────────────────────
    st.subheader("⏰ Upcoming deadlines")
    st.caption("Tasks due within the next 3 days or requiring urgent action")

    urgent_assignments = [
        a for a in assignments
        if not a.get("is_completed") and a.get("urgency") in ("Overdue", "Due Today", "Due Soon")
    ]

    if not urgent_assignments:
        st.success(
            "🎉 You're all caught up! No urgent deadlines in the next 3 days.",
            icon=":material/check_circle:",
        )
    else:
        cols = st.columns(min(len(urgent_assignments), 3))
        for idx, item in enumerate(urgent_assignments):
            col = cols[idx % len(cols)]
            with col:
                with st.container(border=True):
                    urgency_val = item.get("urgency")
                    days = item.get("days_remaining", 0)

                    if urgency_val == "Overdue":
                        st.markdown(f":red[**🚨 Overdue ({abs(days)}d ago)**]")
                    elif urgency_val == "Due Today":
                        st.markdown(":red[**⚠️ Due today**]")
                    elif days == 1:
                        st.markdown(":orange[**⏰ Due tomorrow**]")
                    else:
                        st.markdown(f":orange[**⏰ Due in {days} days**]")

                    st.markdown(f"**{item['title']}**")
                    st.caption(f"Subject: {item['subject']} | Date: `{item['deadline']}`")

                    if st.button(
                        "Mark done",
                        icon=":material/check:",
                        key=f"urgent_done_{item['id']}",
                        width="stretch",
                    ):
                        requests.patch(f"{API_URL}/assignments/{item['id']}/toggle", timeout=5)
                        st.rerun()

    st.divider()

    # ── Upload a Document ─────────────────────────────────────────────────────
    st.subheader(":material/upload_file: Upload a document")
    st.caption(
        "Upload a PDF, Word document, or image. CampusMate will extract the text "
        "and pre-fill the assignment form for you."
    )

    with st.container(border=True):
        uploaded_file = st.file_uploader(
            "Choose a file",
            type=["pdf", "docx", "png", "jpg", "jpeg"],
            label_visibility="collapsed",
            help="Supported: PDF, DOCX, PNG, JPG/JPEG · Max 10 MB",
            key=f"doc_uploader_{st.session_state['uploader_key']}",
        )

        # If user clears the uploader, reset session state
        if uploaded_file is None:
            st.session_state["upload_result"] = None

        if uploaded_file is not None:
            file_bytes = uploaded_file.read()
            size_kb = len(file_bytes) / 1024

            col_info1, col_info2 = st.columns(2)
            col_info1.markdown(f"**File:** `{uploaded_file.name}`")
            col_info2.markdown(f"**Size:** `{size_kb:.1f} KB`")

            # Only call the API once per file (cache result in session state)
            if st.session_state["upload_result"] is None:
                with st.spinner("Extracting text and detecting assignment details…"):
                    try:
                        res_upload = requests.post(
                            f"{API_URL}/upload",
                            files={"file": (uploaded_file.name, file_bytes, uploaded_file.type)},
                            timeout=30,
                        )
                        if res_upload.status_code == 200:
                            st.session_state["upload_result"] = res_upload.json()
                        else:
                            try:
                                err = res_upload.json().get("detail", res_upload.text)
                            except Exception:
                                err = res_upload.text
                            st.error(f"Upload failed ({res_upload.status_code}): {err}", icon=":material/error:")
                    except requests.exceptions.RequestException as exc:
                        st.error(f"Network error while uploading: {exc}")

            upload_data = st.session_state.get("upload_result")
            if upload_data:
                parsed        = upload_data.get("parsed", {})
                extracted_txt = upload_data.get("extracted_text", "")
                stored_name   = upload_data.get("stored_name", "")
                mime_type     = upload_data.get("mime_type", "application/octet-stream")

                st.success(
                    "Text extracted successfully! Review the details below and click **Save assignment** to confirm.",
                    icon=":material/check_circle:",
                )

                with st.expander(":material/article: View extracted text", expanded=False):
                    st.text(extracted_txt if extracted_txt.strip() else "(no text detected)")

                st.markdown("#### Confirm assignment details")
                with st.form("upload_confirm_form", clear_on_submit=True):
                    up_col1, up_col2 = st.columns(2)
                    with up_col1:
                        up_title = st.text_input(
                            "Assignment title",
                            value=parsed.get("title", ""),
                            placeholder="Enter assignment title",
                        )
                    with up_col2:
                        up_subject = st.text_input(
                            "Subject / Course",
                            value=parsed.get("subject", ""),
                            placeholder="e.g., Computer Science",
                        )

                    up_col3, up_col4 = st.columns(2)
                    with up_col3:
                        raw_deadline = parsed.get("deadline", "")
                        try:
                            pre_deadline = datetime.date.fromisoformat(raw_deadline) if raw_deadline else datetime.date.today()
                        except ValueError:
                            pre_deadline = datetime.date.today()
                        deadline_label = "Deadline" + (" *(none detected — set manually)*" if not raw_deadline else "")
                        up_deadline = st.date_input(
                            deadline_label,
                            value=pre_deadline,
                            min_value=datetime.date.today(),
                        )
                    with up_col4:
                        priority_opts = ["Low", "Medium", "High"]
                        pre_priority  = parsed.get("priority", "Medium")
                        up_priority   = st.selectbox(
                            "Priority",
                            priority_opts,
                            index=priority_opts.index(pre_priority) if pre_priority in priority_opts else 1,
                        )

                    save_submitted = st.form_submit_button(":material/save: Save assignment", width="stretch")

                    if save_submitted:
                        if up_title.strip() and up_subject.strip():
                            payload = {
                                "title":    up_title.strip(),
                                "subject":  up_subject.strip(),
                                "deadline": str(up_deadline),
                                "priority": up_priority,
                                # Attachment metadata saved with the assignment
                                "attachment_original_name": uploaded_file.name,
                                "attachment_stored_name":   stored_name,
                                "attachment_mime_type":     mime_type,
                                "extracted_text":           extracted_txt[:3000],
                            }
                            try:
                                save_res = requests.post(f"{API_URL}/assignments", json=payload, timeout=5)
                                if save_res.status_code in (200, 201):
                                    # Reset upload state and force the file_uploader to clear
                                    st.session_state["upload_result"] = None
                                    st.session_state["uploader_key"] += 1
                                    st.rerun()
                                else:
                                    st.error(f"Could not save: {save_res.text}")
                            except requests.exceptions.RequestException as exc:
                                st.error(f"Network error: {exc}")
                        else:
                            st.error("Please fill in at least the title and subject before saving.")

    st.divider()

    # ── Add an Assignment (manual) ────────────────────────────────────────────
    st.subheader("Add an assignment")
    with st.form("assignment_form", clear_on_submit=True):
        col_t, col_s = st.columns(2)
        with col_t:
            title   = st.text_input("Assignment title", placeholder="e.g., Operating Systems Lab 1")
        with col_s:
            subject = st.text_input("Subject", placeholder="e.g., Computer Science")

        col_d, col_p = st.columns(2)
        with col_d:
            deadline = st.date_input("Deadline", min_value=datetime.date.today())
        with col_p:
            priority = st.selectbox("Priority", ["Low", "Medium", "High"], index=1)

        submitted = st.form_submit_button("Add assignment", width="stretch")

        if submitted:
            if title.strip() and subject.strip():
                data = {
                    "title":    title.strip(),
                    "subject":  subject.strip(),
                    "deadline": str(deadline),
                    "priority": priority,
                }
                try:
                    res = requests.post(f"{API_URL}/assignments", json=data, timeout=5)
                    if res.status_code in (200, 201):
                        st.success("Assignment added successfully!")
                        st.rerun()
                    else:
                        st.error(f"Could not add assignment: {res.text}")
                except requests.exceptions.RequestException as e:
                    st.error(f"Network error: {e}")
            else:
                st.error("Please enter both assignment title and subject.")

    st.divider()

    # ── All Assignments with Urgency Badges & Filters ─────────────────────────
    st.subheader("All assignments")

    view_filter = st.segmented_control(
        "Filter assignments",
        options=["All", "Urgent / Due soon", "Pending", "Completed"],
        default="All",
        label_visibility="collapsed",
    )

    filtered_assignments = assignments
    if view_filter == "Pending":
        filtered_assignments = [a for a in assignments if not a.get("is_completed")]
    elif view_filter == "Completed":
        filtered_assignments = [a for a in assignments if a.get("is_completed")]
    elif view_filter == "Urgent / Due soon":
        filtered_assignments = [
            a for a in assignments
            if not a.get("is_completed") and a.get("urgency") in ("Overdue", "Due Today", "Due Soon")
        ]

    if not filtered_assignments:
        st.info("No assignments to show in this view.")
    else:
        for assignment in filtered_assignments:
            is_done        = assignment.get("is_completed", False)
            assignment_id  = assignment["id"]
            urgency_status = assignment.get("urgency", "Upcoming")
            days_rem       = assignment.get("days_remaining", 0)
            attach_name    = assignment.get("attachment_original_name") or ""
            attach_stored  = assignment.get("attachment_stored_name") or ""

            with st.container(border=True):
                col_left, col_right = st.columns([3, 2], vertical_alignment="center")

                # ── Left column: title + metadata ─────────────────────────────
                with col_left:
                    if is_done:
                        st.markdown(f"### ~~{assignment['title']}~~ :green[✓ Completed]")
                    else:
                        st.markdown(f"### {assignment['title']}")

                    # Urgency badge
                    if is_done:
                        urgency_badge = ":green[**✓ Completed**]"
                    elif urgency_status == "Overdue":
                        urgency_badge = f":red[**🚨 Overdue ({abs(days_rem)}d ago)**]"
                    elif urgency_status == "Due Today":
                        urgency_badge = ":red[**⚠️ Due today**]"
                    elif urgency_status == "Due Soon":
                        urgency_badge = f":orange[**⏰ Due soon ({days_rem}d left)**]"
                    else:
                        urgency_badge = f":blue[**📅 Upcoming ({days_rem}d left)**]"

                    # Priority badge
                    priority_val   = assignment.get("priority", "Medium")
                    priority_color = {"High": "red", "Medium": "orange", "Low": "blue"}.get(priority_val, "gray")

                    st.markdown(
                        f"**Subject:** {assignment['subject']} &nbsp;&nbsp;|&nbsp;&nbsp; "
                        f"**Deadline:** `{assignment['deadline']}` &nbsp;&nbsp;|&nbsp;&nbsp; "
                        f"{urgency_badge} &nbsp;&nbsp;|&nbsp;&nbsp; "
                        f":{priority_color}[**{priority_val} priority**]"
                    )

                    # ── Attachment chip ───────────────────────────────────────
                    if attach_name:
                        # Determine icon by extension
                        ext_lower = attach_name.rsplit(".", 1)[-1].lower() if "." in attach_name else ""
                        file_icon = {
                            "pdf":  "📄",
                            "docx": "📝",
                            "png":  "🖼️",
                            "jpg":  "🖼️",
                            "jpeg": "🖼️",
                        }.get(ext_lower, "📎")

                        att_col1, att_col2 = st.columns([5, 1])
                        with att_col1:
                            st.markdown(
                                f"{file_icon} **Attachment:** "
                                f"[{attach_name}]({API_URL}/attachments/{assignment_id})"
                            )
                        with att_col2:
                            # Remove attachment button
                            if st.button(
                                "",
                                icon=":material/link_off:",
                                key=f"rm_attach_{assignment_id}",
                                help="Remove attachment",
                            ):
                                rm_res = requests.delete(
                                    f"{API_URL}/attachments/{assignment_id}", timeout=5
                                )
                                if rm_res.status_code == 200:
                                    st.success("Attachment removed.")
                                    st.rerun()
                                else:
                                    st.error(f"Could not remove: {rm_res.text}")

                # ── Right column: action buttons ──────────────────────────────
                with col_right:
                    # Row 1: Status / Edit / Delete
                    col_b1, col_b2, col_b3 = st.columns(3)

                    with col_b1:
                        toggle_help = "Mark pending" if is_done else "Mark completed"
                        toggle_icon = ":material/undo:" if is_done else ":material/check_circle:"
                        if st.button(
                            "Status",
                            icon=toggle_icon,
                            key=f"toggle_{assignment_id}",
                            help=toggle_help,
                            width="stretch",
                        ):
                            requests.patch(f"{API_URL}/assignments/{assignment_id}/toggle", timeout=5)
                            st.rerun()

                    with col_b2:
                        with st.popover("Edit", icon=":material/edit:"):
                            st.write(f"Edit Assignment #{assignment_id}")
                            with st.form(f"edit_form_{assignment_id}"):
                                new_title   = st.text_input("Title",   value=assignment["title"])
                                new_subject = st.text_input("Subject", value=assignment["subject"])
                                try:
                                    parsed_date = datetime.date.fromisoformat(assignment["deadline"])
                                except (ValueError, TypeError):
                                    parsed_date = datetime.date.today()
                                new_deadline = st.date_input("Deadline", value=parsed_date)
                                priority_options      = ["Low", "Medium", "High"]
                                current_priority_idx  = (
                                    priority_options.index(assignment.get("priority", "Medium"))
                                    if assignment.get("priority") in priority_options else 1
                                )
                                new_priority = st.selectbox("Priority", priority_options, index=current_priority_idx)

                                update_submitted = st.form_submit_button("Save changes", width="stretch")
                                if update_submitted:
                                    update_payload = {
                                        "title":    new_title.strip(),
                                        "subject":  new_subject.strip(),
                                        "deadline": str(new_deadline),
                                        "priority": new_priority,
                                    }
                                    res = requests.put(
                                        f"{API_URL}/assignments/{assignment_id}",
                                        json=update_payload,
                                        timeout=5,
                                    )
                                    if res.status_code == 200:
                                        st.success("Assignment updated!")
                                        st.rerun()
                                    else:
                                        st.error(f"Failed to update: {res.text}")

                    with col_b3:
                        if st.button(
                            "Delete",
                            icon=":material/delete:",
                            key=f"del_{assignment_id}",
                            help="Delete assignment",
                            width="stretch",
                        ):
                            res = requests.delete(f"{API_URL}/assignments/{assignment_id}", timeout=5)
                            if res.status_code == 200:
                                st.success("Assignment deleted!")
                                st.rerun()
                            else:
                                st.error(f"Could not delete: {res.text}")

                    # Row 2: ChatGPT (full-width, single button)
                    # ⚠️ Honest limitation note:
                    # ChatGPT does NOT support automatic file attachment via URL.
                    # The extracted document text is embedded directly in the prompt
                    # so ChatGPT can reason about the content without a separate file.
                    chatgpt_url = _chatgpt_url(assignment)
                    st.link_button(
                        "Ask ChatGPT",
                        chatgpt_url,
                        icon=":material/open_in_new:",
                        width="stretch",
                        help=(
                            "Opens ChatGPT with a prepared prompt containing the assignment details"
                            + (" and extracted document text." if assignment.get("extracted_text") else ".")
                            + "\n\n⚠️ ChatGPT does not support automatic file attachment via URL. "
                            "If you need ChatGPT to read the original file, open ChatGPT, "
                            "then upload the file manually using the attachment button."
                        ),
                    )

                    # If there is an attached file, show a reminder about manual upload
                    if attach_name:
                        st.caption(
                            f":material/info: The extracted text from **{attach_name}** is included in the "
                            "prompt above. To attach the original file, download it first, then upload "
                            "it manually inside ChatGPT."
                        )

except requests.exceptions.RequestException:
    st.error("Cannot connect to the backend. Make sure FastAPI is running on http://127.0.0.1:8000.")