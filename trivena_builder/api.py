import ipaddress
import os
import socket
from io import BytesIO
from types import FunctionType, MethodType, ModuleType
from typing import Any
from urllib.parse import unquote, urlparse

import trivena_framework as trivena
import requests
from trivena_framework.apps import get_apps as get_permitted_apps
from trivena_framework.core.doctype.file.file import get_local_image
from trivena_framework.core.doctype.file.utils import delete_file
from trivena_framework.model.document import Document
from trivena_framework.utils.caching import redis_cache
from trivena_framework.utils.safe_exec import NamespaceDict, get_safe_globals
from PIL import Image
from werkzeug.wrappers import Response

from trivena_builder import builder_analytics
from trivena_builder.builder.doctype.builder_page.builder_page import BuilderPageRenderer
from trivena_builder.builder.doctype.builder_snapshot import builder_snapshot
from trivena_builder.utils import compact_json, has_page_read, has_page_write


@trivena.whitelist()
def get_versioned_doc(snapshot: str) -> dict:
	return builder_snapshot.get_versioned_doc(snapshot).as_dict()


@trivena.whitelist()
def is_site_read_only() -> bool:
	return bool(trivena.flags.read_only)


@trivena.whitelist()
def get_page_preview_html(page: str, **kwargs) -> Response:
	if not trivena.has_permission("Builder Page", "read", page):
		trivena.throw("No permission to preview this page")

	# to load preview without publishing
	trivena.form_dict.update(kwargs)
	trivena.local.request.for_preview = True
	renderer = BuilderPageRenderer(path="")
	renderer.docname = page
	renderer.doctype = "Builder Page"
	trivena.local.no_cache = 1
	renderer.init_context()
	response = renderer.render()
	page_doc = trivena.get_cached_doc("Builder Page", page)
	trivena.enqueue_doc(
		page_doc.doctype,
		page_doc.name,
		"generate_page_preview_image",
		html=str(response.data, "utf-8"),
		queue="short",
	)
	return response


@trivena.whitelist()
@has_page_write("You do not have permission to upload assets.")
def upload_builder_asset():
	from trivena_framework.handler import upload_file

	image_file = upload_file()
	if (
		image_file
		and image_file.file_url.endswith((".png", ".jpeg", ".jpg"))
		and trivena.get_cached_value("Builder Settings", "Builder Settings", "auto_convert_images_to_webp")
	):
		convert_to_webp(file_doc=image_file)
	return image_file


