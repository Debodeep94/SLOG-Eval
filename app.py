import streamlit as st
import pandas as pd
import json
import os
import glob
import random

# === Credentials from secrets.toml ===
# Ensure you have a .streamlit/secrets.toml file with your credentials
# Example:
# [credentials]
# user1 = "pass1"
# user2 = "pass2"
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

# === Data load with normalization ===
def normalize(df):
    if "reports_preds" in df.columns:
        df = df.rename(columns={"reports_preds": "report"})
    elif "report_text" in df.columns:
        df = df.rename(columns={"report_text": "report"})
    else:
        # Fallback if no specific column is found
        if "report" not in df.columns:
            raise ValueError("No 'report', 'reports_preds', or 'report_text' column found in the CSV.")
    return df

# Wrap data loading in a cached function to improve performance
@st.cache_data
def load_data():
    data1 = normalize(pd.read_csv("selected_samples.csv"))
    data2 = normalize(pd.read_csv("selected_samples00.csv"))

    # Merge for annotation
    data = pd.concat(
        [data1.assign(source_file="selected_samples.csv"),
         data2.assign(source_file="selected_samples00.csv")],
        ignore_index=True
    )
    return data

data = load_data()

# Pick common study_ids for qualitative feedback
if "qual_samples" not in st.session_state:
    data1_ids = set(data[data['source_file'] == 'selected_samples.csv']['study_id'])
    data2_ids = set(data[data['source_file'] == 'selected_samples00.csv']['study_id'])
    common_ids = list(data1_ids.intersection(data2_ids))
    
    if len(common_ids) >= 5:
        st.session_state.qual_samples = random.sample(common_ids, 5)
    else:
        st.session_state.qual_samples = common_ids

# Shuffle reports once per session
if "shuffled_data" not in st.session_state:
    st.session_state.shuffled_data = data.sample(frac=1, random_state=42).reset_index(drop=True)

# Initialize session state variables
if "report_index" not in st.session_state:
    st.session_state.report_index = 0
if "annotations" not in st.session_state:
    st.session_state.annotations = {} # To hold annotations during the session

symptoms = [
    'Atelectasis', 'Cardiomegaly', 'Consolidation', 'Edema',
    'Enlarged Cardiomediastinum', 'Fracture', 'Lung Lesion',
    'Lung Opacity', 'No Finding', 'Pleural Effusion', 'Pleural Other',
    'Pneumonia', 'Pneumothorax', 'Support Devices'
]

# === Annotate page ===
if page == "Annotate":
    num_reports = len(st.session_state.shuffled_data)

    if st.session_state.report_index < num_reports:
        # Get current report details
        row = st.session_state.shuffled_data.iloc[st.session_state.report_index]
        report_index_display = st.session_state.report_index + 1  # For user display (1-based)
        study_id = row["study_id"]
        report = row["report"]
        source = row["source_file"]

        # --- Display Progress ---
        st.progress(
            (st.session_state.report_index) / num_reports,
            text=f"Progress: {report_index_display} / {num_reports}"
        )

        st.header(f"Patient Report #{report_index_display} (Study {study_id})")
        st.text_area("Report Text", report, height=200, key=f"report_text_{study_id}")

        st.subheader("Symptom Evaluation")
        
        # --- Load saved annotations for this report if they exist ---
        current_annotations = st.session_state.annotations.get(study_id, {})
        saved_scores = current_annotations.get("symptom_scores", {})
        
        scores = {}
        for symptom in symptoms:
            # Use saved score as the default index for the radio button
            default_index = saved_scores.get(symptom, 0)
            selected = st.radio(
                label=symptom,
                options=[0, 1, 2],
                index=default_index,
                horizontal=True,
                key=f"symptom_{symptom}_{study_id}" # Unique key per symptom and study
            )
            scores[symptom] = selected

        # === Qualitative section for selected studies ===
        qualitative = {}
        if study_id in st.session_state.qual_samples:
            st.subheader("📝 Qualitative Feedback")
            saved_qual = current_annotations.get("qualitative", {})
            
            qualitative["confidence"] = st.text_area(
                "How confident do you feel about your overall evaluation of this report?",
                value=saved_qual.get("confidence", ""),
                key=f"q1_{study_id}"
            )
            qualitative["difficult_symptoms"] = st.text_area(
                "Were there any symptoms that were particularly difficult to score?",
                value=saved_qual.get("difficult_symptoms", ""),
                key=f"q2_{study_id}"
            )
            qualitative["extra_info_needed"] = st.text_area(
                "Do you think additional information (like clinical history) would help?",
                value=saved_qual.get("extra_info_needed", ""),
                key=f"q3_{study_id}"
            )
            qualitative["other_feedback"] = st.text_area(
                "Any other feedback or observations?",
                value=saved_qual.get("other_feedback", ""),
                key=f"q4_{study_id}"
            )

        # --- Navigation Buttons ---
        col1, col2 = st.columns([1, 1])

        with col1:
            if st.button("⬅️ Previous", use_container_width=True, disabled=(st.session_state.report_index == 0)):
                st.session_state.report_index -= 1
                st.rerun()

        with col2:
            if st.button("Next ➡️", use_container_width=True):
                # Save current selections to session state
                st.session_state.annotations[study_id] = {
                    "symptom_scores": scores,
                    "qualitative": qualitative,
                }
                
                # Save result to a JSON file
                result = {
                    "report_id": report_index_display,
                    "study_id": study_id,
                    "report_text": report,
                    "symptom_scores": scores,
                    "qualitative": qualitative,
                    "annotator": st.session_state.username,
                    "source_file": source
                }
                os.makedirs("annotations", exist_ok=True)
                filename = f"annotations/report_{study_id}_{st.session_state.username}.json"
                with open(filename, "w") as f:
                    json.dump(result, f, indent=2)

                # Move to the next report
                st.session_state.report_index += 1
                st.rerun()
    else:
        st.success("🎉 You have completed all annotations!")
        st.balloons()

# === Review Results page ===
elif page == "Review Results":
    st.header("📊 Review & Download Survey Results")
    files = glob.glob("annotations/*.json")
    if files:
        all_records = []
        for f in files:
            with open(f, 'r') as infile:
                all_records.append(json.load(infile))

        rows = []
        for r in all_records:
            row_data = {
                "report_id": r.get("report_id"),
                "study_id": r.get("study_id"),
                "annotator": r.get("annotator"),
                "source_file": r.get("source_file"),
                "report_text": r.get("report_text"),
            }
            # Add symptom scores
            row_data.update(r.get("symptom_scores", {}))
            
            # Add qualitative feedback safely
            qual_feedback = r.get("qualitative", {})
            row_data["confidence"] = qual_feedback.get("confidence", "")
            row_data["difficult_symptoms"] = qual_feedback.get("difficult_symptoms", "")
            row_data["extra_info_needed"] = qual_feedback.get("extra_info_needed", "")
            row_data["other_feedback"] = qual_feedback.get("other_feedback", "")
            
            rows.append(row_data)

        # Create and display DataFrame
        df = pd.DataFrame(rows)
        st.dataframe(df)

        # --- Download Button ---
        @st.cache_data
        def convert_df_to_csv(df_to_convert):
            return df_to_convert.to_csv(index=False).encode('utf-8')

        csv = convert_df_to_csv(df)

        st.download_button(
            label="📥 Download results as CSV",
            data=csv,
            file_name='annotations_summary.csv',
            mime='text/csv',
        )

    else:
        st.warning("No annotation files found yet.")