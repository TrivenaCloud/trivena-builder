import trivena_framework as trivena
from trivena_framework.core.api.file import create_new_folder


def execute():
	"""create upload folder for builder"""
	create_new_folder("Builder Uploads", "Home")
	create_new_folder("Fonts", "Home/Builder Uploads")
