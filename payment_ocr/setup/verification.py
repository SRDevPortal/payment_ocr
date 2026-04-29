import frappe

from .utils import create_cf_with_module


DT = "SR Multi Mode Payment"


def apply():
	_make_payment_verification_fields()


def _make_payment_verification_fields():
	if not frappe.db.exists("DocType", DT):
		return

	create_cf_with_module(
		{
			DT: [
				{
					"fieldname": "mmp_payment_verification_section",
					"fieldtype": "Section Break",
					"label": "Payment Verification",
					"insert_after": "mmp_reference_date",
				},
				{
					"fieldname": "mmp_payment_verification_status",
					"fieldtype": "Select",
					"label": "Verification Status",
					"options": "Unverified\nPending\nVerified\nPartial Matched\nAmount Mismatch\nDuplicate\nFailed",
					"default": "Unverified",
					"insert_after": "mmp_payment_verification_section",
					"read_only": 1,
				},
				{
					"fieldname": "mmp_verified_transaction_id",
					"fieldtype": "Data",
					"label": "Verified Transaction ID",
					"insert_after": "mmp_payment_verification_status",
					"read_only": 1,
				},
				{
					"fieldname": "mmp_verified_amount",
					"fieldtype": "Currency",
					"label": "Verified Amount",
					"insert_after": "mmp_verified_transaction_id",
					"read_only": 1,
				},
				{
					"fieldname": "mmp_verified_date",
					"fieldtype": "Date",
					"label": "Verified Date",
					"insert_after": "mmp_verified_amount",
					"read_only": 1,
				},
				{
					"fieldname": "mmp_verified_payer",
					"fieldtype": "Data",
					"label": "Verified Payer",
					"insert_after": "mmp_verified_date",
					"read_only": 1,
				},
				{
					"fieldname": "mmp_verified_source",
					"fieldtype": "Data",
					"label": "Verified Source",
					"insert_after": "mmp_verified_payer",
					"read_only": 1,
				},
				{
					"fieldname": "mmp_verified_at",
					"fieldtype": "Datetime",
					"label": "Verified At",
					"insert_after": "mmp_verified_source",
					"read_only": 1,
				},
				{
					"fieldname": "mmp_verification_note",
					"fieldtype": "Small Text",
					"label": "Verification Note",
					"insert_after": "mmp_verified_at",
					"read_only": 1,
				},
			]
		}
	)
