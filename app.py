import streamlit as st
import pandas as pd
import json
import os
import glob

# === Define users (you can store in secrets.toml for safety) ===
USERS = st.secrets["credentials"]

# === Login check ===
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

def login():
    st.title("🔐 Login Required")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if username in USERS and USERS[username] == password:
            st.session_state.logged_in = True
            st.session_state.username = username
            st.success("✅ Logged in successfully!")
            st.rerun()
        else:
            st.error("❌ Invalid username or password")

if not st.session_state.logged_in:
    login()
    st.stop()

# === Main app (only shows if logged in) ===
st.sidebar.success(f"Logged in as {st.session_state.username}")

# Load your data
data = pd.read_csv('selected_samples.csv')
reports = data['reports_preds'].tolist()
image_url = data['paths'].tolist()

symptoms = [
    'Atelectasis','Cardiomegaly','Consolidation','Edema',
    'Enlarged Cardiomediastinum','Fracture','Lung Lesion',
    'Lung Opacity','No Finding','Pleural Effusion','Pleural Other',
    'Pneumonia','Pneumothorax','Support Devices'
]

# Sidebar
st.sidebar.title("Report Navigator")
report_index = st.sidebar.selectbox("Select Report", range(1,31))
report = reports[report_index-1]

st.header(f"Patient Report #{report_index}")
st.text_area("Report Text", report, height=200)

# Image
st.image(image_url[report_index-1], caption=f"Chest X-ray #{report_index}", use_container_width=True)

# Symptom scoring
st.subheader("Symptom Evaluation")
st.write(
    "Please review the report and chest X-ray, then assign a score for each listed symptom. "
    "Use the following coding scheme:\n\n"
    "- **0** = Assured absence\n"
    "- **1** = Assured presence\n"
    "- **2** = Ambiguous / uncertain"
)
scores = {}
for symptom in symptoms:
    selected = st.radio(
        label=symptom,
        options=[0, 1, 2],
        horizontal=True,
        key=f"{symptom}_{report_index}"
    )
    scores[symptom] = selected

# === Qualitative Feedback Section ===
st.subheader("Qualitative Feedback")

clarity = st.selectbox(
    "How clear and clinically useful did you find this report?",
    ["Very clear", "Somewhat clear", "Neutral", "Somewhat unclear", "Very unclear"],
    key=f"clarity_{report_index}"
)

difficulty = st.text_area(
    "Which symptoms were most difficult to assess, and why?",
    key=f"difficulty_{report_index}"
)

confidence = st.selectbox(
    "How confident did you feel in your scoring decisions?",
    ["Very confident", "Somewhat confident", "Neutral", "Somewhat unsure", "Very unsure"],
    key=f"confidence_{report_index}"
)

improvements = st.text_area(
    "What improvements would make the evaluation process faster or easier?",
    key=f"improvements_{report_index}"
)

st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Annotate", "Review Results"])

if page == "Annotate":
    # 👉 put your survey code here
    pass

elif page == "Review Results":
    st.header("📊 Review & Download Survey Results")

    files = glob.glob("annotations/*.json")
    if files:
        all_records = []
        for f in files:
            with open(f) as infile:
                all_records.append(json.load(infile))
        df = pd.json_normalize(all_records)

        st.dataframe(df)

        st.download_button(
            "⬇️ Download all annotations as CSV",
            df.to_csv(index=False).encode("utf-8"),
            file_name="survey_results.csv",
            mime="text/csv"
        )
    else:
        st.info("No annotations found.")
