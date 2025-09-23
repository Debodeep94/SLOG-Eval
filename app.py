import streamlit as st
import pandas as pd
import numpy as np
from typing import List
import gspread
from google.oauth2.service_account import Credentials
import gspread.exceptions as gse

# ==== CONFIG ====
SYMPTOMS: List[str] = [
    'Atelectasis','Cardiomegaly','Consolidation','Edema',
    'Enlarged Cardiomediastinum','Fracture','Lung Lesion',
    'Lung Opacity','No Finding','Pleural Effusion','Pleural Other',
    'Pneumonia','Pneumothorax','Support Devices'
]
QUANT_TARGET_REPORTS = 50  # you said 50
NUM_QUAL_STUDY_IDS = 5     # 5 study_ids => 10 qual rows (df1 + df2)
SHEET_URL = st.secrets["gsheet"]["url"]
ANNOTATIONS_SHEET_NAME = "Annotations"

# A canonical header set so rows line up in Google Sheets
BASE_HEADERS = [
    "phase","report_number_in_quant","qual_case_number",
    "study_id","source_file","source_label","uid",
    "report_text","annotator",
    "q1_confidence_1_10","q2_challenges","q3_additional_info","q4_rationale","q5_inconsistencies"
]
SYMPTOM_HEADERS = [f"symptom_scores.{s}" for s in SYMPTOMS]
ALL_HEADERS = BASE_HEADERS[:]
ALL_HEADERS[ALL_HEADERS.index("uid")] = "uid"  # ensure uid position exists
ALL_HEADERS.extend(SYMPTOM_HEADERS)

# ==== GOOGLE SHEETS ====
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

def ensure_worksheet(sh, title, headers):
    try:
        ws = sh.worksheet(title)
    except gse.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows="2000", cols=str(max(100, len(headers))))
        ws.append_row(headers)
    # if first row is empty, seed headers
    first = ws.row_values(1)
    if not first:
        ws.append_row(headers)
    return ws

def clean_for_sheet(v):
    if pd.isna(v):
        return ""
    return str(v)

def row_to_values(row_dict, headers):
    return [clean_for_sheet(row_dict.get(h, "")) for h in headers]

def append_to_gsheet(row_dict):
    sh = connect_gsheet()
    ws = ensure_worksheet(sh, ANNOTATIONS_SHEET_NAME, ALL_HEADERS)
    # ensure any new keys don’t break alignment: we only write known headers
    ws.append_row(row_to_values(row_dict, ws.row_values(1)))

@st.cache_data(ttl=30)
def load_all_from_gsheet():
    """Return DataFrame of all annotations (cached for 30s)."""
    sh = connect_gsheet()
    ws = ensure_worksheet(sh, ANNOTATIONS_SHEET_NAME, ALL_HEADERS)
    data = ws.get_all_records()
    return pd.DataFrame(data) if data else pd.DataFrame(columns=ALL_HEADERS)

# ==== AUTH ====
USERS = st.secrets["credentials"]
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

def login():
    st.title("🔐 Login Required")
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")
    if st.button("Login"):
        if u in USERS and USERS[u] == p:
            st.session_state.logged_in = True
            st.session_state.username = u
            st.success("✅ Logged in successfully!")
            st.rerun()
        else:
            st.error("❌ Invalid username or password")

if not st.session_state.logged_in:
    login()
    st.stop()

user = st.session_state.username

# ==== LOAD DATA ====
df1 = pd.read_csv("selected_samples.csv")
df1["source_file"] = "selected_samples.csv"
df1["source_label"] = "df1"

df2 = pd.read_csv("selected_samples00.csv")
df2["source_file"] = "selected_samples00.csv"
df2["source_label"] = "df2"