@trivena.whitelist()
def convert_to_webp(image_url: str | None = None, file_doc: Document | None = None) -> str:
	"""
	Convert image to webp format.
	Handles local files, builder assets, and external URLs.
	Returns the new webp file URL or the original if conversion is not possible.
	"""
	import hashlib

	CONVERTIBLE_IMAGE_EXTENSIONS = ["png", "jpeg", "jpg"]

	def can_convert_image(extn: str) -> bool:
		return extn.lower() in CONVERTIBLE_IMAGE_EXTENSIONS

	def get_extension(filename: str) -> str:
		return filename.split(".")[-1].lower() if "." in filename else ""

	def save_as_webp(image, path: str) -> None:
		image.save(path, "WEBP")

	def to_webp_url(url: str, extn: str) -> str:
		return url.replace(extn, "webp")

	def to_webp_path(path: str, extn: str) -> str:
		return path.replace(extn, "webp")

	def handle_file_doc(file_doc: Document) -> str:
		if not file_doc.file_url.startswith("/files"):
			return file_doc.file_url
		image, _, extn = get_local_image(file_doc.file_url)
		if not can_convert_image(extn):
			return file_doc.file_url
		save_as_webp(image, to_webp_path(file_doc.get_full_path(), extn))
		delete_file(file_doc.get_full_path())
		file_doc.file_url = to_webp_url(file_doc.file_url, extn)
		file_doc.save()
		return file_doc.file_url

	def handle_local_url(image_url: str) -> str:
		image, _, extn = get_local_image(image_url)
		if not can_convert_image(extn):
			return image_url
		files = trivena.get_all("File", filters={"file_url": image_url}, fields=["name"], limit=1)
		if not files:
			return image_url
		file = trivena.get_doc("File", files[0].name)
		save_as_webp(image, to_webp_path(file.get_full_path(), extn))
		new_file = trivena.copy_doc(file)
		new_file.file_name = to_webp_url(file.file_name, extn)
		new_file.file_url = to_webp_url(file.file_url, extn)
		new_file.save()
		return new_file.file_url

	def handle_builder_asset(image_url: str) -> str:
		image_path = os.path.abspath(trivena.get_app_path("trivena_builder", "www", image_url.lstrip("/")))
		image_path = image_path.replace("_", "-").replace("/builder-assets", "/builder_assets")
		extn = get_extension(image_path)
		if not can_convert_image(extn):
			return image_url
		image = Image.open(image_path)
		save_as_webp(image, to_webp_path(image_path, extn))
		return to_webp_url(image_url, extn)

	def get_external_webp_filename(image_url: str) -> str:
		filename = image_url.split("/")[-1].split("?")[0]
		base = filename.rsplit(".", 1)[0] if "." in filename else ""
		if not base or base.lower() == "webp" or filename.lower() == "webp":
			return f"external-{hashlib.md5(image_url.encode()).hexdigest()[:8]}.webp"
		return base + ".webp"

	def handle_external_url(image_url: str) -> str:
		url = unquote(image_url)
		assert_not_private_url(url)
		image = Image.open(BytesIO(requests.get(url).content))
		filename = get_external_webp_filename(url)
		file = trivena.get_doc({"doctype": "File", "file_name": filename, "file_url": f"/files/{filename}"})
		save_as_webp(image, file.get_full_path())
		file.save()
		return file.file_url

	if not image_url and not file_doc:
		return ""
	if file_doc:
		return handle_file_doc(file_doc)

	image_url = image_url or ""
	if image_url.startswith("/files"):
		return handle_local_url(image_url)
	if image_url.startswith("/builder_assets"):
		return handle_builder_asset(image_url)
	if image_url.startswith("http"):
		return handle_external_url(image_url)
	return image_url


def assert_not_private_url(url: str) -> None:
	"""Raise PermissionError if the URL resolves to a private/internal IP (SSRF guard)."""
	parsed = urlparse(url)
	if parsed.scheme not in ("http", "https"):
		trivena.throw("Only HTTP/HTTPS URLs are allowed for external images.", trivena.PermissionError)
	hostname = parsed.hostname
	if not hostname:
		trivena.throw("Invalid URL: missing hostname.", trivena.ValidationError)
	try:
		addr_infos = socket.getaddrinfo(hostname, None)
	except socket.gaierror:
		trivena.throw(f"Could not resolve hostname: {hostname}", trivena.ValidationError)
	for addr_info in addr_infos:
		ip = ipaddress.ip_address(addr_info[4][0])
		if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
			trivena.throw("Requests to private or internal addresses are not allowed.", trivena.PermissionError)


def check_app_permission():
	if trivena.session.user == "Administrator":
		return True

	if trivena.has_permission("Builder Page", ptype="write"):
		return True

	return False


@trivena.whitelist()
def get_pending_invitations() -> list[dict]:
	from trivena_framework.core.doctype.user_invitation.user_invitation import UserInvitation

	UserInvitation.validate_role("trivena_builder")
	invitations = trivena.get_all(
		"User Invitation",
		filters={"status": "Pending", "app_name": "trivena_builder"},
		fields=["name", "email", "creation", "invited_by"],
		order_by="creation desc",
	)
	for invitation in invitations:
		invitation.invited_by_name = trivena.db.get_value("User", invitation.invited_by, "full_name")
	return invitations


