from rest_framework import generics, permissions, status, serializers, viewsets
from rest_framework.decorators import api_view, permission_classes

from common.mixins import AdminBypassMixin
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta

from django.db.models import Q
import logging
import json
import time

from httprunner import HttpRunner
from common.api import response

logger = logging.getLogger(__name__)
from .models import (
    APISpecification, APIModule, APIEndpoint, APITestCase,
    APITestExecution, APITestSuite, APITestCaseExecutionDetail,
    APITestSuiteExecutionDetail, APITestSuiteCaseExecution
)
from projects.models import Environment
from .tasks import (
    generate_endpoint_test_cases_async,
    generate_scenario_async,
    import_postman_collection_async,
)
from .serializers import (
    APISpecificationSerializer, APISpecificationCreateSerializer,
    APITestCaseSerializer, APITestCaseDetailSerializer, APITestCaseCreateSerializer,
    APITestExecutionListSerializer,
    EndpointTestGenerationSerializer,
    APITestSuiteSerializer, APITestSuiteCreateSerializer, APITestSuiteUpdateSerializer,
    APITestSuiteAddTestCaseSerializer, APITestCaseExecutionDetailSerializer,
    APITestSuiteExecutionDetailSerializer, APITestSuiteCaseExecutionSerializer,
    APITestCaseScriptUpdateSerializer,
)
from common.storage import APISpecFileService
from .api_parser_service import APIParserService

from projects.models import Project
from projects.knowledge.models import UploadedFile
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.core.files.storage import default_storage
from ai_core.models import LLMConfiguration

logger = logging.getLogger(__name__)


