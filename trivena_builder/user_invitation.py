import trivena_framework as trivena
from trivena_framework.model.document import Document
from trivena_framework.utils.telemetry import capture


def capture_user_invited(doc: Document, method: str | None = None) -> None:
	if doc.app_name == "trivena_builder":
		capture("builder_user_invited", "trivena_builder")


def after_accept(invitation: Document, user: Document, user_inserted: bool) -> None:
	if invitation.app_name == "trivena_builder":
		capture("builder_user_invitation_accepted", "trivena_builder")