@trivena.whitelist()
def get_builder_users() -> list[dict]:
	from trivena_framework.core.doctype.user_invitation.user_invitation import UserInvitation

	UserInvitation.validate_role("trivena_builder")
	role_rows = trivena.get_all(
		"Has Role",
		filters={"role": ["in", ["System Manager", "Website Manager"]], "parenttype": "User"},
		fields=["parent", "role"],
	)
	admins = {row.parent for row in role_rows if row.role == "System Manager"}
	users = trivena.get_all(
		"User",
		filters=[
			["name", "in", list({row.parent for row in role_rows})],
			["name", "not in", ["Administrator", "Guest"]],
			["enabled", "=", 1],
			["user_type", "=", "System User"],
		],
		fields=["name", "full_name", "user_image"],
		order_by="full_name",
	)
	for user in users:
		user.is_admin = user.name in admins
	return users


@trivena.whitelist()
@redis_cache()
def get_apps():
	apps = get_permitted_apps()
	app_list = [
		{
			"name": "frappe",
			"logo": "/assets/trivena_builder/images/desk.png",
			"title": "Desk",
			"route": "/app",
		}
	]
	app_list += filter(lambda app: app.get("name") != "trivena_builder", apps)

	return app_list


@trivena.whitelist()
@has_page_write("You do not have permission to update page folder.")
def update_page_folder(pages: list[str], folder_name: str) -> None:
	if not pages:
		return
	trivena.db.set_value(
		"Builder Page", {"name": ["in", pages]}, "project_folder", folder_name, update_modified=False
	)


def clone_client_scripts(source_page, new_page) -> None:
	"""Clone the source page's client scripts onto new_page with hashed names,
	so the copy never shares scripts with the source."""
	client_scripts = source_page.client_scripts
	new_page.client_scripts = []
	for script in client_scripts:
		builder_script = trivena.get_doc("Builder Client Script", script.builder_script)
		new_script = trivena.copy_doc(builder_script)
		new_script.name = f"{builder_script.name}-{trivena.generate_hash(length=5)}"
		new_script.insert(ignore_permissions=True)
		new_page.append("client_scripts", {"builder_script": new_script.name})


@trivena.whitelist()
@has_page_write("You do not have permission to duplicate a page.")
def duplicate_page(page_name: str):
	page = trivena.get_doc("Builder Page", page_name)
	new_page = trivena.copy_doc(page)
	del new_page.page_name
	new_page.route = None
	clone_client_scripts(page, new_page)
	new_page.insert()
	return new_page


# Templates live on a central Builder Hub site. Builder just fetches the catalog
# and, on use, a per-page bundle over HTTP (server-side — no CORS), then builds a
# page from it. Point at the hub via `template_hub_url` in the site config (or
# common_site_config for the whole bench).
DEFAULT_HUB_URL = "https://preview.frappe.cloud"


def hub_url() -> str:
	return (trivena.conf.get("template_hub_url") or DEFAULT_HUB_URL).rstrip("/")


@redis_cache(ttl=600)
def hub_get_cached(method: str, params_key: tuple):
	# make_get_request (not builder's make_safe_get_request, which blocks private
	# IPs and would reject a localhost hub). Trust = admin-set hub URL.
	from trivena_framework.integrations.utils import make_get_request

	resp = make_get_request(
		f"{hub_url()}/api/method/builder_hub.api.{method}", params=dict(params_key) or None
	)
	return resp.get("message") if resp else None


def hub_get(method: str, **params):
	return hub_get_cached(method, tuple(sorted(params.items())))


@trivena.whitelist()
@has_page_read("You do not have permission to view templates.")
def get_template_groups() -> list[dict]:
	"""Template groups for the picker, fetched live from the hub. Empty (just
	Blank page) if the hub is unreachable."""
	try:
		return hub_get("get_catalog") or []  # type: ignore[return-value]
	except Exception:
		trivena.log_error("Failed to fetch templates from hub")
		return []


