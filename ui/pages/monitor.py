import streamlit as st
import pandas as pd
import json

# -------------------------
# Page config
# -------------------------
st.set_page_config(layout="wide")
st.title("📊 LLM Monitoring Dashboard")

# -------------------------
# Load Logs
# -------------------------
def load_logs():
    data = []
    try:
        with open("/app/logs.json") as f:
            for line in f:
                try:
                    data.append(json.loads(line))
                except:
                    continue
    except:
        pass
    return pd.DataFrame(data)

df = load_logs()

if df.empty:
    st.warning("No data yet")
    st.stop()

# -------------------------
# 🔥 ROBUST DATA CLEANING (NO MORE CRASHES)
# -------------------------

def clean_tools(x):
    # Case 1: correct list
    if isinstance(x, list):
        return [str(t) for t in x]

    # Case 2: dict (bad format)
    if isinstance(x, dict):
        return [str(x.get("tool", ""))]

    # Case 3: string / corrupted
    return []

# Apply cleaning
df["tools_used"] = df.get("tools_used", []).apply(clean_tools)

# Ensure numeric columns
df["latency_ms"] = pd.to_numeric(df.get("latency_ms"), errors="coerce")
df["tokens"] = pd.to_numeric(df.get("tokens"), errors="coerce")
df["cost"] = pd.to_numeric(df.get("cost"), errors="coerce")

# Fill missing safely
df = df.fillna(0)

# Timestamp fix
df["timestamp"] = pd.to_datetime(df.get("timestamp"), errors="coerce")
df = df.sort_values("timestamp")

# Derived features
df["num_tools"] = df["tools_used"].apply(len)

# -------------------------
# KPIs
# -------------------------
col1, col2, col3, col4 = st.columns(4)

col1.metric("Total Calls", len(df))
col2.metric("Avg Latency (ms)", round(df["latency_ms"].mean(), 2))
col3.metric("Total Tokens", int(df["tokens"].sum()))
col4.metric("Total Cost ($)", round(df["cost"].sum(), 4))

# -------------------------
# Transfer Status
# -------------------------
st.subheader("Transfer Status")

if "status" in df.columns:
    status_counts = df["status"].value_counts()
    st.bar_chart(status_counts)
else:
    st.info("No status data available")

# -------------------------
# Latency Over Time
# -------------------------
st.subheader("Latency Over Time")
st.line_chart(df.set_index("timestamp")["latency_ms"])

# -------------------------
# Token Consumption
# -------------------------
st.subheader("Token Consumption")
st.line_chart(df.set_index("timestamp")["tokens"])

# -------------------------
# Cost Over Time
# -------------------------
st.subheader("Cost Over Time")
st.line_chart(df.set_index("timestamp")["cost"])

# -------------------------
# Tool Usage
# -------------------------
st.subheader("Tool Usage")

tools = df["tools_used"].explode().value_counts()
st.bar_chart(tools)

# -------------------------
# Tools per Call
# -------------------------
st.subheader("Tools per Call")

st.metric("Avg Tools / Call", round(df["num_tools"].mean(), 2))
st.line_chart(df.set_index("timestamp")["num_tools"])

# -------------------------
# Raw Data (SAFE)
# -------------------------
with st.expander("Raw Data"):
    df_display = df.copy()
    df_display["tools_used"] = df_display["tools_used"].apply(lambda x: str(x))
    st.dataframe(df_display)
