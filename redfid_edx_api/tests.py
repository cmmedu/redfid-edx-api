import json
import sys
from contextlib import contextmanager
from types import ModuleType
from unittest.mock import patch

from common.djangoapps.student.models import CourseEnrollment, UserProfile
from common.djangoapps.student.tests.factories import UserFactory, CourseEnrollmentFactory
from django.conf import settings
from django.contrib.auth.models import User
from django.db.utils import IntegrityError
from django.test import Client
from django.urls import reverse
from lms.djangoapps.certificates.models import GeneratedCertificate
from lms.djangoapps.courseware.models import StudentModule
from social_django.models import UserSocialAuth
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from xmodule.modulestore.tests.factories import CourseFactory


# --- Helpers for faking optional XBlock packages (iaaxblock, iterativexblock) ---
#
# GetIAA*/GetIterativeXBlock* views import their models lazily, inside the
# request handler, and treat an ImportError as "the XBlock isn't installed"
# (returns a 400). Since neither package is a dependency of this repo (they're
# optional third-party XBlocks that may or may not be present in a given
# edx-platform deployment), we fake their presence via sys.modules so the
# success/validation code paths inside the view can be exercised too.

@contextmanager
def fake_module(module_path, **attrs):
    """Temporarily register a fake module in sys.modules so a
    ``from <module_path> import X`` inside a view succeeds without the real
    (optional) package being installed."""
    package_name = module_path.split('.')[0]
    fake_pkg = ModuleType(package_name)
    fake_mod = ModuleType(module_path)
    for name, value in attrs.items():
        setattr(fake_mod, name, value)

    had_package = package_name in sys.modules
    had_module = module_path in sys.modules
    old_package = sys.modules.get(package_name)
    old_module = sys.modules.get(module_path)

    sys.modules[package_name] = fake_pkg
    sys.modules[module_path] = fake_mod
    try:
        yield fake_mod
    finally:
        if had_module:
            sys.modules[module_path] = old_module
        else:
            sys.modules.pop(module_path, None)
        if had_package:
            sys.modules[package_name] = old_package
        else:
            sys.modules.pop(package_name, None)


class FakeQuerySet(list):
    """Minimal stand-in for a Django QuerySet, enough to support the
    .filter().all() / .get() / .first() / .exists() chains used in views.py
    against plain Python objects."""

    def filter(self, **kwargs):
        def matches(obj):
            for key, value in kwargs.items():
                if key.endswith('__in'):
                    if getattr(obj, key[:-len('__in')]) not in value:
                        return False
                elif getattr(obj, key) != value:
                    return False
            return True
        return FakeQuerySet([obj for obj in self if matches(obj)])

    def all(self):
        return self

    def exists(self):
        return len(self) > 0

    def first(self):
        return self[0] if self else None

    def get(self, **kwargs):
        return self.filter(**kwargs)[0]


class FakeManager(object):
    def __init__(self, instances):
        self._qs = FakeQuerySet(instances)

    def filter(self, **kwargs):
        return self._qs.filter(**kwargs)

    def all(self):
        return self._qs.all()

    def get(self, **kwargs):
        return self._qs.get(**kwargs)


def fake_model(instances):
    """Build a throwaway class whose `.objects` behaves like a Django manager
    wrapping the given list of plain Python instances."""
    cls = type('FakeModel', (object,), {})
    cls.objects = FakeManager(instances)
    return cls


class FakeIAAActivity(object):
    def __init__(self, id_course, activity_name):
        self.id_course = id_course
        self.activity_name = activity_name


class FakeIAAStage(object):
    def __init__(self, activity, stage_label, stage_number):
        self.activity = activity
        self.stage_label = stage_label
        self.stage_number = stage_number


class FakeIAASubmission(object):
    def __init__(self, id_student, stage, submission, submission_time):
        self.id_student = id_student
        self.stage = stage
        self.submission = submission
        self.submission_time = submission_time


class FakeIterativeQuestion(object):
    def __init__(self, id, id_xblock, id_course, id_question):
        self.id = id
        self.id_xblock = id_xblock
        self.id_course = id_course
        self.id_question = id_question


class FakeIterativeAnswer(object):
    def __init__(self, id_student, question_id, answer, timestamp, id_course):
        self.id_student = id_student
        self.question_id = question_id
        self.answer = answer
        self.timestamp = timestamp
        self.id_course = id_course


