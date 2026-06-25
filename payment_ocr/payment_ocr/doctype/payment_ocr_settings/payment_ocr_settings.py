import frappe
from frappe.model.document import Document


class PaymentOCRSettings(Document):
	def validate(self):
		if not self.enable_payment_ocr:
			self.enable_auto_ocr = 0
			self.enable_manual_ocr = 0
			self.enable_gateway_verification = 0
			self.enable_partial_gateway_match = 0
			self.use_app_level_gateway_config = 0

		if not self.enable_gateway_verification:
			self.enable_partial_gateway_match = 0
			self.use_app_level_gateway_config = 0
