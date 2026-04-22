from __future__ import annotations


import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


import uuid
import asyncio
import streamlit as st

# -------------------------
# Agent imports
# -------------------------
from adapters.adk_agent import AgentRunner
from core.repository import get_repository

# -------------------------
# Streamlit Config
# -------------------------
st.set_page_config(
    page_title="Send Money Agent",
    page_icon="💸",
    layout="centered"
)

st.title("💸 Send Money Agent")
st.caption("Powered by Google ADK (Cloud Run)")

# -------------------------
# Init Agent (once)
# -------------------------
if "runner" not in st.session_state:
    repository = get_repository("memory")
    st.session_state.runner = AgentRunner(repository=repository)

runner = st.session_state.runner

# -------------------------
# Session Init
# -------------------------
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []

if "done" not in st.session_state:
    st.session_state.done = False

# -------------------------
# Sidebar — State Inspector
# -------------------------
with st.sidebar:
    st.header("🔍 Transfer State")

    try:
        state_obj = runner.repository.get(st.session_state.session_id)

        if state_obj:
            state = state_obj.model_dump()
            missing = state_obj.missing_fields()

            st.json(state)

            # Progress bar
            total_fields = 5
            progress = (total_fields - len(missing)) / total_fields
            st.progress(progress)

            if missing:
                st.warning(f"Missing: {', '.join(missing)}")
            else:
                st.success("All fields collected!")

        else:
            st.info("State not available yet.")

    except Exception as e:
        st.info(f"Start a conversation to see state. ({str(e)})")

    st.divider()

    # Reset button
    if st.button("🔄 Start Over", use_container_width=True):
        try:
            runner.reset(st.session_state.session_id)
        except Exception:
            pass

        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.done = False
        st.rerun()

    st.divider()
    st.caption(f"Session: `{st.session_state.session_id[:8]}...`")

# -------------------------
# Chat History
# -------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# -------------------------
# Transfer Complete Banner
# -------------------------
if st.session_state.done:
    st.success("✅ Transfer submitted successfully! Start a new one from the sidebar.")
    st.stop()

# -------------------------
# Chat Input
# -------------------------
if prompt := st.chat_input("Type your message..."):

    # User message
    st.session_state.messages.append({
        "role": "user",
        "content": prompt
    })

    with st.chat_message("user"):
        st.markdown(prompt)

    # Assistant response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                result = asyncio.run(
                    runner.run_async(
                        session_id=st.session_state.session_id,
                        message=prompt
                    )
                )

                reply = result["response"]
                st.session_state.done = result.get("done", False)

            except Exception as e:
                reply = f"⚠️ Unexpected error: {str(e)}"

        st.markdown(reply)

    st.session_state.messages.append({
        "role": "assistant",
        "content": reply
    })

    st.rerun()