#!/usr/bin/env python
# -- coding: utf-8 --

from django.conf import settings
from django.contrib.auth import logout
from django.db.utils import IntegrityError
from django.http import HttpResponseRedirect, HttpResponseForbidden, Http404, HttpResponseBadRequest, HttpResponse, JsonResponse
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
            if username in settings.FORBIDDEN_USERNAMES:
                return HttpResponseBadRequest("Username is forbidden")
            try:
                new_user = User.objects.create_user(username, email, password, first_name=first_name, last_name=last_name)
                new_user.save()
            except IntegrityError:
                return HttpResponseBadRequest("User already exists")
            full_name = first_name + " " + last_name
            try:
                new_userprofile = UserProfile.objects.create(user=new_user, name=full_name)
                new_userprofile.save()
            except IntegrityError:
                return HttpResponseBadRequest("UserProfile already exists") # should never happen
            try:
                new_usersocialauth = UserSocialAuth.objects.create(user=new_user, provider='tpa-saml', uid="default:" + username, extra_data={})
                new_usersocialauth.save()
            except IntegrityError:
                return HttpResponseBadRequest("UserSocialAuth already exists") # should never happen
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
                return HttpResponseBadRequest("UserProfile not found") # should never happen
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

        try:
            data = json.loads(request.body)
            username = data.get('username')
            if not username:
                return HttpResponseBadRequest("Missing username")
            user = User.objects.get(username=username)
            if not user:
                return HttpResponseBadRequest("User not found")
            user.delete()
            return HttpResponse(f"User {username} deleted successfully")
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


class GetIAAUserData(View):
    
    def post(self, request):
        """
        Endpoint usado por el panel de administración de RedFID para obtener los datos de un usuario en el IAAXBlock.
        """
        from django.contrib.auth.models import User
        try:
            from iaaxblock.models import IAAActivity, IAAStage, IAASubmission
        except ImportError:
            return HttpResponseBadRequest("IAAXBlock not found")
        data = json.loads(request.body)
        username = data.get('username')
        if not username:
            return HttpResponseBadRequest("Missing username")
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return HttpResponseBadRequest("User not found")
        activities = IAAActivity.objects.filter().all()
        stages = IAAStage.objects.filter().all()
        out = []
        for activity in activities:
            out.append({
                "id_course": activity.id_course,
                "name": activity.activity_name,
                "stages": [{
                    "label": stage.stage_label,
                    "number": stage.stage_number,
                    "answer": IAASubmission.objects.get(id_student=user.id, stage=stage).submission if IAASubmission.objects.filter(id_student=user.id, stage=stage).exists() else None,
                    "timestamp": str(IAASubmission.objects.get(id_student=user.id, stage=stage).submission_time) if IAASubmission.objects.filter(id_student=user.id, stage=stage).exists() else None
                } for stage in stages if stage.activity == activity]
            })
        return JsonResponse(out, safe=False)


class GetIAACourseData(View):
        
    def post(self, request):
        """
        Endpoint usado por el panel de administración de RedFID para obtener los datos de un curso en el IAAXBlock.
        """
        from django.contrib.auth.models import User
        try:
            from iaaxblock.models import IAAActivity, IAAStage, IAASubmission
        except ImportError:
            return HttpResponseBadRequest("IAAXBlock not found")
        data = json.loads(request.body)
        course_id = data.get('course_id')
        if not course_id:
            return HttpResponseBadRequest("Missing course_id")
        activities = IAAActivity.objects.filter(id_course=course_id).all()
        stages = IAAStage.objects.filter(activity__in=activities).all()
        out = []
        for activity in activities:
            out.append({
                "id_course": activity.id_course,
                "name": activity.activity_name,
                "stages": [{
                    "label": stage.stage_label,
                    "number": stage.stage_number,
                    "answers": [{
                        "user": User.objects.get(id=submission.id_student).username if User.objects.filter(id=submission.id_student).exists() else None,
                        "username": User.objects.get(id=submission.id_student).username,
                        "answer": submission.submission,
                        "timestamp": str(submission.submission_time)
                    } for submission in IAASubmission.objects.filter(stage=stage).all()]
                } for stage in stages if stage.activity == activity]
            })
        return JsonResponse(out, safe=False)


