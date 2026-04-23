frappe.ui.form.on("Patient Encounter", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		frm.add_custom_button(__("Read Payment Proofs"), () => {
			frappe.call({
				method: "payment_ocr.api.process_patient_encounter",
				args: {
					encounter_name: frm.doc.name,
				},
				freeze: true,
				freeze_message: __("Reading payment proofs..."),
				callback(r) {
					const results = r.message || [];
					const mismatches = results.filter(
						(row) => row.amount_match_status === "Mismatched"
					);
					const failed = results.filter((row) => row.status === "Failed");
					const duplicates = results.filter((row) => row.duplicate_log_name);

					if (duplicates.length) {
						frappe.msgprint({
							title: __("Duplicate Payment Proof"),
							indicator: "red",
							message: __(
								"Duplicate payment proof was found in {0} row(s). Duplicate attachment was removed, and reference number/date were left blank.",
								[duplicates.length]
							),
						});
					} else if (mismatches.length) {
						frappe.msgprint({
							title: __("Payment OCR Warning"),
							indicator: "orange",
							message: __(
								"Payment OCR completed, but amount mismatch was found in {0} row(s). Please verify paid amount manually.",
								[mismatches.length]
							),
						});
					} else if (failed.length) {
						frappe.msgprint({
							title: __("Payment OCR Failed"),
							indicator: "red",
							message: __("{0} payment proof row(s) could not be processed.", [
								failed.length,
							]),
						});
					} else {
						frappe.show_alert({
							message: __("Payment OCR completed"),
							indicator: "green",
						});
					}

					frm.reload_doc();
				},
			});
		});
	},
});
