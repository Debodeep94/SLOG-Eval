import streamlit as st
import pandas as pd
import numpy as np
import json
from typing import List
import requests

# === CONFIG ===
SYMPTOMS: List[str] = [
    'Atelectasis','Cardiomegaly','Consolidation','Edema',
    'Enlarged Cardiomediastinum','Fracture','Lung Lesion',
    'Lung Opacity','No Finding','Pleural Effusion','Pleural Other',
    'Pneumonia','Pneumothorax','Support Devices'
]
symptom_list_str = ", ".join(SYMPTOMS)
QUANT_TARGET_REPORTS = 60
NUM_QUAL_STUDY_IDS = 5

# === GitHub Gist setup ===
GIST_ID = "YOUR_GIST_ID"  # create a gist and put its ID here

def get_headers():
    return {"Authorization": f"token {st.secrets['github']['token']}"}

def save_annotation_to_gist(phase, filename, data):
    url = f"https://api.github.com/gists/{GIST_ID}"
    payload = {
        "files": {
            f"{phase}/{filename}": {"content": json.dumps(data, indent=2)}
        }
    }
    resp = requests.patch(url, headers=get_headers(), json=payload)
    return resp.status_code == 200

def list_gist_files(phase, user):
    url = f"https://api.github.com/gists/{GIST_ID}"
    resp = requests.get(url, headers=get_headers())
    if resp.status_code != 200:
        return []
    files = resp.json()["files"]
    return [f for f in files if f.startswith(f"{phase}/") and f.endswith(f"_{user}.json")]

def load_annotation_from_gist(filename):
    url = f"https://api.github.com/gists/{GIST_ID}"
    resp = requests.get(url, headers=get_headers())
    if resp.status_code != 200:
        return None
    files = resp.json()["files"]
    if filename in files:
        return json.loads(files[filename]["content"])
    return None

# === Credentials from secrets.toml ===
USERS = st.secrets["credentials"]

# === Session state defaults ===
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# === Login ===
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

# === Load data and prepare quant/qual splits once per session ===
if "prepared" not in st.session_state:
    df1 = pd.read_csv("selected_samples.csv")
    df1["source_file"] = "selected_samples.csv"
    df1["source_label"] = "df1"

    df2 = pd.read_csv("selected_samples00.csv")
    df2["source_file"] = "selected_samples00.csv"
    df2["source_label"] = "df2"

    required_cols = {"study_id", "reports_preds"}
    if not required_cols.issubset(df1.columns) or not required_cols.issubset(df2.columns):
        st.error(f"Missing required columns in input files. Required: {required_cols}")
        st.stop()

    common_ids = pd.Index(df1["study_id"]).intersection(pd.Index(df2["study_id"]))
    if len(common_ids) == 0:
        st.error("No overlapping study_id values between selected_samples.csv and selected_samples00.csv")
        st.stop()

    user_seed = abs(hash(st.session_state.username)) % (2**32)
    n_pick = min(NUM_QUAL_STUDY_IDS, len(common_ids))
    chosen_ids = pd.Series(common_ids).sample(n=n_pick, random_state=user_seed).tolist()

    df1_qual = df1[df1["study_id"].isin(chosen_ids)].copy()
    df2_qual = df2[df2["study_id"].isin(chosen_ids)].copy()
    qual_df = pd.concat([df1_qual, df2_qual], ignore_index=True)
    qual_df["uid"] = qual_df["study_id"].astype(str) + "__" + qual_df["source_label"]

    df1_pool = df1[~df1["study_id"].isin(chosen_ids)].copy()
    df2_pool = df2[~df2["study_id"].isin(chosen_ids)].copy()
    pool_df = pd.concat([df1_pool, df2_pool], ignore_index=True)
    pool_df["uid"] = pool_df["study_id"].astype(str) + "__" + pool_df["source_label"]
    pool_df = pool_df.sample(frac=1, random_state=user_seed).reset_index(drop=True)

    quant_df = pool_df.iloc[:min(QUANT_TARGET_REPORTS, len(pool_df))].reset_index(drop=True)

    st.session_state.quant_df = quant_df
    st.session_state.qual_df = qual_df.reset_index(drop=True)
    st.session_state.prepared = True

# === Resume logic using Gist ===
user = st.session_state.username
quant_done_files = list_gist_files("quant", user)
qual_done_files = list_gist_files("qual", user)

if len(quant_done_files) >= len(st.session_state.quant_df):
    st.session_state.phase = "qual"
    st.session_state.current_index = len(qual_done_files)
else:
    st.session_state.phase = "quant"
    st.session_state.current_index = len(quant_done_files)

quant_df = st.session_state.quant_df
qual_df = st.session_state.qual_df
phase = st.session_state.phase
idx = st.session_state.current_index

