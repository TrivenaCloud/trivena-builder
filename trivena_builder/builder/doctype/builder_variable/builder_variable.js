// Copyright (c) 2025, Frappe Technologies Pvt Ltd and contributors
// For license information, please see license.txt

trivena.ui.form.on("Builder Variable", {
  refresh: function (frm) {
    // Only show is_standard field in developer mode
    frm.get_field("is_standard").toggle(trivena.boot.developer_mode);
  },
});
