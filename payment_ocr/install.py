import frappe


REQUIRED_DOCTYPES = ("Patient Encounter", "SR Multi Mode Payment")
REQUIRED_CHILD_FIELDS = (
	"mmp_payment_proof",
	"mmp_paid_amount",
	"mmp_reference_no",
	"mmp_reference_date",
)


def before_install():
	installed_apps = frappe.get_installed_apps()
	if "sriaas_clinic" not in installed_apps:
		frappe.throw("Install sriaas_clinic before installing Payment OCR.")

	for doctype in REQUIRED_DOCTYPES:
		if not frappe.db.exists("DocType", doctype):
			frappe.throw(f"Required DocType not found: {doctype}")

	meta = frappe.get_meta("SR Multi Mode Payment")
	missing_fields = [fieldname for fieldname in REQUIRED_CHILD_FIELDS if not meta.has_field(fieldname)]
	if missing_fields:
		frappe.throw("Missing SR Multi Mode Payment field(s): " + ", ".join(missing_fields))


def after_install():
	if frappe.db.exists("DocType", "Payment OCR Settings"):
		settings = frappe.get_single("Payment OCR Settings")
		if settings.enable_auto_ocr is None:
			settings.enable_auto_ocr = 1
		if not settings.openai_model:
			settings.openai_model = "gpt-4.1-mini"
		if not settings.amount_mismatch_behavior:
			settings.amount_mismatch_behavior = "Warn Only"
		settings.save(ignore_permissions=True)
		frappe.db.commit()
