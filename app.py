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

    # === Qualitative survey questions ===
    st.subheader("Qualitative Feedback")

    q1 = st.text_area("📝 How confident do you feel about your overall evaluation of this report?")
    q2 = st.text_area("🤔 Were there any symptoms that were particularly difficult to score? Why?")
    q3 = st.text_area("💡 Do you think additional information (like clinical history) would help?")
    q4 = st.text_area("📌 Any other feedback or observations?")

    if st.button("Save Evaluation"):
        result = {
            "report_id": report_index,
            "report_text": report,
            "symptom_scores": scores,
            "qualitative": {
                "confidence": q1,
                "difficult_symptoms": q2,
                "extra_info_needed": q3,
                "other_feedback": q4,
            },
            "annotator": st.session_state.username
        }
        os.makedirs("annotations", exist_ok=True)
        with open(f"annotations/report_{report_index}_{st.session_state.username}.json", "w") as f:
            json.dump(result, f, indent=2)
        st.success("✅ Evaluation saved successfully!")
