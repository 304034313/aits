"""
Postman 脚本翻译服务

负责把 Postman 的 pm.test() / pre-request JavaScript 脚本"同化"为 HttpRunner 原生的
- validate（断言列表）
- extract（变量提取，jsonpath / 内置字段）
- variables（固定变量赋值）
- debugtalk_snippets（复杂逻辑的 Python 函数片段，写入 spec 级 debugtalk 备注）
- unrecognized_raw（AI 也无法处理的 JS 原文，由调用方写入用例 description）

使用 LLM 的 Pydantic 结构化输出能力，沿用 api_testcase_generator.py 的同款模式。

调用方应在 LLM 不可用时回退到 fallback_translation()。
"""
import json
import logging
from typing import Dict, List, Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from ai_core.model_manager import get_llm_manager

logger = logging.getLogger(__name__)


# ============ Pydantic 输出结构 ============

class TranslatedScript(BaseModel):
    """Postman JS 脚本被翻译为 HttpRunner 原生结构的标准化产物。"""

    validators: List[Dict[str, List[Any]]] = Field(
        default_factory=list,
        description=(
            "HttpRunner 断言列表，每项是单键字典，"
            "如 {'eq': ['status_code', 200]}, {'eq': ['body.code', 0]}, "
            "{'contains': ['body.message', 'ok']}, "
            "{'less_than': ['response_time', 1000]}。"
            "支持的比较器: eq, ne, gt, ge, lt, le, contains, startswith, endswith, "
            "length_eq, length_greater_than, length_less_than, type_match。"
        ),
    )
    extract: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "从 pm.environment.set / pm.collectionVariables.set 等语句中识别出的变量提取，"
            "key 是变量名，value 是 HttpRunner jmespath 表达式，"
            "如 {'token': 'body.data.token', 'userId': 'body.user.id'}"
        ),
    )
    variables: Dict[str, Any] = Field(
        default_factory=dict,
        description="从 prerequest 中识别到的固定变量赋值（值为常量字面量时）",
    )
    debugtalk_snippets: List[str] = Field(
        default_factory=list,
        description=(
            "AI 认为可以转换为 Python 工具函数的复杂逻辑片段（如随机生成签名、动态时间戳）。"
            "每个片段为合法的 Python 函数源码，函数名以 pm_ 开头，便于汇总到 debugtalk.py。"
        ),
    )
    unrecognized_raw: str = Field(
        default='',
        description="AI 无法可靠转换的 JS 原文，调用方会写回用例 description 供人工迁移",
    )
    notes: str = Field(
        default='',
        description="对翻译过程的简要说明（可选）",
    )


# ============ 系统提示词 ============

_SYSTEM_PROMPT = """你是一个资深的接口自动化测试工程师，精通 Postman 和 HttpRunner。
任务：把用户给你的 Postman JavaScript 脚本（pm.test 与 pre-request）翻译为 HttpRunner v3 的原生结构。

【输出规则】（必须严格遵守）：
1. validators: 每项必须是"单键字典"，键是比较器名，值是 [jsonpath/字段, 期望值] 的二元数组。
   - 状态码: {"eq": ["status_code", 200]}
   - 响应体字段: {"eq": ["body.code", 0]}, {"eq": ["body.data.id", 123]}
   - 包含子串: {"contains": ["body.message", "ok"]}
   - 响应时间: {"less_than": ["response_time", 1000]}
   - 数组长度: {"length_eq": ["body.items", 3]}
2. extract: 来自 pm.environment.set / pm.collectionVariables.set / pm.globals.set 的赋值，
   key 是变量名，value 是 jmespath 表达式（如 body.data.token）。
3. variables: 当 prerequest 中是固定字面量赋值（如 pm.variables.set("user","admin")），写入这里。
4. debugtalk_snippets: 仅当 JS 包含复杂运行时逻辑（签名、随机串、加密、动态时间戳）时，
   生成 Python 函数（函数名 pm_xxx），其余情况留空数组即可。
5. unrecognized_raw: 把你确实没法稳妥翻译的 JS 原文片段塞进来（保留原意供人工迁移）。

【映射示例】
JS: pm.expect(pm.response.code).to.eql(200);
=> validators: [{"eq": ["status_code", 200]}]

JS: pm.test("ok", function(){ var json=pm.response.json(); pm.expect(json.code).to.eql(0); });
=> validators: [{"eq": ["body.code", 0]}]

JS: pm.environment.set("token", pm.response.json().data.token);
=> extract: {"token": "body.data.token"}

JS: pm.expect(pm.response.responseTime).to.be.below(800);
=> validators: [{"less_than": ["response_time", 800]}]

JS: pm.variables.set("ts", Date.now());
=> debugtalk_snippets: ["def pm_timestamp_ms():\\n    import time\\n    return int(time.time() * 1000)"]
   (并 variables: {"ts": "${pm_timestamp_ms()}"})

【绝对不要】
- 输出额外的解释性文字（结构化字段以外）
- 编造原 JS 中不存在的断言
- 把 status_code 写成字符串"200"
"""