class APISpecificationListView(AdminBypassMixin, generics.ListCreateAPIView):
    """API规范列表和创建视图"""
    serializer_class = APISpecificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None  # 禁用默认分页，使用自定义分页

    def get_queryset(self):
        # 使用URL路径参数获取项目ID
        project_id = self.kwargs.get('project_id')
        if project_id:
            return APISpecification.objects.filter(project_id=project_id)
        else:
            # 如果没有项目ID，返回空查询集
            return APISpecification.objects.none()

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return APISpecificationCreateSerializer
        return APISpecificationSerializer

    def list(self, request, *args, **kwargs):
        """自定义列表响应，使用统一响应格式"""
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
            message="获取API规范列表成功"
        )
    
    def create(self, request, *args, **kwargs):
        """创建API规范 - 使用统一响应格式"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        return response(
            kind="success",
            data=serializer.data,
            message="API规范创建成功"
        )

    def create(self, request, *args, **kwargs):
        project_id = self.kwargs.get('project_id')
        
        if not project_id:
            return response(
                kind="error",
                message="项目ID未提供"
            )

        project = get_object_or_404(Project, id=project_id)

        if not self.check_project_member(project, 'can_edit'):
            return response(
                kind="permission_denied",
                message="没有权限"
            )

        spec_file = request.FILES.get('spec_file')
        if not spec_file:
            return response(
                kind="error",
                message="必须上传API规范文件"
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        spec_type = serializer.validated_data.get('spec_type', 'swagger')
        # Postman 专属的导入参数（其他类型忽略）
        import_mode = serializer.validated_data.pop('import_mode', 'spec_only')
        enable_ai_translate = serializer.validated_data.pop('enable_ai_translate', True)

        upload_result = APISpecFileService.upload_api_spec_file(
            spec_file,
            project.id,
            request.user,
            spec_type
        )
        if not upload_result.get('success'):
            return response(
                kind="error",
                message=upload_result.get('error', '文件上传失败')
            )

        # 获取已创建的UploadedFile记录
        uploaded_file = UploadedFile.objects.get(id=upload_result['uploaded_file_id'])
        spec = serializer.save(created_by=request.user, project=project, uploaded_file=uploaded_file)

        # 如果没有提供spec_name，使用文件名作为默认值
        if not spec.spec_name and uploaded_file:
            spec.spec_name = uploaded_file.original_name

        # ============ Postman Collection：走异步任务 + LLM 翻译 ============
        if spec_type == 'postman':
            spec.status = APISpecification.TaskStatus.RUNNING
            spec.metadata = {
                **(spec.metadata or {}),
                'import_mode': import_mode,
                'enable_ai_translate': enable_ai_translate,
            }
            spec.save()

            task = import_postman_collection_async.delay(
                spec_id=spec.id,
                import_mode=import_mode,
                enable_ai_translate=enable_ai_translate,
                user_id=request.user.id,
            )

            logger.info(
                f"已启动 Postman 导入任务 task_id={task.id}, spec_id={spec.id}, "
                f"import_mode={import_mode}, enable_ai_translate={enable_ai_translate}"
            )

            return response(
                kind="created",
                data={
                    "id": spec.id,
                    "file_name": spec.file_name,
                    "uploaded": True,
                    "status": spec.status,
                    "task_id": str(task.id),
                    "task_info": {
                        "spec_id": spec.id,
                        "spec_type": spec_type,
                        "import_mode": import_mode,
                        "enable_ai_translate": enable_ai_translate,
                    },
                },
                message="Postman 导入任务已启动，可通过 task_id 查询进度"
            )

        # ============ 其他类型保持原有同步解析逻辑 ============
        parse_result = APIParserService().parse_api_specification_from_file(spec, uploaded_file)
        if parse_result.get('success'):
            spec.parsed_content = parse_result.get('spec_content', '')
            spec.metadata = parse_result.get('parsed_structure', {})
            spec.status = 'completed'
        else:
            spec.status = 'failed'
            spec.error_message = parse_result.get('error', '解析失败')

        spec.save()

        return response(
            kind="created",
            data={
                "id": spec.id,
                "file_name": spec.file_name,
                "uploaded": True,
                "status": spec.status
            },
            message="API规范创建成功"
        )


class APISpecificationRetrieveUpdateDestroyView(AdminBypassMixin, generics.RetrieveUpdateDestroyAPIView):
    """API规范详情、更新和删除视图"""
    serializer_class = APISpecificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'pk'
    
    def get_queryset(self):
        """获取当前项目的API规范"""
        project_id = self.kwargs.get('project_id')
        if project_id:
            return APISpecification.objects.filter(project_id=project_id)
        return APISpecification.objects.none()
    
    def retrieve(self, request, *args, **kwargs):
        """获取API规范详情 - 使用统一响应格式"""
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            
            project = instance.project
            if not self.check_project_member(project):
                return response(
                    kind="permission_denied",
                    message="没有权限访问此API规范"
                )
            
            return response(
                kind="success",
                data=serializer.data,
                message="获取API规范详情成功"
            )
        except APISpecification.DoesNotExist:
            return response(
                kind="error",
                message="API规范不存在或无权限访问"
            )
        except Exception as e:
            logger.error(f"获取API规范详情失败: {e}", exc_info=True)
            return response(
                kind="error",
                message=f"获取API规范详情失败: {str(e)}"
            )
    
    def update(self, request, *args, **kwargs):
        """更新API规范 - 使用统一响应格式"""
        try:
            partial = kwargs.pop('partial', False)
            instance = self.get_object()
            
            project = instance.project
            if not self.check_project_member(project, 'can_edit'):
                return response(
                    kind="permission_denied",
                    message="没有权限编辑此API规范"
                )
            
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            if serializer.is_valid():
                serializer.save()
                
                logger.info(f"API规范更新成功: ID={instance.id}, 用户={request.user.id}")
                return response(
                    kind="success",
                    data=serializer.data,
                    message="API规范更新成功"
                )
            else:
                return response(
                    kind="error",
                    message="数据验证失败",
                    errors=serializer.errors
                )
        except APISpecification.DoesNotExist:
            return response(
                kind="error",
                message="API规范不存在或无权限访问"
            )
        except Exception as e:
            logger.error(f"更新API规范失败: {e}", exc_info=True)
            return response(
                kind="error",
                message=f"更新API规范失败: {str(e)}"
            )
    
    def destroy(self, request, *args, **kwargs):
        """删除API规范 - 使用统一响应格式"""
        try:
            instance = self.get_object()
            instance_id = instance.id
            instance_name = instance.spec_name or (instance.uploaded_file.original_name if instance.uploaded_file else "Unknown")
            
            project = instance.project
            if not self.check_project_member(project, 'can_edit'):
                return response(
                    kind="permission_denied",
                    message="没有权限删除此API规范"
                )
            
            # 保存上传文件引用，用于后续删除
            uploaded_file = instance.uploaded_file
            
            # 删除关联的端点
            instance.endpoints.all().delete()
            
            # 删除API规范
            self.perform_destroy(instance)
            
            # 删除关联的上传文件记录和物理文件
            if uploaded_file:
                try:
                    # 删除物理文件
                    if uploaded_file.file:
                        file_path = uploaded_file.file.name
                        if default_storage.exists(file_path):
                            default_storage.delete(file_path)
                            logger.info(f"已删除物理文件: {file_path}")
                        else:
                            logger.warning(f"物理文件不存在: {file_path}")
                    
                    # 删除上传文件记录
                    uploaded_file_id = uploaded_file.id
                    uploaded_file.delete()
                    logger.info(f"已删除上传文件记录: ID={uploaded_file_id}")
                except Exception as e:
                    # 文件删除失败不应该阻止整个删除流程，只记录警告
                    logger.warning(f"删除上传文件失败: {e}", exc_info=True)
            
            logger.info(f"API规范删除成功: ID={instance_id}, 名称={instance_name}, 用户={request.user.id}")
            return response(
                kind="success",
                message="API规范删除成功"
            )
        except APISpecification.DoesNotExist:
            return response(
                kind="error",
                message="API规范不存在或无权限访问"
            )
        except Exception as e:
            logger.error(f"删除API规范失败: {e}", exc_info=True)
            return response(
                kind="error",
                message=f"删除API规范失败: {str(e)}"
            )


class APIEndpointListView(AdminBypassMixin, generics.ListAPIView):
    """API端点列表视图"""
    serializer_class = None  # 暂时不使用序列化器，直接返回数据
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        spec_id = self.kwargs.get('spec_id')
        project_id = self.kwargs.get('project_id')
        
        if not spec_id or not project_id:
            return APIEndpoint.objects.none()

        spec = APISpecification.objects.get(id=spec_id, project_id=project_id)
        if not self.check_project_member(spec.project):
            return APIEndpoint.objects.none()

        return spec.endpoints.select_related('module').all()

    def list(self, request, *args, **kwargs):
        """自定义列表响应，直接返回所有数据"""
        queryset = self.get_queryset()

        # 获取所有端点数据
        all_endpoints = queryset.all()

        # 将端点数据转换为字典格式
        endpoints_data = []
        for endpoint in all_endpoints:
            endpoints_data.append({
                'id': endpoint.id,
                'path': endpoint.path,
                'method': endpoint.method,
                'summary': endpoint.summary,
                'description': endpoint.description,
                'parameters': endpoint.parameters,
                'request_body': endpoint.request_body,
                'responses': endpoint.responses,
                'tags': endpoint.tags,
                'operation_id': endpoint.operation_id,
                'module_id': endpoint.module_id,
                'module_name': endpoint.module.name if endpoint.module else None,
                'created_at': endpoint.created_at.isoformat() if endpoint.created_at else None,
                'updated_at': endpoint.updated_at.isoformat() if endpoint.updated_at else None
            })

        # 使用统一响应格式，直接返回所有数据
        return response(
            kind="success",
            data=endpoints_data,
            message=f"获取API端点列表成功，共 {len(endpoints_data)} 个端点"
        )


class APIEndpointDetailView(AdminBypassMixin, generics.RetrieveUpdateDestroyAPIView):
    """API端点详情视图"""
    serializer_class = None  # 暂时不使用序列化器
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        spec_id = self.kwargs.get('spec_id')
        project_id = self.kwargs.get('project_id')
        
        if not spec_id or not project_id:
            return APIEndpoint.objects.none()

        spec = APISpecification.objects.get(id=spec_id, project_id=project_id)
        if not self.check_project_member(spec.project):
            return APIEndpoint.objects.none()

        return spec.endpoints.select_related('module').all()

    def retrieve(self, request, *args, **kwargs):
        """自定义详情响应"""
        instance = self.get_object()

        endpoint_data = {
            'id': instance.id,
            'path': instance.path,
            'method': instance.method,
            'summary': instance.summary,
            'description': instance.description,
            'parameters': instance.parameters,
            'request_body': instance.request_body,
            'responses': instance.responses,
            'tags': instance.tags,
            'operation_id': instance.operation_id,
            'module_id': instance.module_id,
            'module_name': instance.module.name if instance.module else None,
            'created_at': instance.created_at.isoformat() if instance.created_at else None,
            'updated_at': instance.updated_at.isoformat() if instance.updated_at else None
        }

        return response(
            kind="success",
            data=endpoint_data,
            message="获取API端点详情成功"
        )


class EndpointTestGenerationView(AdminBypassMixin, APIView):
    """端点测试用例生成视图类"""
    
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request, project_id, spec_id: int, endpoint_id: int):
        """为指定API规范中的指定端点异步生成测试用例"""
        # 1. 获取并验证API规范
        api_spec = get_object_or_404(APISpecification, id=spec_id)

        # 2. 获取并验证端点
        endpoint = get_object_or_404(APIEndpoint, id=endpoint_id, spec=api_spec)

        project = api_spec.project
        if not self.check_project_member(project, 'can_edit'):
            return response(
                kind="permission_denied",
                message="没有权限访问此API规范"
            )

        # 4. 验证请求数据
        serializer = EndpointTestGenerationSerializer(data=request.data)
        if not serializer.is_valid():
            return response(
                kind="validation_error",
                errors=serializer.errors,
                message="请求数据验证失败"
            )

        # 获取测试类型配置
        test_type_configs = serializer.validated_data.get('test_type_configs', {})

        # 5. 检查LLM配置是否可用
        if not LLMConfiguration.objects.filter(is_active=True).exists():
            return response(
                kind="error",
                message="数据库中没有可用的LLM配置，请先创建并配置LLM"
            )

        # 6. 启动Celery异步任务
        logger.info(f"启动异步任务为端点 {endpoint_id} 生成测试用例，配置: {test_type_configs}")

        task = generate_endpoint_test_cases_async.delay(
            spec_id=spec_id,
            endpoint_id=endpoint_id,
            test_type_configs=test_type_configs,
            user_id=request.user.id
        )

        # 7. 准备响应数据
        response_data = {
            'task_id': str(task.id),
            'status': 'PROCESSING',
            'task_info': {
                'spec_id': spec_id,
                'endpoint_id': endpoint_id,
                'endpoint_path': endpoint.path,
                'endpoint_method': endpoint.method,
                'test_type_configs': test_type_configs,
                'include_assertions': serializer.validated_data.get('include_assertions', True),
                'include_negative_cases': serializer.validated_data.get('include_negative_cases', True),
                'custom_prompt': serializer.validated_data.get('custom_prompt', '')
            }
        }

        logger.info(f"成功启动异步任务 {task.id} 为端点 {endpoint_id} 生成测试用例")

        return response(
            kind="success",
            data=response_data,
            message=f"AI测试用例生成任务已启动，任务ID: {task.id}"
        )


class ScenarioGenerateView(AdminBypassMixin, APIView):
    """智能场景生成API视图"""
    permission_classes = [IsAuthenticated]

    def post(self, request, project_id):
        """生成智能场景测试用例"""
        user_request = request.data.get('user_request')

        if not user_request:
            return response(
                kind="error",
                message="必须提供业务场景描述"
            )

        # 使用URL路径参数中的项目ID
        if not project_id:
            return response(
                kind="error",
                message="项目ID未提供"
            )

        project = self.get_project_for_request(project_id)

        if not self.check_project_member(project, 'can_edit'):
            return response(
                kind="permission_denied",
                message="您没有该项目的编辑权限"
            )

        # 检查项目资源
        if not APISpecification.objects.filter(project=project).exists():
            return response(
                kind="error",
                message="项目中没有API规范，请先上传API规范文件"
            )

        # 检查LLM配置
        if not LLMConfiguration.objects.filter(is_active=True).exists():
            return response(
                kind="error",
                message="数据库中没有可用的LLM配置，请先创建并配置LLM"
            )

        # 启动异步任务
        task = generate_scenario_async.delay(
            project_id=project_id,
            user_request=user_request,
            user_id=request.user.id
        )

        logger.info(f"智能场景生成任务已启动，任务ID: {task.id}")

        return response(
            kind="success",
            message='智能场景生成任务已启动',
            data={
                'task_id': task.id,
                'status': 'PROCESSING',
                'progress': 0,
                'message_detail': '正在初始化场景生成...'
            }
        )


class APITestCaseListCreateView(AdminBypassMixin, generics.ListCreateAPIView):
    """
    API测试用例列表和创建视图 (RESTful)
    GET /api/v1/projects/{project_id}/api-testing/test-cases/ - 获取测试用例列表
    POST /api/v1/projects/{project_id}/api-testing/test-cases/ - 创建测试用例
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        """根据请求方法返回不同的序列化器"""
        if self.request.method == 'POST':
            return APITestCaseCreateSerializer
        return APITestCaseSerializer
    
    def get_queryset(self):
        """获取当前用户的测试用例"""
        queryset = self.filter_by_user(APITestCase.objects.all(), created_by=self.request.user)
        
        project_id = self.kwargs.get('project_id')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        
        test_type = self.request.query_params.get('test_type')
        if test_type:
            queryset = queryset.filter(test_type=test_type)
        
        # 测试用例类型过滤
        test_case_type = self.request.query_params.get('test_case_type')
        if test_case_type:
            queryset = queryset.filter(test_case_type=test_case_type)
        
        # 优先级过滤
        priority = self.request.query_params.get('priority')
        if priority:
            queryset = queryset.filter(priority=priority)

        # 模块（端点所属模块，仅端点用例有 endpoint）
        module_id = self.request.query_params.get('module_id')
        if module_id:
            queryset = queryset.filter(endpoint__module_id=module_id)

        # 端点
        endpoint_id = self.request.query_params.get('endpoint_id')
        if endpoint_id:
            queryset = queryset.filter(endpoint_id=endpoint_id)

        # 标题模糊（沿用 query 参数名 search，兼容旧客户端）
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(title__icontains=search)

        # 综合关键字：标题或描述
        keyword = self.request.query_params.get('keyword')
        if keyword:
            queryset = queryset.filter(
                Q(title__icontains=keyword) | Q(description__icontains=keyword)
            )

        return queryset.select_related('endpoint', 'project', 'created_by').order_by('sort_order', '-created_at')
    
    def list(self, request, *args, **kwargs):
        """重写list方法以使用自定义响应格式"""
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
            message="获取API测试用例列表成功"
        )
    
    def create(self, request, *args, **kwargs):
        """重写create方法以使用自定义响应格式"""
        try:
            serializer = self.get_serializer(data=request.data)
            if serializer.is_valid():
                # 设置用户和项目
                project_id = self.kwargs.get('project_id')
                if not project_id:
                    return response(
                        kind="error",
                        message="项目ID未提供"
                    )
                
                # 获取项目对象
                from projects.models import Project
                try:
                    project = Project.objects.get(id=project_id)
                except Project.DoesNotExist:
                    return response(
                        kind="error",
                        message="项目不存在"
                    )
                
                if not self.check_project_member(project, 'can_execute_tests'):
                    return response(
                        kind="permission_denied",
                        message="没有权限在此项目中创建测试用例"
                    )
                
                # 保存测试用例
                test_case = serializer.save(created_by=request.user, project=project)
                
                logger.info(f"API测试用例创建成功: ID={test_case.id}, 标题={test_case.title}, 用户={request.user.id}")
                
                # 重新序列化，确保包含更新后的字段
                response_serializer = APITestCaseSerializer(test_case)
                return response(
                    kind="success",
                    data=response_serializer.data,
                    message="API测试用例创建成功"
                )
            else:
                return response(
                    kind="error",
                    message="数据验证失败",
                    errors=serializer.errors
                )
        except Exception as e:
            logger.error(f"创建API测试用例失败: {e}", exc_info=True)
            return response(
                kind="error",
                message=f"创建API测试用例失败: {str(e)}"
            )