def create_page_from_bundle(bundle: dict, project_folder: str | None = None) -> str:
	"""Create an editable page from a fetched hub bundle and return its name.

	Installs shared components/variables/scripts/fonts, then builds the page
	from its blocks. Created pages hot-link the hub's /builder_assets/ images."""
	from trivena_framework.modules.import_file import import_doc

	for font in bundle.get("fonts") or []:
		import_doc(docdict=font)
	for var in bundle.get("variables") or []:
		import_doc(docdict=var)
	for comp in bundle.get("components") or []:
		import_doc(docdict=comp)

	page = bundle.get("page")
	assert isinstance(page, dict)
	preview = page.get("preview")
	new_page = trivena.get_doc(
		{
			"doctype": "Builder Page",
			"page_title": page.get("page_title") or "My Page",
			"preview": preview or None,
			"draft_blocks": compact_json(page.get("blocks") or []),
			"page_data_script": page.get("page_data_script"),
			"head_html": page.get("head_html"),
			"body_html": page.get("body_html"),
			"meta_description": page.get("meta_description"),
			"project_folder": project_folder or None,
		}
	)
	for cs in bundle.get("client_scripts") or []:
		new_script = trivena.get_doc(
			{
				"doctype": "Builder Client Script",
				"name": f"{cs.get('name')}-{trivena.generate_hash(length=5)}",
				"script_type": cs.get("script_type"),
				"script": cs.get("script"),
			}
		)
		new_script.insert(ignore_permissions=True)
		new_page.append("client_scripts", {"builder_script": new_script.name})
	new_page.insert()
	# only fall back to async generation when the template carried no preview
	if not preview:
		trivena.enqueue_doc(
			"Builder Page",
			new_page.name,
			"generate_page_preview_image",
			queue="short",
			enqueue_after_commit=True,
		)
	return new_page.name or ""


@trivena.whitelist()
@has_page_write("You do not have permission to create a page.")
def create_page_from_template(template_page: str, project_folder: str | None = None) -> str:
	"""Create an editable page from a hub template and return its name."""
	try:
		bundle = hub_get("get_template_bundle", page=template_page)
	except Exception:
		trivena.log_error("Failed to fetch template bundle")
		bundle = None
	if not bundle or not bundle.get("page"):
		trivena.throw(trivena._("Could not load the selected template. Please try again."))

	assert isinstance(bundle, dict)
	return create_page_from_bundle(bundle, project_folder)


@trivena.whitelist()
@has_page_write("You do not have permission to create pages.")
def import_template_group(template_group: str, project_folder: str | None = None) -> list[str]:
	"""Import all pages from a template group and return their names."""
	groups = get_template_groups()
	group = next((g for g in groups if g.get("name") == template_group), None)
	if not group:
		trivena.throw(trivena._("Template group not found."))

	pages = group.get("pages") or []
	if not pages:
		trivena.throw(trivena._("No pages found in this template group."))

	created = []
	for page in pages:
		try:
			bundle = hub_get("get_template_bundle", page=page.get("name"))
		except Exception:
			trivena.log_error(f"Failed to fetch template bundle for {page.get('name')}")
			continue
		if not bundle or not bundle.get("page"):
			continue
		name = create_page_from_bundle(bundle, project_folder)
		created.append(name)

	if not created:
		trivena.throw(trivena._("Could not import any pages from this template group."))

	return created


@trivena.whitelist()
@has_page_write("You do not have permission to delete a folder.")
def delete_folder(folder_name: str) -> None:
	# remove folder from all pages in a single update
	trivena.db.set_value(
		"Builder Page", {"project_folder": folder_name}, "project_folder", "", update_modified=False
	)

	trivena.db.delete("Builder Project Folder", {"folder_name": folder_name})


@trivena.whitelist()
@has_page_write("You do not have permission to sync a component.")
def sync_component(component_id: str):
	component = trivena.get_doc("Builder Component", component_id)
	component.sync_component()


@trivena.whitelist()
@has_page_read("You do not have permission to view analytics.")
def get_page_analytics(
	route: str,
	interval: str = "daily",
	from_date: str | None = None,
	to_date: str | None = None,
	route_filter_type: str = "wildcard",
):
	return builder_analytics.get_page_analytics(
		route=route,
		interval=interval,
		from_date=from_date,
		to_date=to_date,
		route_filter_type=route_filter_type,
	)


