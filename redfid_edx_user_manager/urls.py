from django.contrib import admin
from django.conf.urls import url
from django.views.decorators.csrf import csrf_exempt
from .views import *


urlpatterns = [
    url('logout_get/', RedfidLogoutGet.as_view(), name='logout_get'),
    url('logout_post/', csrf_exempt(RedfidLogoutPost.as_view()), name='logout_post'),
    url('create_user/', csrf_exempt(CreateRedfidUser.as_view()), name='create_user'),
]