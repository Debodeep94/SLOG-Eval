import streamlit as st
import pandas as pd
import numpy as np
from typing import List
import gspread
from google.oauth2.service_account import Credentials

# === CONFIG ===
SYMPTOMS: List[str] = [
    'Atelectasis','Cardiomegaly','Consolidation','Edema',
    'Enlarged Cardiomediastinum','Fracture','Lung Lesion',
    'Lung Opacity','No Finding','Pleural Effusion','Pleural Other',
    'Pneumonia','Pneumothorax','Support Devices'
]
symptom_list_str = ", ".join(SYMPTOMS)


# === Google Sheets setup ===
SHEET_URL = st.secrets["gsheet"]["url"]

@st.cache_resource
def connect_gsheet():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    client = gspread.authorize(creds)
    return client.open_by_url(SHEET_URL)

def append_to_gsheet(worksheet_name, row_dict):
    sh = connect_gsheet()
    ws = sh.worksheet(worksheet_name)

    # Ensure headers exist
    headers = ws.row_values(1)
    if not headers:
        headers = list(row_dict.keys())
        ws.append_row(headers)

    # Sanitize values: replace NaN/None with ""
    def clean_value(v):
        if pd.isna(v):
            return ""
        return str(v)

    values = [clean_value(row_dict.get(h, "")) for h in headers]
    ws.append_row(values)

@st.cache_data(ttl=2)  # cache reads to reduce API quota
def load_all_from_gsheet(worksheet_name):
    sh = connect_gsheet()
    ws = sh.worksheet(worksheet_name)
    data = ws.get_all_records()
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data)

def get_progress_from_gsheet(user):
    df = load_all_from_gsheet("Annotations")
    if df.empty:
        return set(), set()
    user_df = df[df["annotator"] == user]
    quant_done = set(user_df[user_df["phase"] == "quant"]["study_id"].astype(str) 
                     + "__" + user_df[user_df["phase"] == "quant"]["source_label"])
    qual_done = set(user_df[user_df["phase"] == "qual"]["study_id"].astype(str) 
                    + "__" + user_df[user_df["phase"] == "qual"]["source_label"])
    return quant_done, qual_done

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

# === Load sample data ===
df1 = pd.read_csv("selected_samples.csv")
df1["source_file"] = "selected_samples.csv"
df1["source_label"] = "df1"

df2 = pd.read_csv("selected_samples00.csv")
df2["source_file"] = "selected_samples00.csv"
df2["source_label"] = "df2"

NUM_QUAL_STUDY_IDS = 5
QUANT_TARGET_REPORTS = df1.shape[0] + df2.shape[0] - NUM_QUAL_STUDY_IDS * 2

# === Prepare quant/qual splits once per session ===
if "prepared" not in st.session_state:
    common_ids = pd.Index(df1["study_id"]).intersection(pd.Index(df2["study_id"]))
    st.write("Common IDs:", len(common_ids))
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
    print('pool size: ', len(pool_df))
    quant_df = pool_df.iloc[:min(QUANT_TARGET_REPORTS, len(pool_df))].reset_index(drop=True)
    st.write(f"Total quantitative reports: {quant_df.shape[0]}")

    st.session_state.quant_df = quant_df
    st.session_state.qual_df = qual_df.reset_index(drop=True)
    st.session_state.prepared = True
    st.write("df1 rows:", len(df1))
    st.write("df2 rows:", len(df2))

    st.write("Qual rows:", len(qual_df))
    st.write("Quant rows:", len(quant_df))
    st.write("Total (qual + quant):", len(qual_df) + len(quant_df))

# === Resume progress ===
user = st.session_state.username
quant_done, qual_done = get_progress_from_gsheet(user)
st.write(f"Quant done: {len(quant_done)}, Qual done: {len(qual_done)}")

# Filter out already annotated rows
st.session_state.quant_df = st.session_state.quant_df[
    ~st.session_state.quant_df["uid"].isin(quant_done)
].reset_index(drop=True)

st.session_state.qual_df = st.session_state.qual_df[
    ~st.session_state.qual_df["uid"].isin(qual_done)
].reset_index(drop=True)

quant_df = st.session_state.quant_df
st.write(f"Total quantitative reports: {quant_df.shape[0]}")
qual_df = st.session_state.qual_df

# Decide phase
st.session_state.phase = "quant" if not quant_df.empty else "qual"
st.session_state.current_index = 0  # always start from first remaining

phase = st.session_state.phase
idx = st.session_state.current_index

