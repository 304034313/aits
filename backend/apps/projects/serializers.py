from rest_framework import serializers
from .models import Project, ProjectMember, Environment, ProjectThirdPartyConfig, WorkspaceMenuConfig
from .knowledge.models import KnowledgeBaseFile, UploadedFile


def validate_linked_api_projects_qs(projects):
    """linked_api_projects 仅允许指向 project_type=api 的项目。"""
    for p in projects:
        if p.project_type != 'api':
            raise serializers.ValidationError(
                f'仅允许关联接口自动化项目（project_type=api），项目「{p.name}」类型为 {p.project_type}'
            )
    return projects


class UploadedFileSerializer(serializers.ModelSerializer):
    """上传文件序列化器"""

    # 关联字段序列化（避免N+1查询时用select_related优化）
    uploaded_by_username = serializers.CharField(
        source='uploaded_by.username', read_only=True
    )
    project_name = serializers.CharField(
        source='project.name', read_only=True
    )

    # 衍生/计算字段
    file_url = serializers.SerializerMethodField()
    file_exists = serializers.SerializerMethodField()

    class Meta:
        model = UploadedFile
        fields = [
            'id', 'original_name', 'file', 'file_url', 'file_size',
            'file_type', 'file_hash', 'upload_status',
            'file_exists', 'uploaded_by_username', 'project_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'file', 'file_hash', 'upload_status', 'file_url', 'file_exists',
            'uploaded_by_username', 'project_name',
            'created_at', 'updated_at'
        ]

    def get_file_url(self, obj):
        """返回文件的绝对访问URL"""
        request = self.context.get('request')
        if obj.file and hasattr(obj.file, 'url'):
            return request.build_absolute_uri(obj.file.url) if request else obj.file.url
        return None

    def get_file_exists(self, obj):
        """检查文件是否存在于存储中"""
        return bool(obj.file and obj.file.storage.exists(obj.file.name))



class UploadedFileCreateSerializer(serializers.ModelSerializer):
    """上传文件创建序列化器"""

    class Meta:
        model = UploadedFile
        fields = [
            'original_name', 'file_size', 'file_type'
        ]
        read_only_fields = ['id', 'file', 'file_hash', 'upload_status', 'created_at', 'updated_at']

# 环境序列化器
class EnvironmentSerializer(serializers.ModelSerializer):
    """环境序列化器"""
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    is_api_environment = serializers.BooleanField(read_only=True)
    is_web_environment = serializers.BooleanField(read_only=True)
    is_app_environment = serializers.BooleanField(read_only=True)
    
    # 根据环境类型提供配置示例
    config_example = serializers.SerializerMethodField()
    
    class Meta:
        model = Environment
        fields = [
            'id', 'name', 'description', 'category', 'category_display',
            'config', 'is_active', 'is_api_environment', 'is_web_environment', 'is_app_environment',
            'config_example', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_config_example(self, obj):
        """获取配置示例"""
        return obj.get_config_example()


# 环境创建序列化器
class EnvironmentCreateSerializer(serializers.ModelSerializer):
    """环境创建序列化器"""
    class Meta:
        model = Environment
        fields = [
            'name', 'description', 'category', 'config', 'is_active'
        ]
    
    def validate(self, attrs):
        """验证环境配置"""
        category = attrs.get('category')
        config = attrs.get('config', {})
        
        # 创建临时对象进行验证
        temp_env = Environment(category=category, config=config)
        errors = temp_env.validate_config()
        
        if errors:
            raise serializers.ValidationError({
                'config': errors
            })
        
        return attrs


class ProjectMemberSerializer(serializers.ModelSerializer):
    """项目成员序列化器"""
    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    
    class Meta:
        model = ProjectMember
        fields = ['id', 'username', 'email', 'first_name', 'last_name',
                 'role', 'can_edit', 'can_delete', 'can_execute_tests', 
                 'can_view_reports', 'joined_at', 'updated_at']

class KnowledgeBaseFileSerializer(serializers.ModelSerializer):
    """知识库文件序列化器"""

    uploaded_by_username = serializers.CharField(source='uploaded_by.username', read_only=True)
    file_path = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeBaseFile
        fields = [
            'id',
            'file_name',        # 来自 property
            'file_size',        # 来自 property
            'file_size_mb',     # 来自 property
            'file_type',        # 来自 property
            'file_path',        # 单独方法获取路径
            'status',
            'parsed_content',
            'error_message',
            'metadata',
            'uploaded_by_username',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id', 'file_name', 'file_size', 'file_size_mb', 'file_type',
            'file_path', 'parsed_content', 'error_message',
            'created_at', 'updated_at'
        ]

    def get_file_path(self, obj):
        """从关联的UploadedFile获取文件路径"""
        if obj.uploaded_file and obj.uploaded_file.file:
            return obj.uploaded_file.file.url
        return None



class ProjectSerializer(serializers.ModelSerializer):
    """项目序列化器"""
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    owner_username = serializers.CharField(source='owner.username', read_only=True)
    project_type_display = serializers.CharField(source='get_project_type_display', read_only=True)
    linked_api_project_details = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            'id', 'name', 'description', 'project_type', 'project_type_display',
            'sonic_project_id',
            'created_by_username', 'owner_username',
            'linked_api_projects', 'linked_api_project_details',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'linked_api_project_details']

    def get_linked_api_project_details(self, obj):
        return [{'id': p.id, 'name': p.name} for p in obj.linked_api_projects.all()]

    def validate_linked_api_projects(self, projects):
        return validate_linked_api_projects_qs(projects)


