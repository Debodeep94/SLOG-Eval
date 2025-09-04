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

if "current_index" not in st.session_state:
    st.session_state.current_index = 0  # index for quantitative phase

if "phase" not in st.session_state:
    st.session_state.phase = "quant"  # quant or qual

# Track qualitative index separately
if "qual_index" not in st.session_state:
    st.session_state.qual_index = 0

# === Login function ===
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

# === Load and prepare dataset (once per session) ===
if "quant_data" not in st.session_state:

    df1 = pd.read_csv("selected_samples.csv")
    df1["source_file"] = "df1"

    df2 = pd.read_csv("selected_samples00.csv")
    df2["source_file"] = "df2"

    # Pick 5 random study_ids from df1 and get their pairs from df2
    chosen_ids = random.sample(df1["study_id"].unique().tolist(), 5)
    paired_df1 = df1[df1["study_id"].isin(chosen_ids)]
    paired_df2 = df2[df2["study_id"].isin(chosen_ids)]

    # Remaining pool for random selection
    remaining_df1 = df1[~df1["study_id"].isin(chosen_ids)]

    # Sample to complete 50 additional cases (total 60 including paired)
    extra = remaining_df1.sample(n=50, random_state=42)

    # Final quantitative dataset (60 rows)
    # Ensure paired cases appear at the END for smooth transition into qualitative phase
    quant_data_main = extra.sample(frac=1, random_state=42).reset_index(drop=True)
    quant_data = pd.concat([quant_data_main, paired_df1, paired_df2], ignore_index=True)

    # Save to session state
    st.session_state.quant_data = quant_data
    st.session_state.qual_data = pd.concat([paired_df1, paired_df2], ignore_index=True)

quant_data = st.session_state.quant_data
qual_data = st.session_state.qual_data

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

    # --- Quantitative Phase ---
    if st.session_state.phase == "quant":
        idx = st.session_state.current_index
        if idx < len(quant_data):
            row = quant_data.iloc[idx]
            sid = row["study_id"]
            report = row["reports_preds"]

            st.header(f"Patient Report {idx+1} of {len(quant_data)} - ID: {sid}")
            st.text_area("Report Text", report, height=200)

            st.subheader("Symptom Evaluation")
            st.write(
                "Please review the report and assign a score for each listed symptom. "
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
                    key=f"{symptom}_{sid}_quant"
                )
                scores[symptom] = selected

            if st.button("Save and Next"):
                result = {
                    "phase": "quant",
                    "report_number": idx+1,
                    "study_id": sid,
                    "report_text": report,
                    "symptom_scores": scores,
                    "annotator": st.session_state.username,
                    "source_file": row["source_file"]
                }
                os.makedirs("annotations", exist_ok=True)
                out_path = f"annotations/quant_{sid}_{st.session_state.username}.json"
                with open(out_path, "w") as f:
                    json.dump(result, f, indent=2)

                if st.session_state.current_index < len(quant_data) - 1:
                    st.session_state.current_index += 1
                    st.rerun()
                else:
                    st.success("🎉 Quantitative phase completed! Moving to qualitative phase.")
                    st.session_state.phase = "qual"
                    st.session_state.qual_index = 0
                    st.rerun()
        else:
            st.info("All quantitative reports done.")

    # --- Qualitative Phase ---
    elif st.session_state.phase == "qual":
        qidx = st.session_state.qual_index
        if qidx < len(qual_data):
            row = qual_data.iloc[qidx]
            sid = row["study_id"]
            report = row["reports_preds"]
            image_path = row["paths"]

            st.header(f"Qualitative Report {qidx+1} of {len(qual_data)} - ID: {sid}")
            st.text_area("Report Text", report, height=200)
            st.image(image_path, caption=f"Chest X-ray (ID: {sid})", use_container_width=True)

            st.subheader("Qualitative Questions")
            q1 = st.text_area("How confident do you feel about your overall evaluation of this report? (1-10 scale)", key=f"q1_{sid}")
            q2 = st.text_area("Which aspects of the report or image were most difficult to interpret?", key=f"q2_{sid}")
            q3 = st.text_area("What additional information would have helped you make a better decision?", key=f"q3_{sid}")
            q4 = st.text_area("If there were discrepancies between report and image, please describe them.", key=f"q4_{sid}")

            if st.button("Save and Next (Qualitative)"):
                result = {
                    "phase": "qual",
                    "report_number": qidx+1,
                    "study_id": sid,
                    "report_text": report,
                    "qualitative_answers": {
                        "confidence": q1,
                        "difficult_aspects": q2,
                        "additional_info": q3,
                        "discrepancies": q4
                    },
                    "annotator": st.session_state.username,
                }
                os.makedirs("annotations", exist_ok=True)
                out_path = f"annotations/qual_{sid}_{st.session_state.username}.json"
                with open(out_path, "w") as f:
                    json.dump(result, f, indent=2)

                if st.session_state.qual_index < len(qual_data) - 1:
                    st.session_state.qual_index += 1
                    st.rerun()
                else:
                    st.success("🎉 All phases completed! Thank you for your annotations.")
        else:
            st.info("All qualitative reports done.")

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
