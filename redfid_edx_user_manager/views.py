#!/usr/bin/env python
# -- coding: utf-8 --

from django.conf import settings
from django.contrib.auth import logout
from django.http import HttpResponseRedirect, HttpResponseForbidden, Http404, HttpResponseBadRequest, HttpResponse
from django.urls import reverse
from django.views.generic.base import View
from openedx.core.djangoapps.site_configuration import helpers as configuration_helpers
import json
import requests
import logging

logger = logging.getLogger(__name__)

class CreateRedfidUser(View):

    def post(self, request):
        
        from django.contrib.auth.models import User
        from social_django.models import UserSocialAuth

        try:
            logger.info("CreateRedfidUser - request: {}".format(request))
            data = json.loads(request.body)
            username = data.get('username')
            password = data.get('password')
            email = data.get('email')
            first_name = data.get('first_name')
            last_name = data.get('last_name')
            if not username or not password or not email or not first_name or not last_name:
                return HttpResponseBadRequest("Missing required fields")
            new_user = User.objects.create_user(username, email, password, first_name=first_name, last_name=last_name)
            new_user.save()
            new_usersocialauth = UserSocialAuth.objects.create(user=new_user, provider='tpa-saml', uid="default:" + username, extra_data='{}')
            new_usersocialauth.save()
            return HttpResponse(f"User {username} created successfully")
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid JSON data")


class RedfidLogoutGet(View):
    def get(self, request):
        logout(request)
        if not request.user.is_anonymous:
            logger.info("RedfidLogoutGet - logout user: {}".format(request.user))
        else:
            logger.info("RedfidLogoutGet - anonymous user")
        redirect_url = configuration_helpers.get_value('REDFID_REDIRECT_LOGOUT_URL', settings.REDFID_REDIRECT_LOGOUT_URL)
        return HttpResponseRedirect(redirect_url)


class RedfidLogoutPost(View):
    def post(self, request):
        logout(request)
        if not request.user.is_anonymous:
            logger.info("RedfidLogoutPost - logout user: {}".format(request.user))
        else:
            logger.info("RedfidLogoutPost - anonymous user")
        redirect_url = configuration_helpers.get_value('REDFID_REDIRECT_POST_URL', settings.REDFID_REDIRECT_POST_URL)
        return HttpResponseRedirect(redirect_url)