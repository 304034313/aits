from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.core.paginator import Paginator
from django.core.files.storage import default_storage
import logging

from users.models import UserPreference
from .models import Project, ProjectMember, ProjectThirdPartyConfig, WorkspaceMenuConfig
from .serializers import (
    ProjectSerializer, ProjectCreateSerializer, ProjectMemberSerializer,
    ProjectMemberCreateSerializer, ProjectDetailSerializer, ProjectThirdPartyConfigSerializer,
    WorkspaceMenuConfigSerializer,
)
from common.api import response
from common.mixins import AdminBypassMixin

logger = logging.getLogger(__name__)


class ProjectViewSet(AdminBypassMixin, viewsets.ModelViewSet):
    """项目管理ViewSet"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if self.is_admin:
            queryset = Project.objects.all()
        else:
            queryset = Project.objects.filter(
                Q(members__user=user) | Q(created_by=user) | Q(owner=user)
            ).distinct()

        # 按项目类型过滤
        project_type = self.request.query_params.get('project_type', '')
        if project_type and project_type in ['api', 'web', 'app', 'perf']:
            queryset = queryset.filter(project_type=project_type)

        # 搜索功能
        search_query = self.request.query_params.get('search', '')
        if search_query:
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(description__icontains=search_query)
            )

        return queryset.prefetch_related('linked_api_projects').order_by('-updated_at')

    def get_serializer_class(self):
        if self.action == 'create':
            return ProjectCreateSerializer
        elif self.action in ['retrieve', 'update', 'partial_update']:
            return ProjectDetailSerializer
        return ProjectSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 20))
        # 直接使用封装的分页函数
        return response(
            kind="paginated_queryset",
            data=queryset,
            page=page,
            page_size=page_size,
            serializer_class=self.get_serializer_class(),
            message="获取项目列表成功"
        )

    def perform_destroy(self, instance):
        """删除项目时，同时删除所有相关的物理文件和数据库记录"""
        try:
            # 获取项目下的所有上传文件
            uploaded_files = instance.uploaded_files.all()

            # 删除物理文件
            for uploaded_file in uploaded_files:
                if uploaded_file.file:
                    try:
                        file_path = uploaded_file.file.name
                        if default_storage.exists(file_path):
                            default_storage.delete(file_path)
                            logger.info(f"已删除项目文件: {file_path}")
                        else:
                            logger.warning(f"项目文件不存在: {file_path}")
                    except Exception as e:
                        logger.warning(f"删除项目文件失败: {uploaded_file.file.name if uploaded_file.file else 'Unknown'}, 错误: {e}")

            # 删除项目记录（这会自动删除所有相关的CASCADE记录）
            super().perform_destroy(instance)
            logger.info(f"已删除项目: {instance.name} (ID: {instance.id})")

        except Exception as e:
            logger.error(f"删除项目失败: {instance.id}, 错误: {e}")
            raise

    @action(detail=False, methods=['get'])
    def user_projects(self, request):
        """获取当前用户的项目列表"""
        if self.is_admin:
            projects = Project.objects.all()
        else:
            user = request.user
            projects = Project.objects.filter(
                Q(members__user=user) | Q(created_by=user) | Q(owner=user)
            ).distinct()
        serializer = ProjectSerializer(projects, many=True)
        return response(
            kind="success",
            data=serializer.data,
            message="获取用户项目列表成功"
        )

    @action(detail=True, methods=['post'])
    def leave(self, request, pk=None):
        """离开项目"""
        project = self.get_object()
        member = get_object_or_404(ProjectMember, project=project, user=request.user)

        # 项目所有者不能离开项目
        if project.owner == request.user:
            return response(
                kind="error",
                message="项目所有者不能离开项目"
            )

        member.delete()
        return response(
            kind="success",
            data={"message": "已成功离开项目"},
            message="已成功离开项目"
        )

    @action(detail=True, methods=['get'])
    def statistics(self, request, pk=None):
        """获取项目统计信息"""
        project = self.get_object()

        if not self.check_project_member(project, 'can_view_reports'):
            return response(
                kind="error",
                message="您没有权限查看此项目的统计信息"
            )

        # 统计信息
        total_members = project.members.count()
        total_environments = project.environments.count()
        total_knowledge_files = project.knowledge_files.count()

        return response(
            kind="success",
            data={
                "project_id": project.id,
                "project_name": project.name,
                "total_members": total_members,
                "total_environments": total_environments,
                "total_knowledge_files": total_knowledge_files,
                "created_at": project.created_at,
                "updated_at": project.updated_at
            },
            message="获取项目统计信息成功"
        )


class ProjectThirdPartyConfigView(generics.GenericAPIView):
    """项目第三方配置：按 project_id 查询与创建/更新。"""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProjectThirdPartyConfigSerializer

    @staticmethod
    def _extract_project_id(request):
        raw = (
            request.query_params.get('project_id')
            or (request.data.get('project_id') if isinstance(request.data, dict) else None)
            or (request.data.get('project') if isinstance(request.data, dict) else None)
        )
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    def get(self, request):
        project_id = self._extract_project_id(request)
        if not project_id:
            return Response({'detail': 'project_id 必填'}, status=status.HTTP_400_BAD_REQUEST)
        row = (
            ProjectThirdPartyConfig.objects.select_related('project')
            .filter(project_id=project_id)
            .first()
        )
        if not row:
            return Response(
                {
                    'project': project_id,
                    'project_id': project_id,
                    'project_name': None,
                    'grafana_dashboard_url': '',
                    'ai_diagnosis_url': '',
                    'grafana_admin_url': '',
                    'prometheus_url': '',
                    'skywalking_url': '',
                },
                status=status.HTTP_200_OK,
            )
        return Response(self.get_serializer(row).data, status=status.HTTP_200_OK)

    def post(self, request):
        return self._upsert(request)

    def put(self, request):
        return self._upsert(request)

    def patch(self, request):
        return self._upsert(request)

    def _upsert(self, request):
        if not isinstance(request.data, dict):
            return Response({'detail': '请求体必须是 JSON 对象'}, status=status.HTTP_400_BAD_REQUEST)
        project_id = self._extract_project_id(request)
        if not project_id:
            return Response({'detail': 'project_id 必填'}, status=status.HTTP_400_BAD_REQUEST)

        payload = {
            'project': project_id,
            'grafana_dashboard_url': request.data.get('grafana_dashboard_url', ''),
            'ai_diagnosis_url': request.data.get('ai_diagnosis_url', ''),
            'grafana_admin_url': request.data.get('grafana_admin_url', ''),
            'prometheus_url': request.data.get('prometheus_url', ''),
            'skywalking_url': request.data.get('skywalking_url', ''),
        }
        row = ProjectThirdPartyConfig.objects.filter(project_id=project_id).first()
        serializer = self.get_serializer(instance=row, data=payload, partial=bool(row))
        serializer.is_valid(raise_exception=True)
        saved = serializer.save()
        return Response(self.get_serializer(saved).data, status=status.HTTP_200_OK)


class ProjectMemberListView(AdminBypassMixin, generics.ListCreateAPIView):
    """项目成员列表和添加视图"""
    serializer_class = ProjectMemberSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        project_id = self.kwargs.get('project_id')
        project = get_object_or_404(Project, id=project_id)
        if not self.check_project_member(project, 'can_view_reports'):
            return ProjectMember.objects.none()
        return ProjectMember.objects.filter(project=project)


# ===================== 工作区菜单配置 =====================

class MenuConfigListView(generics.GenericAPIView):
    """GET: 返回全部模块的菜单配置（已认证用户）"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        configs = WorkspaceMenuConfig.objects.all()
        data = {}
        for cfg in configs:
            data[cfg.module] = cfg.menu_items
        return response(kind='success', data=data, message='获取菜单配置成功')


