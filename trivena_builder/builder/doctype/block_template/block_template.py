# Copyright (c) 2024, Frappe Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import json
import os
import shutil

import trivena_framework as trivena
from trivena_framework import _
from trivena_framework.model.document import Document
from trivena_framework.modules import scrub
from trivena_framework.modules.export_file import export_to_files

from trivena_builder.utils import copy_img_to_asset_folder, get_template_assets_folder_path


class BlockTemplate(Document):
	def on_update(self):
		if not self.preview:
			trivena.throw(_("Preview Image is mandatory"))

		files = trivena.get_all("File", filters={"file_url": self.preview}, fields=["name"])
		if files:
			_file = trivena.get_doc("File", files[0].name)
			# block-template thumbnails always live in builder, never the template hub app
			assets_folder_path = get_template_assets_folder_path(self, app="trivena_builder")
			shutil.copy(_file.get_full_path(), assets_folder_path)
			self.preview = f"/builder_assets/{self.name}/{self.preview.split('/')[-1]}"
			self.db_set("preview", self.preview)

		block = trivena.parse_json(self.block)
		if block:
			copy_img_to_asset_folder(block, self, app="trivena_builder")
		self.db_set("block", json.dumps(block, separators=(",", ":")))

		export_to_files(
			record_list=[
				[
					"Block Template",
					self.name,
					"builder_block_template",
				],
			],
			record_module="trivena_builder",
		)

	def on_trash(self):
		block_template_folder = os.path.join(
			trivena.get_app_path("trivena_builder"), "trivena_builder", "builder_block_template", scrub(self.name)
		)
		shutil.rmtree(block_template_folder, ignore_errors=True)
		assets_folder_path = get_template_assets_folder_path(self, app="trivena_builder")
		shutil.rmtree(assets_folder_path, ignore_errors=True)
