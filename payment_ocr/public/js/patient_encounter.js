frappe.ui.form.on("Patient Encounter", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		frappe.call({
			method: "payment_ocr.api.ocr.get_ocr_availability",
			callback(r) {
				if (r.message && r.message.manual_ocr_enabled) {
					add_read_payment_proofs_button(frm);
				}
			},
		});

		frm.add_custom_button(__("Verify Payment Receipts"), () => {
			frappe.call({
				method: "payment_ocr.api.gateway.reconcile_patient_encounter_payment_verifications",
				args: {
					encounter_name: frm.doc.name,
				},
				freeze: true,
				freeze_message: __("Verifying payment receipts..."),
				callback(r) {
					const results = r.message || [];
					const verified = results.filter(
						(row) => row.verification_status === "Verified"
					);
					const partials = results.filter(
						(row) => row.verification_status === "Partial Matched"
					);
					const pending = results.filter((row) => row.verification_status === "Pending");
					const mismatches = results.filter(
						(row) => row.verification_status === "Amount Mismatch"
					);
					const duplicates = results.filter(
						(row) => row.verification_status === "Duplicate"
					);

					if (duplicates.length || mismatches.length) {
						frappe.msgprint({
							title: __("Payment Verification Warning"),
							indicator: "red",
							message: __(
								"{0} duplicate and {1} amount mismatch payment row(s) need review.",
								[duplicates.length, mismatches.length]
							),
						});
					} else if (pending.length) {
						frappe.msgprint({
							title: __("Payment Verification Pending"),
							indicator: "orange",
							message: __("{0} payment row(s) are still pending gateway receipt.", [
								pending.length,
							]),
						});
					} else if (partials.length) {
						frappe.msgprint({
							title: __("Payment Partially Matched"),
							indicator: "orange",
							message: __(
								"{0} payment row(s) verified and {1} payment row(s) partially matched.",
								[verified.length, partials.length]
							),
						});
					} else {
						frappe.show_alert({
							message: __("{0} payment row(s) verified", [verified.length]),
							indicator: "green",
						});
					}

					frm.reload_doc();
				},
			});
		});
	},
});

function add_read_payment_proofs_button(frm) {
	frm.add_custom_button(__("Read Payment Proofs"), () => {
		frappe.call({
			method: "payment_ocr.api.ocr.process_patient_encounter",
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
}
