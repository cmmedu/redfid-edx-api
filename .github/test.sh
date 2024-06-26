#!/bin/dash

pip install -e /openedx/requirements/redfid-edx-api

cd /openedx/requirements/redfid-edx-api
cp /openedx/edx-platform/setup.cfg .
mkdir test_root
cd test_root/
ln -s /openedx/staticfiles .

cd /openedx/requirements/redfid-edx-api

DJANGO_SETTINGS_MODULE=lms.envs.test EDXAPP_TEST_MONGO_HOST=mongodb pytest redfid_edx_api/tests.py