@trivena.whitelist()
@has_page_read("You do not have permission to view analytics.")
def get_overall_analytics(
	interval: str = "daily",
	route: str | None = None,
	from_date: str | None = None,
	to_date: str | None = None,
	route_filter_type: str = "wildcard",
):
	return builder_analytics.get_overall_analytics(
		interval=interval,
		route=route,
		from_date=from_date,
		to_date=to_date,
		route_filter_type=route_filter_type,
	)


@trivena.whitelist()
@has_page_read("You do not have permission to view analytics.")
def get_page_ctr(
	route: str | None = None,
	from_date: str | None = None,
	to_date: str | None = None,
	route_filter_type: str = "wildcard",
):
	return builder_analytics.get_page_ctr(
		route=route,
		from_date=from_date,
		to_date=to_date,
		route_filter_type=route_filter_type,
	)


@trivena.whitelist(allow_guest=True, methods=["POST"])
def make_click_log(
	element: str | None = None,
	text: str | None = None,
	visitor_id: str | None = None,
):
	"""Autocapture a click on a published Builder page. Mirrors Frappe's make_view_log so
	clicks share the exact same `path` (derived from the Referer) as Web Page View rows."""
	from trivena_framework.website.doctype.web_page_view.web_page_view import is_tracking_enabled

	if not is_tracking_enabled():
		return

	path = trivena.request.headers.get("Referer")
	if not trivena.utils.is_site_link(path):
		return

	path = urlparse(path).path
	if path != "/" and path.startswith("/"):
		path = path[1:]
	if path.startswith(("api/", "app/", "assets/", "private/files/")):
		return

	is_unique = bool(visitor_id) and not trivena.db.exists(
		"Builder Page Click", {"visitor_id": visitor_id, "path": path, "element": element or ""}
	)

	click = trivena.new_doc("Builder Page Click")
	click.path = path
	click.element = element
	click.text = text[:140] if text else text  # cap server-side; deferred_insert skips controller validation
	click.is_unique = is_unique
	click.visitor_id = visitor_id

	try:
		click.deferred_insert()
	except Exception:
		trivena.log_error("Failed to log builder page click")


def get_keys_for_autocomplete(
	key: str,
	value: Any,
	depth: int = 0,
	max_depth: int | None = None,
):
	if max_depth and depth > max_depth:
		return None  # Or some other sentinel value to indicate termination

	if key.startswith("_"):
		return None

	if isinstance(value, NamespaceDict | dict) and value:
		result = {}
		for k, v in value.items():
			nested_result = get_keys_for_autocomplete(
				k,
				v,
				depth + 1,
				max_depth=max_depth,
			)
			if nested_result is not None:  # Only add if not terminated
				result[k] = nested_result
		return result if result else None  # Return None if the dictionary is empty

	else:
		if isinstance(value, type) and issubclass(value, Exception):
			var_type = "type"  # Exceptions are types
		elif isinstance(value, ModuleType):
			var_type = "namespace"
		elif isinstance(value, FunctionType | MethodType):
			var_type = "function"
		elif isinstance(value, type):
			var_type = "type"
		elif isinstance(value, dict):
			var_type = "property"  # Assuming dict should be mapped to other
		else:
			var_type = "property"  # Default to text if no other type matches
		return {"true_type": type(value).__name__, "type": var_type}


@trivena.whitelist()
@redis_cache()
def get_codemirror_completions():
	return get_keys_for_autocomplete(
		key="",
		value=get_safe_globals(),
	)


@trivena.whitelist()
@has_page_write("You do not have permission to reorder client scripts")
def reorder_client_scripts(script_order: list[str]):
	for idx, script_name in enumerate(script_order, start=1):
		trivena.db.set_value("Builder Page Client Script", script_name, "idx", idx)


@trivena.whitelist()
@has_page_write("You do not have permission to evaluate component scripts")
def get_component_data(
	component_name: str, props: dict | str | None = None, script: str | None = None
) -> dict:
	from trivena_builder.builder.doctype.builder_component.builder_component import (
		get_component_data as _get_component_data,
	)

	return _get_component_data(component_name, props, script)
