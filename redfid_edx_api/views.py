#!/usr/bin/env python
# -- coding: utf-8 --

from django.conf import settings
from django.contrib.auth import logout
from django.http import HttpResponseRedirect, HttpResponseForbidden, Http404, HttpResponseBadRequest, HttpResponse
from django.views.generic.base import View
from openedx.core.djangoapps.site_configuration import helpers as configuration_helpers
import json
import logging

logger = logging.getLogger(__name__)

class CreateRedfidUser(View):

    def post(self, request):
        """
        Endpoint usado por el panel de administración de RedFID para crear un usuario en la base de datos de Open edX.
        Se crea una instancia del modelo base User, y se le asigna un UserProfile y un UserSocialAuth asociado al SSO de RedFID.
        """
        
        from django.contrib.auth.models import User
        from common.djangoapps.student.models import UserProfile
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
            full_name = first_name + " " + last_name
            new_userprofile = UserProfile.objects.create(user=new_user, name=full_name)
            new_userprofile.save()
            new_usersocialauth = UserSocialAuth.objects.create(user=new_user, provider='tpa-saml', uid="default:" + username, extra_data='{}')
            new_usersocialauth.save()
            return HttpResponse(f"User {username} created successfully")
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid JSON data")


class EditRedfidUser(View):
    
    def post(self, request):
        """
        Endpoint usado por el panel de administración de RedFID para editar un usuario en la base de datos de Open edX.
        Se actualizan los campos email, first_name y last_name del modelo base User, y el campo name del model UserProfile.
        """

        from django.contrib.auth.models import User
        from common.djangoapps.student.models import UserProfile

        try:
            data = json.loads(request.body)
            username = data.get('username')
            if not username:
                return HttpResponseBadRequest("Missing username")
            user = User.objects.get(username=username)
            if not user:
                return HttpResponseBadRequest("User not found")
            email = data.get('email')
            first_name = data.get('first_name')
            last_name = data.get('last_name')
            user.email = email
            user.first_name = first_name
            user.last_name = last_name
            user.save()
            userprofile = UserProfile.objects.get(user=user)
            if not userprofile:
                return HttpResponseBadRequest("UserProfile not found")
            full_name = first_name + " " + last_name
            userprofile.name = full_name
            userprofile.save()
            return HttpResponse(f"User {username} updated successfully")
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid JSON data")



class SuspendOrActivateRedfidUser(View):

    def post(self, request):
        """
        Endpoint usado por el panel de administración de RedFID para suspender o activar un usuario en la base de datos de Open edX.
        Se actualiza el campo is_active del modelo base User.
        """

        from django.contrib.auth.models import User

        try:
            data = json.loads(request.body)
            username = data.get('username')
            if not username:
                return HttpResponseBadRequest("Missing username")
            user = User.objects.get(username=username)
            if not user:
                return HttpResponseBadRequest("User not found")
            is_active = data.get('is_active')
            if is_active:
                user.is_active = True
            else:
                user.is_active = False
            user.save()
            return HttpResponse(f"User {username} is_active updated successfully")
        except json.JSONDecodeError:
            return HttpResponseBadRequest("Invalid JSON data")


class DeleteRedfidUser(View):

    def post(self, request):
        """
        Endpoint usado por el panel de administración de RedFID para eliminar un usuario en la base de datos de Open edX.
        Se eliminan las instancias del modelo base User, UserProfile y UserSocialAuth asociadas al usuario.
        """

        from django.contrib.auth.models import User
        from common.djangoapps.student.models import UserProfile

        # se puede? consultar con thomas
        return HttpResponseForbidden("Forbidden")
    

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


class GetIAAUserData(View):
    
    def post():
        """
        Endpoint usado por el panel de administración de RedFID para obtener los datos de un usuario en el IAAXBlock.
        """
        pass


class GetIAACourseData(View):
        
    def post():
        """
        Endpoint usado por el panel de administración de RedFID para obtener los datos de un curso en el IAAXBlock.
        """
        pass


class GetIterativeXBlockUserData(View):
    
    def post():
        """
        Endpoint usado por el panel de administración de RedFID para obtener los datos de un usuario en el IterativeXBlock.
        """
        pass


class GetIterativeXBlockCourseData(View):
    
    def post():
        """
        Endpoint usado por el panel de administración de RedFID para obtener los datos de un curso en el IterativeXBlock.
        """
        pass
        

# para encuestas y otros indicadores (como consentimiento informado, etc)
class GetDataXBlockStudentAnswer(View):
    pass


class GetUserCertificates(View):

    def post():
        """
        Endpoint usado por el panel de administración de RedFID para obtener los certificados de un usuario.
        """
        pass


class GetCourseCertificates(View):

    def post():
        """
        Endpoint usado por el panel de administración de RedFID para obtener los certificados de un curso.
        """
        pass
    