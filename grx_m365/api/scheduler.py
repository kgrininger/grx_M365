import frappe


def sync_enabled_calendar_accounts():
    """
    Scheduler entry point.
    Syncs all enabled M365 Calendar Accounts with pull sync enabled.
    """

    accounts = frappe.get_all(
        "M365 Calendar Account",
        filters={
            "enabled": 1,
            "pull_enabled": 1,
        },
        pluck="name",
    )

    for account in accounts:
        try:
            frappe.enqueue(
                "grx_m365.api.calendar_pull.sync_account",
                queue="long",
                timeout=600,
                account=account,
                now=False,
            )
        except Exception:
            frappe.log_error(
                title=f"M365 Calendar Scheduler failed for {account}",
                message=frappe.get_traceback(),
            )