class GetIterativeXBlockUserData(View):
    
    def post(self, request):
        """
        Endpoint usado por el panel de administración de RedFID para obtener los datos de un usuario en el IterativeXBlock.
        """
        from django.contrib.auth.models import User
        try:
            from iterativexblock.models import IterativeXBlockQuestion, IterativeXBlockAnswer
        except ImportError:
            return HttpResponseBadRequest("IterativeXBlock not found")
        data = json.loads(request.body)
        username = data.get('username')
        if not username:
            return HttpResponseBadRequest("Missing username")
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return HttpResponseBadRequest("User not found")
        questions = IterativeXBlockQuestion.objects.filter().all()
        out = []
        for question in questions:
            answer = IterativeXBlockAnswer.objects.filter(id_student=user.id, question_id=question.id).first()
            q = {
                "id_xblock": question.id_xblock,
                "id_course": question.id_course,
                "id_question": question.id_question,
                "answer": answer.answer if answer else None,
                "timestamp": str(answer.timestamp) if answer else None
            }
            out.append(q)
        return JsonResponse(out, safe=False)


class GetIterativeXBlockCourseData(View):
    
    def post(self, request):
        """
        Endpoint usado por el panel de administración de RedFID para obtener los datos de un curso en el IterativeXBlock.
        """
        from django.contrib.auth.models import User
        try:
            from iterativexblock.models import IterativeXBlockQuestion, IterativeXBlockAnswer
        except ImportError:
            return HttpResponseBadRequest("IterativeXBlock not found")
        data = json.loads(request.body)
        course_id = data.get('course_id')
        if not course_id:
            return HttpResponseBadRequest("Missing course_id")
        questions = IterativeXBlockQuestion.objects.filter(id_course=course_id).all()
        answers = IterativeXBlockAnswer.objects.filter(id_course=course_id).all()
        out = []
        for question in questions:
            q = {
                "id_xblock": question.id_xblock,
                "id_question": question.id_question,
                "answers": []
            }
            for answer in answers:
                if answer.question_id == question.id:
                    try:
                        username = User.objects.get(id=answer.id_student).username
                    except User.DoesNotExist:
                        username = None
                    q['answers'].append({
                        "username": username,
                        "answer": answer.answer,
                        "timestamp": str(answer.timestamp)
                    })
            out.append(q)
        return JsonResponse(out, safe=False)
            

class GetUserCertificates(View):

    def post(self, request):
        """
        Endpoint usado por el panel de administración de RedFID para obtener los certificados de un usuario.
        """
        pass


class GetCourseCertificates(View):

    def post(self, request):
        """
        Endpoint usado por el panel de administración de RedFID para obtener los certificados de un curso.
        """
        pass
    

class GetXBlockUserData(View):
    
    def post(self, request):
        """
        Endpoint usado por el panel de administración de RedFID para obtener los certificados de un curso.
        """
        from django.contrib.auth.models import User
        from lms.djangoapps.courseware.models import StudentModule
        data = json.loads(request.body)
        username = data.get('username')
        id_xblock = data.get('id_xblock')
        xblock_type = data.get('xblock_type')
        course_id = data.get('course_id')
        if not username:
            return HttpResponseBadRequest("Missing username")
        if not id_xblock:
            return HttpResponseBadRequest("Missing id_xblock")
        if not course_id:
            return HttpResponseBadRequest("Missing course_id")
        if not xblock_type:
            return HttpResponseBadRequest("Missing xblock_type")
        if xblock_type not in ['iterativexblock', 'freetextresponse']:
            return HttpResponseBadRequest("Invalid xblock_type")
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return HttpResponseBadRequest("User not found")
        try:
            module_state_key = "block-v1:{}+type@{}+block@{}".format(course_id.split("course-v1:")[1], xblock_type, id_xblock)
            student_module = StudentModule.objects.get(student=user, module_state_key=module_state_key)
            if xblock_type == 'freetextresponse':
                out = {
                    "answer": json.loads(student_module.state)['student_answer']
                }
            elif xblock_type == 'iterativexblock':
                out = {
                    "answer": json.loads(student_module.state)['student_answers']
                }
            else:
                out = {
                    "answer": None
                }
        except StudentModule.DoesNotExist:
            out = {
                "answer": None
            }
        return JsonResponse(out, safe=False)


