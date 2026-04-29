from frappe.custom.doctype.custom_field.custom_field import create_custom_fields as _create_custom_fields


MODULE_DEF_NAME = "Payment OCR"


def create_cf_with_module(mapping: dict, module: str = MODULE_DEF_NAME):
	for fields in mapping.values():
		for field in fields:
			field.setdefault("module", module)

	_create_custom_fields(mapping, ignore_validate=True)
