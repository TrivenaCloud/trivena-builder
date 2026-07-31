import trivena_framework as trivena
from trivena_framework.model.rename_doc import rename_doc


def execute():
	if trivena.db.exists("DocType", "Web Page Component") and not trivena.db.exists(
		"DocType", "Builder Component"
	):
		rename_doc("DocType", "Web Page Component", "Builder Component")
