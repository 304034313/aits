"""
Postman Collection v2.1 解析服务

将上传的 Postman Collection JSON 文件解析为 AITS 内部统一的数据结构：
- APISpecification: 元信息（名称、描述、base_url、变量、auth 等写入 metadata）
- APIEndpoint:      每个 request 一条（含 method/path/headers/body/query 等）
- APIModule:        按 Postman 文件夹层级派生

该服务只做"纯规则"解析，不依赖 LLM。
pm.test()/prerequest 的 JavaScript 脚本会作为 raw 字段暂存到端点信息中，
由后续的 `PostmanScriptTranslator`（AI 节点）翻译为 HttpRunner 原生 validate / extract。
"""
import json
import logging
import os
import re
from typing import Dict, List, Any, Optional, Tuple
from urllib.parse import urlparse

from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)


# Postman 路径变量 (:id 风格) -> HttpRunner / OpenAPI 大括号变量
_POSTMAN_PATH_VAR_RE = re.compile(r':([A-Za-z_][A-Za-z0-9_]*)')
# Postman 变量 {{var}} -> HttpRunner 变量 $var
_POSTMAN_VAR_RE = re.compile(r'\{\{\s*([A-Za-z_][A-Za-z0-9_\-]*)\s*\}\}')


def convert_postman_vars(text: str) -> str:
    """将 Postman 风格的 `{{var}}` 替换为 HttpRunner 风格的 `$var`。"""
    if not isinstance(text, str) or not text:
        return text
    return _POSTMAN_VAR_RE.sub(r'$\1', text)


def convert_path_vars(path: str) -> str:
    """将 Postman 的 `:id` 风格转换为 OpenAPI / AITS 统一的 `{id}` 风格。"""
    if not isinstance(path, str) or not path:
        return path
    return _POSTMAN_PATH_VAR_RE.sub(r'{\1}', path)