# === Sidebar & nav ===
st.sidebar.success(f"Logged in as {st.session_state.username}")
pages = ["Annotate"]
if st.session_state.username == "admin":
    st.sidebar.warning("⚠️ Admin mode: You can review all annotations.")
    pages.append("Review Results")

# Sidebar progress tracker
try:
    st.sidebar.markdown("### 📊 Progress")
    st.sidebar.write(f"**Quantitative:** {len(quant_done)}/{QUANT_TARGET_REPORTS}")
    st.sidebar.write(f"**Qualitative:** {len(qual_done)}/{NUM_QUAL_STUDY_IDS*2}")

    if st.session_state.username == "admin":
        df_all = load_all_from_gsheet("Annotations")
        st.sidebar.write("---")
        st.sidebar.write(f"**Total annotations (all users):** {df_all.shape[0]}")
except Exception as e:
    st.sidebar.error(f"Progress tracker failed: {e}")

page = st.sidebar.radio("📂 Navigation", pages)

def row_safe(df, i):
    if i < 0 or i >= len(df):
        return None
    return df.iloc[i]

# === Annotation page ===
if page == "Annotate":
    if phase == "quant":
        total_quant = len(quant_df)
        st.write(f"Total quantitative reports remaining: {total_quant}")
        row = row_safe(quant_df, idx)
        if row is None:
            st.info("Quantitative phase complete. Moving to qualitative...")
            st.session_state.phase = "qual"
            st.session_state.current_index = 0
            st.rerun()

        report_text = row["reports_preds"]
        study_id = row["study_id"]

        st.header(f"Patient Report {len(quant_done)+1} of {QUANT_TARGET_REPORTS} - ID: {study_id}")
        st.text_area("Report Text", report_text, height=220)

        st.subheader("Symptom Evaluation")
        scores = {}
        for symptom in SYMPTOMS:
            selected = st.radio(
                label=symptom,
                options=['Yes', 'No', 'May be'],
                horizontal=True,
                key=f"quant_{idx}_{symptom}"
            )
            scores[symptom] = np.nan if selected == '' else selected

        if st.button("Save and Next (Quant)"):
            result = {
                "phase": "quant",
                "report_number_in_quant": idx+1,
                "study_id": study_id,
                "report_text": report_text,
                "source_file": row["source_file"],
                "source_label": row["source_label"],
                "annotator": user,
                **{f"symptom_scores.{k}": v for k, v in scores.items()}
            }
            append_to_gsheet("Annotations", result)
            st.success("✅ Saved quantitative annotation.")

            st.session_state.current_index += 1
            st.rerun()

    elif phase == "qual":
        total_qual = len(qual_df)
        row = row_safe(qual_df, idx)
        if row is None:
            st.header("Phase: Qualitative")
            st.info("🎉 You have completed all qualitative items.")
        else:
            study_id = row["study_id"]
            report_text = row["reports_preds"]

            st.header(f"Qualitative — Case {idx+1} of {total_qual}")
            st.subheader(f"Patient ID: {row['uid']}")
            st.text_area("Report Text", report_text, height=220)

            q1 = st.text_input("Q1. Confidence (1-10)", key=f"q1_{idx}")
            q2 = st.text_area(f"Q2. Difficult symptoms? Options: {symptom_list_str}", key=f"q2_{idx}")
            q3 = st.text_area("Q3. Additional info needed? (Yes/No)", key=f"q3_{idx}")
            q4 = st.text_area("Q4. Rationale for key decisions", key=f"q4_{idx}")
            q5 = st.text_area("Q5. Inconsistencies between image and text?", key=f"q5_{idx}")

            if st.button("Save and Next (Qual)"):
                result = {
                    "phase": "qual",
                    "qual_case_number": idx+1,
                    "study_id": study_id,
                    "report_text": report_text,
                    "source_file": row["source_file"],
                    "source_label": row["source_label"],
                    "annotator": user,
                    "q1_confidence_1_10": q1,
                    "q2_challenges": q2,
                    "q3_additional_info": q3,
                    "q4_rationale": q4,
                    "q5_inconsistencies": q5,
                }
                append_to_gsheet("Annotations", result)
                st.success("✅ Saved qualitative annotation.")

                st.session_state.current_index += 1
                st.rerun()

# === Review Results page ===
elif page == "Review Results":
    st.header("📊 Review & Download Survey Results")
    df = load_all_from_gsheet("Annotations")
    if df.empty:
        st.info("No annotations found yet.")
    else:
        st.dataframe(df)
        st.download_button(
            "⬇️ Download all annotations as CSV",
            df.to_csv(index=False).encode("utf-8"),
            file_name="survey_results.csv",
            mime="text/csv"
        )
