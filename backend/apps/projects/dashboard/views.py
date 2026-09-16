"""
项目 Dashboard 统计 API：企业级研发效能核心指标
按 project_type 动态路由到对应模型（api/web/app），统一返回结构。
"""
from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from projects.models import Project
from .services import get_dashboard_summary, get_dashboard_trend, get_dashboard_top_failures


def _get_project_or_404(project_id, user):
    """校验项目存在且用户有权限"""
    from django.shortcuts import get_object_or_404
    from common.mixins import is_admin_user
    if is_admin_user(user):
        return get_object_or_404(Project, id=project_id)
    return get_object_or_404(
        Project.objects.filter(
            Q(members__user=user) | Q(created_by=user) | Q(owner=user)
        ).distinct(),
        id=project_id
    )


class DashboardSummaryView(APIView):
    """Top Cards 核心指标：今日通过率、执行次数、AI 创建用例占比、用例总数"""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = _get_project_or_404(project_id, request.user)
        data = get_dashboard_summary(project)
        return Response(data)


class DashboardTrendView(APIView):
    """趋势图表：最近 7 天每日执行总数、成功数、失败数、通过率"""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = _get_project_or_404(project_id, request.user)
        data = get_dashboard_trend(project)
        return Response({'data': data})


class DashboardTopFailuresView(APIView):
    """风险预警：最近 7 天失败次数最多的 Top 5 测试用例"""

    permission_classes = [IsAuthenticated]

    def get(self, request, project_id):
        project = _get_project_or_404(project_id, request.user)
        data = get_dashboard_top_failures(project)
        return Response({'data': data})