# ==== BUILD DETERMINISTIC FULL POOLS (ONCE PER USER SESSION) ====
if "built_pools" not in st.session_state:
    # intersect IDs present in both to pick qual pairs
    common_ids = pd.Index(df1["study_id"]).intersection(pd.Index(df2["study_id"]))
    user_seed = abs(hash(user)) % (2**32)

    # --- Qualitative: pick NUM_QUAL_STUDY_IDS study_ids, take both df1 & df2 rows
    n_pick = min(NUM_QUAL_STUDY_IDS, len(common_ids))
    chosen_ids = pd.Series(common_ids).sample(n=n_pick, random_state=user_seed).tolist()

    df1_qual = df1[df1["study_id"].isin(chosen_ids)].copy()
    df2_qual = df2[df2["study_id"].isin(chosen_ids)].copy()
    qual_all = pd.concat([df1_qual, df2_qual], ignore_index=True)

    # --- Quantitative: everything except the qual rows
    df1_pool = df1[~df1["study_id"].isin(chosen_ids)].copy()
    df2_pool = df2[~df2["study_id"].isin(chosen_ids)].copy()
    quant_pool = pd.concat([df1_pool, df2_pool], ignore_index=True)

    # add uid column
    for d in (qual_all, quant_pool):
        d["uid"] = d["study_id"].astype(str) + "__" + d["source_label"].astype(str)

    # deterministic shuffle per user
    quant_pool = quant_pool.sample(frac=1, random_state=user_seed).reset_index(drop=True)

    # hard cap quant at QUANT_TARGET_REPORTS, keep qual as 2 * NUM_QUAL_STUDY_IDS
    quant_all = quant_pool.head(QUANT_TARGET_REPORTS).reset_index(drop=True)
    qual_all = qual_all.reset_index(drop=True)

    st.session_state.quant_all = quant_all
    st.session_state.qual_all = qual_all
    st.session_state.built_pools = True

quant_all: pd.DataFrame = st.session_state.quant_all
qual_all: pd.DataFrame = st.session_state.qual_all

# ==== PROGRESS + NEXT INDEX (ALWAYS RELATIVE TO FULL POOLS) ====
def user_done_uids_df():
    df = load_all_from_gsheet()
    if df.empty:
        return set(), df
    if "source_label" not in df.columns:
        df["source_label"] = ""  # safety
    df["uid"] = df["study_id"].astype(str) + "__" + df["source_label"].astype(str)
    uids = set(df.loc[df["annotator"] == user, "uid"])
    return uids, df

def count_done_in_pool(pool_df: pd.DataFrame, done_uids: set, phase: str) -> int:
    # count only rows in this pool that are done by this user with this phase
    df = load_all_from_gsheet()
    if df.empty: return 0
    df["uid"] = df["study_id"].astype(str) + "__" + df["source_label"].astype(str)
    in_pool = df["uid"].isin(set(pool_df["uid"]))
    mine = df["annotator"] == user
    right_phase = df["phase"] == phase
    return int((in_pool & mine & right_phase).sum())

def next_unseen_index(pool_df: pd.DataFrame, done_uids: set) -> int:
    for i, u in enumerate(pool_df["uid"]):
        if u not in done_uids:
            return i
    return len(pool_df)

done_uids, df_all_ann = user_done_uids_df()

quant_total = len(quant_all)                     # fixed at <= 50
qual_total  = len(qual_all)                      # fixed at 2 * NUM_QUAL_STUDY_IDS (10)

quant_done  = count_done_in_pool(quant_all, done_uids, phase="quant")
qual_done   = count_done_in_pool(qual_all,  done_uids, phase="qual")

quant_next  = next_unseen_index(quant_all, done_uids)
qual_next   = next_unseen_index(qual_all,  done_uids)

# Choose phase based on whether quant is fully done
phase = "qual" if quant_done >= quant_total else "quant"

# ==== SIDEBAR ====
st.sidebar.success(f"Logged in as {user}")
pages = ["Annotate"]
if user == "admin":
    st.sidebar.warning("⚠️ Admin mode: You can review all annotations.")
    pages.append("Review Results")

st.sidebar.markdown("### 📊 Progress")
st.sidebar.write(f"**Quantitative:** {quant_done}/{quant_total}")  # e.g., 30/50
st.sidebar.write(f"**Qualitative:** {qual_done}/{qual_total}")     # e.g., 0/10
if user == "admin":
    st.sidebar.write("---")
    st.sidebar.write(f"**Total annotations (all users):** {len(df_all_ann)}")

page = st.sidebar.radio("📂 Navigation", pages)

