from django.urls import path
from . import views

app_name = 'settings'

urlpatterns = [
    path('menu-config/', views.MenuConfigListView.as_view(), name='menu_config_list'),
    path('menu-config/<str:module>/', views.MenuConfigDetailView.as_view(), name='menu_config_detail'),
    path('menu-config-reset/', views.MenuConfigResetView.as_view(), name='menu_config_reset'),
]
