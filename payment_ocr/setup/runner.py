from . import settings, verification


def setup_all():
	verification.apply()
	settings.apply()
