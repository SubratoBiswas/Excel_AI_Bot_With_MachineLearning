import streamlit as st
from dotenv import load_dotenv

from excel_store import ExcelStore
from llm_agent import generate_sql
from feedback_store import FeedbackStore

load_dotenv()

st.set_page_config(page_title="Excel Analysis Bot", layout="wide")
st.title("📊 Excel Analysis Bot (multi-file)")

# --- Session state init ---
if "store" not in st.session_state:
    st.session_state.store = ExcelStore()

if "messages" not in st.session_state:
    st.session_state.messages = []

if "feedback_db" not in st.session_state:
    st.session_state.feedback_db = FeedbackStore()

# Track latest interaction for feedback UI
if "last_record_id" not in st.session_state:
    st.session_state.last_record_id = None
if "last_sql" not in st.session_state:
    st.session_state.last_sql = None
if "last_question" not in st.session_state:
    st.session_state.last_question = None


# --- Sidebar: Upload + Catalog ---
with st.sidebar:
    st.header("Upload Excel files")
    uploads = st.file_uploader(
        "Upload one or more .xlsx files",
        type=["xlsx", "xls"],
        accept_multiple_files=True
    )

    if uploads:
        for f in uploads:
            st.session_state.store.add_excel_file(f.name, f.read())
        st.success(f"Loaded {len(uploads)} file(s).")

    st.subheader("Loaded tables")
    catalog = st.session_state.store.catalog()
    st.write(f"{len(catalog)} table(s) available.")
    for t, meta in catalog.items():
        st.caption(f"**{t}** — {meta['file']} / {meta['sheet']} — {meta['rows']} rows")

st.divider()

# --- Chat History ---
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

question = st.chat_input("Ask a question about your uploaded Excel files…")

# --- Handle new question ---
if question:
    st.session_state.messages.append({"role": "user", "content": question})
    st.session_state.last_question = question

    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        catalog = st.session_state.store.catalog()

        if not catalog:
            st.warning("Upload Excel files first.")
        else:
            feedback_db = st.session_state.feedback_db

            # Get signature for current schema & pull prior good examples
            catalog_sig = st.session_state.store.catalog_signature()
            examples = feedback_db.top_examples(catalog_sig, limit=20)

            # Generate plan using examples
            plan = generate_sql(question, catalog, examples)
            sql = (plan.get("sql") or "").strip().rstrip(";")
            explanation = plan.get("explanation") or ""

            # Store interaction for future training
            record_id = feedback_db.add_record(question, catalog_sig, sql)
            st.session_state.last_record_id = record_id
            st.session_state.last_sql = sql

            # Display
            st.markdown("### Answer")
            st.markdown(explanation)

            st.markdown("### SQL used")
            st.code(sql, language="sql")

            try:
                df = st.session_state.store.run_sql(sql)
                st.markdown("### Results")
                st.dataframe(df, use_container_width=True)
            except Exception as e:
                st.error(f"SQL execution failed: {e}")

            # Save to chat history
            st.session_state.messages.append(
                {"role": "assistant", "content": f"{explanation}\n\nSQL:\n{sql}"}
            )

st.divider()

# --- Feedback UI (only if there is a last interaction) ---
if st.session_state.last_record_id is not None:
    feedback_db = st.session_state.feedback_db

    st.markdown("## Feedback (helps me learn)")

    st.markdown("### Was this correct?")
    col1, col2 = st.columns(2)

    with col1:
        if st.button("👍 Yes", key="fb_yes"):
            feedback_db.add_feedback(st.session_state.last_record_id, rating=1)
            st.success("Saved ✅ I’ll reuse this pattern next time for similar questions.")

    with col2:
        if st.button("👎 No", key="fb_no"):
            feedback_db.add_feedback(st.session_state.last_record_id, rating=-1)
            st.info("Got it. If you paste corrected SQL below, I’ll learn faster.")

    st.markdown("### If it can be improved, paste a corrected SQL (optional)")
    corrected = st.text_area("Corrected SQL", height=150, key="fb_corrected_sql")

    if st.button("Submit improvement", key="fb_submit"):
        rid = st.session_state.last_record_id
        corrected_sql = corrected.strip().rstrip(";") if corrected and corrected.strip() else None

        feedback_db.add_feedback(
            rid,
            rating=-1,
            feedback_text="User provided corrected SQL",
            corrected_sql=corrected_sql
        )
        st.success("Saved ✅ I’ll use this correction as a training example next time.")
else:
    st.caption("Ask a question to enable feedback & training.")
