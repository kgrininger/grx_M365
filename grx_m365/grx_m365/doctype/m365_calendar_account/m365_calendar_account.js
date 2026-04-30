frappe.ui.form.on("M365 Calendar Account", {
    refresh(frm) {

        frm.add_custom_button("Sync Outlook Calendar", function () {
            frappe.call({
                method: "grx_m365.api.calendar_pull.sync_account",
                args: {
                    account: frm.doc.name
                },
                freeze: true,
                freeze_message: "Synchronisiere Outlook Kalender...",
                callback: function (r) {
                    if (r.message) {
                        frappe.msgprint(
                            "Sync fertig.<br><br>" +
                            JSON.stringify(r.message.stats, null, 2)
                        );
                        frm.reload_doc();
                    }
                }
            });
        });

        if (frm.doc.m365_account) {
            frm.add_custom_button("Open M365 Account", function () {
                frappe.set_route(
                    "Form",
                    "M365 Account",
                    frm.doc.m365_account
                );
            });
        }
    }
});