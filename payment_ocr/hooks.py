app_name = "payment_ocr"
app_title = "Payment OCR"
app_publisher = "SRIAAS"
app_description = "Payment proof OCR for Patient Encounter payment rows"
app_email = "webdevelopersriaas@gmail.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "payment_ocr",
# 		"logo": "/assets/payment_ocr/logo.png",
# 		"title": "Payment OCR",
# 		"route": "/payment_ocr",
# 		"has_permission": "payment_ocr.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/payment_ocr/css/payment_ocr.css"
# app_include_js = "/assets/payment_ocr/js/payment_ocr.js"

# include js, css files in header of web template
# web_include_css = "/assets/payment_ocr/css/payment_ocr.css"
# web_include_js = "/assets/payment_ocr/js/payment_ocr.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "payment_ocr/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "payment_ocr/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "payment_ocr.utils.jinja_methods",
# 	"filters": "payment_ocr.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "payment_ocr.install.before_install"
before_install = "payment_ocr.install.before_install"
after_install = "payment_ocr.install.after_install"
after_migrate = "payment_ocr.install.after_migrate"

# Uninstallation
# ------------

# before_uninstall = "payment_ocr.uninstall.before_uninstall"
# after_uninstall = "payment_ocr.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "payment_ocr.utils.before_app_install"
# after_app_install = "payment_ocr.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "payment_ocr.utils.before_app_uninstall"
# after_app_uninstall = "payment_ocr.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "payment_ocr.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Patient Encounter": {
		"on_update": "payment_ocr.handlers.on_update_patient_encounter",
		"after_insert": "payment_ocr.handlers.after_insert_patient_encounter",
	}
}

doctype_js = {
	"Patient Encounter": "public/js/patient_encounter.js",
}

fixtures = [
	{"dt": "Custom Field", "filters": [["module", "=", "Payment OCR"]]},
]

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"payment_ocr.tasks.all"
# 	],
# 	"daily": [
# 		"payment_ocr.tasks.daily"
# 	],
# 	"hourly": [
# 		"payment_ocr.tasks.hourly"
# 	],
# 	"weekly": [
# 		"payment_ocr.tasks.weekly"
# 	],
# 	"monthly": [
# 		"payment_ocr.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "payment_ocr.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "payment_ocr.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "payment_ocr.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["payment_ocr.utils.before_request"]
# after_request = ["payment_ocr.utils.after_request"]

# Job Events
# ----------
# before_job = ["payment_ocr.utils.before_job"]
# after_job = ["payment_ocr.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"payment_ocr.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
