# Copyright (c) 2024, Frappe Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import trivena_framework as trivena
from trivena_framework.model.document import Document


class BuilderProjectFolder(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from trivena_framework.types import DF

		folder_name: DF.Data | None
		is_standard: DF.Check
	# end: auto-generated types

	def validate(self):
		"""Validate that standard folders cannot be edited if not in developer mode"""
		if self.is_standard and not trivena.conf.get("developer_mode"):
			if not is_system_activity():
				trivena.throw(
					trivena._(
						"Standard folders cannot be modified. Please enable developer mode to edit standard folders."
					),
					trivena.PermissionError,
				)

	def on_trash(self):
		"""Prevent deletion of standard folders when not in developer mode"""
		if self.is_standard and not trivena.conf.get("developer_mode"):
			if not is_system_activity():
				trivena.throw(
					trivena._(
						"Standard folders cannot be deleted. Please enable developer mode to delete standard folders."
					),
					trivena.PermissionError,
				)


def is_system_activity():
	return (
		trivena.flags.in_import
		or trivena.flags.in_patch
		or trivena.flags.in_migrate
		or trivena.in_test
		or trivena.flags.in_install
	)
