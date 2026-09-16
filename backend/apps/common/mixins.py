"""
AdminBypassMixin — 超管数据穿透的统一基础设施。

类视图用法：让 ViewSet / APIView 继承 AdminBypassMixin，然后调用工具方法：
  - self.is_admin                         → 判断是否为管理员
  - self.get_project_for_request(pid)     → 获取项目对象（admin 跳过成员校验）
  - self.filter_by_user(qs, field=user)   → 按用户过滤（admin 跳过）
  - self.check_project_member(proj, perm) → 校验项目成员权限（admin 直接通过）

函数视图用法：
  - is_admin_user(request.user)           → 独立函数，判断是否为管理员
"""
import json, time, os
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied

# #region agent log
_DEBUG_LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), 'debug-ace39e.log')
def _dlog(msg, data=None, hypothesis='A'):
    try:
        entry = {'sessionId':'ace39e','timestamp':int(time.time()*1000),'location':'common/mixins.py','message':msg,'hypothesisId':hypothesis}
        if data: entry['data'] = data
        with open(_DEBUG_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + '\n')
    except: pass
# #endregion


def is_admin_user(user):
    """独立函数：判断用户是否为管理员。供 @api_view 等函数视图使用。"""
    result = user.is_authenticated and (user.is_superuser or user.is_staff)
    # #region agent log
    _dlog('is_admin_user called', {'username': getattr(user, 'username', '?'), 'is_superuser': getattr(user, 'is_superuser', False), 'is_staff': getattr(user, 'is_staff', False), 'result': result}, 'A')
    # #endregion
    return result


class AdminBypassMixin:
    """DRF View/ViewSet mixin：管理员（is_staff / is_superuser）跳过数据隔离。"""

    @property
    def is_admin(self):
        u = self.request.user
        result = u.is_authenticated and (u.is_superuser or u.is_staff)
        # #region agent log
        _dlog('is_admin property', {'username': getattr(u, 'username', '?'), 'is_superuser': getattr(u, 'is_superuser', False), 'is_staff': getattr(u, 'is_staff', False), 'result': result, 'view': self.__class__.__name__}, 'A')
        # #endregion
        return result

    # ---------- 项目级访问 ----------

    def get_project_for_request(self, project_id):
        """
        根据 project_id 返回 Project 实例。
        - admin：只校验项目存在
        - 普通用户：额外校验成员 / 创建者 / 负责人
        """
        from projects.models import Project
        project = get_object_or_404(Project, id=project_id)
        if self.is_admin:
            return project
        user = self.request.user
        is_member = (
            project.members.filter(user=user).exists()
            or project.created_by == user
            or project.owner == user
        )
        if not is_member:
            raise PermissionDenied('您不是该项目的成员，无权访问')
        return project

    def check_project_member(self, project, permission_field=None):
        """
        校验当前用户是否为项目成员（可选校验某个权限字段如 'can_edit'）。
        - admin：始终返回 True
        - 普通用户：检查 ProjectMember + 可选权限字段
        """
        if self.is_admin:
            return True
        user = self.request.user
        if project.created_by == user or project.owner == user:
            return True
        member = project.members.filter(user=user).first()
        if not member:
            return False
        if permission_field:
            return getattr(member, permission_field, False)
        return True

    # ---------- 用户级数据过滤 ----------

    def filter_by_user(self, queryset, **lookup):
        """
        按用户字段过滤 queryset。admin 跳过，普通用户应用过滤。
        示例: self.filter_by_user(qs, created_by=self.request.user)
              self.filter_by_user(qs, executor=self.request.user)
        """
        admin = self.is_admin
        # #region agent log
        _dlog('filter_by_user', {'admin': admin, 'model': queryset.model.__name__, 'lookup_keys': list(lookup.keys()), 'view': self.__class__.__name__}, 'B')
        # #endregion
        if admin:
            return queryset
        return queryset.filter(**lookup)