def fake_iaa_module(activities=(), stages=(), submissions=()):
    return fake_module(
        'iaaxblock.models',
        IAAActivity=fake_model(list(activities)),
        IAAStage=fake_model(list(stages)),
        IAASubmission=fake_model(list(submissions)),
    )


def fake_iterative_module(questions=(), answers=()):
    return fake_module(
        'iterativexblock.models',
        IterativeXBlockQuestion=fake_model(list(questions)),
        IterativeXBlockAnswer=fake_model(list(answers)),
    )


class TestRedfidEdxApi(ModuleStoreTestCase):

    def setUp(self):
        super(TestRedfidEdxApi, self).setUp()

        self.non_auth_client = Client()
        self.auth_client = Client()
        self.staff_user = UserFactory(
            username='apistaff',
            password='12345',
            email='apistaff@edx.org',
            is_staff=True,
        )
        self.auth_client.login(username='apistaff', password='12345')

        self.course1 = CourseFactory.create(org='mss', course='100', run='2020', display_name='Sample course 1')
        self.course2 = CourseFactory.create(org='mss', course='101', run='2020', display_name='Sample course 2')

        self.student1 = UserFactory(username='student1', password='12345', email='student1@edx.org')
        self.student2 = UserFactory(username='student2', password='12345', email='student2@edx.org')
        CourseEnrollmentFactory(user=self.student1, course_id=self.course1.id)

    # -- request helpers --

    def _post(self, name, payload):
        return self.auth_client.post(
            reverse('redfid_edx_api:%s' % name),
            content_type='application/json',
            data=json.dumps(payload),
        )

    def _post_raw(self, name, raw_body):
        return self.auth_client.post(
            reverse('redfid_edx_api:%s' % name),
            content_type='application/json',
            data=raw_body,
        )

    def _make_student_module(self, student, course_id, xblock_type, block_id, state):
        course_suffix = str(course_id).split('course-v1:')[1]
        module_state_key = 'block-v1:{}+type@{}+block@{}'.format(course_suffix, xblock_type, block_id)
        return StudentModule.objects.create(
            student=student,
            course_id=course_id,
            module_state_key=module_state_key,
            module_type=xblock_type,
            state=json.dumps(state),
        )

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def test_endpoints_require_authentication(self):
        response = self.non_auth_client.get(reverse('redfid_edx_api:get_users'))
        self.assertEqual(response.status_code, 401)

        post_endpoints = [
            'create_user', 'edit_user', 'suspend_or_activate_user',
            'change_user_password', 'delete_user', 'ensure_user_has_redfid_social_auth',
            'get_iaa_user_data', 'get_iaa_course_data',
            'get_iterativexblock_user_data', 'get_iterativexblock_course_data',
            'get_user_certificates', 'get_course_certificates',
            'emit_user_certificate', 'revoke_user_certificate',
            'get_xblock_user_data', 'get_xblock_course_data',
            'enroll_user_into_course', 'unenroll_user_from_course',
        ]
        for name in post_endpoints:
            response = self.non_auth_client.post(
                reverse('redfid_edx_api:%s' % name), content_type='application/json', data='{}',
            )
            self.assertEqual(response.status_code, 401, 'endpoint %s did not require auth' % name)

    # ------------------------------------------------------------------
    # GetRedfidUsers
    # ------------------------------------------------------------------

    def test_get_users_success(self):
        response = self.auth_client.get(reverse('redfid_edx_api:get_users'))
        self.assertEqual(response.status_code, 200)
        usernames = [u['username'] for u in response.json()]
        self.assertIn('student1', usernames)
        self.assertIn('apistaff', usernames)
        student_entry = next(u for u in response.json() if u['username'] == 'student1')
        self.assertEqual(student_entry['email'], 'student1@edx.org')
        self.assertFalse(student_entry['is_staff'])

    # ------------------------------------------------------------------
    # CreateRedfidUser
    # ------------------------------------------------------------------

    def test_create_user_missing_fields(self):
        response = self._post('create_user', {'username': 'newuser'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Missing required fields')

    def test_create_user_invalid_json(self):
        response = self._post_raw('create_user', 'not-json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Invalid JSON data')

    def test_create_user_forbidden_username(self):
        forbidden = settings.FORBIDDEN_USERNAMES[0]
        response = self._post('create_user', {
            'user_id': 'redfid-uuid-1',
            'username': forbidden,
            'password': 'pw12345',
            'email': 'x@example.com',
            'first_name': 'A',
            'last_name': 'B',
            'is_staff': False,
            'is_superuser': False,
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Username is forbidden')

    def test_create_user_already_exists(self):
        User.objects.create_user('dupuser', 'dup@example.com', 'pw12345')
        response = self._post('create_user', {
            'user_id': 'redfid-uuid-2',
            'username': 'dupuser',
            'password': 'pw12345',
            'email': 'dup2@example.com',
            'first_name': 'A',
            'last_name': 'B',
            'is_staff': False,
            'is_superuser': False,
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'User already exists')

    def test_create_user_success(self):
        response = self._post('create_user', {
            'user_id': 'redfid-uuid-3',
            'username': 'brandnewuser',
            'password': 'pw12345',
            'email': 'brandnew@example.com',
            'first_name': 'Brand',
            'last_name': 'New',
            'is_staff': False,
            'is_superuser': False,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'User brandnewuser created successfully')

        user = User.objects.get(username='brandnewuser')
        self.assertEqual(user.email, 'brandnew@example.com')
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.name, 'Brand New')
        social_auth = UserSocialAuth.objects.get(user=user, provider='redfid')
        self.assertEqual(social_auth.uid, 'redfid-uuid-3')

    def test_create_user_userprofile_integrity_error(self):
        with patch.object(UserProfile.objects, 'create', side_effect=IntegrityError('dup')):
            response = self._post('create_user', {
                'user_id': 'redfid-uuid-4',
                'username': 'profileclash',
                'password': 'pw12345',
                'email': 'profileclash@example.com',
                'first_name': 'A',
                'last_name': 'B',
                'is_staff': False,
                'is_superuser': False,
            })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'UserProfile already exists')

    def test_create_user_usersocialauth_integrity_error(self):
        with patch.object(UserSocialAuth.objects, 'create', side_effect=IntegrityError('dup')):
            response = self._post('create_user', {
                'user_id': 'redfid-uuid-5',
                'username': 'socialauthclash',
                'password': 'pw12345',
                'email': 'socialauthclash@example.com',
                'first_name': 'A',
                'last_name': 'B',
                'is_staff': False,
                'is_superuser': False,
            })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'UserSocialAuth already exists')

    # ------------------------------------------------------------------
    # EditRedfidUser
    # ------------------------------------------------------------------

    def test_edit_user_missing_username(self):
        response = self._post('edit_user', {})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Missing username')

    def test_edit_user_invalid_json(self):
        response = self._post_raw('edit_user', 'not-json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Invalid JSON data')

    def test_edit_user_not_found(self):
        response = self._post('edit_user', {'username': 'ghost'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'User not found')

    def test_edit_user_missing_email(self):
        response = self._post('edit_user', {'username': 'student1'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Missing email')

    def test_edit_user_missing_first_name(self):
        response = self._post('edit_user', {'username': 'student1', 'email': 'x@example.com'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Missing first_name')

    def test_edit_user_missing_last_name(self):
        response = self._post('edit_user', {
            'username': 'student1', 'email': 'x@example.com', 'first_name': 'X',
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Missing last_name')

    def test_edit_user_missing_is_staff(self):
        response = self._post('edit_user', {
            'username': 'student1', 'email': 'x@example.com', 'first_name': 'X', 'last_name': 'Y',
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Missing is_staff')

    def test_edit_user_missing_is_superuser(self):
        response = self._post('edit_user', {
            'username': 'student1', 'email': 'x@example.com', 'first_name': 'X', 'last_name': 'Y',
            'is_staff': False,
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Missing is_superuser')

    def test_edit_user_success(self):
        response = self._post('edit_user', {
            'username': 'student1',
            'email': 'student1-new@example.com',
            'first_name': 'Student',
            'last_name': 'One',
            'is_staff': True,
            'is_superuser': False,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'User student1 updated successfully')

        self.student1.refresh_from_db()
        self.assertEqual(self.student1.email, 'student1-new@example.com')
        self.assertTrue(self.student1.is_staff)
        profile = UserProfile.objects.get(user=self.student1)
        self.assertEqual(profile.name, 'Student One')

    def test_edit_user_userprofile_not_found(self):
        UserProfile.objects.filter(user=self.student1).delete()
        response = self._post('edit_user', {
            'username': 'student1',
            'email': 'student1-new@example.com',
            'first_name': 'Student',
            'last_name': 'One',
            'is_staff': False,
            'is_superuser': False,
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'UserProfile not found')

    # ------------------------------------------------------------------
    # SuspendOrActivateRedfidUser
    # ------------------------------------------------------------------

    def test_suspend_missing_username(self):
        response = self._post('suspend_or_activate_user', {})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Missing username')

    def test_suspend_invalid_json(self):
        response = self._post_raw('suspend_or_activate_user', 'not-json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Invalid JSON data')

    def test_suspend_missing_is_active(self):
        response = self._post('suspend_or_activate_user', {'username': 'student1'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Missing is_active')

    def test_suspend_user_not_found(self):
        response = self._post('suspend_or_activate_user', {'username': 'ghost', 'is_active': False})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'User not found')

    def test_suspend_success_deactivate(self):
        response = self._post('suspend_or_activate_user', {'username': 'student1', 'is_active': False})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'User student1 is_active updated successfully')
        self.student1.refresh_from_db()
        self.assertFalse(self.student1.is_active)

    def test_suspend_success_activate(self):
        self.student1.is_active = False
        self.student1.save()
        response = self._post('suspend_or_activate_user', {'username': 'student1', 'is_active': True})
        self.assertEqual(response.status_code, 200)
        self.student1.refresh_from_db()
        self.assertTrue(self.student1.is_active)

    # ------------------------------------------------------------------
    # ChangeRedfidUserPassword
    # ------------------------------------------------------------------

    def test_change_password_missing_username(self):
        response = self._post('change_user_password', {})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Missing username')

    def test_change_password_invalid_json(self):
        response = self._post_raw('change_user_password', 'not-json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Invalid JSON data')

    def test_change_password_missing_password(self):
        response = self._post('change_user_password', {'username': 'student1'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Missing password')

    def test_change_password_user_not_found(self):
        response = self._post('change_user_password', {'username': 'ghost', 'password': 'x'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'User not found')

    def test_change_password_success(self):
        response = self._post('change_user_password', {'username': 'student1', 'password': 'newpw12345'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'User student1 password updated successfully')
        self.student1.refresh_from_db()
        self.assertTrue(self.student1.check_password('newpw12345'))

    # ------------------------------------------------------------------
    # DeleteRedfidUser
    # ------------------------------------------------------------------

    def test_delete_user_missing_username(self):
        response = self._post('delete_user', {})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Missing username')

    def test_delete_user_invalid_json(self):
        response = self._post_raw('delete_user', 'not-json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Invalid JSON data')

    def test_delete_user_not_found(self):
        response = self._post('delete_user', {'username': 'ghost'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'User not found')

    def test_delete_user_success(self):
        response = self._post('delete_user', {'username': 'student2'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'User student2 deleted successfully')
        self.assertFalse(User.objects.filter(username='student2').exists())

    # ------------------------------------------------------------------
    # EnsureUserHasRedfidSocialAuth
    # ------------------------------------------------------------------

    def test_ensure_social_auth_missing_username(self):
        response = self._post('ensure_user_has_redfid_social_auth', {'user_id': 'x'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Missing username')

    def test_ensure_social_auth_invalid_json(self):
        response = self._post_raw('ensure_user_has_redfid_social_auth', 'not-json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Invalid JSON data')

    def test_ensure_social_auth_missing_user_id(self):
        response = self._post('ensure_user_has_redfid_social_auth', {'username': 'student1'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Missing user_id')

    def test_ensure_social_auth_user_not_found(self):
        response = self._post('ensure_user_has_redfid_social_auth', {'username': 'ghost', 'user_id': 'x'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'User not found')

    def test_ensure_social_auth_creates_new(self):
        response = self._post('ensure_user_has_redfid_social_auth', {
            'username': 'student1', 'user_id': 'redfid-uuid-9',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Created OAuth2: True', response.content)
        self.assertIn(b'Deleted SAML: False', response.content)
        self.assertTrue(UserSocialAuth.objects.filter(
            user=self.student1, provider='redfid', uid='redfid-uuid-9').exists())

    def test_ensure_social_auth_replaces_saml(self):
        UserSocialAuth.objects.create(user=self.student1, provider='tpa-saml', uid='saml-uid', extra_data={})
        response = self._post('ensure_user_has_redfid_social_auth', {
            'username': 'student1', 'user_id': 'redfid-uuid-10',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Created OAuth2: True', response.content)
        self.assertIn(b'Deleted SAML: True', response.content)
        self.assertFalse(UserSocialAuth.objects.filter(user=self.student1, provider='tpa-saml').exists())

    def test_ensure_social_auth_already_exists(self):
        UserSocialAuth.objects.create(
            user=self.student1, provider='redfid', uid='redfid-uuid-11', extra_data={})
        response = self._post('ensure_user_has_redfid_social_auth', {
            'username': 'student1', 'user_id': 'redfid-uuid-11',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Created OAuth2: False', response.content)
        self.assertEqual(
            UserSocialAuth.objects.filter(user=self.student1, provider='redfid').count(), 1)

    # ------------------------------------------------------------------
    # GetIAAUserData / GetIAACourseData (iaaxblock is an optional dependency)
    # ------------------------------------------------------------------

    def test_get_iaa_user_data_not_installed(self):
        response = self._post('get_iaa_user_data', {'username': 'student1', 'course_id': 'x'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'IAAXBlock not found')

    def test_get_iaa_course_data_not_installed(self):
        response = self._post('get_iaa_course_data', {'course_id': 'x'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'IAAXBlock not found')

    def test_get_iaa_user_data_invalid_json(self):
        with fake_iaa_module():
            response = self._post_raw('get_iaa_user_data', 'not-json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Invalid JSON data')

    def test_get_iaa_course_data_invalid_json(self):
        with fake_iaa_module():
            response = self._post_raw('get_iaa_course_data', 'not-json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Invalid JSON data')

    def test_get_iaa_user_data_validation(self):
        with fake_iaa_module():
            response = self._post('get_iaa_user_data', {})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.content, b'Missing username')

            response = self._post('get_iaa_user_data', {'username': 'ghost'})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.content, b'User not found')

            response = self._post('get_iaa_user_data', {'username': 'student1'})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.content, b'Missing course_id')

    def test_get_iaa_user_data_success(self):
        activity = FakeIAAActivity(id_course='course-x', activity_name='Activity 1')
        stage = FakeIAAStage(activity=activity, stage_label='Stage 1', stage_number=1)
        submission = FakeIAASubmission(
            id_student=self.student1.id, stage=stage, submission='my answer', submission_time='2020-01-01',
        )
        with fake_iaa_module(activities=[activity], stages=[stage], submissions=[submission]):
            response = self._post('get_iaa_user_data', {'username': 'student1', 'course_id': 'course-x'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['name'], 'Activity 1')
        self.assertEqual(data[0]['stages'][0]['answer'], 'my answer')

    def test_get_iaa_course_data_missing_course_id(self):
        with fake_iaa_module():
            response = self._post('get_iaa_course_data', {})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Missing course_id')

    def test_get_iaa_course_data_success(self):
        activity = FakeIAAActivity(id_course='course-x', activity_name='Activity 1')
        stage = FakeIAAStage(activity=activity, stage_label='Stage 1', stage_number=1)
        submission = FakeIAASubmission(
            id_student=self.student1.id, stage=stage, submission='my answer', submission_time='2020-01-01',
        )
        with fake_iaa_module(activities=[activity], stages=[stage], submissions=[submission]):
            response = self._post('get_iaa_course_data', {'course_id': 'course-x'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data[0]['stages'][0]['answers'][0]['username'], 'student1')
        self.assertEqual(data[0]['stages'][0]['answers'][0]['answer'], 'my answer')

    # ------------------------------------------------------------------
    # GetIterativeXBlockUserData / GetIterativeXBlockCourseData (optional dependency)
    # ------------------------------------------------------------------

    def test_get_iterativexblock_user_data_not_installed(self):
        response = self._post('get_iterativexblock_user_data', {'username': 'student1', 'course_id': 'x'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'IterativeXBlock not found')

    def test_get_iterativexblock_course_data_not_installed(self):
        response = self._post('get_iterativexblock_course_data', {'course_id': 'x'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'IterativeXBlock not found')

    def test_get_iterativexblock_user_data_invalid_json(self):
        with fake_iterative_module():
            response = self._post_raw('get_iterativexblock_user_data', 'not-json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Invalid JSON data')

    def test_get_iterativexblock_course_data_invalid_json(self):
        with fake_iterative_module():
            response = self._post_raw('get_iterativexblock_course_data', 'not-json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Invalid JSON data')

    def test_get_iterativexblock_user_data_validation(self):
        with fake_iterative_module():
            response = self._post('get_iterativexblock_user_data', {})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.content, b'Missing username')

            response = self._post('get_iterativexblock_user_data', {'username': 'ghost'})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.content, b'User not found')

            response = self._post('get_iterativexblock_user_data', {'username': 'student1'})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.content, b'Missing course_id')

    def test_get_iterativexblock_user_data_success(self):
        question = FakeIterativeQuestion(id=1, id_xblock='block-1', id_course='course-x', id_question='q1')
        answer = FakeIterativeAnswer(
            id_student=self.student1.id, question_id=1, answer='42', timestamp='2020-01-01', id_course='course-x',
        )
        with fake_iterative_module(questions=[question], answers=[answer]):
            response = self._post('get_iterativexblock_user_data', {'username': 'student1', 'course_id': 'course-x'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['answer'], '42')

    def test_get_iterativexblock_course_data_missing_course_id(self):
        with fake_iterative_module():
            response = self._post('get_iterativexblock_course_data', {})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Missing course_id')

    def test_get_iterativexblock_course_data_success(self):
        question = FakeIterativeQuestion(id=1, id_xblock='block-1', id_course='course-x', id_question='q1')
        answer = FakeIterativeAnswer(
            id_student=self.student1.id, question_id=1, answer='42', timestamp='2020-01-01', id_course='course-x',
        )
        with fake_iterative_module(questions=[question], answers=[answer]):
            response = self._post('get_iterativexblock_course_data', {'course_id': 'course-x'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data[0]['answers'][0]['username'], 'student1')
        self.assertEqual(data[0]['answers'][0]['answer'], '42')

    def test_get_iterativexblock_course_data_unknown_student(self):
        question = FakeIterativeQuestion(id=1, id_xblock='block-1', id_course='course-x', id_question='q1')
        answer = FakeIterativeAnswer(
            id_student=999999, question_id=1, answer='42', timestamp='2020-01-01', id_course='course-x',
        )
        with fake_iterative_module(questions=[question], answers=[answer]):
            response = self._post('get_iterativexblock_course_data', {'course_id': 'course-x'})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()[0]['answers'][0]['username'])

    # ------------------------------------------------------------------
    # Certificates: GetUserCertificates / GetCourseCertificates /
    # EmitUserCertificate / RevokeUserCertificate
    # ------------------------------------------------------------------

    def test_get_user_certificates_invalid_json(self):
        response = self._post_raw('get_user_certificates', 'not-json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Invalid JSON data')

    def test_get_user_certificates_missing_username(self):
        response = self._post('get_user_certificates', {})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Missing username')

    def test_get_user_certificates_empty(self):
        response = self._post('get_user_certificates', {'username': 'student1'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_get_user_certificates_success(self):
        GeneratedCertificate.objects.create(
            user=self.student1, course_id=self.course1.id, verify_uuid='uuid-1', key='key-1',
        )
        response = self._post('get_user_certificates', {'username': 'student1'})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['course_id'], str(self.course1.id))
        self.assertEqual(data[0]['verify_uuid'], 'uuid-1')

    def test_get_course_certificates_invalid_json(self):
        response = self._post_raw('get_course_certificates', 'not-json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Invalid JSON data')

    def test_get_course_certificates_missing_course_id(self):
        response = self._post('get_course_certificates', {})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Missing course_id')

    def test_get_course_certificates_invalid_course_id(self):
        response = self._post('get_course_certificates', {'course_id': 'not-a-valid-course-id!!'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Course not found')

    def test_get_course_certificates_success(self):
        GeneratedCertificate.objects.create(
            user=self.student1, course_id=self.course1.id, verify_uuid='uuid-2', key='key-2',
        )
        response = self._post('get_course_certificates', {'course_id': str(self.course1.id)})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['username'], 'student1')

    def test_emit_certificate_invalid_json(self):
        response = self._post_raw('emit_user_certificate', 'not-json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Invalid JSON data')

    def test_emit_certificate_missing_username(self):
        response = self._post('emit_user_certificate', {'course_id': str(self.course1.id)})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Missing username')

    def test_emit_certificate_missing_course_id(self):
        response = self._post('emit_user_certificate', {'username': 'student1'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Missing course_id')

    def test_emit_certificate_user_not_found(self):
        response = self._post('emit_user_certificate', {'username': 'ghost', 'course_id': str(self.course1.id)})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'User not found')

    def test_emit_certificate_invalid_course_id(self):
        response = self._post('emit_user_certificate', {'username': 'student1', 'course_id': 'bad!!'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Invalid course_id')

    def test_emit_certificate_success(self):
        with patch('redfid_edx_api.views.XQueueCertInterface') as MockXQueue:
            response = self._post('emit_user_certificate', {
                'username': 'student1', 'course_id': str(self.course1.id),
            })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Certificate emitted for user student1', response.content)
        MockXQueue.return_value.add_cert.assert_called_once()
        _, kwargs = MockXQueue.return_value.add_cert.call_args
        self.assertEqual(kwargs.get('forced_grade'), 'Aprobado')

    def test_revoke_certificate_invalid_json(self):
        response = self._post_raw('revoke_user_certificate', 'not-json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Invalid JSON data')

    def test_revoke_certificate_missing_username(self):
        response = self._post('revoke_user_certificate', {'course_id': str(self.course1.id)})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Missing username')

    def test_revoke_certificate_missing_course_id(self):
        response = self._post('revoke_user_certificate', {'username': 'student1'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Missing course_id')

    def test_revoke_certificate_user_not_found(self):
        response = self._post('revoke_user_certificate', {'username': 'ghost', 'course_id': str(self.course1.id)})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'User not found')

    def test_revoke_certificate_invalid_course_id(self):
        response = self._post('revoke_user_certificate', {'username': 'student1', 'course_id': 'bad!!'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Invalid course_id')

    def test_revoke_certificate_not_found(self):
        response = self._post('revoke_user_certificate', {
            'username': 'student1', 'course_id': str(self.course1.id),
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Certificate not found')

    def test_revoke_certificate_success(self):
        GeneratedCertificate.objects.create(
            user=self.student1, course_id=self.course1.id, verify_uuid='uuid-3', key='key-3',
        )
        response = self._post('revoke_user_certificate', {
            'username': 'student1', 'course_id': str(self.course1.id),
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Certificate revoked for user student1', response.content)
        self.assertFalse(GeneratedCertificate.objects.filter(
            user=self.student1, course_id=self.course1.id).exists())

    # ------------------------------------------------------------------
    # GetXBlockUserData / GetXBlockCourseData
    # ------------------------------------------------------------------

    def test_get_xblock_user_data_invalid_json(self):
        response = self._post_raw('get_xblock_user_data', 'not-json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Invalid JSON data')

    def test_get_xblock_user_data_missing_fields(self):
        base = {
            'username': 'student1', 'id_xblock': 'b1', 'course_id': str(self.course1.id),
            'xblock_type': 'problem',
        }
        for missing in ('username', 'id_xblock', 'course_id', 'xblock_type'):
            payload = {k: v for k, v in base.items() if k != missing}
            response = self._post('get_xblock_user_data', payload)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.content, ('Missing %s' % missing).encode())

    def test_get_xblock_user_data_invalid_type(self):
        response = self._post('get_xblock_user_data', {
            'username': 'student1', 'id_xblock': 'b1', 'course_id': str(self.course1.id),
            'xblock_type': 'not-a-real-type',
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Invalid xblock_type')

    def test_get_xblock_user_data_user_not_found(self):
        response = self._post('get_xblock_user_data', {
            'username': 'ghost', 'id_xblock': 'b1', 'course_id': str(self.course1.id),
            'xblock_type': 'problem',
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'User not found')

    def test_get_xblock_user_data_no_response(self):
        response = self._post('get_xblock_user_data', {
            'username': 'student1', 'id_xblock': 'nonexistent', 'course_id': str(self.course1.id),
            'xblock_type': 'problem',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'answer': None})

    def test_get_xblock_user_data_freetextresponse(self):
        self._make_student_module(
            self.student1, self.course1.id, 'freetextresponse', 'ftr1',
            {'student_answer': 'hello world'},
        )
        response = self._post('get_xblock_user_data', {
            'username': 'student1', 'id_xblock': 'ftr1', 'course_id': str(self.course1.id),
            'xblock_type': 'freetextresponse',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'answer': 'hello world'})

    def test_get_xblock_user_data_problem_list_of_ids(self):
        self._make_student_module(
            self.student1, self.course1.id, 'problem', 'p1', {'student_answers': {'a': '1'}},
        )
        self._make_student_module(
            self.student1, self.course1.id, 'problem', 'p2', {'student_answers': {'a': '2'}},
        )
        response = self._post('get_xblock_user_data', {
            'username': 'student1', 'id_xblock': ['p1', 'p2', 'p3'], 'course_id': str(self.course1.id),
            'xblock_type': 'problem',
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 3)
        self.assertEqual(data[0]['answer'], {'a': '1'})
        self.assertEqual(data[1]['answer'], {'a': '2'})
        self.assertIsNone(data[2]['answer'])

    def test_get_xblock_course_data_invalid_json(self):
        response = self._post_raw('get_xblock_course_data', 'not-json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Invalid JSON data')

    def test_get_xblock_course_data_missing_fields(self):
        base = {'id_xblock': 'b1', 'course_id': str(self.course1.id), 'xblock_type': 'problem'}
        for missing in ('id_xblock', 'course_id', 'xblock_type'):
            payload = {k: v for k, v in base.items() if k != missing}
            response = self._post('get_xblock_course_data', payload)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.content, ('Missing %s' % missing).encode())

    def test_get_xblock_course_data_invalid_type(self):
        response = self._post('get_xblock_course_data', {
            'id_xblock': 'b1', 'course_id': str(self.course1.id), 'xblock_type': 'not-a-real-type',
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Invalid xblock_type')

    def test_get_xblock_course_data_single_id(self):
        self._make_student_module(
            self.student1, self.course1.id, 'problem', 'p1', {'student_answers': {'a': '1'}},
        )
        response = self._post('get_xblock_course_data', {
            'id_xblock': 'p1', 'course_id': str(self.course1.id), 'xblock_type': 'problem',
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['id_xblock'], 'p1')
        self.assertEqual(data['answers'][0]['username'], 'student1')
        self.assertEqual(data['answers'][0]['answer'], {'a': '1'})

    def test_get_xblock_course_data_list_of_ids(self):
        self._make_student_module(
            self.student1, self.course1.id, 'problem', 'p1', {'student_answers': {'a': '1'}},
        )
        response = self._post('get_xblock_course_data', {
            'id_xblock': ['p1', 'p2'], 'course_id': str(self.course1.id), 'xblock_type': 'problem',
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]['answers'][0]['answer'], {'a': '1'})
        self.assertEqual(data[1]['answers'], [])

    # ------------------------------------------------------------------
    # EnrollUserIntoCourse / UnenrollUserFromCourse
    # ------------------------------------------------------------------

    def test_enroll_invalid_json(self):
        response = self._post_raw('enroll_user_into_course', 'not-json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Invalid JSON data')

    def test_enroll_missing_username(self):
        response = self._post('enroll_user_into_course', {'course_id': str(self.course2.id)})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Missing username')

    def test_enroll_missing_course_id(self):
        response = self._post('enroll_user_into_course', {'username': 'student2'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Missing course_id')

    def test_enroll_invalid_course_id(self):
        response = self._post('enroll_user_into_course', {'username': 'student2', 'course_id': 'bad!!'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Invalid course_id')

    def test_enroll_user_not_found(self):
        response = self._post('enroll_user_into_course', {
            'username': 'ghost', 'course_id': str(self.course2.id),
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'User not found')

    def test_enroll_success(self):
        response = self._post('enroll_user_into_course', {
            'username': 'student2', 'course_id': str(self.course2.id),
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'User student2 enrolled in course', response.content)
        self.assertTrue(CourseEnrollment.is_enrolled(self.student2, self.course2.id))

    def test_enroll_error(self):
        with patch('lms.djangoapps.instructor.enrollment.enroll_email', side_effect=Exception('boom')):
            response = self._post('enroll_user_into_course', {
                'username': 'student2', 'course_id': str(self.course2.id),
            })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Error enrolling user in course')

    def test_unenroll_invalid_json(self):
        response = self._post_raw('unenroll_user_from_course', 'not-json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Invalid JSON data')

    def test_unenroll_missing_username(self):
        response = self._post('unenroll_user_from_course', {'course_id': str(self.course1.id)})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Missing username')

    def test_unenroll_missing_course_id(self):
        response = self._post('unenroll_user_from_course', {'username': 'student1'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Missing course_id')

    def test_unenroll_invalid_course_id(self):
        response = self._post('unenroll_user_from_course', {'username': 'student1', 'course_id': 'bad!!'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Invalid course_id')

    def test_unenroll_user_not_found(self):
        response = self._post('unenroll_user_from_course', {
            'username': 'ghost', 'course_id': str(self.course1.id),
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'User not found')

    def test_unenroll_success(self):
        self.assertTrue(CourseEnrollment.is_enrolled(self.student1, self.course1.id))
        response = self._post('unenroll_user_from_course', {
            'username': 'student1', 'course_id': str(self.course1.id),
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'User student1 unenrolled from course', response.content)
        self.assertFalse(CourseEnrollment.is_enrolled(self.student1, self.course1.id))

    def test_unenroll_error(self):
        with patch('lms.djangoapps.instructor.enrollment.unenroll_email', side_effect=Exception('boom')):
            response = self._post('unenroll_user_from_course', {
                'username': 'student1', 'course_id': str(self.course1.id),
            })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'Error unenrolling user from course')