class APITestCaseBatchDeleteView(AdminBypassMixin, APIView):
    """API测试用例批量删除"""
    permission_classes = [IsAuthenticated]

    def post(self, request, project_id):
        try:
            case_ids = request.data.get('case_ids', [])
            if not case_ids:
                return response(kind="error", message="case_ids 不能为空")
            queryset = self.filter_by_user(
                APITestCase.objects.filter(id__in=case_ids, project_id=project_id),
                created_by=request.user
            )
            count = queryset.count()
            queryset.delete()
            return response(kind="success", data={'deleted_count': count}, message=f"成功删除 {count} 个测试用例")
        except Exception as e:
            logger.error(f"批量删除API测试用例失败: {e}", exc_info=True)
            return response(kind="error", message=f"批量删除失败: {str(e)}")


class APITestCaseRetrieveUpdateDestroyView(AdminBypassMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    API测试用例详情、更新和删除视图 (RESTful)
    GET /api/v1/projects/{project_id}/api-testing/test-cases/{id}/ - 获取测试用例详情
    PUT /api/v1/projects/{project_id}/api-testing/test-cases/{id}/ - 更新测试用例
    PATCH /api/v1/projects/{project_id}/api-testing/test-cases/{id}/ - 部分更新测试用例
    DELETE /api/v1/projects/{project_id}/api-testing/test-cases/{id}/ - 删除测试用例
    """
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'pk'
    
    serializer_class = APITestCaseDetailSerializer
    
    def get_queryset(self):
        """获取当前用户的测试用例"""
        queryset = self.filter_by_user(APITestCase.objects.all(), created_by=self.request.user)
        
        project_id = self.kwargs.get('project_id')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        
        return queryset.select_related('endpoint', 'project', 'created_by')
    
    def retrieve(self, request, *args, **kwargs):
        """重写retrieve方法以使用自定义响应格式"""
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            
            return response(
                kind="success",
                data=serializer.data,
                message="获取API测试用例详情成功"
            )
        except APITestCase.DoesNotExist:
            return response(
                kind="error",
                message="API测试用例不存在或无权限访问"
            )
        except Exception as e:
            logger.error(f"获取API测试用例详情失败: {e}", exc_info=True)
            return response(
                kind="error",
                message=f"获取API测试用例详情失败: {str(e)}"
            )
    
    def update(self, request, *args, **kwargs):
        """重写update方法以使用自定义响应格式"""
        try:
            partial = kwargs.pop('partial', False)
            instance = self.get_object()
            # 使用精简版更新序列化器，只接受元数据 + script_content，
            # 拒绝 pre_script / post_script / request_data / variables / assertions 等冗余字段
            serializer = APITestCaseScriptUpdateSerializer(
                instance, data=request.data, partial=partial
            )
            
            if serializer.is_valid():
                test_case = serializer.save()
                
                logger.info(f"API测试用例更新成功: ID={test_case.id}, 标题={test_case.title}, 用户={request.user.id}")
                
                # 返回时仍使用详情序列化器，保证前端收到完整数据
                response_serializer = APITestCaseDetailSerializer(test_case)
                return response(
                    kind="success",
                    data=response_serializer.data,
                    message="API测试用例更新成功"
                )
            else:
                return response(
                    kind="error",
                    message="数据验证失败",
                    errors=serializer.errors
                )
        except APITestCase.DoesNotExist:
            return response(
                kind="error",
                message="API测试用例不存在或无权限访问"
            )
        except Exception as e:
            logger.error(f"更新API测试用例失败: {e}", exc_info=True)
            return response(
                kind="error",
                message=f"更新API测试用例失败: {str(e)}"
            )
    
    def destroy(self, request, *args, **kwargs):
        """重写destroy方法以使用自定义响应格式"""
        try:
            instance = self.get_object()
            instance_id = instance.id
            instance_title = instance.title
            
            self.perform_destroy(instance)
            
            logger.info(f"API测试用例删除成功: ID={instance_id}, 标题={instance_title}, 用户={request.user.id}")
            return response(
                kind="success",
                message="API测试用例删除成功"
            )
        except APITestCase.DoesNotExist:
            return response(
                kind="error",
                message="API测试用例不存在或无权限访问"
            )
        except Exception as e:
            logger.error(f"删除API测试用例失败: {e}", exc_info=True)
            return response(
                kind="error",
                message=f"删除API测试用例失败: {str(e)}"
            )

# 单个测试用例执行视图
class ExecuteAPITestCaseView(AdminBypassMixin, APIView):
    """单个API测试用例执行视图"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, project_id, pk):
        """执行单个测试用例（支持同步和异步模式）"""
        try:
            # 获取测试用例
            test_case = get_object_or_404(APITestCase, pk=pk)
            
            if not self.check_project_member(test_case.project, 'can_execute_tests'):
                return response(
                    kind="permission_denied",
                    message="没有权限执行此测试用例"
                )
            
            # 检查是否是同步执行模式（默认为异步）
            is_sync = request.data.get('sync', False)
            
            # 如果是同步模式，直接使用httprunner执行并返回结果
            if is_sync:
                return self._execute_sync(test_case, request.data)
            
            # 异步模式：使用原有的Celery任务逻辑
            # 从请求数据中获取环境ID
            environment_id = request.data.get('environment_id')
            
            if not environment_id:
                return response(
                    kind="error",
                    message="必须指定测试环境ID"
                )
            
            # 获取环境
            try:
                environment = Environment.objects.get(
                    id=environment_id,
                    project=test_case.project,
                    is_active=True
                )
            except Environment.DoesNotExist:
                return response(
                    kind="error",
                    message="指定的测试环境不存在或已被禁用"
                )
            
            # 创建测试执行记录（使用新的模型结构）
            execution = APITestExecution.objects.create(
                exec_type='case',
                name=test_case.title,
                description=test_case.description,
                status='pending',
                trigger_type='manual',
                executor=request.user,
                environment=environment,
                project_id=project_id
            )
            
            # 创建单用例执行详情（使用get_or_create避免重复创建）
            case_detail, created = APITestCaseExecutionDetail.objects.get_or_create(
                execution=execution,
                defaults={
                    'test_case': test_case,
                    'name': test_case.title,
                    'status': 'pending'
                }
            )
            
            # 如果已存在，更新基本信息（防止数据不一致）
            if not created:
                case_detail.test_case = test_case
                case_detail.name = test_case.title
                if case_detail.status == 'pending':
                    case_detail.status = 'pending'
                case_detail.save()
            
            # 启动异步任务执行测试用例
            from api_testing.tasks import execute_api_test_case_async
            task = execute_api_test_case_async.delay(execution.id, test_case.id, environment.id)
            
            # 更新执行记录的任务ID
            execution.task_id = task.id
            execution.save()
            
            logger.info(f"开始执行测试用例 {pk}, 执行记录ID: {execution.id}, 任务ID: {task.id}")
            
            return response(
                kind="success",
                data={
                    "execution_id": execution.id,
                    "task_id": task.id,
                    "execution_name": test_case.title,
                    "environment_name": environment.name
                },
                message="测试用例执行已开始"
            )
            
        except Exception as e:
            logger.error(f"执行测试用例失败: {e}", exc_info=True)
            return response(
                kind="error",
                message=f"执行测试用例失败: {str(e)}"
            )
    
    def _execute_sync(self, test_case, request_data):
        """同步执行测试用例（用于Postman风格的立即执行）"""
        from api_testing.httprunner_runner import execute_api_test_case
        from projects.models import Environment
        
        try:
            # 获取执行参数
            base_url = request_data.get('base_url', '')
            script_content = request_data.get('script_content', '')
            environment_id = request_data.get('environment_id')
            
            # 如果没有提供script_content，使用测试用例的script_content
            if not script_content:
                script_content = test_case.script_content
            
            if not script_content:
                return response(
                    kind="error",
                    message="测试用例没有脚本内容"
                )
            
            # 构建环境配置
            environment_config = {
                'base_url': base_url,
                'timeout': request_data.get('timeout', 30),
                'headers': request_data.get('headers', {}),
                'variables': request_data.get('variables', {}),
            }

            logger.info(f"同步执行测试用例 {test_case.id}, base_url: {base_url}")
            
            # 执行测试用例
            result = execute_api_test_case(
                test_case_id=test_case.id,
                script_content=script_content,
                environment=environment_config
            )
            
            logger.info(f"测试用例 {test_case.id} 执行完成，success: {result.get('success')}")

            # 自动保存脚本中更新的环境变量
            try:
                if environment_id and isinstance(result.get('pm_environment_variables'), dict):
                    env = Environment.objects.get(id=environment_id, project=test_case.project)
                    config = env.config or {}
                    variables = config.get('variables') or {}
                    if not isinstance(variables, dict):
                        variables = {}
                    variables.update(result.get('pm_environment_variables'))
                    config['variables'] = variables
                    env.config = config
                    env.save(update_fields=['config'])
                    
            except Exception as save_error:
                logger.warning(f"自动保存环境变量失败: {save_error}")
            
            # 返回执行结果
            return response(
                kind="success",
                data=result,
                message="测试执行完成"
            )
            
        except Exception as e:
            logger.error(f"同步执行测试用例失败: {e}", exc_info=True)
            return response(
                kind="error",
                message=f"执行失败: {str(e)}",
                data={
                    'success': False,
                    'error': str(e),
                    'error_type': type(e).__name__
                }
            )


class TestStatisticsView(AdminBypassMixin, APIView):
    """项目测试统计信息视图"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, project_id):
        """获取项目测试统计信息"""
        project = self.get_project_for_request(project_id)
        if not self.check_project_member(project, 'can_view_reports'):
            return response(
                kind="permission_denied",
                message="没有权限查看此项目的测试报告"
            )

        # 统计测试用例
        total_cases = APITestCase.objects.filter(project=project).count()

        # 统计测试执行记录（参考Web UI执行统计信息格式）
        total_executions = APITestExecution.objects.filter(
            environment__project=project
        ).count()
        
        pending_executions = APITestExecution.objects.filter(
            environment__project=project,
            status='pending'
        ).count()
        
        running_executions = APITestExecution.objects.filter(
            environment__project=project,
            status='running'
        ).count()
        
        passed_executions = APITestExecution.objects.filter(
            environment__project=project,
            status='passed'
        ).count()
        
        failed_executions = APITestExecution.objects.filter(
            environment__project=project,
            status='failed'
        ).count()
        
        error_executions = APITestExecution.objects.filter(
            environment__project=project,
            status='error'
        ).count()
        
        stopped_executions = APITestExecution.objects.filter(
            environment__project=project,
            status='stopped'
        ).count()

        # 计算成功率
        success_rate = (passed_executions / total_executions * 100) if total_executions > 0 else 0

        # 使用统一响应格式（参考Web UI执行统计信息格式）
        return response(
            kind="success",
            data={
                'total': total_executions,
                'pending': pending_executions,
                'running': running_executions,
                'passed': passed_executions,
                'failed': failed_executions,
                'error': error_executions,
                'stopped': stopped_executions,
                'success_rate': round(success_rate, 1)
            },
            message="API测试执行统计信息获取成功"
        )














class EndpointTestCasesView(AdminBypassMixin, APIView):
    """端点测试用例列表视图"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, project_id, spec_id, endpoint_id):
        """获取指定端点的测试用例列表"""
        # 获取API规范
        api_spec = get_object_or_404(APISpecification, id=spec_id)

        if not self.check_project_member(api_spec.project):
            return response(
                kind="permission_denied",
                message="没有权限访问此API规范"
            )

        endpoint = get_object_or_404(APIEndpoint, id=endpoint_id, spec=api_spec)

        # 获取该端点的所有测试用例（不分页）：先按 sort_order 升序，再按 created_at 降序
        test_cases = APITestCase.objects.filter(
            endpoint=endpoint
        ).order_by('sort_order', '-created_at')

        # 序列化所有数据
        test_cases_data = APITestCaseSerializer(test_cases, many=True).data

        # 使用统一响应格式，直接返回所有数据
        return response(
            kind="success",
            data=test_cases_data,
            message=f"成功获取端点 {endpoint.path} 的测试用例列表，共 {len(test_cases_data)} 个"
        )


class EndpointTestCasesOrderView(AdminBypassMixin, APIView):
    """端点测试用例批量更新排序视图"""
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, project_id, spec_id, endpoint_id):
        """
        批量更新端点下测试用例的 sort_order
        Payload: {"case_ids": [5, 2, 8, 1]} 按拖拽后的顺序
        """
        api_spec = get_object_or_404(APISpecification, id=spec_id, project_id=project_id)
        if not self.check_project_member(api_spec.project):
            return response(kind="permission_denied", message="没有权限访问此API规范")

        endpoint = get_object_or_404(APIEndpoint, id=endpoint_id, spec=api_spec)

        case_ids = request.data.get('case_ids')
        if not isinstance(case_ids, list):
            return response(kind="error", message="case_ids 必须为数组")

        if not case_ids:
            return response(kind="success", message="排序已更新")

        cases = list(self.filter_by_user(
            APITestCase.objects.filter(id__in=case_ids, endpoint=endpoint),
            created_by=request.user
        ))
        if len(cases) != len(case_ids):
            return response(kind="error", message="部分用例不存在或不属于该端点")

        # 构建 id -> index 映射，使用 bulk_update 一次性更新
        id_to_index = {cid: idx for idx, cid in enumerate(case_ids)}
        for case in cases:
            case.sort_order = id_to_index.get(case.id, case.sort_order)

        APITestCase.objects.bulk_update(cases, ['sort_order'])
        return response(kind="success", message="排序已更新")


