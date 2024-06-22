from django.conf.urls import url
from django.views.decorators.csrf import csrf_exempt
from .views import *


urlpatterns = [
    url('logout_get/', RedfidLogoutGet.as_view(), name='logout_get'),
    url('logout_post/', csrf_exempt(RedfidLogoutPost.as_view()), name='logout_post'),
    url('get_users/', GetRedfidUsers.as_view(), name='get_users'),
    url('create_user/', csrf_exempt(CreateRedfidUser.as_view()), name='create_user'),
    url('edit_user/', csrf_exempt(EditRedfidUser.as_view()), name='edit_user'),
    url('suspend_or_activate_user/', csrf_exempt(SuspendOrActivateRedfidUser.as_view()), name='suspend_or_activate_user'),
    url('change_user_password/', csrf_exempt(ChangeRedfidUserPassword.as_view()), name='change_user_password'),
    url('delete_user/', csrf_exempt(DeleteRedfidUser.as_view()), name='delete_user'),
    url('get_iaa_user_data/', csrf_exempt(GetIAAUserData.as_view()), name='get_iaa_user_data'),
    url('get_iaa_course_data/', csrf_exempt(GetIAACourseData.as_view()), name='get_iaa_course_data'),
    url('get_iterativexblock_user_data/', csrf_exempt(GetIterativeXBlockUserData.as_view()), name='get_iterativexblock_user_data'),
    url('get_iterativexblock_course_data/', csrf_exempt(GetIterativeXBlockCourseData.as_view()), name='get_iterativexblock_course_data'),
    url('get_user_certificates/', csrf_exempt(GetUserCertificates.as_view()), name='get_user_certificates'),
    url('get_course_certificates/', csrf_exempt(GetCourseCertificates.as_view()), name='get_course_certificates'),
    url('emit_user_certificate/', csrf_exempt(EmitUserCertificate.as_view()), name='emit_user_certificate'),
    url('revoke_user_certificate/', csrf_exempt(RevokeUserCertificate.as_view()), name='revoke_user_certificate'),
    url('get_xblock_user_data/', csrf_exempt(GetXBlockUserData.as_view()), name='get_xblock_user_data'),
    url('enroll_user_into_course/', csrf_exempt(EnrollUserIntoCourse.as_view()), name='enroll_user_into_course'),
    url('unenroll_user_from_course/', csrf_exempt(UnenrollUserFromCourse.as_view()), name='unenroll_user_from_course'),
]