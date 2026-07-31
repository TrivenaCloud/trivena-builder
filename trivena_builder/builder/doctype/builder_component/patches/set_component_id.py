import trivena_framework as trivena


def execute():
	"""Set Component ID"""
	component_list = trivena.get_all("Builder Component")

	for component in component_list:
		component_doc = trivena.get_doc("Builder Component", component)
		component_doc.component_id = component_doc.name
		component_doc.db_set("component_id", component_doc.name, update_modified=False)
