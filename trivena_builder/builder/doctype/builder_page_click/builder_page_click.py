# Copyright (c) 2026, Frappe Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import trivena_framework as trivena
from trivena_framework.model.document import Document


class BuilderPageClick(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from trivena_framework.types import DF

		element: DF.Data | None
		is_unique: DF.Check
		path: DF.Data | None
		text: DF.Data | None
		visitor_id: DF.Data | None
	# end: auto-generated types

	@staticmethod
	def clear_old_logs(days=180):
		from trivena_framework.query_builder import Interval
		from trivena_framework.query_builder.functions import Now

		table = trivena.qb.DocType("Builder Page Click")
		trivena.db.delete(table, filters=(table.creation < (Now() - Interval(days=days))))