class PostmanScriptTranslator:
    """Postman JS 脚本 → HttpRunner 原生结构 翻译器。"""

    EMPTY_RESULT: Dict[str, Any] = {
        'validators': [],
        'extract': {},
        'variables': {},
        'debugtalk_snippets': [],
        'unrecognized_raw': '',
        'notes': '',
    }

    def __init__(self):
        try:
            self.llm_manager = get_llm_manager()
            self.use_ai = bool(self.llm_manager and self.llm_manager.current_llm)
            if self.use_ai:
                logger.info(
                    f"Postman 脚本翻译器初始化成功，LLM: {self.llm_manager.llm_type}"
                )
            else:
                logger.warning("Postman 脚本翻译器未检测到可用 LLM，将使用规则回退")
        except Exception as e:
            logger.warning(f"Postman 脚本翻译器初始化失败: {e}")
            self.llm_manager = None
            self.use_ai = False

    # ============ 公共方法 ============

    def translate(self,
                  test_script: str,
                  prerequest_script: str = '',
                  request_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """翻译 Postman JS 脚本为 HttpRunner 原生结构。

        Args:
            test_script: pm.test() 块的 JS 原文
            prerequest_script: prerequest 块的 JS 原文
            request_context: 当前请求的上下文（method/path/body 等，仅用于给 AI 提示）

        Returns:
            TranslatedScript.model_dump() 形式的字典；失败/无 LLM 时返回规则回退。
        """
        test_script = (test_script or '').strip()
        prerequest_script = (prerequest_script or '').strip()

        # 都为空时直接返回默认 validator（200）
        if not test_script and not prerequest_script:
            return self._default_result()

        if not self.use_ai or not self.llm_manager or not self.llm_manager.current_llm:
            logger.info("LLM 不可用，使用规则回退翻译 Postman 脚本")
            return self.fallback_translation(test_script, prerequest_script)

        try:
            structured_llm = self.llm_manager.current_llm.with_structured_output(TranslatedScript)
            messages = [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=self._build_prompt(test_script, prerequest_script, request_context)),
            ]
            response: TranslatedScript = structured_llm.invoke(messages)
            result = response.model_dump()
            # 确保至少有一个状态码断言
            if not result.get('validators'):
                result['validators'] = [{'eq': ['status_code', 200]}]
            return result
        except Exception as e:
            logger.error(f"AI 翻译 Postman 脚本失败，使用规则回退: {e}", exc_info=True)
            fallback = self.fallback_translation(test_script, prerequest_script)
            fallback['notes'] = f'AI 翻译失败，已使用规则回退: {e}'
            return fallback

    # ============ 规则回退（不依赖 LLM） ============

    def fallback_translation(self, test_script: str, prerequest_script: str) -> Dict[str, Any]:
        """简易规则解析：识别最常见的 status_code、pm.environment.set 等模式。

        其他无法识别的内容会写入 unrecognized_raw，由调用方落到用例 description。
        """
        result = self._default_result()

        import re

        unrecognized_parts: List[str] = []

        if test_script:
            # status_code eq
            for m in re.finditer(
                r'pm\.response\.code\s*\)\s*\.to\.eql\s*\(\s*(\d{3})\s*\)', test_script
            ):
                result['validators'].append({'eq': ['status_code', int(m.group(1))]})
            for m in re.finditer(
                r'pm\.expect\(\s*pm\.response\.code\s*\)\s*\.to\.equal\s*\(\s*(\d{3})\s*\)', test_script
            ):
                result['validators'].append({'eq': ['status_code', int(m.group(1))]})

            # response time
            for m in re.finditer(
                r'pm\.response\.responseTime\s*\)\s*\.to\.be\.below\s*\(\s*(\d+)\s*\)', test_script
            ):
                result['validators'].append({'less_than': ['response_time', int(m.group(1))]})

            # contains
            for m in re.finditer(
                r'pm\.expect\(\s*pm\.response\.text\(\s*\)\s*\)\.to\.include\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)',
                test_script,
            ):
                result['validators'].append({'contains': ['body', m.group(1)]})

            # pm.environment.set / pm.collectionVariables.set / pm.globals.set
            for m in re.finditer(
                r'pm\.(?:environment|collectionVariables|globals)\.set\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*pm\.response\.json\(\s*\)\.([\w\.\[\]]+)\s*\)',
                test_script,
            ):
                var_name = m.group(1)
                jpath = m.group(2).replace('[', '.').replace(']', '')
                result['extract'][var_name] = f"body.{jpath}"

            # 未匹配上的整段都视为 unrecognized
            stripped = test_script.strip()
            if stripped and not (result['validators'] or result['extract']):
                unrecognized_parts.append('// pm.test 脚本:\n' + stripped)

        if prerequest_script:
            for m in re.finditer(
                r'pm\.(?:variables|environment|collectionVariables|globals)\.set\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*[\'"]([^\'"]+)[\'"]\s*\)',
                prerequest_script,
            ):
                result['variables'][m.group(1)] = m.group(2)

            # 其余 prerequest 内容直接保留为 unrecognized
            stripped = prerequest_script.strip()
            if stripped and not result['variables']:
                unrecognized_parts.append('// pm.prerequest 脚本:\n' + stripped)

        if not result['validators']:
            # 兜底：默认 200 OK
            result['validators'].append({'eq': ['status_code', 200]})

        if unrecognized_parts:
            result['unrecognized_raw'] = '\n\n'.join(unrecognized_parts)

        return result

    # ============ 内部工具 ============

    def _default_result(self) -> Dict[str, Any]:
        result = {k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v)
                  for k, v in self.EMPTY_RESULT.items()}
        result['validators'] = [{'eq': ['status_code', 200]}]
        return result

    def _build_prompt(self,
                      test_script: str,
                      prerequest_script: str,
                      request_context: Optional[Dict[str, Any]]) -> str:
        ctx_str = ''
        if request_context:
            ctx_str = '【请求上下文】\n' + json.dumps(request_context, ensure_ascii=False, indent=2)

        sections = [ctx_str] if ctx_str else []
        if prerequest_script:
            sections.append(f"【pm.prerequest 脚本】\n{prerequest_script}")
        if test_script:
            sections.append(f"【pm.test 脚本】\n{test_script}")
        sections.append('请严格按 TranslatedScript 结构输出。')
        return '\n\n'.join(sections)


# ============ 单例缓存（避免在循环中反复创建） ============

_translator_singleton: Optional[PostmanScriptTranslator] = None


def get_postman_script_translator() -> PostmanScriptTranslator:
    """返回（按需创建的）翻译器单例。"""
    global _translator_singleton
    if _translator_singleton is None:
        _translator_singleton = PostmanScriptTranslator()
    return _translator_singleton