# === Sidebar & nav ===
st.sidebar.success(f"Logged in as {st.session_state.username}")
pages = ["Annotate"]
if st.session_state.username == "admin":
    st.sidebar.warning("⚠️ Admin mode: You can review all annotations.")
    pages.append("Review Results")
page = st.sidebar.radio("📂 Navigation", pages)

def row_safe(df, i):
    if i < 0 or i >= len(df):
        return None
    return df.iloc[i]

# === Annotate page ===
if page == "Annotate":
    if phase == "quant":
        total_quant = len(quant_df)
        if total_quant == 0:
            st.error("No reports available for quantitative phase.")
        else:
            display_idx = idx + 1
            row = row_safe(quant_df, idx)
            if row is None:
                st.info("Quantitative phase complete. Moving to qualitative...")
                st.session_state.phase = "qual"
                st.session_state.current_index = len(list_gist_files("qual", user))
                st.rerun()

            report_text = row["reports_preds"]
            study_id = row["study_id"]
            source_file = row.get("source_file", "")
            source_label = row.get("source_label", "")

            st.header(f"Patient Report {display_idx} of {total_quant} - ID: {study_id}")
            st.text_area("Report Text (quantitative phase — no image shown)", report_text, height=220)
            st.subheader("Symptom Evaluation")
            st.write(
                "Assign a score for each symptom. Leave blank if not mentioned.\n"
                "Options: '', 'Yes', 'No', 'May be'"
            )

            scores = {}
            for symptom in SYMPTOMS:
                selected = st.radio(
                    label=symptom,
                    options=['', 'Yes', 'No', 'May be'],
                    horizontal=True,
                    key=f"quant_{idx}_{symptom}"
                )
                scores[symptom] = np.nan if selected == '' else selected

            if st.button("Save and Next (Quant)"):
                result = {
                    "phase": "quant",
                    "report_number_in_quant": display_idx,
                    "study_id": study_id,
                    "report_text": report_text,
                    "symptom_scores": scores,
                    "annotator": user,
                    "source_file": source_file,
                    "source_label": source_label,
                }
                filename = f"{row['uid']}_{user}.json"
                save_annotation_to_gist("quant", filename, result)
                st.success("✅ Saved quantitative annotation.")
                st.rerun()

    elif phase == "qual":
        total_qual = len(qual_df)
        if total_qual == 0:
            st.info("No qualitative paired cases reserved.")
        elif idx >= total_qual:
            st.header("Phase: Qualitative")
            st.info("🎉 You have completed all qualitative items for this set.")
        else:
            row = row_safe(qual_df, idx)
            study_id = row["study_id"]
            report_text = row["reports_preds"]
            img_path = row.get("paths", None)
            source_file = row.get("source_file", "")
            source_label = row.get("source_label", "")

            st.header(f"Qualitative — Case {idx+1} of {total_qual}")
            st.subheader(f"Patient ID: {study_id} • source: {source_label}")
            if img_path:
                st.image(img_path, caption=f"CXR — study {study_id}", use_container_width=True)
            st.text_area("Report Text", report_text, height=220)

            q1 = st.text_input("Q1. Confidence (1-10)", key=f"q1_{idx}")
            q2 = st.text_area(f"Q2. Difficult symptoms? Options: {symptom_list_str}", key=f"q2_{idx}")
            q3 = st.text_area("Q3. Additional info needed? (Yes/No)", key=f"q3_{idx}")
            q4 = st.text_area("Q4. Rationale for key decisions", key=f"q4_{idx}")
            q5 = st.text_area("Q5. Inconsistencies between image and text?", key=f"q5_{idx}")

            if st.button("Save and Next (Qual)"):
                qual_answers = {
                    "q1_confidence_1_10": q1,
                    "q2_challenges": q2,
                    "q3_additional_info": q3,
                    "q4_rationale": q4,
                    "q5_inconsistencies": q5,
                }
                result = {
                    "phase": "qual",
                    "qual_case_number": idx + 1,
                    "study_id": study_id,
                    "report_text": report_text,
                    "image_path": img_path,
                    "qualitative_answers": qual_answers,
                    "annotator": user,
                    "source_file": source_file,
                    "source_label": source_label,
                }
                filename = f"{row['uid']}_{user}.json"
                save_annotation_to_gist("qual", filename, result)
                st.success("✅ Saved qualitative annotation.")
                st.rerun()

# === Review Results page ===
elif page == "Review Results":
    st.header("📊 Review & Download Survey Results")
    quant_files = list_gist_files("quant", user)
    qual_files = list_gist_files("qual", user)
    records = [load_annotation_from_gist(f) for f in quant_files + qual_files if load_annotation_from_gist(f)]
    if records:
        df = pd.json_normalize(records)
        st.dataframe(df)
        st.download_button(
            "⬇️ Download all annotations as CSV",
            df.to_csv(index=False).encode("utf-8"),
            file_name="survey_results.csv",
            mime="text/csv"
        )
    else:
        st.info("No annotations found yet.")