class PostmanParserService:
    """Postman Collection v2.1 解析服务"""

    SUPPORTED_SCHEMAS = (
        'https://schema.getpostman.com/json/collection/v2.1.0/collection.json',
        'https://schema.getpostman.com/json/collection/v2.0.0/collection.json',
    )

    def __init__(self):
        self.collection: Dict[str, Any] = {}

    # ============ 公共入口 ============

    def load_file(self, uploaded_file) -> Dict[str, Any]:
        """读取 UploadedFile 的内容，返回 collection JSON。

        Args:
            uploaded_file: projects.UploadedFile 实例

        Returns:
            解析得到的 JSON 字典
        """
        if not uploaded_file or not uploaded_file.file_exists:
            raise ValueError('上传的文件不存在或无法访问')

        file_path = uploaded_file.file.name if uploaded_file.file else None
        if not file_path:
            raise ValueError('文件路径不存在')

        file_extension = os.path.splitext(uploaded_file.original_name)[1].lower()
        if file_extension != '.json':
            raise ValueError(f'Postman Collection 必须是 .json 文件，当前: {file_extension}')

        try:
            with default_storage.open(file_path, 'rb') as f:
                raw = f.read()
            for encoding in ('utf-8', 'utf-8-sig', 'gbk', 'latin-1'):
                try:
                    text = raw.decode(encoding)
                    return json.loads(text)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
            raise ValueError('无法用常见编码解析 Postman JSON 文件')
        except Exception as e:
            raise ValueError(f'读取 Postman 文件失败: {str(e)}')

    def validate_collection(self, collection: Dict[str, Any]) -> None:
        """校验是否为受支持的 Postman Collection。

        Raises:
            ValueError: 校验失败时抛出。
        """
        if not isinstance(collection, dict):
            raise ValueError('Postman Collection 顶层必须是 JSON 对象')

        info = collection.get('info') or {}
        if not isinstance(info, dict):
            raise ValueError('Postman Collection 缺少有效的 info 字段')

        schema = info.get('schema', '')
        has_supported_schema = any(s in schema for s in ('v2.1.0', 'v2.0.0'))
        has_postman_id = bool(info.get('_postman_id') or info.get('postman_id'))

        if not (has_supported_schema or has_postman_id):
            raise ValueError(
                '该文件不是受支持的 Postman Collection（仅支持 v2.0 / v2.1 格式）'
            )

        if 'item' not in collection or not isinstance(collection['item'], list):
            raise ValueError('Postman Collection 缺少 item 列表')

    # ============ 主流程 ============

    def parse(self, collection: Dict[str, Any]) -> Dict[str, Any]:
        """解析 Postman Collection 为 AITS 内部统一结构。

        Returns:
            {
                'metadata': { 'name', 'description', 'schema',
                              'base_url', 'variables', 'auth' },
                'endpoints': [ { ... endpoint dict ... } ],
                'requests_raw': N,   # 总请求条数（含重复 path+method）
            }
        """
        self.validate_collection(collection)
        self.collection = collection

        info = collection.get('info') or {}
        variables = self._extract_collection_variables(collection.get('variable') or [])
        base_url = self._guess_base_url(collection)

        metadata = {
            'source': 'postman',
            'name': info.get('name', ''),
            'description': info.get('description', '') if isinstance(info.get('description', ''), str) else '',
            'schema': info.get('schema', ''),
            'postman_id': info.get('_postman_id') or info.get('postman_id', ''),
            'base_url': base_url,
            'variables': variables,
            'auth': self._extract_auth(collection.get('auth')),
        }

        endpoints: List[Dict[str, Any]] = []
        # collection 顶层也可以有 event（v2.1 schema 支持），同样作为继承起点
        root_events = self._extract_events(collection.get('event') or [])
        inherited = {
            'prerequest': [root_events['prerequest']] if root_events['prerequest'] else [],
            'test': [root_events['test']] if root_events['test'] else [],
        }
        self._walk_items(
            collection.get('item') or [],
            folder_path=[],
            endpoints=endpoints,
            inherited_events=inherited,
        )

        return {
            'metadata': metadata,
            'endpoints': endpoints,
            'requests_raw': len(endpoints),
        }

    # ============ 内部工具 ============

    def _walk_items(self, items: List[Dict[str, Any]], folder_path: List[str],
                    endpoints: List[Dict[str, Any]],
                    inherited_events: Optional[Dict[str, List[str]]] = None) -> None:
        """递归遍历 collection.item 树，并把 folder-level events 累加到子请求。

        Postman v2.1 schema 支持 folder 级别的 event：
        - prerequest 会在子请求执行前运行（外层 → 内层 → 叶子）
        - test 会在子请求执行后运行（叶子 → 内层 → 外层）
        AITS 为了"复刻"原始行为，把这些脚本按层级累加拼接，最终交给 AI 翻译器处理。
        """
        inherited_events = inherited_events or {'prerequest': [], 'test': []}

        for item in items:
            if not isinstance(item, dict):
                continue

            if 'request' in item:
                try:
                    leaf_events = self._extract_events(item.get('event') or [])
                    # 叶子 prerequest：累加（外层 + 自身），test：累加（自身 + 外层）
                    merged_events = {
                        'prerequest': '\n\n'.join(
                            s for s in (inherited_events['prerequest'] + [leaf_events['prerequest']]) if s
                        ),
                        'test': '\n\n'.join(
                            s for s in ([leaf_events['test']] + inherited_events['test']) if s
                        ),
                    }
                    endpoint = self._convert_request_to_endpoint(item, folder_path, merged_events)
                    if endpoint:
                        endpoints.append(endpoint)
                except Exception as e:
                    logger.warning(
                        f"Postman item 转换失败，已跳过: name={item.get('name')}, err={e}"
                    )
                continue

            sub_items = item.get('item')
            if isinstance(sub_items, list):
                # folder：把自身 event 加到继承链中传递给子项
                folder_events = self._extract_events(item.get('event') or [])
                child_inherited = {
                    'prerequest': inherited_events['prerequest']
                                  + ([folder_events['prerequest']] if folder_events['prerequest'] else []),
                    'test': inherited_events['test']
                            + ([folder_events['test']] if folder_events['test'] else []),
                }
                child_folder = folder_path + [item.get('name', '未命名文件夹')]
                self._walk_items(sub_items, child_folder, endpoints, child_inherited)

    def _convert_request_to_endpoint(self, item: Dict[str, Any],
                                     folder_path: List[str],
                                     merged_events: Optional[Dict[str, str]] = None
                                     ) -> Optional[Dict[str, Any]]:
        """把一个 Postman item (含 request) 转换为 endpoint 字典。

        Args:
            merged_events: 由 _walk_items 计算的、已合并父 folder 的 events；
                           为 None 时仅使用本节点 events（向后兼容）。
        """
        request = item.get('request') or {}
        if not request:
            return None

        method = (request.get('method') or 'GET').upper()
        url_info = self._parse_url(request.get('url'))
        if not url_info['path']:
            logger.warning(f"Postman request 缺少 path，跳过: name={item.get('name')}")
            return None

        headers = self._parse_headers(request.get('header') or [])
        body = self._parse_body(request.get('body') or {})
        path_params, query_params = self._build_parameters(url_info, headers)

        # 事件（pm.test、pm.prerequest）原始 JS 脚本（供 AI 节点处理）
        if merged_events is not None:
            events = merged_events
        else:
            events = self._extract_events(item.get('event') or [])

        # 模块名优先使用文件夹的第一级名称
        tag_name = folder_path[0] if folder_path else '未分类'

        endpoint = {
            'path': url_info['path'],
            'method': method,
            'summary': item.get('name', '') or f"{method} {url_info['path']}",
            'description': self._normalize_description(request.get('description', '')),
            'operation_id': self._make_operation_id(item.get('name', ''), method, url_info['path']),
            'tags': folder_path or [tag_name],
            'parameters': path_params + query_params + self._headers_as_parameters(headers),
            'request_body': body,
            'responses': {},
            # 透传字段：原始头/查询/url 信息，供任务阶段构造 HttpRunner step
            '_postman_raw': {
                'name': item.get('name', ''),
                'folder_path': folder_path,
                'method': method,
                'url_raw': url_info['raw'],
                'host': url_info['host'],
                'path': url_info['path'],
                'headers': headers,
                'query': url_info['query'],
                'body': body,
                'auth': self._extract_auth(request.get('auth')),
                'events': events,
            },
        }
        return endpoint

    def _parse_url(self, url: Any) -> Dict[str, Any]:
        """解析 request.url（字符串或对象两种格式）。"""
        result = {
            'raw': '',
            'host': '',
            'path': '',
            'query': [],  # [{ 'key', 'value', 'description' }]
        }

        if isinstance(url, str):
            result['raw'] = url
            parsed = urlparse(convert_postman_vars(url))
            result['host'] = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else ''
            result['path'] = convert_path_vars(parsed.path or '/')
            if parsed.query:
                result['query'] = [
                    {'key': p.split('=', 1)[0], 'value': p.split('=', 1)[1] if '=' in p else ''}
                    for p in parsed.query.split('&') if p
                ]
            return result

        if isinstance(url, dict):
            raw = url.get('raw') or ''
            result['raw'] = raw

            # path
            path_parts = url.get('path') or []
            if isinstance(path_parts, list):
                path = '/' + '/'.join(str(p) for p in path_parts if p)
            else:
                path = str(path_parts)
            result['path'] = convert_path_vars(convert_postman_vars(path or '/'))

            # host
            host = url.get('host') or []
            protocol = url.get('protocol') or ''
            port = url.get('port') or ''
            if isinstance(host, list):
                host_str = '.'.join(str(h) for h in host if h)
            else:
                host_str = str(host)
            if host_str:
                base = f"{protocol}://{host_str}" if protocol else host_str
                if port:
                    base = f"{base}:{port}"
                result['host'] = convert_postman_vars(base)

            # query
            query = url.get('query') or []
            normalized_query = []
            if isinstance(query, list):
                for q in query:
                    if not isinstance(q, dict):
                        continue
                    if q.get('disabled'):
                        continue
                    normalized_query.append({
                        'key': q.get('key', ''),
                        'value': convert_postman_vars(q.get('value', '')) if isinstance(q.get('value', ''), str) else q.get('value', ''),
                        'description': q.get('description', '') if isinstance(q.get('description', ''), str) else '',
                    })
            result['query'] = normalized_query
            return result

        return result

    def _parse_headers(self, headers: List[Any]) -> List[Dict[str, Any]]:
        """规范化 header 列表。"""
        normalized = []
        for h in headers or []:
            if not isinstance(h, dict) or h.get('disabled'):
                continue
            key = h.get('key', '')
            value = h.get('value', '')
            if isinstance(value, str):
                value = convert_postman_vars(value)
            normalized.append({
                'key': key,
                'value': value,
                'description': h.get('description', '') if isinstance(h.get('description', ''), str) else '',
            })
        return normalized

    def _parse_body(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """规范化 request.body 为 AITS 端点结构 (request_body)。

        返回结构与 OpenAPI 解析器对齐：
            {
                'required': bool,
                'description': str,
                'content': {
                    'application/json': { 'schema': {...}, 'example': ... },
                    'multipart/form-data': {...},
                    ...
                }
            }
        """
        if not isinstance(body, dict) or not body:
            return {}

        mode = body.get('mode') or ''
        body_data: Dict[str, Any] = {
            'required': False,
            'description': '',
            'content': {},
        }

        if mode == 'raw':
            raw = body.get('raw', '')
            options = body.get('options') or {}
            raw_options = options.get('raw') or {}
            language = (raw_options.get('language') or '').lower()
            content_type = 'application/json' if language in ('json', '') else f'application/{language}'

            normalized_raw = convert_postman_vars(raw)
            example: Any = normalized_raw
            if content_type == 'application/json':
                try:
                    example = json.loads(normalized_raw) if normalized_raw.strip() else {}
                except (json.JSONDecodeError, ValueError):
                    # JSON 解析失败，保留原文
                    content_type = 'text/plain'
                    example = normalized_raw

            body_data['content'][content_type] = {
                'schema': {'type': 'object' if isinstance(example, dict) else 'string'},
                'example': example,
            }

        elif mode in ('urlencoded', 'formdata'):
            content_type = 'application/x-www-form-urlencoded' if mode == 'urlencoded' else 'multipart/form-data'
            fields = body.get(mode) or []
            example: Dict[str, Any] = {}
            schema_props: Dict[str, Any] = {}
            for field in fields:
                if not isinstance(field, dict) or field.get('disabled'):
                    continue
                key = field.get('key', '')
                if not key:
                    continue
                if field.get('type') == 'file':
                    example[key] = f'<file: {field.get("src", "")}>'
                    schema_props[key] = {'type': 'string', 'format': 'binary'}
                else:
                    value = field.get('value', '')
                    if isinstance(value, str):
                        value = convert_postman_vars(value)
                    example[key] = value
                    schema_props[key] = {'type': 'string'}
            body_data['content'][content_type] = {
                'schema': {'type': 'object', 'properties': schema_props},
                'example': example,
            }
            if mode == 'formdata' and any(
                isinstance(f, dict) and f.get('type') == 'file' for f in fields
            ):
                body_data['description'] = '注意：本接口包含文件上传字段，需手工补充文件内容'

        elif mode == 'file':
            file_info = body.get('file') or {}
            body_data['content']['application/octet-stream'] = {
                'schema': {'type': 'string', 'format': 'binary'},
                'example': f'<file: {file_info.get("src", "")}>',
            }
            body_data['description'] = '注意：本接口为二进制文件请求，需手工补充文件内容'

        elif mode == 'graphql':
            graphql = body.get('graphql') or {}
            body_data['content']['application/json'] = {
                'schema': {'type': 'object'},
                'example': {
                    'query': convert_postman_vars(graphql.get('query', '') or ''),
                    'variables': graphql.get('variables') or {},
                },
            }

        return body_data if body_data['content'] else {}

    def _build_parameters(self, url_info: Dict[str, Any],
                          headers: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]],
                                                                   List[Dict[str, Any]]]:
        """从 url path / query 中构造 OpenAPI 风格的 parameters。

        Returns:
            (path_params, query_params)
        """
        path_params: List[Dict[str, Any]] = []
        for match in re.finditer(r'\{([A-Za-z_][A-Za-z0-9_]*)\}', url_info['path']):
            path_params.append({
                'name': match.group(1),
                'in': 'path',
                'required': True,
                'description': '',
                'schema': {'type': 'string'},
                'example': '',
            })

        query_params: List[Dict[str, Any]] = []
        for q in url_info.get('query') or []:
            query_params.append({
                'name': q.get('key', ''),
                'in': 'query',
                'required': False,
                'description': q.get('description', ''),
                'schema': {'type': 'string'},
                'example': q.get('value', ''),
            })

        return path_params, query_params

    def _headers_as_parameters(self, headers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """把 header 转为 OpenAPI 风格的 parameters（仅展示用）。"""
        params: List[Dict[str, Any]] = []
        # 跳过常见的会话/工具自动头，避免噪音
        skip_keys = {'content-type', 'content-length', 'host', 'user-agent',
                     'accept', 'accept-encoding', 'connection'}
        for h in headers:
            if str(h.get('key', '')).lower() in skip_keys:
                continue
            params.append({
                'name': h.get('key', ''),
                'in': 'header',
                'required': False,
                'description': h.get('description', ''),
                'schema': {'type': 'string'},
                'example': h.get('value', ''),
            })
        return params

    def _extract_events(self, events: List[Dict[str, Any]]) -> Dict[str, str]:
        """提取 pm.test / pre-request 的 JS 原文。"""
        result: Dict[str, str] = {'prerequest': '', 'test': ''}
        for evt in events or []:
            if not isinstance(evt, dict):
                continue
            listen = evt.get('listen')
            script = evt.get('script') or {}
            exec_lines = script.get('exec')
            if isinstance(exec_lines, list):
                code = '\n'.join(str(line) for line in exec_lines)
            elif isinstance(exec_lines, str):
                code = exec_lines
            else:
                code = ''
            if listen in result:
                result[listen] = code.strip()
        return result

    def _extract_collection_variables(self, variables: List[Any]) -> Dict[str, Any]:
        """提取 collection.variable 为 {name: value} 字典。"""
        result: Dict[str, Any] = {}
        for var in variables or []:
            if not isinstance(var, dict):
                continue
            key = var.get('key')
            if not key:
                continue
            value = var.get('value', '')
            if isinstance(value, str):
                value = convert_postman_vars(value)
            result[key] = value
        return result

    def _extract_auth(self, auth: Any) -> Dict[str, Any]:
        """规范化 auth 配置（仅保留有意义的常见类型）。"""
        if not isinstance(auth, dict):
            return {}
        auth_type = auth.get('type')
        if not auth_type:
            return {}

        # auth.<type> 是一个数组：[{'key','value','type'}, ...]
        config = auth.get(auth_type) or []
        flat: Dict[str, Any] = {}
        if isinstance(config, list):
            for entry in config:
                if isinstance(entry, dict) and 'key' in entry:
                    value = entry.get('value', '')
                    if isinstance(value, str):
                        value = convert_postman_vars(value)
                    flat[entry['key']] = value
        elif isinstance(config, dict):
            flat = {k: convert_postman_vars(v) if isinstance(v, str) else v
                    for k, v in config.items()}

        return {'type': auth_type, 'config': flat}

    def _guess_base_url(self, collection: Dict[str, Any]) -> str:
        """根据 collection 变量推断 base_url。"""
        variables = collection.get('variable') or []
        for var in variables:
            if not isinstance(var, dict):
                continue
            key = (var.get('key') or '').lower()
            if key in ('baseurl', 'base_url', 'host', 'url'):
                value = var.get('value', '')
                if isinstance(value, str) and value:
                    return convert_postman_vars(value)
        # 退而求其次：扫描第一个 request 的 url.host
        first_host = self._find_first_host(collection.get('item') or [])
        return first_host or ''

    def _find_first_host(self, items: List[Any]) -> str:
        for item in items or []:
            if not isinstance(item, dict):
                continue
            if 'request' in item:
                url_info = self._parse_url(item['request'].get('url'))
                if url_info['host']:
                    return url_info['host']
            sub = item.get('item')
            if isinstance(sub, list):
                found = self._find_first_host(sub)
                if found:
                    return found
        return ''

    def _make_operation_id(self, name: str, method: str, path: str) -> str:
        """生成稳定的 operation_id（兼容现有结构）。"""
        slug = re.sub(r'[^A-Za-z0-9]+', '_', name).strip('_').lower()
        path_slug = re.sub(r'[^A-Za-z0-9]+', '_', path).strip('_').lower()
        return f"postman_{method.lower()}_{slug or path_slug}"

    def _normalize_description(self, description: Any) -> str:
        """description 可能是字符串或 {'content': str} 结构。"""
        if isinstance(description, str):
            return description
        if isinstance(description, dict):
            content = description.get('content')
            if isinstance(content, str):
                return content
        return ''


# ============ 端点写库工具 ============

def create_endpoints_from_postman(spec, parse_result: Dict[str, Any]) -> List[Any]:
    """根据解析结果将 endpoint 持久化到数据库。

    复用与 APIParserService 一致的去重策略：(spec, path, method) 唯一。
    重复时合并 description，避免抛出 IntegrityError。

    Args:
        spec: APISpecification 实例
        parse_result: PostmanParserService.parse 返回值

    Returns:
        创建（或更新）后的 APIEndpoint 列表，顺序与解析结果一致。
    """
    from .models import APIEndpoint, APIModule

    endpoints: List[Any] = []
    module_cache: Dict[str, Any] = {}

    for index, ep_info in enumerate(parse_result.get('endpoints') or []):
        tags = ep_info.get('tags') or ['未分类']
        module_name = tags[0] if tags else '未分类'

        module = module_cache.get(module_name)
        if module is None:
            module, _ = APIModule.objects.get_or_create(
                project_id=spec.project_id,
                name=module_name,
                defaults={'sort_order': 0},
            )
            module_cache[module_name] = module

        path = ep_info.get('path', '')
        method = ep_info.get('method', '').upper()

        try:
            endpoint, created = APIEndpoint.objects.update_or_create(
                spec=spec,
                path=path,
                method=method,
                defaults={
                    'module': module,
                    'summary': ep_info.get('summary', ''),
                    'description': ep_info.get('description', ''),
                    'parameters': ep_info.get('parameters', []),
                    'request_body': ep_info.get('request_body', {}),
                    'responses': ep_info.get('responses', {}),
                    'tags': tags,
                    'operation_id': ep_info.get('operation_id', ''),
                    'sort_order': index,
                },
            )
            # 透传 Postman 原始信息供后续 AI 翻译/HttpRunner 组装使用
            endpoint._postman_raw = ep_info.get('_postman_raw') or {}
            endpoints.append(endpoint)
            if not created:
                logger.info(f"Postman 端点已存在，已合并: {method} {path}")
        except Exception as e:
            logger.error(f"创建 Postman 端点失败: {method} {path}, err={e}")

    return endpoints