class MenuConfigDetailView(generics.GenericAPIView):
    """
    GET:  返回单个模块的菜单配置（已认证用户）
    PUT:  更新单个模块的菜单配置（仅管理员 is_staff）
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, module):
        valid_modules = [c[0] for c in WorkspaceMenuConfig.MODULE_CHOICES]
        if module not in valid_modules:
            return response(kind='error', message=f'无效的模块: {module}')
        try:
            cfg = WorkspaceMenuConfig.objects.get(module=module)
            serializer = WorkspaceMenuConfigSerializer(cfg)
            return response(kind='success', data=serializer.data)
        except WorkspaceMenuConfig.DoesNotExist:
            return response(kind='success', data={'module': module, 'menu_items': []})

    def put(self, request, module):
        if not request.user.is_staff:
            return response(kind='permission_denied', message='仅管理员可修改菜单配置')

        valid_modules = [c[0] for c in WorkspaceMenuConfig.MODULE_CHOICES]
        if module not in valid_modules:
            return response(kind='error', message=f'无效的模块: {module}')

        menu_items = request.data.get('menu_items')
        if menu_items is None:
            return response(kind='validation_error', errors={'menu_items': '此字段是必填项'})

        cfg, _ = WorkspaceMenuConfig.objects.update_or_create(
            module=module,
            defaults={'menu_items': menu_items, 'updated_by': request.user},
        )
        serializer = WorkspaceMenuConfigSerializer(cfg)
        return response(kind='updated', data=serializer.data, message='菜单配置已保存')


class MenuConfigResetView(generics.GenericAPIView):
    """POST: 重置所有模块菜单配置为默认值（仅管理员 is_staff）"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not request.user.is_staff:
            return response(kind='permission_denied', message='仅管理员可重置菜单配置')

        module = request.data.get('module')
        if module:
            WorkspaceMenuConfig.objects.filter(module=module).delete()
        else:
            WorkspaceMenuConfig.objects.all().delete()
        return response(kind='success', message='菜单配置已重置为默认值')
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ProjectMemberCreateSerializer
        return ProjectMemberSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['project'] = get_object_or_404(Project, id=self.kwargs.get('project_id'))
        return context


class ProjectMemberDetailView(AdminBypassMixin, generics.RetrieveUpdateDestroyAPIView):
    """项目成员详情视图"""
    serializer_class = ProjectMemberSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        project_id = self.kwargs.get('project_id')
        project = get_object_or_404(Project, id=project_id)
        if not self.check_project_member(project, 'can_edit'):
            return ProjectMember.objects.none()
        return ProjectMember.objects.filter(project=project)