class ScenarioTestCasesOrderView(AdminBypassMixin, APIView):
    """场景测试用例批量更新排序视图"""
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, project_id):
        """
        批量更新项目下场景测试用例的 sort_order
        Payload: {"case_ids": [45, 12, 33, ...]} 按拖拽后的顺序
        """
        project = self.get_project_for_request(project_id)
        if not self.check_project_member(project):
            return response(kind="permission_denied", message="没有权限访问此项目")

        case_ids = request.data.get('case_ids')
        if not isinstance(case_ids, list):
            return response(kind="error", message="case_ids 必须为数组")

        if not case_ids:
            return response(kind="success", message="排序已更新")

        cases = list(self.filter_by_user(
            APITestCase.objects.filter(
                id__in=case_ids,
                project_id=project_id,
                test_case_type='scenario',
                endpoint__isnull=True,
            ),
            created_by=request.user
        ))
        if len(cases) != len(case_ids):
            return response(kind="error", message="部分用例不存在或不属于该项目的场景测试用例")

        id_to_index = {cid: idx for idx, cid in enumerate(case_ids)}
        for case in cases:
            case.sort_order = id_to_index.get(case.id, case.sort_order)

        APITestCase.objects.bulk_update(cases, ['sort_order'])
        return response(kind="success", message="排序已更新")


