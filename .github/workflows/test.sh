#!/bin/dash

pip install -e /openedx/requirements/redfid_edx_user_manager

cd /openedx/requirements/redfid_edx_user_manager
cp /openedx/edx-platform/setup.cfg .
mkdir test_root
cd test_root/
ln -s /openedx/staticfiles .

cd /openedx/requirements/redfid_edx_user_manager

DJANGO_SETTINGS_MODULE=lms.envs.test EDXAPP_TEST_MONGO_HOST=mongodb pytest redfid_edx_user_manager/tests.py

rm -rf test_root