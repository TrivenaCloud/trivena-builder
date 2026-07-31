import trivena_framework as trivena
from trivena_framework.model.rename_doc import rename_doc


def execute():
	if trivena.db.exists("DocType", "Web Page Beta") and not trivena.db.exists("DocType", "Builder Page"):
		rename_doc("DocType", "Web Page Beta", "Builder Page")