class APIModuleListView(AdminBypassMixin, APIView):
    """模块列表视图 - 返回项目下模块及其排序，用于端点测试用例页面的模块顺序"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, project_id):
        """返回模块列表，按 sort_order 排序"""
        project = self.get_project_for_request(project_id)
        if not self.check_project_member(project):
            return response(kind="permission_denied", message="没有权限访问此项目")

        modules = list(APIModule.objects.filter(project_id=project_id).order_by('sort_order', '-created_at'))
        data = [{'id': m.id, 'name': m.name, 'sort_order': m.sort_order} for m in modules]
        return response(kind="success", data=data, message=f"共 {len(data)} 个模块")


class APIModuleOrderView(AdminBypassMixin, APIView):
    """模块批量更新排序视图 - 用于端点测试用例页面的模块拖拽排序"""
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, project_id):
        """
        批量更新模块的 sort_order
        Payload: {"module_ids": [3, 1, 2]} 或 {"module_names": ["用户相关操作", "订单", "其他"]}
        """
        project = self.get_project_for_request(project_id)
        if not self.check_project_member(project):
            return response(kind="permission_denied", message="没有权限访问此项目")

        module_ids = request.data.get('module_ids')
        module_names = request.data.get('module_names')

        if module_ids is not None:
            if not isinstance(module_ids, list):
                return response(kind="error", message="module_ids 必须为数组")
            if not module_ids:
                return response(kind="success", message="排序已更新")
            modules = list(APIModule.objects.filter(id__in=module_ids, project_id=project_id))
            if len(modules) != len(module_ids):
                return response(kind="error", message="部分模块不存在或不属于该项目")
            id_to_index = {mid: idx for idx, mid in enumerate(module_ids)}
            for mod in modules:
                mod.sort_order = id_to_index.get(mod.id, mod.sort_order)
            APIModule.objects.bulk_update(modules, ['sort_order'])
        elif module_names is not None:
            if not isinstance(module_names, list):
                return response(kind="error", message="module_names 必须为数组")
            if not module_names:
                return response(kind="success", message="排序已更新")
            to_update = []
            for idx, name in enumerate(module_names):
                if not name:
                    continue
                mod, _ = APIModule.objects.get_or_create(
                    project_id=project_id,
                    name=name,
                    defaults={'sort_order': idx}
                )
                mod.sort_order = idx
                to_update.append(mod)
            if to_update:
                APIModule.objects.bulk_update(to_update, ['sort_order'])
        else:
            return response(kind="error", message="请提供 module_ids 或 module_names")

        return response(kind="success", message="排序已更新")


class APIEndpointOrderView(AdminBypassMixin, APIView):
    """端点批量更新排序视图 - 用于同一 spec 下端点拖拽排序"""
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, project_id, spec_id):
        """
        批量更新端点的 sort_order
        Payload: {"endpoint_ids": [5, 8, 4]} 按拖拽后的顺序
        """
        api_spec = get_object_or_404(APISpecification, id=spec_id, project_id=project_id)
        if not self.check_project_member(api_spec.project):
            return response(kind="permission_denied", message="没有权限访问此API规范")

        endpoint_ids = request.data.get('endpoint_ids')
        if not isinstance(endpoint_ids, list):
            return response(kind="error", message="endpoint_ids 必须为数组")

        if not endpoint_ids:
            return response(kind="success", message="排序已更新")

        endpoints = list(APIEndpoint.objects.filter(id__in=endpoint_ids, spec=api_spec))
        if len(endpoints) != len(endpoint_ids):
            return response(kind="error", message="部分端点不存在或不属于该规范")

        id_to_index = {eid: idx for idx, eid in enumerate(endpoint_ids)}
        for ep in endpoints:
            ep.sort_order = id_to_index.get(ep.id, ep.sort_order)

        APIEndpoint.objects.bulk_update(endpoints, ['sort_order'])
        return response(kind="success", message="排序已更新")


# task-status 需透传的 Celery 结果字段（执行统计 + 场景/端点生成）
_TASK_STATUS_EXTRA_KEYS = (
    'total_cases', 'passed_cases', 'failed_cases', 'skipped_cases',
    'execution_id', 'test_suite_id', 'test_suite_name', 'environment_name',
    'execution_status', 'duration',
    'test_case_id', 'generated_script', 'success', 'full_script',
    'spec_id', 'endpoint_id', 'endpoint_path', 'endpoint_method',
    'test_cases', 'created_cases_count', 'cases_generated', 'cases_saved',
)


def _normalize_task_status(status):
    if status in ('SUCCESS', 'completed'):
        return 'completed'
    if status in ('FAILURE', 'failed'):
        return 'failed'
    return status


def _merge_task_status_payload(response_data, celery_result):
    """将 Celery 完整结果合并进 API 响应，避免按任务类型遗漏字段。"""
    for key in _TASK_STATUS_EXTRA_KEYS:
        if key in celery_result:
            response_data[key] = celery_result[key]
    nested = celery_result.get('result')
    if isinstance(nested, dict):
        response_data['result'] = nested
    else:
        response_data['result'] = celery_result
    return response_data


def _build_task_status_response(task_id, celery_result):
    status = celery_result.get('status')
    progress = celery_result.get('progress', 0)
    message = celery_result.get('message', '')
    error_msg = celery_result.get('error', '')
    normalized = _normalize_task_status(status)

    if normalized == 'completed':
        response_data = {
            'task_id': task_id,
            'status': normalized,
            'progress': 100,
            'message': message or '任务执行完成',
        }
        _merge_task_status_payload(response_data, celery_result)
        return response_data, message or '任务执行完成'

    if normalized == 'failed':
        response_data = {
            'task_id': task_id,
            'status': normalized,
            'progress': progress,
            'message': message or error_msg or '任务执行失败',
        }
        if error_msg:
            response_data['error'] = error_msg
        _merge_task_status_payload(response_data, celery_result)
        return response_data, message or error_msg or '任务执行失败'

    return {
        'task_id': task_id,
        'status': status,
        'progress': progress,
        'message': message or '任务正在运行中...',
    }, '任务状态查询成功'


class TaskStatusView(AdminBypassMixin, APIView):
    """统一任务状态查询视图 - 支持智能场景生成和端点测试用例生成"""
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id, task_id: str):
        """查询任务状态"""
        from common.task import get_celery_task_status
        result = get_celery_task_status(task_id)
        if not result:
            return response(
                kind="not_found",
                message=f"任务:{task_id}不存在"
            )

        response_data, response_message = _build_task_status_response(task_id, result)
        return response(
            kind="success",
            data=response_data,
            message=response_message
        )

# ============ API测试套件管理视图 ============

class APITestSuiteListCreateView(AdminBypassMixin, generics.ListCreateAPIView):
    """API测试套件列表创建视图"""
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return APITestSuiteCreateSerializer
        return APITestSuiteSerializer

    def get_queryset(self):
        """获取当前用户的测试套件"""
        project_id = self.kwargs.get('project_id')
        
        queryset = self.filter_by_user(
            APITestSuite.objects.filter(project_id=project_id),
            user=self.request.user
        ).select_related(
            'user', 'project'
        ).prefetch_related(
            'test_cases'
        ).order_by('-created_at')
        
        return queryset

    def get_serializer_context(self):
        """获取序列化器上下文"""
        context = super().get_serializer_context()
        # 从URL路径参数获取项目ID
        project_id = self.kwargs.get('project_id')
        
        if project_id:
            from projects.models import Project
            try:
                project = Project.objects.get(id=project_id)
                context['project'] = project
            except Project.DoesNotExist:
                pass
        
        return context
    
    def list(self, request, *args, **kwargs):
        """获取测试套件列表 - 使用统一响应格式和分页"""
        queryset = self.get_queryset()
        page = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 20))
        
        # 使用统一响应格式和分页
        return response(
            kind="paginated_queryset",
            data=queryset,
            page=page,
            page_size=page_size,
            serializer_class=self.get_serializer_class(),
            message="获取测试套件列表成功"
        )

    def create(self, request, *args, **kwargs):
        """创建测试套件 - 使用统一响应格式"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        suite_data = APITestSuiteSerializer(serializer.instance).data
        
        # 使用统一响应格式
        return response(
            kind="success",
            data=suite_data,
            message="测试套件创建成功"
        )
    
    def perform_create(self, serializer):
        """创建测试套件"""
        # 项目信息已经在 get_serializer_context 中设置
        # 序列化器的 create 方法会自动从 context 中获取项目信息
        serializer.save()


