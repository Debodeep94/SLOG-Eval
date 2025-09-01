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
pages = ["Annotate", "Review Results"]
page = st.sidebar.radio("📂 Navigation", pages)

# === Load data from two CSVs ===
data1 = pd.read_csv("selected_samples.csv")
data2 = pd.read_csv("selected_samples00.csv")

# Combine datasets for main annotation pool
data = pd.concat(
    [
        data1.assign(source_file="selected_samples.csv"),
        data2.assign(source_file="selected_samples00.csv"),
    ],
    ignore_index=True,
)

reports = data["reports_preds"].tolist()
image_url = data["paths"].tolist()
study_ids = data["study_id"].tolist()

symptoms = [
    "Atelectasis",
    "Cardiomegaly",
    "Consolidation",
    "Edema",
    "Enlarged Cardiomediastinum",
    "Fracture",
    "Lung Lesion",
    "Lung Opacity",
    "No Finding",
    "Pleural Effusion",
    "Pleural Other",
    "Pneumonia",
    "Pneumothorax",
    "Support Devices",
]

# === Pick 5 qualitative study_ids that exist in both datasets ===
common_ids = list(set(data1["study_id"]).intersection(set(data2["study_id"])))
if "qual_samples" not in st.session_state:
    if len(common_ids) >= 5:
        st.session_state.qual_samples = random.sample(common_ids, 5)
    else:
        st.session_state.qual_samples = common_ids

# === Annotate page ===
if page == "Annotate":
    st.sidebar.title("Report Navigator")

    # total = 30 quantitative + qualitative at the end
    total_main = 30
    total_qual = len(st.session_state.qual_samples)

    report_index = st.sidebar.number_input(
        "Select Question", min_value=1, max_value=total_main + total_qual, step=1
    )

    # === Main 30 quantitative questions ===
    if report_index <= total_main:
        report = reports[report_index - 1]
        sid = study_ids[report_index - 1]

        st.header(f"Patient Report #{report_index}")
        st.text_area("Report Text", report, height=200)
        st.image(
            image_url[report_index - 1],
            caption=f"Chest X-ray (Study {sid})",
            use_container_width=True,
        )

        st.subheader("Symptom Evaluation")
        st.write(
            "Please review the report and chest X-ray, then assign a score for each listed symptom.\n\n"
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
                key=f"{symptom}_{report_index}",
            )
            scores[symptom] = selected

        if st.button("Save Evaluation", key=f"save_{report_index}"):
            result = {
                "report_id": report_index,
                "study_id": sid,
                "report_text": report,
                "symptom_scores": scores,
                "annotator": st.session_state.username,
            }
            os.makedirs("annotations", exist_ok=True)
            with open(
                f"annotations/report_{report_index}_{sid}_{st.session_state.username}.json",
                "w",
            ) as f:
                json.dump(result, f, indent=2)
            st.success("✅ Evaluation saved successfully!")

    # === Extra 5 qualitative-only questions ===
    else:
        q_index = report_index - total_main - 1
        if q_index < len(st.session_state.qual_samples):
            sid = st.session_state.qual_samples[q_index]

            st.header(f"Qualitative Feedback (Study {sid})")

            q1 = st.text_area(
                "How confident do you feel about your overall evaluation of this report?",
                key=f"q1_{sid}",
            )
            q2 = st.text_area(
                "Were there any symptoms that were particularly difficult to score?",
                key=f"q2_{sid}",
            )
            q3 = st.text_area(
                "Do you think additional information (like clinical history) would help?",
                key=f"q3_{sid}",
            )
            q4 = st.text_area(
                "Any other feedback or observations?",
                key=f"q4_{sid}",
            )

            if st.button("Save Qualitative Feedback", key=f"save_qual_{sid}"):
                result = {
                    "study_id": sid,
                    "annotator": st.session_state.username,
                    "qualitative": {
                        "confidence": q1,
                        "difficult_symptoms": q2,
                        "extra_info_needed": q3,
                        "other_feedback": q4,
                    },
                }
                os.makedirs("qual_annotations", exist_ok=True)
                with open(
                    f"qual_annotations/qual_{sid}_{st.session_state.username}.json", "w"
                ) as f:
                    json.dump(result, f, indent=2)
                st.success("✅ Qualitative feedback saved successfully!")

# === Review Results page ===
elif page == "Review Results":
    st.header("📊 Review & Download Survey Results")

    # Quantitative
    files = glob.glob("annotations/*.json")
    if files:
        all_records = []
        for f in files:
            with open(f) as infile:
                all_records.append(json.load(infile))
        df = pd.json_normalize(all_records)
        st.subheader("Quantitative Results")
        st.dataframe(df)
        st.download_button(
            "⬇️ Download quantitative annotations as CSV",
            df.to_csv(index=False).encode("utf-8"),
            file_name="survey_results.csv",
            mime="text/csv",
        )
    else:
        st.info("No quantitative annotations found yet.")

    # Qualitative
    qfiles = glob.glob("qual_annotations/*.json")
    if qfiles:
        all_qrecords = []
        for f in qfiles:
            with open(f) as infile:
                all_qrecords.append(json.load(infile))
        qdf = pd.json_normalize(all_qrecords)
        st.subheader("Qualitative Results")
        st.dataframe(qdf)
        st.download_button(
            "⬇️ Download qualitative annotations as CSV",
            qdf.to_csv(index=False).encode("utf-8"),
            file_name="qualitative_results.csv",
            mime="text/csv",
        )
    else:
        st.info("No qualitative annotations found yet.")
