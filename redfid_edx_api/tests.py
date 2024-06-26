
from mock import patch, Mock
from django.test import TestCase, Client
from django.test.client import RequestFactory
from django.urls import reverse
from common.djangoapps.util.testing import UrlResetMixin
from xmodule.modulestore import ModuleStoreEnum
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from xmodule.modulestore.tests.factories import CourseFactory, ItemFactory
from common.djangoapps.student.tests.factories import UserFactory, CourseEnrollmentFactory
from capa.tests.response_xml_factory import StringResponseXMLFactory
from lms.djangoapps.courseware.tests.factories import StudentModuleFactory
from lms.djangoapps.grades.tasks import compute_all_grades_for_course as task_compute_all_grades_for_course
from opaque_keys.edx.keys import CourseKey
from lms.djangoapps.courseware.courses import get_course_with_access
from six import text_type
from six.moves import range

from . import views

USER_COUNT = 11


class TestRedfidEdxApi(UrlResetMixin, ModuleStoreTestCase):

    def setUp(self):
        super(TestRedfidEdxApi, self).setUp()

        #### crear credenciales oauth

        self.course1 = CourseFactory.create(org='mss', course='100', display_name='Sample course 1')
        self.course2 = CourseFactory.create(org='mss', course='200', display_name='Sample course 2')

        # Now give it some content
        ### agregar iaa, iterative, encuestas
        with self.store.bulk_operations(self.course1.id, emit_signals=False):
            chapter = ItemFactory.create(
                parent_location=self.course1.location,
                category="sequential",
            )
            section = ItemFactory.create(
                parent_location=chapter.location,
                category="sequential",
                metadata={'graded': True, 'format': 'Homework'}
            )
            self.items = [
                ItemFactory.create(
                    parent_location=section.location,
                    category="problem",
                    data=StringResponseXMLFactory().build_xml(answer='foo'),
                    metadata={'rerandomize': 'always'}
                )
                for __ in range(USER_COUNT - 1)
            ]

        #### crear certificados
        self.users = [UserFactory.create() for _ in range(USER_COUNT)]
        for user in self.users:
            CourseEnrollmentFactory.create(user=user, course_id=self.course1.id)
        for i, item in enumerate(self.items):
            for j, user in enumerate(self.users):
                StudentModuleFactory.create(
                    grade=1 if i < j else 0,
                    max_grade=1,
                    student=user,
                    course_id=self.course1.id,
                    module_state_key=item.location
                )
        task_compute_all_grades_for_course.apply_async(kwargs={'course_key': text_type(self.course1.id)})

        # Patch the comment client user save method so it does not try
        # to create a new cc user when creating a django user
        with patch('student.models.cc.User.save'):
            self.student1 = UserFactory(username='student1', password='test', email='student1@edx.org')
            self.student2 = UserFactory(username='student2', password='test', email='student2@edx.org')
            self.student3 = UserFactory(username='student3', password='test', email='student3@edx.org')

            # Enroll the student in the course
            CourseEnrollmentFactory(user=self.student1, course_id=self.course1.id)

