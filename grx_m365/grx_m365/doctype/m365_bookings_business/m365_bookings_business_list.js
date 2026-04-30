frappe.listview_settings["M365 Bookings Business"] = {
    onload(listview) {
        listview.page.add_inner_button("Pull Bookings Businesses", function () {
            frappe.prompt(
                [
                    {
                        fieldname: "m365_account",
                        fieldtype: "Link",
                        label: "M365 Account",
                        options: "M365 Account",
                        reqd: 1
                    }
                ],
                function (values) {
                    frappe.call({
                        method: "grx_m365.api.bookings.list_businesses",
                        args: {
                            m365_account: values.m365_account,
                            upsert: 1
                        },
                        freeze: true,
                        freeze_message: "Importiere Microsoft Bookings Businesses...",
                        callback: function (r) {
                            if (r.message) {
                                frappe.msgprint(
                                    "Import abgeschlossen.<br><br>" +
                                    "Gefunden: " + r.message.count + "<br>" +
                                    "Aktualisiert/angelegt: " + (r.message.upserted || []).length
                                );
                                listview.refresh();
                            }
                        }
                    });
                },
                "Microsoft Bookings importieren",
                "Importieren"
            );
        });
    }
};