class APITestSuiteRetrieveUpdateDestroyView(AdminBypassMixin, generics.RetrieveUpdateDestroyAPIView):
    """API测试套件详情更新删除视图"""
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return APITestSuiteUpdateSerializer
        return APITestSuiteSerializer
    
    def get_queryset(self):
        """获取当前用户的测试套件"""
        project_id = self.kwargs.get('project_id')
        
        return self.filter_by_user(
            APITestSuite.objects.filter(project_id=project_id),
            user=self.request.user
        ).select_related(
            'user', 'project'
        ).prefetch_related(
            'test_cases'
        )
    
    def retrieve(self, request, *args, **kwargs):
        """获取测试套件详情 - 使用统一响应格式"""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return response(
            kind="success",
            data=serializer.data,
            message="获取测试套件详情成功"
        )
    
    def update(self, request, *args, **kwargs):
        """更新测试套件 - 使用统一响应格式"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        return response(
            kind="success",
            data=serializer.data,
            message="测试套件更新成功"
        )
    
    def destroy(self, request, *args, **kwargs):
        """删除测试套件 - 使用统一响应格式"""
        instance = self.get_object()
        self.perform_destroy(instance)
        return response(
            kind="success",
            message="测试套件删除成功"
        )


class APITestSuiteAddTestCaseView(AdminBypassMixin, APIView):
    """API测试套件添加测试用例视图"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, project_id, pk):
        """添加测试用例到套件"""
        try:
            logger.info(f"开始添加测试用例到套件 {pk}, 项目: {project_id}, 用户: {request.user.id}")
            logger.info(f"请求数据: {request.data}")
            
            test_suite = get_object_or_404(APITestSuite, pk=pk) if self.is_admin else get_object_or_404(APITestSuite, pk=pk, user=request.user)
            
            serializer = APITestSuiteAddTestCaseSerializer(data=request.data, context={'request': request})
            if not serializer.is_valid():
                return response(
                    kind="error",
                    message="数据验证失败",
                    data=serializer.errors
                )
            
            test_case_ids = serializer.validated_data['test_case_ids']
            
            # 添加测试用例到套件
            test_suite.test_cases.add(*test_case_ids)
            # 维护执行顺序（追加新用例）
            order_list = list(test_suite.test_case_order or [])
            for case_id in test_case_ids:
                if case_id not in order_list:
                    order_list.append(case_id)
            test_suite.test_case_order = order_list
            test_suite.save(update_fields=['test_case_order'])
            
            logger.info(f"成功添加 {len(test_case_ids)} 个测试用例到套件 {pk}")
            
            return response(
                kind="success",
                message=f"成功添加 {len(test_case_ids)} 个测试用例到套件"
            )
            
        except Exception as e:
            logger.error(f"添加测试用例到套件失败: {e}", exc_info=True)
            return response(
                kind="error",
                message=f"添加测试用例失败: {str(e)}"
            )


