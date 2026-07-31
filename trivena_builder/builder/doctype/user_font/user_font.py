# Copyright (c) 2024, Frappe Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import trivena_framework as trivena
from trivena_framework.model.document import Document
from trivena_framework.utils.caching import redis_cache


@redis_cache(ttl=60 * 60)
def get_all_user_fonts() -> list:
	return trivena.get_all("User Font", fields=["font_name", "font_file"])


class UserFont(Document):
	def after_insert(self):
		get_all_user_fonts.clear_cache()

	def on_update(self):
		get_all_user_fonts.clear_cache()

	def on_trash(self):
		get_all_user_fonts.clear_cache()
