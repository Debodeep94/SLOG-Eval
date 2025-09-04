import streamlit as st
import pandas as pd
import json
import os
import glob

# === Credentials from secrets.toml ===
USERS = st.secrets["credentials"]

# === Login check ===
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# Track current report index
if "current_index" not in st.session_state:
    st.session_state.current_index = 0 # default start

def login():
    st.title("🔐 Login Required")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if username in USERS and USERS[username] == password:
            st.session_state.logged_in = True
            st.session_state.username = username

            # === Resume progress ===
            os.makedirs("annotations", exist_ok=True)
            user_files = glob.glob(f"annotations/*_{username}.json")
            if user_files:
                # get max annotated report_id from saved files
                annotated_ids = []
                for f in user_files:
                    with open(f) as infile:
                        record = json.load(infile)
                        annotated_ids.append(record["report_id"])
                if annotated_ids:
                    st.session_state.current_index = max(annotated_ids)  # continue from next
            else:
                st.session_state.current_index = 0

            st.success("✅ Logged in successfully! Resuming your progress...")
            st.rerun()
        else:
            st.error("❌ Invalid username or password")

if not st.session_state.logged_in:
    login()
    st.stop()

# === Load and shuffle combined dataset (once per session) ===
if "data" not in st.session_state:

    df1 = pd.read_csv("selected_samples.csv")
    df1["source_file"] = "selected_samples.csv"

    df2 = pd.read_csv("selected_samples00.csv")
    df2["source_file"] = "selected_samples00.csv"

    combined = pd.concat([df1, df2], ignore_index=True)
    combined = combined.sample(frac=1, random_state=None).reset_index(drop=True)

    st.session_state.data = combined

data = st.session_state.data
reports = data['reports_preds'].tolist()
sources = data['source_file'].tolist()
study_ids = data['study_id'].tolist()

symptoms = [
    'Atelectasis','Cardiomegaly','Consolidation','Edema',
    'Enlarged Cardiomediastinum','Fracture','Lung Lesion',
    'Lung Opacity','No Finding','Pleural Effusion','Pleural Other',
    'Pneumonia','Pneumothorax','Support Devices'
]

# === Main navigation ===
st.sidebar.success(f"Logged in as {st.session_state.username}")
if st.session_state.username == "admin":
    st.sidebar.warning("⚠️ Admin mode: You can review all annotations.")
    pages = ["Annotate", "Review Results"]
    page = st.sidebar.radio("📂 Navigation", pages)
else:
    pages = ["Annotate"]
    page = st.sidebar.radio("📂 Navigation", pages)

# === Annotate page ===
if page == "Annotate":
    report_index = st.session_state.current_index
    total_reports = len(reports)

    if report_index >= total_reports:
        st.info("🎉 You have completed all reports!")
    else:
        report = reports[report_index]
        source_file = sources[report_index]
        study_id = study_ids[report_index]

        st.header(f"Patient Report {report_index+1} of {total_reports} - ID: {study_id}")
        st.text_area("Report Text", report, height=200)

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

        if st.button("Save and Next"):
            result = {
                "report_id": report_index+1,
                "study_id": study_id,
                "report_text": report,
                "symptom_scores": scores,
                "annotator": st.session_state.username,
                "source_file": source_file
            }
            os.makedirs("annotations", exist_ok=True)
            out_path = f"annotations/report_{report_index+1}_{st.session_state.username}.json"
            with open(out_path, "w") as f:
                json.dump(result, f, indent=2)
            st.success("✅ Evaluation saved successfully!")

            # Move to next report if available
            if st.session_state.current_index < total_reports - 1:
                st.session_state.current_index += 1
                st.rerun()
            else:
                st.info("🎉 You have completed all reports!")

# === Review Results page ===
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
