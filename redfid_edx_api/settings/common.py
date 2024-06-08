def plugin_settings(settings):
    settings.REDFID_REDIRECT_LOGOUT_URL = "https://www.redfid.cl/wp-login.php?action=logout"
    settings.REDFID_REDIRECT_POST_URL = "https://www.redfid.cl/"
    settings.FORBIDDEN_USERNAMES = [
        "admin",
        "administrador",
        "administrator",
        "root",
        "redfid",
        "edx",
        "test",
        "login_service_user",
        "ecommerce_worker",
        "discovery_worker",
        "mod",
        "moderador",
        "moderator",
        "staff",
        "formador",
        "super",
        "superuser",
        "user",
        "usuario",
        "discourse"
    ]