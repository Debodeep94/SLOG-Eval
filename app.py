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
            st.session_state.current_index = 0  # start from first report
            st.success("✅ Logged in successfully!")
            st.rerun()
        else:
            st.error("❌ Invalid username or password")

if not st.session_state.logged_in:
    login()
    st.stop()

# === Main navigation ===
st.sidebar.success(f"Logged in as {st.session_state.username}")
pages = ["Annotate", "Review Results"]
page = st.sidebar.radio("📂 Navigation", pages)

# === Data load ===
data1 = pd.read_csv("selected_samples.csv")
data2 = pd.read_csv("selected_samples00.csv")

# Merge for annotation
data = pd.concat(
    [data1.assign(source_file="selected_samples.csv"),
     data2.assign(source_file="selected_samples00.csv")],
    ignore_index=True
)

# Pick common study_ids for qualitative
common_ids = list(set(data1["study_id"]).intersection(set(data2["study_id"])))
if "qual_samples" not in st.session_state:
    if len(common_ids) >= 5:
        st.session_state.qual_samples = random.sample(common_ids, 5)
    else:
        st.session_state.qual_samples = common_ids

# Shuffle reports ONCE per login
if "shuffled_data" not in st.session_state:
    st.session_state.shuffled_data = data.sample(frac=1, random_state=42).reset_index(drop=True).to_dict("records")

symptoms = [
    'Atelectasis','Cardiomegaly','Consolidation','Edema',
    'Enlarged Cardiomediastinum','Fracture','Lung Lesion',
    'Lung Opacity','No Finding','Pleural Effusion','Pleural Other',
    'Pneumonia','Pneumothorax','Support Devices'
]

# === Annotate page ===
if page == "Annotate":
    reports_total = len(st.session_state.shuffled_data)

    if st.session_state.current_index >= reports_total:
        st.success("🎉 All reports completed! Please go to 'Review Results' to download your data.")
        st.stop()

    # Get current report
    record = st.session_state.shuffled_data[st.session_state.current_index]
    report_index = st.session_state.current_index + 1
    report = record["reports_preds"]
    study_id = record["study_id"]
    source = record["source_file"]

    st.header(f"Report {report_index} of {reports_total} (Study {study_id})")
    st.text_area("Report Text", report, height=200)

    st.subheader("Symptom Evaluation")
    scores = {}
    for symptom in symptoms:
        selected = st.radio(
            label=symptom,
            options=[0, 1, 2],
            horizontal=True,
            key=f"{symptom}_{report_index}"
        )
        scores[symptom] = selected

    # === If study_id is in qualitative sample, show extra questions ===
    qualitative = {}
    if study_id in st.session_state.qual_samples:
        st.subheader("📝 Qualitative Feedback")
        qualitative["confidence"] = st.text_area(
            "How confident do you feel about your overall evaluation of this report?",
            key=f"q1_{report_index}"
        )
        qualitative["difficult_symptoms"] = st.text_area(
            "Were there any symptoms that were particularly difficult to score?",
            key=f"q2_{report_index}"
        )
        qualitative["extra_info_needed"] = st.text_area(
            "Do you think additional information (like clinical history) would help?",
            key=f"q3_{report_index}"
        )
        qualitative["other_feedback"] = st.text_area(
            "Any other feedback or observations?",
            key=f"q4_{report_index}"
        )

    if st.button("Next ➡️"):
        result = {
            "report_id": report_index,
            "study_id": study_id,
            "report_text": report,
            "symptom_scores": scores,
            "qualitative": qualitative if study_id in st.session_state.qual_samples else {},
            "annotator": st.session_state.username,
            "source_file": source
        }
        os.makedirs("annotations", exist_ok=True)
        filename = f"annotations/report_{study_id}_{st.session_state.username}.json"
        with open(filename, "w") as f:
            json.dump(result, f, indent=2)

        st.session_state.current_index += 1
        st.rerun()

# === Review Results page ===
elif page == "Review Results":
    st.header("📊 Review & Download Survey Results")
    files = glob.glob("annotations/*.json")
    if files:
        all_records = []
        for f in files:
            with open(f) as infile:
                all_records.append(json.load(infile))

        # Build dataframe with symptom scores + qualitative
        rows = []
        for r in all_records:
            row = {
                "report_id": r["report_id"],
                "study_id": r["study_id"],
                "annotator": r["annotator"],
                "source_file": r["source_file"],
                "report_text": r["report_text"],
            }
            # Add symptoms
            row.update(r["symptom_scores"])
            # Add qualitative (if any)
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