class APITestSuiteRemoveTestCaseView(AdminBypassMixin, APIView):
    """API测试套件移除测试用例视图"""
    permission_classes = [IsAuthenticated]
    
    def delete(self, request, project_id, pk, test_case_id):
        """从套件中移除测试用例"""
        try:
            test_suite = get_object_or_404(APITestSuite, pk=pk) if self.is_admin else get_object_or_404(APITestSuite, pk=pk, user=request.user)
            
            test_case = get_object_or_404(APITestCase, pk=test_case_id) if self.is_admin else get_object_or_404(APITestCase, pk=test_case_id, created_by=request.user)
            
            # 从套件中移除测试用例
            test_suite.test_cases.remove(test_case)
            # 同步移除执行顺序
            order_list = list(test_suite.test_case_order or [])
            if test_case.id in order_list:
                order_list.remove(test_case.id)
                test_suite.test_case_order = order_list
                test_suite.save(update_fields=['test_case_order'])
            
            logger.info(f"成功从套件 {pk} 中移除测试用例 {test_case_id}")
            
            return response(
                kind="success",
                message="成功从套件中移除测试用例"
            )
            
        except Exception as e:
            logger.error(f"从套件中移除测试用例失败: {e}", exc_info=True)
            return response(
                kind="error",
                message=f"移除测试用例失败: {str(e)}"
            )


class ExecuteAPITestSuiteView(AdminBypassMixin, APIView):
    """执行API测试套件视图"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, project_id, pk):
        """执行测试套件"""
        try:
            test_suite = get_object_or_404(APITestSuite, pk=pk) if self.is_admin else get_object_or_404(APITestSuite, pk=pk, user=request.user)
            
            # 检查套件是否有测试用例
            if not test_suite.test_cases.exists():
                return response(
                    kind="error",
                    message="测试套件中没有测试用例，无法执行"
                )
            
            # 获取环境
            environment_id = request.data.get('environment_id')
            if not environment_id:
                return response(
                    kind="error",
                    message="请选择执行环境"
                )
            
            environment = get_object_or_404(Environment, pk=environment_id, project_id=project_id)
            
            # 创建执行记录
            execution = APITestExecution.objects.create(
                exec_type='suite',
                name=test_suite.name,
                description=test_suite.description,
                status='pending',
                trigger_type='manual',
                executor=request.user,
                environment=environment,
                project_id=project_id
            )
            
            # 创建套件执行详情
            suite_detail = APITestSuiteExecutionDetail.objects.create(
                execution=execution,
                test_suite=test_suite,
                total_cases=test_suite.test_cases.count()
            )
            
            # 创建子用例执行记录
            order_list = test_suite.test_case_order or []
            order_map = {case_id: index for index, case_id in enumerate(order_list)}
            ordered_cases = sorted(
                list(test_suite.test_cases.all()),
                key=lambda case: (order_map.get(case.id, 10**9), case.id)
            )
            for test_case in ordered_cases:
                APITestSuiteCaseExecution.objects.create(
                    suite_execution=suite_detail,
                    test_case=test_case,
                    name=test_case.title,
                    status='pending'
                )
            
            # 启动异步任务执行测试套件
            from api_testing.tasks import execute_api_test_suite_async
            task = execute_api_test_suite_async.delay(execution.id, test_suite.id, environment.id)
            
            # 更新执行记录的任务ID
            execution.task_id = task.id
            execution.save()
            
            logger.info(f"开始执行测试套件 {pk}, 执行记录ID: {execution.id}, 任务ID: {task.id}")
            
            return response(
                kind="success",
                data={
                    "execution_id": execution.id,
                    "task_id": task.id,
                    "test_suite_name": test_suite.name,
                    "environment_name": environment.name,
                    "total_cases": test_suite.test_cases.count()
                },
                message="测试套件执行已开始"
            )
            
        except Exception as e:
            logger.error(f"执行测试套件失败: {e}", exc_info=True)
            return response(
                kind="error",
                message=f"执行测试套件失败: {str(e)}"
            )


# ============ API测试执行记录管理视图 ============

class APITestExecutionListView(AdminBypassMixin, generics.ListAPIView):
    """统一执行记录列表视图 - 获取所有执行记录（包含类型）"""
    serializer_class = APITestExecutionListSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """获取当前用户的执行记录"""
        project_id = self.kwargs.get('project_id')
        
        queryset = self.filter_by_user(
            APITestExecution.objects.filter(environment__project_id=project_id),
            executor=self.request.user
        ).select_related(
            'executor', 'environment'
        ).prefetch_related(
            'case_execution_detail__test_case',
            'suite_execution_detail__test_suite'
        ).order_by('-created_at')
        
        # 支持按执行类型过滤
        exec_type = self.request.GET.get('exec_type')
        if exec_type in ['case', 'suite']:
            queryset = queryset.filter(exec_type=exec_type)
        
        # 支持按状态过滤
        status = self.request.GET.get('status')
        if status in ['pending', 'running', 'passed', 'failed', 'error', 'stopped']:
            queryset = queryset.filter(status=status)
        
        # 支持按触发方式过滤
        trigger_type = self.request.GET.get('trigger_type')
        if trigger_type in ['manual', 'schedule', 'api', 'llm', 'jenkins', 'ci_cd']:
            queryset = queryset.filter(trigger_type=trigger_type)

        return queryset

    def list(self, request, *args, **kwargs):
        """重写list方法以支持分页和自定义响应格式"""
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
            message="获取执行记录列表成功"
        )


class APITestCaseExecutionDetailView(AdminBypassMixin, APIView):
    """单用例执行详情视图"""
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id, pk):
        """获取单用例执行详情"""
        try:
            qs = APITestCaseExecutionDetail.objects.select_related(
                'execution', 'test_case'
            ).filter(
                execution_id=pk,
                execution__exec_type='case'
            )
            case_detail = self.filter_by_user(qs, execution__executor=request.user).first()
            
            if not case_detail:
                return response(
                    kind="error",
                    message="执行记录不存在或无权限访问"
                )
            
            serializer = APITestCaseExecutionDetailSerializer(case_detail)
            return response(
                kind="success",
                data=serializer.data,
                message="获取单用例执行详情成功"
            )
        except Exception as e:
            logger.error(f"获取单用例执行详情失败: {e}", exc_info=True)
            return response(
                kind="error",
                message=f"获取单用例执行详情失败: {str(e)}"
            )


class APITestSuiteExecutionDetailView(AdminBypassMixin, APIView):
    """套件执行详情视图"""
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id, pk):
        """获取套件执行详情"""
        try:
            qs = APITestSuiteExecutionDetail.objects.select_related(
                'execution', 'test_suite'
            ).prefetch_related(
                'case_executions__test_case'
            ).filter(
                execution_id=pk,
                execution__exec_type='suite'
            )
            suite_detail = self.filter_by_user(qs, execution__executor=request.user).get()
            serializer = APITestSuiteExecutionDetailSerializer(suite_detail)
            return response(
                kind="success",
                data=serializer.data,
                message="获取套件执行详情成功"
            )
        except APITestSuiteExecutionDetail.DoesNotExist:
            return response(
                kind="error",
                message="执行记录不存在或无权限访问"
            )
        except Exception as e:
            logger.error(f"获取套件执行详情失败: {e}", exc_info=True)
            return response(
                kind="error",
                message=f"获取套件执行详情失败: {str(e)}"
            )


class APITestExecutionCasesView(AdminBypassMixin, APIView):
    """执行记录子用例视图 - 如果是套件执行，返回子用例执行详情"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, project_id, pk):
        """获取套件执行的子用例执行详情"""
        try:
            if self.is_admin:
                execution = get_object_or_404(APITestExecution, pk=pk, exec_type='suite')
            else:
                execution = get_object_or_404(APITestExecution, pk=pk, executor=request.user, exec_type='suite')
            
            # 获取套件执行详情
            suite_detail = get_object_or_404(
                APITestSuiteExecutionDetail,
                execution=execution
            )
            
            # 获取子用例执行记录
            case_executions = suite_detail.case_executions.all().order_by('test_case')
            serializer = APITestSuiteCaseExecutionSerializer(case_executions, many=True)
            
            return response(
                kind="success",
                data=serializer.data,
                message="获取子用例执行详情成功"
            )
            
        except Exception as e:
            logger.error(f"获取子用例执行详情失败: {e}", exc_info=True)
            return response(
                kind="error",
                message=f"获取子用例执行详情失败: {str(e)}"
            )


