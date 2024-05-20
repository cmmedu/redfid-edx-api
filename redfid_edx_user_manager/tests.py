#!/usr/bin/env python
# -*- coding: utf-8 -*-
from mock import patch, Mock, MagicMock
from collections import namedtuple
from django.urls import reverse
from django.test import TestCase, Client
from django.test import Client
from django.conf import settings
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from urllib.parse import parse_qs
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from common.djangoapps.student.tests.factories import UserFactory

import re
import json
import urllib.parse


class TestRedfidLogoutGet(TestCase):

    def setUp(self):
        self.client = Client()
        with patch('common.djangoapps.student.models.cc.User.save'):
            user = UserFactory(
                username='testuser1',
                password='12345',
                email='student1@edx.org')
            self.client.login(username='testuser1', password='12345')

    def test_logout_get(self):
        result = self.client.get(reverse('redfid_edx_user_manager:logout_get'))
        self.assertEqual(result.status_code, 302)
        
        request = urllib.parse.urlparse(result.url)
        args = urllib.parse.parse_qs(request.query)

        self.assertEqual(request.netloc, 'www.redfid.cl')
        self.assertEqual(request.path, '/wp-login.php')
        self.assertEqual(args['action'][0], "logout")

    def test_logout_post(self):
        result = self.client.post(reverse('redfid_edx_user_manager:logout_get'))
        self.assertEqual(result.status_code, 405)

class TestRedfidLogoutPost(TestCase):

    def setUp(self):
        self.client = Client()
        with patch('common.djangoapps.student.models.cc.User.save'):
            user = UserFactory(
                username='testuser1',
                password='12345',
                email='student1@edx.org')
            self.client.login(username='testuser1', password='12345')

    def test_logout_get(self):
        result = self.client.get(reverse('redfid_edx_user_manager:logout_post'))
        self.assertEqual(result.status_code, 405)

    def test_logout_post(self):
        result = self.client.post(reverse('redfid_edx_user_manager:logout_post'))
        self.assertEqual(result.status_code, 302)
        
        request = urllib.parse.urlparse(result.url)
        args = urllib.parse.parse_qs(request.query)

        self.assertEqual(request.netloc, 'www.redfid.cl')