frappe.ui.form.on("Payment OCR Settings", {
	onload(frm) {
		setup_autofill_guard(frm);
	},

	refresh(frm) {
		setup_autofill_guard(frm);
	},

	textract_access_key_id(frm) {
		disable_autofill(frm);
	},

	textract_secret_access_key(frm) {
		disable_autofill(frm);
	},

	openai_api_key(frm) {
		disable_autofill(frm);
	},

	gateway_webhook_secret(frm) {
		disable_autofill(frm);
	},
});

function setup_autofill_guard(frm) {
	disable_autofill(frm);

	if (frm.__payment_ocr_autofill_guard) {
		return;
	}

	frm.__payment_ocr_autofill_guard = true;
	const wrapper = frm && frm.wrapper ? frm.wrapper[0] || frm.wrapper : null;

	if (wrapper && window.MutationObserver) {
		const observer = new MutationObserver(() => disable_autofill(frm));
		observer.observe(wrapper, {
			childList: true,
			subtree: true,
		});
		frm.__payment_ocr_autofill_observer = observer;
	}

	[100, 500, 1000, 2000].forEach((delay) => {
		setTimeout(() => disable_autofill(frm), delay);
	});
}

function disable_autofill(frm) {
	const $wrapper = frm && frm.wrapper ? $(frm.wrapper) : $(".form-page");
	const $fields = $wrapper.find("input, textarea, select");

	$fields.each(function () {
		const $field = $(this);
		const type = String($field.attr("type") || "").toLowerCase();
		const fieldname = get_fieldname($field);
		const is_editable_text = ["", "email", "number", "password", "search", "tel", "text", "url"].includes(type)
			|| this.tagName.toLowerCase() === "textarea";

		$field.attr({
			autocomplete: "new-password",
			autocapitalize: "off",
			autocorrect: "off",
			"data-1p-ignore": "true",
			"data-bwignore": "true",
			"data-form-type": "other",
			"data-lpignore": "true",
			"data-protonpass-ignore": "true",
			spellcheck: "false",
		});

		if (fieldname && !$field.attr("data-payment-ocr-original-name")) {
			$field.attr("data-payment-ocr-original-name", $field.attr("name") || "");
			$field.attr("name", `payment_ocr_no_autofill_${fieldname}_${get_random_suffix()}`);
		}

		if (is_editable_text && !$field.is(":focus")) {
			$field.attr("readonly", "readonly");
			$field.one("focus mousedown keydown touchstart", function () {
				$(this).removeAttr("readonly");
			});
		}
	});

	$wrapper.find("form").attr({
		autocomplete: "off",
		"data-form-type": "other",
	});
}

function get_fieldname($field) {
	return (
		$field.attr("data-fieldname")
		|| $field.closest("[data-fieldname]").attr("data-fieldname")
		|| $field.closest(".frappe-control").attr("data-fieldname")
	);
}

function get_random_suffix() {
	return Math.random().toString(36).slice(2, 10);
}