class ProjectDetailSerializer(serializers.ModelSerializer):
    """项目详情序列化器"""
    environments = EnvironmentSerializer(many=True, read_only=True)
    members = ProjectMemberSerializer(many=True, read_only=True)
    knowledge_files = KnowledgeBaseFileSerializer(many=True, read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    owner_username = serializers.CharField(source='owner.username', read_only=True)
    project_type_display = serializers.CharField(source='get_project_type_display', read_only=True)
    linked_api_project_details = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            'id', 'name', 'description', 'project_type', 'project_type_display',
            'sonic_project_id',
            'environments', 'members', 'knowledge_files',
            'created_by_username', 'owner_username',
            'linked_api_projects', 'linked_api_project_details',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'linked_api_project_details']

    def get_linked_api_project_details(self, obj):
        return [{'id': p.id, 'name': p.name} for p in obj.linked_api_projects.all()]

    def validate(self, attrs):
        inst = getattr(self, 'instance', None)
        pt = attrs.get('project_type', inst.project_type if inst else 'api')
        if 'linked_api_projects' in attrs and pt != 'perf':
            attrs['linked_api_projects'] = []
        return attrs

    def validate_linked_api_projects(self, projects):
        return validate_linked_api_projects_qs(projects)

    def update(self, instance, validated_data):
        ret = super().update(instance, validated_data)
        if ret.project_type != 'perf':
            ret.linked_api_projects.clear()
        return ret


class ProjectCreateSerializer(serializers.ModelSerializer):
    """项目创建序列化器"""
    project_type = serializers.ChoiceField(
        choices=Project.PROJECT_TYPE_CHOICES,
        default='api',
        required=False
    )
    linked_api_projects = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Project.objects.filter(project_type='api'),
        required=False,
        allow_empty=True,
    )

    class Meta:
        model = Project
        fields = ['name', 'description', 'project_type', 'linked_api_projects']

    def validate(self, attrs):
        pt = attrs.get('project_type', 'api')
        linked = attrs.get('linked_api_projects')
        if linked is None:
            linked = []
        if linked and pt != 'perf':
            raise serializers.ValidationError({'linked_api_projects': '仅性能测试项目可关联接口自动化项目'})
        return attrs

    def create(self, validated_data):
        linked = validated_data.pop('linked_api_projects', [])
        project = super().create(validated_data)

        # 创建者自动成为项目所有者
        ProjectMember.objects.create(
            project=project,
            user=self.context['request'].user,
            role='owner',
            can_edit=True,
            can_delete=True,
            can_execute_tests=True,
            can_view_reports=True
        )

        if project.project_type == 'perf' and linked:
            project.linked_api_projects.set(linked)

        return project


class ProjectThirdPartyConfigSerializer(serializers.ModelSerializer):
    project_id = serializers.IntegerField(source='project.id', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)

    class Meta:
        model = ProjectThirdPartyConfig
        fields = [
            'id',
            'project',
            'project_id',
            'project_name',
            'grafana_dashboard_url',
            'ai_diagnosis_url',
            'grafana_admin_url',
            'prometheus_url',
            'skywalking_url',
            'updated_at',
        ]
        read_only_fields = ['id', 'project_id', 'project_name', 'updated_at']


class ProjectMemberCreateSerializer(serializers.ModelSerializer):
    """项目成员创建序列化器"""
    class Meta:
        model = ProjectMember
        fields = ['user', 'role', 'can_edit', 'can_delete', 
                 'can_execute_tests', 'can_view_reports']
    
    def validate(self, attrs):
        project = self.context.get('project')
        user = attrs.get('user')
        
        # 检查用户是否已经是项目成员
        if ProjectMember.objects.filter(project=project, user=user).exists():
            raise serializers.ValidationError('该用户已经是项目成员')
        
        return attrs




class KnowledgeBaseFileCreateSerializer(serializers.ModelSerializer):
    """知识库文件创建序列化器"""
    class Meta:
        model = KnowledgeBaseFile
        fields = ['project', 'uploaded_file']
    
    def create(self, validated_data):
        validated_data['uploaded_by'] = self.context['request'].user
        return super().create(validated_data)


class WorkspaceMenuConfigSerializer(serializers.ModelSerializer):
    updated_by_username = serializers.CharField(source='updated_by.username', read_only=True, default=None)

    class Meta:
        model = WorkspaceMenuConfig
        fields = ['module', 'menu_items', 'updated_by_username', 'updated_at']
        read_only_fields = ['updated_by_username', 'updated_at']
