import streamlit as st

st.set_page_config(page_title="MP Debug", page_icon="🔧", layout="wide")

st.title("🔧 MP Debug Mode")
st.success("Streamlit container booted successfully!")

# Test loading config
try:
  import requests

  url = "https://raw.githubusercontent.com/jboring33/MP/main/config.json"
  r = requests.get(url, timeout=3)
  if r.status_code == 200:
    st.write("✅ Successfully fetched `config.json` from GitHub:", r.json())
  else:
    st.warning(f"⚠️ GitHub returned status code: {r.status_code}")
except Exception as e:
  st.error(f"❌ Error fetching config: {e}")
