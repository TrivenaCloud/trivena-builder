import trivena_framework as trivena
from trivena_framework.integrations.frappe_providers.frappecloud_billing import is_fc_site
from trivena_framework.pulse.utils import get_app_version
from trivena_framework.utils.telemetry import capture

from trivena_builder.hooks import builder_path

no_cache = 1


def get_context(context):
	csrf_token = trivena.sessions.get_csrf_token()
	trivena.db.commit()
	context.csrf_token = csrf_token
	context.site_name = trivena.local.site
	context.builder_path = builder_path
	context.builder_version = get_app_version("trivena_builder")
	# developer mode
	context.is_developer_mode = trivena.conf.developer_mode
	context.is_fc_site = is_fc_site()
	context.is_read_only_mode = bool(trivena.flags.read_only)
	if trivena.session.user != "Guest":
		capture("active_site", "trivena_builder")
