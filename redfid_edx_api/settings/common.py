def plugin_settings(settings):
    settings.FORBIDDEN_USERNAMES = [
        "admin",
        "administrator",
        "root",
        "superadmin",
        "login_service_user",
        "ecommerce_worker",
        "discovery_worker",
    ]