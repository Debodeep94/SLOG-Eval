import streamlit as st
import pandas as pd
import json
import os
import glob
from typing import List

# === CONFIG ===
SYMPTOMS: List[str] = [
    'Atelectasis','Cardiomegaly','Consolidation','Edema',
    'Enlarged Cardiomediastinum','Fracture','Lung Lesion',
    'Lung Opacity','No Finding','Pleural Effusion','Pleural Other',
    'Pneumonia','Pneumothorax','Support Devices'
]
QUANT_TARGET_REPORTS = 60   # number of patient reports (questions) in quantitative phase
NUM_QUAL_STUDY_IDS = 5      # number of study_ids to reserve (both df1 & df2) for qualitative

# === Credentials from secrets.toml ===
USERS = st.secrets["credentials"]

# === Session state defaults ===
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "phase" not in st.session_state:
    st.session_state.phase = "quant"  # phases: "quant" then "qual"
if "current_index" not in st.session_state:
    st.session_state.current_index = 0  # index within current phase

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
    # Load original dataframes
    df1 = pd.read_csv("selected_samples.csv")
    df1["source_file"] = "selected_samples.csv"
    df1["source_label"] = "df1"

    df2 = pd.read_csv("selected_samples00.csv")
    df2["source_file"] = "selected_samples00.csv"
    df2["source_label"] = "df2"

    # Basic sanity checks
    required_cols = {"study_id", "reports_preds"}
    if not required_cols.issubset(df1.columns) or not required_cols.issubset(df2.columns):
        st.error(f"Missing required columns in input files. Required: {required_cols}")
        st.stop()

    # find study_ids present in both
    common_ids = pd.Index(df1["study_id"]).intersection(pd.Index(df2["study_id"]))
    if len(common_ids) == 0:
        st.error("No overlapping study_id values between selected_samples.csv and selected_samples00.csv")
        st.stop()

    # Deterministic per-user seed so the same user resumes the same split
    user_seed = abs(hash(st.session_state.username)) % (2**32)

    # Sample NUM_QUAL_STUDY_IDS from common_ids for qualitative (if available)
    n_pick = min(NUM_QUAL_STUDY_IDS, len(common_ids))
    chosen_ids = pd.Series(common_ids).sample(n=n_pick, random_state=user_seed).tolist()

    # Build qualitative (paired) set: both df1 and df2 rows for chosen_ids
    df1_qual = df1[df1["study_id"].isin(chosen_ids)].copy()
    df2_qual = df2[df2["study_id"].isin(chosen_ids)].copy()
    qual_df = pd.concat([df1_qual, df2_qual], ignore_index=True)
    # create uid
    qual_df["uid"] = qual_df["study_id"].astype(str) + "__" + qual_df["source_label"]

    # Build pool for quantitative: everything except the qual rows
    df1_pool = df1[~df1["study_id"].isin(chosen_ids)].copy()
    df2_pool = df2[~df2["study_id"].isin(chosen_ids)].copy()
    pool_df = pd.concat([df1_pool, df2_pool], ignore_index=True)
    pool_df["uid"] = pool_df["study_id"].astype(str) + "__" + pool_df["source_label"]

    # shuffle pool deterministically per user
    pool_df = pool_df.sample(frac=1, random_state=user_seed).reset_index(drop=True)

    # pick first QUANT_TARGET_REPORTS rows for quantitative. If not enough rows available, use all.
    if len(pool_df) < QUANT_TARGET_REPORTS:
        st.warning(f"Pool only has {len(pool_df)} reports available (less than requested {QUANT_TARGET_REPORTS}). Using {len(pool_df)} for quantitative.")
    quant_df = pool_df.iloc[:min(QUANT_TARGET_REPORTS, len(pool_df))].reset_index(drop=True)

    # Final lists
    st.session_state.quant_df = quant_df
    st.session_state.qual_df = qual_df.reset_index(drop=True)
    st.session_state.prepared = True

    # Create dirs
    os.makedirs("annotations/quant", exist_ok=True)
    os.makedirs("annotations/qual", exist_ok=True)

    # Resume logic: count how many quant/qual files user already saved
    user = st.session_state.username
    quant_done = len(glob.glob(f"annotations/quant/*_{user}.json"))
    qual_done = len(glob.glob(f"annotations/qual/*_{user}.json"))

    if quant_done >= len(st.session_state.quant_df):
        st.session_state.phase = "qual"
        st.session_state.current_index = qual_done
    else:
        st.session_state.phase = "quant"
        st.session_state.current_index = quant_done

# Shortcuts
quant_df: pd.DataFrame = st.session_state.quant_df
qual_df: pd.DataFrame = st.session_state.qual_df
phase = st.session_state.phase
idx = st.session_state.current_index

# === Sidebar & nav ===
st.sidebar.success(f"Logged in as {st.session_state.username}")
if st.session_state.username == "admin":
    st.sidebar.warning("⚠️ Admin mode: You can review all annotations.")
    pages = ["Annotate", "Review Results"]
else:
    pages = ["Annotate"]
page = st.sidebar.radio("📂 Navigation", pages)

# Helper to get row safely
def row_safe(df, i):
    if i < 0 or i >= len(df):
        return None
    return df.iloc[i]

