import streamlit as st
import requests
import os

# Configuration
BACKEND_URL = "http://localhost:8000/api/v1"

st.set_page_config(page_title="Universal Knowledge Platform", layout="wide")

st.title("🧠 Cognitive Knowledge Platform")
st.markdown("### Universal Intelligence over Heterogeneous Data")

# Sidebar for Ingestion
with st.sidebar:
    st.header("Data Ingestion")
    uploaded_file = st.file_uploader("Upload Document (PDF, MD, TXT, CSV)", type=['pdf', 'txt', 'md', 'csv'])
    
    if uploaded_file:
        if st.button("Upload & Ingest"):
            with st.spinner("Uploading..."):
                files = {"file": (uploaded_file.name, uploaded_file, uploaded_file.type)}
                try:
                    # Upload
                    upload_res = requests.post(f"{BACKEND_URL}/upload", files=files)
                    if upload_res.status_code == 200:
                        st.success("File uploaded successfully!")
                        # Trigger Ingestion
                        with st.spinner("Processing & Ingesting..."):
                            ingest_res = requests.post(f"{BACKEND_URL}/ingest")
                            if ingest_res.status_code == 200:
                                st.success("Ingestion complete!")
                            else:
                                st.error(f"Ingestion failed: {ingest_res.text}")
                    else:
                        st.error(f"Upload failed: {upload_res.text}")
                except Exception as e:
                    st.error(f"Connection error: {e}")

    # Standalone Ingestion Button (for Synthetic/Existing Data)
    if st.button("Run Ingestion (Existing Data)"):
        with st.spinner("Ingesting data from server disk..."):
            try:
                ingest_res = requests.post(f"{BACKEND_URL}/ingest")
                if ingest_res.status_code == 200:
                    st.success("Ingestion complete!")
                else:
                    st.error(f"Ingestion failed: {ingest_res.text}")
            except Exception as e:
                 st.error(f"Connection error: {e}")

    st.markdown("---")
    st.markdown("### System Status")
    if st.button("Check Health"):
        try:
            res = requests.get("http://localhost:8000/health")
            st.write(res.json())
        except:
            st.error("Backend seems down.")

# Main Chat Interface
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ask a question about your knowledge base..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                response = requests.post(f"{BACKEND_URL}/chat", json={"query": prompt})
                if response.status_code == 200:
                    data = response.json()
                    answer = data.get("response", "No answer.")
                    tools = data.get("tool_usage", [])
                    
                    st.markdown(answer)
                    if tools:
                        with st.expander("Tools Used"):
                            for t in tools:
                                st.write(f"- {t}")
                                
                    st.session_state.messages.append({"role": "assistant", "content": answer})
                else:
                    st.error(f"Error: {response.text}")
            except Exception as e:
                st.error(f"Connection error: {e}")
