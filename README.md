# RedFID edX API

# Install App

    docker-compose exec lms pip install -e /openedx/requirements/redfid_logout
    docker-compose exec cms pip install -e /openedx/requirements/redfid_logout

# Install Theme

To enable logout button in your theme add the next code:

- _../themes/your_theme/lms/templates/header/user_dropdown.html_

    **edit logout button**

        <div class="mobile-nav-item dropdown-item dropdown-nav-item"><a href="${reverse('redfid_logout:logout_get')}" role="menuitem">${_("Sign Out")}</a></div>


## TESTS
**Prepare tests:**

    > cd .github/
    > docker-compose run lms /openedx/requirements/redfid_logout/.github/test.sh