# === Annotate page ===
if page == "Annotate":
    if phase == "quant":
        total_quant = len(quant_df)
        if total_quant == 0:
            st.error("No reports available for quantitative phase (after reserving qualitative pairs).")
        else:
            # show progress as Patient Report X of 60
            display_idx = idx + 1
            st.header(f"Patient Report {display_idx} of {total_quant} - ID: {quant_df.at[idx, 'study_id'] if idx < total_quant else 'N/A'}")
            row = row_safe(quant_df, idx)
            if row is None:
                st.info("Quantitative phase complete. Moving to qualitative...")
                # switch
                st.session_state.phase = "qual"
                st.session_state.current_index = len(glob.glob(f"annotations/qual/*_{st.session_state.username}.json"))
                st.rerun()

            report_text = row["reports_preds"]
            study_id = row["study_id"]
            source_file = row.get("source_file", "")
            source_label = row.get("source_label", "")

            st.text_area("Report Text (quantitative phase — no image shown)", report_text, height=220)

            st.subheader("Symptom Evaluation")
            st.write(
                "Please review the report, then assign a score for each listed symptom. "
                "Please note, you must assign a score for every symptom before proceeding.\n\n"
                
                "Use the following coding scheme:\n\n"
                "- **Yes** = Assured presence\n"
                "- **No** = Assured absence\n"
                "- **May be** = Ambiguous / uncertain\n\n"
                "The 'Assured presence' (Yes) option should be selected only when the report explicitly confirms the presence of the symptom.\n\n "
                "If the report does not mention the symptom or indicates its absence, select 'Assured absence' (No). \n\n"
                "If the report is ambiguous or does not provide enough information to determine the presence or absence of the symptom, select 'Ambiguous / uncertain' (May be).\n\n"
                )

            scores = {}
            for symptom in SYMPTOMS:
                selected = st.radio(
                    label=symptom,
                    options=[0, 1, 2],
                    horizontal=True,
                    key=f"quant_{idx}_{symptom}"
                )
                scores[symptom] = selected

            if st.button("Save and Next (Quant)"):
                result = {
                    "phase": "quant",
                    "report_number_in_quant": display_idx,
                    "study_id": study_id,
                    "report_text": report_text,
                    "symptom_scores": scores,
                    "annotator": st.session_state.username,
                    "source_file": source_file,
                    "source_label": source_label,
                }
                out_path = f"annotations/quant/{row['uid']}_{st.session_state.username}.json"
                with open(out_path, "w") as f:
                    json.dump(result, f, indent=2)
                st.success("✅ Saved quantitative annotation.")

                # advance
                st.session_state.current_index += 1

                # if completed quant target, switch to qual
                if st.session_state.current_index >= len(quant_df):
                    st.session_state.phase = "qual"
                    st.session_state.current_index = len(glob.glob(f"annotations/qual/*_{st.session_state.username}.json"))
                st.rerun()

    elif phase == "qual":
        total_qual = len(qual_df)
        if total_qual == 0:
            st.info("No qualitative paired cases reserved.")
        else:
            if idx >= total_qual:
                st.header("Phase: Qualitative")
                st.info("🎉 You have completed all qualitative items for this set.")
            else:
                # show qualitative item: here we show image + report + qualitative questions
                row = row_safe(qual_df, idx)
                study_id = row["study_id"]
                source_file = row.get("source_file", "")
                source_label = row.get("source_label", "")
                report_text = row["reports_preds"]
                img_path = row.get("paths", None)

                st.header(f"Qualitative — Case {idx+1} of {total_qual}")
                st.subheader(f"Patient ID: {study_id}  •  source: {source_label}")
                if img_path and str(img_path).strip() != "":
                    st.image(img_path, caption=f"CXR — study {study_id}", use_container_width=True)
                else:
                    st.info("No image path available for this case.")

                st.text_area("Report Text", report_text, height=220)

                # Qualitative questions (q1 user requested + extras)
                q1 = st.text_input("Q1. How confident do you feel about your overall evaluation of this report? (1-10)", key=f"q1_{idx}")
                q2 = st.text_area("Q2. Were there any symptoms that were particularly difficult to score?",SYMPTOMS, key=f"q2_{idx}\n\n")
                q3 = st.text_area("Q3. Do you think additional information (like clinical history) would help?", key=f"q3_{idx}")
                q4 = st.text_area("Q4. Briefly explain the rationale behind your key decisions.", key=f"q4_{idx}")
                q5 = st.text_area("Q5. Did you notice any inconsistencies between the image and the report text? If yes, describe.", key=f"q5_{idx}")
                

                # Qualitative survey
    # st.subheader("Qualitative Feedback")
    # q1 = st.text_area("How confident do you feel about your overall evaluation of this report?")
    # q2 = st.text_area("Were there any symptoms that were particularly difficult to score? Why?")
    # q3 = st.text_area("Do you think additional information (like clinical history) would help?")
    # q4 = st.text_area("Any other feedback or observations?")

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
                        "annotator": st.session_state.username,
                        "source_file": source_file,
                        "source_label": source_label,
                    }
                    out_path = f"annotations/qual/{row['uid']}_{st.session_state.username}.json"
                    with open(out_path, "w") as f:
                        json.dump(result, f, indent=2)
                    st.success("✅ Saved qualitative annotation.")
                    st.session_state.current_index += 1
                    st.rerun()

# === Review Results page ===
elif page == "Review Results":
    st.header("📊 Review & Download Survey Results")
    quant_files = glob.glob("annotations/quant/*.json")
    qual_files = glob.glob("annotations/qual/*.json")

    if not quant_files and not qual_files:
        st.info("No annotations found yet.")
    else:
        records = []
        for f in quant_files + qual_files:
            with open(f) as infile:
                records.append(json.load(infile))
        df = pd.json_normalize(records)
        st.dataframe(df)
        st.download_button(
            "⬇️ Download all annotations as CSV",
            df.to_csv(index=False).encode("utf-8"),
            file_name="survey_results.csv",
            mime="text/csv"
        )
