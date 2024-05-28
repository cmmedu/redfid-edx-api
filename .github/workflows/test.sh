#!/bin/dash

pip install -e /openedx/requirements/redfid_edx_api

cd /openedx/requirements/redfid_edx_api
cp /openedx/edx-platform/setup.cfg .
mkdir test_root
cd test_root/
ln -s /openedx/staticfiles .

cd /openedx/requirements/redfid_edx_api

DJANGO_SETTINGS_MODULE=lms.envs.test EDXAPP_TEST_MONGO_HOST=mongodb pytest redfid_edx_api/tests.py

rm -rf test_root