#!/usr/bin/env python
# -- coding: utf-8 --

from django.conf import settings
from django.contrib.auth import logout
from django.http import HttpResponseRedirect, HttpResponseForbidden, Http404
from django.urls import reverse
from django.views.generic.base import View
from django.http import HttpResponse
from openedx.core.djangoapps.site_configuration import helpers as configuration_helpers
import json
import requests
import logging

logger = logging.getLogger(__name__)

class CreateRedfidUser(View):

    def post(self, request):
        
        from django.contrib.auth.models import User
        from django.social_auth.models import UserSocialAuth

        print(request.text)
        user = request.user
        if not user.email:
            return HttpResponseForbidden("User email is required")
        if not user.first_name:
            return HttpResponseForbidden("User first name is required")
        if not user.last_name:
            return HttpResponseForbidden("User last name is required")
        if not user.username:
            return HttpResponseForbidden("User username is required")
        password = "redfid"
        new_user = User.objects.create_user(user.username, user.email, password, first_name=user.first_name, last_name=(user.first_name + " " + user.last_name))
        new_user.save()
        new_usersocialauth = UserSocialAuth.objects.create(user=new_user, provider='tpa-saml', uid="default:" + user.username, extra_data='{}')
        new_usersocialauth.save()
        return HttpResponse("User created successfully")


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