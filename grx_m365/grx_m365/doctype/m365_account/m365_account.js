frappe.ui.form.on("M365 Account", {
    refresh(frm) {
        frm.add_custom_button("Reconnect Microsoft", function () {
            window.location.href = "/api/method/grx_m365.api.auth.connect";
        });
    }
});