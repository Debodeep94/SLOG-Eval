# ========================
# === Find common study_ids for qualitative ===
# ========================

common_ids = list(set(data1['study_id']).intersection(set(data2['study_id'])))
if "qual_samples" not in st.session_state:
    st.session_state.qual_samples = random.sample(common_ids, 5)

# ========================
# === Annotate Page ===
# ========================

if page == "Annotate":
    st.sidebar.title("Report Navigator")

    total_reports = len(st.session_state.shuffled_indices)
    current_q = st.sidebar.number_input("Report #", 1, total_reports, 1)

    report_index = st.session_state.shuffled_indices[current_q - 1]
    report = reports[report_index]
    study_id = study_ids[report_index]
    source_file = sources[report_index]

    st.header(f"Patient Report #{current_q} (Study ID: {study_id})")
    st.text_area("Report Text", report, height=200)
    st.image(image_url[report_index], caption=f"Chest X-ray (Study ID {study_id})", use_container_width=True)

    st.subheader("Symptom Evaluation")
    st.write("Please review the report and chest X-ray, then assign a score for each listed symptom.")

    scores = {}
    for symptom in symptoms:
        selected = st.radio(
            label=symptom,
            options=[0, 1, 2],
            horizontal=True,
            key=f"{symptom}_{current_q}"
        )
        scores[symptom] = selected

    if st.button("Save Evaluation"):
        result = {
            "report_number": current_q,
            "report_text": report,
            "study_id": study_id,
            "symptom_scores": scores,
            "annotator": st.session_state.username,
            "source_file": source_file
        }

        os.makedirs("annotations", exist_ok=True)
        filename = f"annotations/report_{study_id}_{st.session_state.username}.json"
        with open(filename, "w") as f:
            json.dump(result, f, indent=2)

        st.success("✅ Evaluation saved successfully!")

        # If last question reached, move to qualitative
        if current_q == total_reports:
            st.session_state.done_main = True
            st.rerun()

# ========================
# === Qualitative Page ===
# ========================

elif page == "Annotate" and st.session_state.get("done_main", False):
    st.header("📝 Qualitative Feedback")

    for i, sid in enumerate(st.session_state.qual_samples, 1):
        st.subheader(f"Qualitative Sample {i} (Study ID: {sid})")
        q1 = st.text_area("How confident do you feel about your overall evaluation of this report?", key=f"q1_{sid}")
        q2 = st.text_area("Were there any symptoms that were particularly difficult to score?", key=f"q2_{sid}")
        q3 = st.text_area("Do you think additional information (like clinical history) would help?", key=f"q3_{sid}")
        q4 = st.text_area("Any other feedback or observations?", key=f"q4_{sid}")

        if st.button(f"Save Feedback {i}", key=f"save_{sid}"):
            feedback = {
                "study_id": sid,
                "annotator": st.session_state.username,
                "q1": q1,
                "q2": q2,
                "q3": q3,
                "q4": q4,
            }
            os.makedirs("qualitative", exist_ok=True)
            with open(f"qualitative/qual_{sid}_{st.session_state.username}.json", "w") as f:
                json.dump(feedback, f, indent=2)
            st.success(f"✅ Feedback for Study ID {sid} saved!")

# ========================
# === Review Qualitative ===
# ========================

elif page == "Review Results":
    st.header("📊 Review & Download Results")

    # Normal results
    files = glob.glob("annotations/*.json")
    if files:
        all_records = [json.load(open(f)) for f in files]
        df = pd.json_normalize(all_records)
        st.subheader("Annotation Results")
        st.dataframe(df)
        st.download_button("⬇️ Download Annotations CSV",
                           df.to_csv(index=False).encode("utf-8"),
                           file_name="survey_results.csv",
                           mime="text/csv")

    # Qualitative results
    qfiles = glob.glob("qualitative/*.json")
    if qfiles:
        qual_records = [json.load(open(f)) for f in qfiles]
        qdf = pd.DataFrame(qual_records)
        st.subheader("Qualitative Feedback Results")
        st.dataframe(qdf)
        st.download_button("⬇️ Download Qualitative CSV",
                           qdf.to_csv(index=False).encode("utf-8"),
                           file_name="qualitative_results.csv",
                           mime="text/csv")