class APITestExecutionDeleteView(AdminBypassMixin, APIView):
    """执行记录删除视图 - 支持删除单用例和套件执行记录"""
    permission_classes = [IsAuthenticated]

    def delete(self, request, project_id, pk):
        """删除执行记录"""
        try:
            qs = APITestExecution.objects.select_related(
                'case_execution_detail', 'suite_execution_detail'
            ).filter(pk=pk)
            execution = self.filter_by_user(qs, executor=request.user).get()

            # 记录执行信息用于日志
            exec_type = execution.exec_type
            exec_name = execution.name

            # 删除相关的执行详情记录
            if exec_type == 'case' and hasattr(execution, 'case_execution_detail'):
                execution.case_execution_detail.delete()
            elif exec_type == 'suite' and hasattr(execution, 'suite_execution_detail'):
                # 删除套件执行详情及其子用例执行记录
                suite_detail = execution.suite_execution_detail
                suite_detail.case_executions.all().delete()
                suite_detail.delete()

            # 删除主执行记录
            execution.delete()

            logger.info(f"用户 {request.user.username} 删除了{exec_type}执行记录: {exec_name} (ID: {pk})")

            return response(
                kind="success",
                message=f"删除{exec_type}执行记录成功"
            )

        except APITestExecution.DoesNotExist:
            return response(
                kind="error",
                message="执行记录不存在或无权限访问"
            )
        except Exception as e:
            logger.error(f"删除执行记录失败: {e}", exc_info=True)
            return response(
                kind="error",
                message=f"删除执行记录失败: {str(e)}"
            )


class DebugScenarioStepsView(AdminBypassMixin, APIView):
    """场景调试视图 - 截取前 N 步同步执行，返回逐步响应数据"""
    permission_classes = [IsAuthenticated]

    def post(self, request, project_id):
        from api_testing.httprunner_runner import httprunner_runner, _process_script_content

        config = request.data.get('config', {})
        teststeps = request.data.get('teststeps', [])
        base_url = request.data.get('base_url') or config.get('base_url', '')

        if not teststeps:
            return response(kind="error", message="步骤列表不能为空")

        # 构建临时 HttpRunner JSON
        hrun_json = {
            'config': dict(config),
            'teststeps': teststeps
        }
        if base_url:
            hrun_json['config']['base_url'] = base_url

        script_content = json.dumps(hrun_json, ensure_ascii=False, indent=2)

        try:
            # 从 config 中提取 headers 和 variables，通过 options 传入
            # （HttpRunner TConfig 不支持 headers 字段，_process_script_content 需要从 options 读取）
            env_headers = config.get('headers') or {}
            env_variables = config.get('variables') or {}
            result = httprunner_runner(
                script_id=f"debug_{project_id}",
                script_content=script_content,
                base_url=base_url or None,
                options={
                    'timeout': 30,
                    'headers': env_headers,
                    'variables': env_variables,
                }
            )
        except Exception as e:
            logger.error(f"调试执行失败: {e}", exc_info=True)
            return response(kind="error", message=f"调试执行异常: {str(e)}")

        # 从 summary 中提取逐步响应
        step_responses = []
        raw = result.get('result', result) or {}
        step_datas = raw.get('step_datas', [])
        for sd in step_datas:
            # sd 可能是 dict（model_dump 的结果）或 Pydantic 模型
            if hasattr(sd, 'model_dump'):
                sd = sd.model_dump()
            data = sd.get('data') or {}
            # data 为 List[StepData]（testcase 引用步骤）时取最后一个子步骤
            if isinstance(data, list):
                data = data[-1] if data else {}
            req_resps = data.get('req_resps', [])
            last_rr = req_resps[-1] if req_resps else {}
            last_rr = last_rr if isinstance(last_rr, dict) else {}

            # ---------- 提取 response ----------
            resp = last_rr.get('response', {})
            if hasattr(resp, 'model_dump'):
                resp = resp.model_dump()
            resp = resp or {}
            # body 可能是 bytes，转为字符串
            resp_body = resp.get('body')
            if isinstance(resp_body, bytes):
                try:
                    resp_body = json.loads(resp_body.decode('utf-8'))
                except Exception:
                    resp_body = resp_body.decode('utf-8', errors='replace')

            # ---------- 提取 request（变量替换后的真实请求）----------
            req = last_rr.get('request', {})
            if hasattr(req, 'model_dump'):
                req = req.model_dump()
            req = req or {}
            # request.body 同样可能是 bytes
            req_body = req.get('body')
            if isinstance(req_body, bytes):
                try:
                    req_body = json.loads(req_body.decode('utf-8'))
                except Exception:
                    req_body = req_body.decode('utf-8', errors='replace')

            # elapsed 从 SessionData.stat 中读取（StepData 本身无 elapsed 字段）
            stat = data.get('stat') or {}
            elapsed_ms = stat.get('elapsed_ms') or stat.get('response_time_ms') or 0
            step_responses.append({
                'name': sd.get('name', ''),
                'success': sd.get('success', False),
                # --- response ---
                'status_code': resp.get('status_code'),
                'headers': dict(resp.get('headers') or {}),
                'body': resp_body,
                'elapsed': elapsed_ms,
                # --- request（变量替换后的实际发出请求）---
                'request': {
                    'method': str(req.get('method') or ''),
                    'url': str(req.get('url') or ''),
                    'headers': dict(req.get('headers') or {}),
                    'body': req_body,
                },
            })

        return response(
            kind="success",
            data={
                'success': result.get('success', False),
                'step_responses': step_responses,
                'log': result.get('log') or raw.get('log', ''),
                'error': result.get('error'),
            },
            message="调试执行完成"
        )

