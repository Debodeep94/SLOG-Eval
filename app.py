import streamlit as st
import pandas as pd
import json
import os
import glob
import random

# === Credentials from secrets.toml ===
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

# === Main navigation ===
st.sidebar.success(f"Logged in as {st.session_state.username}")

if st.session_state.username == "admin":
    pages = ["Annotate", "Review Results"]
else:
    pages = ["Annotate"]

page = st.sidebar.radio("📂 Navigation", pages)

# === Data load ===
def normalize(df):
    """Ensure report column is consistently named 'report'."""
    candidates = [c for c in df.columns if c.lower() not in ["study_id", "paths", "image_path", "source_file"]]
    if not candidates:
        raise ValueError(f"No suitable report column found. Available: {df.columns.tolist()}")
    report_col = candidates[0]
    df = df.rename(columns={report_col: "report"})
    return df

data1 = normalize(pd.read_csv("selected_samples.csv"))
data2 = normalize(pd.read_csv("selected_samples00.csv"))

# Tag each dataset so admin can distinguish later
data1 = data1.assign(source_file="selected_samples.csv")
data2 = data2.assign(source_file="selected_samples00.csv")

# Merge into one dataset → should be 60 total
data = pd.concat([data1, data2], ignore_index=True)

# Shuffle so annotators cannot infer source
data = data.sample(frac=1, random_state=42).reset_index(drop=True)

# Pick common study_ids for qualitative (between the two files)
common_ids = list(set(data1["study_id"]).intersection(set(data2["study_id"])))
if "qual_samples" not in st.session_state:
    if len(common_ids) >= 5:
        st.session_state.qual_samples = random.sample(common_ids, 5)
    else:
        st.session_state.qual_samples = common_ids

reports = data["report"].tolist()
study_ids = data["study_id"].tolist()
sources = data["source_file"].tolist()

symptoms = [
    'Atelectasis','Cardiomegaly','Consolidation','Edema',
    'Enlarged Cardiomediastinum','Fracture','Lung Lesion',
    'Lung Opacity','No Finding','Pleural Effusion','Pleural Other',
    'Pneumonia','Pneumothorax','Support Devices'
]

# === Helper: Load existing progress ===
def load_user_progress(username):
    user_files = glob.glob(f"annotations/*_{username}.json")
    completed_ids = []
    for f in user_files:
        with open(f) as infile:
            record = json.load(infile)
            completed_ids.append(record["study_id"])
    return completed_ids

# === Annotate page ===
if page == "Annotate":
    completed = load_user_progress(st.session_state.username)
    remaining_indices = [i for i, sid in enumerate(study_ids) if sid not in completed]

    if not remaining_indices:
        st.success("🎉 You have completed all available reports!")
        st.stop()

    report_index = remaining_indices[0]
    report = reports[report_index]
    study_id = study_ids[report_index]
    source = sources[report_index]  # kept for admin tracking, not shown to annotator

    st.header(f"Patient Report (Study {study_id})")
    st.text_area("Report Text", str(report), height=200, disabled=True)

    st.subheader("Symptom Evaluation")
    scores = {}
    for symptom in symptoms:
        selected = st.radio(
            label=symptom,
            options=[0, 1, 2],
            horizontal=True,
            key=f"{symptom}_{study_id}"
        )
        scores[symptom] = selected

    qualitative = {}
    if study_id in st.session_state.qual_samples:
        st.subheader("📝 Qualitative Feedback")
        qualitative["confidence"] = st.text_area("How confident are you?", key=f"q1_{study_id}")
        qualitative["difficult_symptoms"] = st.text_area("Any difficult symptoms?", key=f"q2_{study_id}")
        qualitative["extra_info_needed"] = st.text_area("Would extra info help?", key=f"q3_{study_id}")
        qualitative["other_feedback"] = st.text_area("Other feedback?", key=f"q4_{study_id}")

    if st.button("💾 Save & Next"):
        result = {
            "study_id": study_id,
            "report_text": str(report),
            "symptom_scores": scores,
            "qualitative": qualitative if study_id in st.session_state.qual_samples else {},
            "annotator": st.session_state.username,
            "source_file": source
        }
        os.makedirs("annotations", exist_ok=True)
        filename = f"annotations/{study_id}_{st.session_state.username}.json"
        with open(filename, "w") as f:
            json.dump(result, f, indent=2)

        st.success("✅ Saved! Loading next...")
        st.rerun()

# === Review Results page (admin only) ===
elif page == "Review Results":
    st.header("📊 Review & Download Survey Results")
    files = glob.glob("annotations/*.json")
    if files:
        all_records = []
        for f in files:
            with open(f) as infile:
                all_records.append(json.load(infile))

        rows = []
        for r in all_records:
            row = {
                "study_id": r["study_id"],
                "annotator": r["annotator"],
                "source_file": r["source_file"],  # visible only to admin
                "report_text": r["report_text"],
            }
            row.update(r["symptom_scores"])
            row["confidence"] = r["qualitative"].get("confidence", "")
            row["difficult_symptoms"] = r["qualitative"].get("difficult_symptoms", "")
            row["extra_info_needed"] = r["qualitative"].get("extra_info_needed", "")
            row["other_feedback"] = r["qualitative"].get("other_feedback", "")
            rows.append(row)

        df = pd.DataFrame(rows)
        st.dataframe(df)

        st.download_button(
            "⬇️ Download all annotations as CSV",
            df.to_csv(index=False).encode("utf-8"),
            file_name="survey_results.csv",
            mime="text/csv"
        )
    else:
        st.info("No annotations found yet.")
