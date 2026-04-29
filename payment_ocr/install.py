import frappe

from payment_ocr.setup.runner import setup_all


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
	setup_all()
	frappe.db.commit()


def after_migrate():
	setup_all()