# ==== UI HELPERS ====
def values_for_sheet_quant(row, report_index_display, scores):
    # Build a dict that matches ALL_HEADERS, missing keys become ""
    base = {
        "phase": "quant",
        "report_number_in_quant": report_index_display,
        "qual_case_number": "",
        "study_id": row["study_id"],
        "source_file": row.get("source_file",""),
        "source_label": row.get("source_label",""),
        "uid": row["uid"],
        "report_text": row["reports_preds"],
        "annotator": user,
        "q1_confidence_1_10": "",
        "q2_challenges": "",
        "q3_additional_info": "",
        "q4_rationale": "",
        "q5_inconsistencies": "",
    }
    for s in SYMPTOMS:
        base[f"symptom_scores.{s}"] = scores.get(s, "")
    return base

def values_for_sheet_qual(row, case_index_display, answers):
    base = {
        "phase": "qual",
        "report_number_in_quant": "",
        "qual_case_number": case_index_display,
        "study_id": row["study_id"],
        "source_file": row.get("source_file",""),
        "source_label": row.get("source_label",""),
        "uid": row["uid"],
        "report_text": row["reports_preds"],
        "annotator": user,
        "q1_confidence_1_10": answers.get("q1",""),
        "q2_challenges": answers.get("q2",""),
        "q3_additional_info": answers.get("q3",""),
        "q4_rationale": answers.get("q4",""),
        "q5_inconsistencies": answers.get("q5",""),
    }
    for s in SYMPTOMS:
        base[f"symptom_scores.{s}"] = ""
    return base

# ==== PAGES ====
if page == "Annotate":
    if phase == "quant":
        if quant_next >= quant_total:
            st.info("Quantitative phase complete. Moving to qualitative…")
            phase = "qual"

    if phase == "quant":
        row = quant_all.iloc[quant_next]
        display_idx = quant_done + 1  # e.g., 31 when 30 done
        st.header(f"Patient Report {display_idx} of {quant_total} - ID: {row['study_id']}")
        st.text_area("Report Text (no image in quant)", row["reports_preds"], height=220)

        st.subheader("Symptom Evaluation")
        st.caption("Select one per symptom (Yes / No / May be).")
        scores = {}
        for s in SYMPTOMS:
            sel = st.radio(s, options=["Yes","No","May be"], horizontal=True, key=f"q_{row['uid']}_{s}")
            scores[s] = sel

        if st.button("Save and Next (Quant)"):
            append_to_gsheet(values_for_sheet_quant(row, display_idx, scores))
            st.success("✅ Saved.")
            # ensure next run sees the new row in Sheets
            st.cache_data.clear()
            st.rerun()

    elif phase == "qual":
        if qual_next >= qual_total:
            st.header("Phase: Qualitative")
            st.success("🎉 You have completed all qualitative items for this set.")
        else:
            row = qual_all.iloc[qual_next]
            display_idx = qual_done + 1
            st.header(f"Qualitative — Case {display_idx} of {qual_total}")
            st.subheader(f"Patient ID: {row['study_id']} • Source: {row.get('source_label','')}")
            st.text_area("Report Text", row["reports_preds"], height=220)

            q1 = st.text_input("Q1. Confidence (1-10)", key=f"qual_q1_{row['uid']}")
            q2 = st.text_area("Q2. Difficult symptoms? (list any)", key=f"qual_q2_{row['uid']}")
            q3 = st.text_area("Q3. Additional info needed? (Yes/No)", key=f"qual_q3_{row['uid']}")
            q4 = st.text_area("Q4. Rationale for key decisions", key=f"qual_q4_{row['uid']}")
            q5 = st.text_area("Q5. Inconsistencies between image & text?", key=f"qual_q5_{row['uid']}")

            if st.button("Save and Next (Qual)"):
                answers = {"q1": q1, "q2": q2, "q3": q3, "q4": q4, "q5": q5}
                append_to_gsheet(values_for_sheet_qual(row, display_idx, answers))
                st.success("✅ Saved.")
                st.cache_data.clear()
                st.rerun()

elif page == "Review Results":
    st.header("📊 Review & Download Survey Results")
    df = load_all_from_gsheet()
    if df.empty:
        st.info("No annotations found yet.")
    else:
        # Keep columns in our preferred order, add any extras at the end
        cols_order = ALL_HEADERS + [c for c in df.columns if c not in ALL_HEADERS]
        df = df.reindex(columns=cols_order)
        st.dataframe(df, use_container_width=True)
        st.download_button(
            "⬇️ Download all annotations as CSV",
            df.to_csv(index=False).encode("utf-8"),
            file_name="survey_results.csv",
            mime="text/csv"
        )
