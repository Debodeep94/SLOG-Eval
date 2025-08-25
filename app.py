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

# === Data load ===
data = pd.read_csv('selected_samples.csv')
reports = data['reports_preds'].tolist()
image_url = data['paths'].tolist()

symptoms = [
    'Atelectasis','Cardiomegaly','Consolidation','Edema',
    'Enlarged Cardiomediastinum','Fracture','Lung Lesion',
    'Lung Opacity','No Finding','Pleural Effusion','Pleural Other',
    'Pneumonia','Pneumothorax','Support Devices'
]

# === Annotate page ===
if page == "Annotate":
    st.sidebar.title("Report Navigator")
    report_index = st.sidebar.selectbox("Select Report", range(1,31))
    report = reports[report_index-1]

    st.header(f"Patient Report #{report_index}")
    st.text_area("Report Text", report, height=200)

    st.image(image_url[report_index-1], caption=f"Chest X-ray #{report_index}", use_container_width=True)

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

    if st.button("Save Evaluation"):
        result = {
            "report_id": report_index,
            "report_text": report,
            "symptom_scores": scores,
            "annotator": st.session_state.username
        }
        os.makedirs("annotations", exist_ok=True)
        with open(f"annotations/report_{report_index}_{st.session_state.username}.json", "w") as f:
            json.dump(result, f, indent=2)
        st.success("✅ Evaluation saved successfully!")

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

        # 🔑 If admin, show all. Otherwise, filter to own responses.
        if st.session_state.username != "admin":
            df = df[df["annotator"] == st.session_state.username]

        st.dataframe(df)

        st.download_button(
            "⬇️ Download your annotations" if st.session_state.username != "admin" else "⬇️ Download all annotations as CSV",
            df.to_csv(index=False).encode("utf-8"),
            file_name=f"survey_results_{st.session_state.username}.csv" if st.session_state.username != "admin" else "survey_results_all.csv",
            mime="text/csv"
        )
    else:
        st.info("No annotations found yet.")
