import streamlit as st
import pandas as pd
import json
import os
import glob
import random
from pydrive2.auth import ServiceAccountCredentials
from pydrive2.drive import GoogleDrive

# ========================
# === Google Drive Utils ===
# ========================

def get_drive():
    """Authenticate and return GoogleDrive client"""
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        st.secrets["google_drive"],
        scopes=["https://www.googleapis.com/auth/drive.file"]
    )
    return GoogleDrive(creds)

def upload_to_drive(local_path, drive_folder_id):
    """Upload file to Google Drive folder"""
    drive = get_drive()
    file_name = os.path.basename(local_path)
    gfile = drive.CreateFile({"title": file_name, "parents": [{"id": drive_folder_id}]})
    gfile.SetContentFile(local_path)
    gfile.Upload()
    return gfile["id"]

# ========================
# === Login System ===
# ========================

USERS = st.secrets["credentials"]

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

# ========================
# === Navigation ===
# ========================

st.sidebar.success(f"Logged in as {st.session_state.username}")
pages = ["Annotate", "Review Results"]
page = st.sidebar.radio("📂 Navigation", pages)

# ========================
# === Load Data ===
# ========================

# Load both CSVs
data1 = pd.read_csv("selected_samples.csv")
data2 = pd.read_csv("selected_samples00.csv")

# Merge them
data1["source_file"] = "selected_samples.csv"
data2["source_file"] = "selected_samples00.csv"
all_data = pd.concat([data1, data2], ignore_index=True)

reports = all_data['reports_preds'].tolist()
image_url = all_data['paths'].tolist()
study_ids = all_data['study_id'].tolist()
sources = all_data['source_file'].tolist()

symptoms = [
    'Atelectasis','Cardiomegaly','Consolidation','Edema',
    'Enlarged Cardiomediastinum','Fracture','Lung Lesion',
    'Lung Opacity','No Finding','Pleural Effusion','Pleural Other',
    'Pneumonia','Pneumothorax','Support Devices'
]

# ========================
# === Annotate Page ===
# ========================

if page == "Annotate":
    st.sidebar.title("Report Navigator")

    # Randomize reports per session
    if "shuffled_indices" not in st.session_state:
        st.session_state.shuffled_indices = random.sample(range(len(all_data)), len(all_data))

    # Which report to show
    report_number = st.sidebar.number_input("Report #", 1, len(st.session_state.shuffled_indices), 1)
    report_index = st.session_state.shuffled_indices[report_number - 1]

    # Load selected report
    report = reports[report_index]
    study_id = study_ids[report_index]
    source_file = sources[report_index]

    st.header(f"Patient Report #{report_number} (Study ID: {study_id})")
    st.text_area("Report Text", report, height=200)
    st.image(image_url[report_index], caption=f"Chest X-ray (Study ID {study_id})", use_container_width=True)

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
            key=f"{symptom}_{report_number}"
        )
        scores[symptom] = selected

    # Save button
    if st.button("Save Evaluation"):
        result = {
            "report_number": report_number,
            "report_text": report,
            "study_id": study_id,
            "symptom_scores": scores,
            "annotator": st.session_state.username,
            "source_file": source_file
        }

        # Save locally
        os.makedirs("annotations", exist_ok=True)
        filename = f"annotations/report_{study_id}_{st.session_state.username}.json"
        with open(filename, "w") as f:
            json.dump(result, f, indent=2)

        # Upload to Google Drive
        DRIVE_FOLDER_ID = "YOUR_GOOGLE_DRIVE_FOLDER_ID"  # Replace with your Drive folder ID
        try:
            file_id = upload_to_drive(filename, DRIVE_FOLDER_ID)
            st.success(f"✅ Evaluation saved locally & uploaded to Google Drive (file ID: {file_id})")
        except Exception as e:
            st.error(f"⚠️ Upload failed: {e}")

# ========================
# === Review Page ===
# ========================

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
        st.info("No annotations found yet.")
