# core/text_postprocessor.py
# 文本后处理模块 - 基于 pangu.py 设计理念

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ==================== CJK 字符定义（参考 pangu.py）====================
CJK = r'\u2e80-\u2eff\u2f00-\u2fdf\u3040-\u309f\u30a0-\u30fa\u30fc-\u30ff\u3100-\u312f\u3200-\u32ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff'
ANY_CJK = re.compile(r'[{CJK}]'.format(CJK=CJK))


class TextPostProcessor:
    """
    文本后处理器 - 基于 pangu.py 设计理念的完全重写版本

    核心理念：
    1. 使用 CJK 字符的完整 Unicode 范围
    2. 精心设计的正则表达式序列处理各种边界
    3. 按顺序应用规则，避免规则冲突
    4. 保留语音识别特有的处理逻辑
    """

    def __init__(self, enable_punctuation: bool = True, enable_filler_removal: bool = True):
        """
        初始化文本后处理器

        Args:
            enable_punctuation: 是否启用标点添加
            enable_filler_removal: 是否启用语气词去除
        """
        self.enable_punctuation = enable_punctuation
        self.enable_filler_removal = enable_filler_removal

        # ==================== pangu.py 风格的正则表达式 ====================
        # CJK 与英文/数字/符号的边界
        self._cjk_ans = re.compile('([{CJK}])([A-Za-z0-9@\\$%\\^&\\*\\-\\+\\\\=\\|/])'.format(CJK=CJK))
        self._ans_cjk = re.compile('([A-Za-z0-9~\\!\\$%\\^&\\*\\-\\+\\\\=\\|;:,\\./\\?])([{CJK}])'.format(CJK=CJK))

        # CJK 与操作符
        self._cjk_operator_ans = re.compile('([{CJK}])([\\+\\-\\*\\/=&\\|<>])([A-Za-z0-9])'.format(CJK=CJK))
        self._ans_operator_cjk = re.compile('([A-Za-z0-9])([\\+\\-\\*\\/=&\\|<>])([{CJK}])'.format(CJK=CJK))

        # CJK 与括号
        self._cjk_left_bracket = re.compile('([{CJK}])([\\(\\[\\{{<>\u201c])'.format(CJK=CJK))
        self._right_bracket_cjk = re.compile('([\\)\\]\\}}<>\u201d])([{CJK}])'.format(CJK=CJK))
        self._an_left_bracket = re.compile(r'([A-Za-z0-9])([\(\[\{])')
        self._right_bracket_an = re.compile(r'([\)\]\}])([A-Za-z0-9])')

        # CJK 与引号
        self._cjk_quote = re.compile('([{CJK}])([`"\u05f4])'.format(CJK=CJK))
        self._quote_cjk = re.compile('([`"\u05f4])([{CJK}])'.format(CJK=CJK))

        # ==================== 语音识别特有的处理 ====================
        # 逐字母拼写修复（pangu.py 没有这个功能）
        # 使用 lookaround 而不是 \b，因为 \b 在 CJK 字符前不工作
        self._letter_spacing_pattern = re.compile(r'(?<![a-zA-Z])[a-z](?: [a-z]){1,5}(?![a-z])', re.IGNORECASE)

        # 英文大小写映射（2025年术语）
        self._english_capitalization = self._build_english_terms()

        # ==================== 填充词处理 ====================
        self._sentence_initial_fillers = [
            re.compile(r'^嗯嗯\s*'), re.compile(r'^啊啊\s*'), re.compile(r'^呃呃\s*'),
            re.compile(r'^那个那个\s*'), re.compile(r'^这个这个\s*'),
        ]
        self._sentence_final_fillers = [
            re.compile(r'啊$'), re.compile(r'呀$'), re.compile(r'哦$'),
        ]

        logger.info("文本后处理器初始化完成 (基于 pangu.py 设计)")

    def _build_english_terms(self) -> dict:
        """构建英文术语字典"""
        return {
            # AI/ML (2025)
            'ai': 'AI', 'ml': 'ML', 'nlp': 'NLP', 'llm': 'LLM',
            'chatgpt': 'ChatGPT', 'gpt': 'GPT', 'claude': 'Claude',
            'llama': 'LLaMA', 'mistral': 'Mistral', 'gemini': 'Gemini',
            'rag': 'RAG', 'agi': 'AGI', 'transformer': 'Transformer',
            'bert': 'BERT', 'langchain': 'LangChain', 'openai': 'OpenAI',
            'huggingface': 'HuggingFace', 'cohere': 'Cohere', 'anthropic': 'Anthropic',

            # 开发工具
            'api': 'API', 'sdk': 'SDK', 'ui': 'UI', 'ux': 'UX',
            'http': 'HTTP', 'https': 'HTTPS', 'tcp': 'TCP', 'udp': 'UDP',
            'ssh': 'SSH', 'ssl': 'TLS', 'ftp': 'FTP', 'dns': 'DNS',
            'url': 'URL', 'uri': 'URI', 'json': 'JSON', 'yaml': 'YAML',
            'xml': 'XML', 'html': 'HTML', 'css': 'CSS', 'sql': 'SQL',
            'markdown': 'Markdown', 'regex': 'Regex', 'rest': 'REST',
            'graphql': 'GraphQL', 'grpc': 'gRPC', 'websocket': 'WebSocket',

            # 编程语言
            'python': 'Python', 'java': 'Java', 'javascript': 'JavaScript',
            'typescript': 'TypeScript', 'golang': 'Golang', 'rust': 'Rust',
            'cpp': 'C++', 'csharp': 'C#', 'php': 'PHP', 'swift': 'Swift',
            'kotlin': 'Kotlin', 'scala': 'Scala', 'ruby': 'Ruby', 'go': 'Go',
            'matlab': 'MATLAB', 'r': 'R', 'julia': 'Julia', 'lua': 'Lua',

            # 框架和库
            'react': 'React', 'vue': 'Vue', 'angular': 'Angular',
            'django': 'Django', 'flask': 'Flask', 'fastapi': 'FastAPI',
            'spring': 'Spring', 'express': 'Express', 'nest': 'Nest',
            'nextjs': 'Next.js', 'nuxtjs': 'Nuxt.js', 'vite': 'Vite',
            'webpack': 'Webpack', 'vite': 'Vite', 'babel': 'Babel',
            'numpy': 'NumPy', 'pandas': 'Pandas', 'tensorflow': 'TensorFlow',
            'pytorch': 'PyTorch', 'keras': 'Keras', 'scikit': 'Scikit',

            # 云服务和工具
            'docker': 'Docker', 'kubernetes': 'Kubernetes', 'k8s': 'K8s',
            'aws': 'AWS', 'azure': 'Azure', 'gcp': 'GCP', 'aliyun': 'Aliyun',
            'nginx': 'Nginx', 'apache': 'Apache', 'mysql': 'MySQL',
            'mongodb': 'MongoDB', 'redis': 'Redis', 'postgresql': 'PostgreSQL',
            'sqlite': 'SQLite', 'elasticsearch': 'Elasticsearch',
            'git': 'Git', 'github': 'GitHub', 'gitlab': 'GitLab',
            'bitbucket': 'Bitbucket', 'gitee': 'Gitee',
            'jenkins': 'Jenkins', 'travis': 'Travis', 'circleci': 'CircleCI',
            'terraform': 'Terraform', 'ansible': 'Ansible', 'puppet': 'Puppet',

            # 系统和平台
            'ios': 'iOS', 'android': 'Android', 'linux': 'Linux',
            'windows': 'Windows', 'macos': 'macOS', 'ubuntu': 'Ubuntu',
            'debian': 'Debian', 'centos': 'CentOS', 'redhat': 'RedHat',
            'fedora': 'Fedora', 'arch': 'Arch', 'gentoo': 'Gentoo',
            'unix': 'Unix', 'posix': 'POSIX', 'gnu': 'GNU',

            # 开发平台
            'vscode': 'VS Code', 'visualstudio': 'Visual Studio',
            'xcode': 'Xcode', 'androidstudio': 'Android Studio',
            'intellij': 'IntelliJ', 'pycharm': 'PyCharm', 'webstorm': 'WebStorm',
            'sublime': 'Sublime', 'atom': 'Atom', 'vim': 'Vim', 'emacs': 'Emacs',

            # 常见缩写
            'ok': 'OK', 'cpu': 'CPU', 'gpu': 'GPU', 'ram': 'RAM',
            'ssd': 'SSD', 'usb': 'USB', 'vpn': 'VPN', 'cdn': 'CDN',
            'ceo': 'CEO', 'cto': 'CTO', 'cfo': 'CFO', 'coo': 'COO',
            'kpi': 'KPI', 'roi': 'ROI', 'qa': 'QA', 'pm': 'PM',
            'hr': 'HR', 'it': 'IT', 'r&d': 'R&D', 'b2b': 'B2B',
            'b2c': 'B2C', 'o2o': 'O2O', 'saas': 'SaaS', 'paas': 'PaaS',
            'iaas': 'IaaS', 'api': 'API', 'sdk': 'SDK', 'ide': 'IDE',

            # 社交和媒体
            'facebook': 'Facebook', 'twitter': 'Twitter', 'instagram': 'Instagram',
            'linkedin': 'LinkedIn', 'youtube': 'YouTube', 'tiktok': 'TikTok',
            'wechat': 'WeChat', 'telegram': 'Telegram', 'discord': 'Discord',
            'slack': 'Slack', 'zoom': 'Zoom', 'teams': 'Teams',

            # 其他常见词
            'wifi': 'Wi-Fi', 'wi-fi': 'Wi-Fi', 'bluetooth': 'Bluetooth', 'nfc': 'NFC',
            'qr': 'QR', 'pdf': 'PDF', 'csv': 'CSV', 'txt': 'TXT',
            'email': 'email', 'ios': 'iOS', 'ipad': 'iPad', 'iphone': 'iPhone',
        }

    def process(self, text: str) -> str:
        """
        处理文本的主入口

        处理流程（基于 pangu.py 理念）：
        1. 去除填充词
        2. 修复逐字母拼写
        3. 转换中文数字
        4. 应用 pangu 风格的空格规则
        5. 修复英文大小写
        6. 添加标点符号
        """
        if not text:
            return text

        # 预处理
        text = text.strip()
        if not text:
            return text

        result = text

        # 步骤1: 去除填充词
        if self.enable_filler_removal:
            result = self._remove_fillers(result)

        # 步骤2: 修复逐字母拼写（语音识别特有）
        result = self._fix_letter_spelling(result)

        # 步骤3: 转换中文数字
        result = self._convert_chinese_numbers(result)

        # 步骤4: 应用 pangu 风格的空格规则（核心）
        result = self._apply_pangu_spacing(result)

        # 步骤5: 修复英文大小写
        result = self._fix_english_capitalization(result)

        # 步骤6: 添加标点符号
        if self.enable_punctuation:
            result = self._add_punctuation(result)

        logger.info(f"规则文本后处理: '{text}' → '{result}'")
        return result

    def _remove_fillers(self, text: str) -> str:
        """去除填充词"""
        result = text

        # 删除句首填充词
        for pattern in self._sentence_initial_fillers:
            result = pattern.sub('', result)

        # 删除句尾填充词
        for pattern in self._sentence_final_fillers:
            result = pattern.sub('', result)

        # 清理多余空格
        result = re.sub(r'\s+', ' ', result)
        result = re.sub(r'^\s+|\s+$', '', result)

        return result

    def _fix_letter_spelling(self, text: str) -> str:
        """
        修复逐字母拼写（语音识别特有功能）

        场景：语音识别将 "API" 识别为 "a p i"
        """
        result = text

        def try_fix(match):
            letters_part = match.group(0)
            letters = letters_part.replace(' ', '')
            # 只有在字典中存在时才修复
            if letters.lower() in self._english_capitalization:
                return letters
            return match.group(0)

        result = self._letter_spacing_pattern.sub(try_fix, result)
        return result

    def _apply_pangu_spacing(self, text: str) -> str:
        """
        应用 pangu 风格的空格规则（核心逻辑）

        参考 pangu.py 的 spacing() 函数
        """
        # 如果没有 CJK 字符，直接返回
        if not ANY_CJK.search(text):
            return text

        result = text

        # 按照 pangu.py 的顺序应用规则
        result = self._cjk_ans.sub(r'\1 \2', result)      # CJK → 英文
        result = self._ans_cjk.sub(r'\1 \2', result)      # 英文 → CJK
        result = self._cjk_operator_ans.sub(r'\1 \2 \3', result)  # CJK 操作符 英文
        result = self._ans_operator_cjk.sub(r'\1 \2 \3', result)  # 英文 操作符 CJK
        result = self._cjk_left_bracket.sub(r'\1 \2', result)     # CJK 括号
        result = self._right_bracket_cjk.sub(r'\1 \2', result)    # 括号 CJK
        result = self._an_left_bracket.sub(r'\1 \2', result)       # 英文 括号
        result = self._right_bracket_an.sub(r'\1 \2', result)      # 括号 英文
        result = self._cjk_quote.sub(r'\1 \2', result)            # CJK 引号
        result = self._quote_cjk.sub(r'\1 \2', result)            # 引号 CJK

        # 清理多余空格
        result = re.sub(r'  +', ' ', result)

        return result

    def _fix_english_capitalization(self, text: str) -> str:
        """修复英文大小写"""
        result = text

        # 按长度降序处理，避免短词覆盖长词
        sorted_terms = sorted(self._english_capitalization.items(),
                             key=lambda x: len(x[0]), reverse=True)

        for term_lower, term_correct in sorted_terms:
            # 使用单词边界，避免部分替换
            pattern = r'\b' + re.escape(term_lower) + r'\b'
            result = re.sub(pattern, term_correct, result, flags=re.IGNORECASE)

        return result

    def _add_punctuation(self, text: str) -> str:
        """
        添加标点符号

        简化版本，专注于句末标点
        """
        # 如果已经有标点，直接返回
        if text[-1:] in ['。', '！', '？', '.', '!', '?', '，', '、', ';', '；']:
            return text

        # 检测疑问语气
        question_markers = ['什么', '怎么', '为什么', '哪里', '吗', '呢']
        if any(marker in text for marker in question_markers):
            return text + '？'

        # 检测感叹语气
        exclamation_markers = ['真', '太', '非常', '超级']
        if any(marker in text for marker in exclamation_markers):
            return text + '！'

        # 默认句号
        return text + '。'

    def _convert_chinese_numbers(self, text: str) -> str:
        """
        智能转换中文数字为阿拉伯数字

        处理规则：
        1. "幺"在数字中替换为"一"：幺三八 → 138
        2. 保留前导零：零一二三 → 0123
        3. 连续数字转换：一二三四五 → 12345
        4. 保护词语中的"一"不被转换：一些、一致、一会儿等

        性能优化：
        - 快速检测是否需要转换（避免不必要的处理）
        - 完善的异常处理
        """
        # 快速检测：如果文本中没有中文数字字符，直接返回
        chinese_digits = '零一二三四五六七八九十百千万亿两〇幺'
        if not any(c in text for c in chinese_digits):
            return text

        try:
            import cn2an

            # 保护模式：包含"一"但不应被转换的词语
            protected_patterns = [
                '一些', '一般', '一样', '一起', '一致', '一会儿',
                '一定', '一旦', '一边', '一直', '一下',
                '万一', '唯一', '第一', '统一', '一切', '一向',
                '一处', '一点', '一种', '个个', '同时',
            ]

            # 去重并排序（长的模式优先匹配）
            protected_patterns = sorted(list(set(protected_patterns)), key=len, reverse=True)

            # 使用占位符保护这些词语
            placeholders = []
            protected_text = text

            # 中文数字字符（这些字符前后不能有被保护的词）
            chinese_digits_pattern = '零一二三四五六七八九十百千万亿两〇'

            for i, pattern in enumerate(protected_patterns):
                # 创建正则模式：pattern 前后不能是中文数字字符
                pattern_escaped = re.escape(pattern)
                negative_lookbehind = f'(?<![{chinese_digits_pattern}])'
                negative_lookahead = f'(?![{chinese_digits_pattern}])'
                regex_pattern = negative_lookbehind + pattern_escaped + negative_lookahead

                def make_replacer(p_idx, p_pattern):
                    def replacer(match):
                        placeholder = f"__PROTECTED_{p_idx}__"
                        placeholders.append((placeholder, p_pattern))
                        return placeholder
                    return replacer

                protected_text = re.sub(regex_pattern, make_replacer(i, pattern), protected_text)

            # 预处理：将"幺"替换为"一"（只在数字语境下）
            processed_text = protected_text
            i = 0
            while i < len(processed_text):
                if processed_text[i] == '幺':
                    # 检查前后是否有数字字符
                    in_number_context = False
                    start = max(0, i - 2)
                    end = min(len(processed_text), i + 3)
                    context = processed_text[start:end]
                    for c in context:
                        if c in '零〇一二三四五六七八九十两':
                            in_number_context = True
                            break
                    if in_number_context:
                        processed_text = processed_text[:i] + '一' + processed_text[i+1:]
                i += 1

            # 使用 cn2an 转换
            result = cn2an.transform(processed_text)

            # 后处理：恢复保护的词语
            for placeholder, original in placeholders:
                result = result.replace(placeholder, original)

            return result

        except ImportError:
            logger.warning("cn2an 库未安装，跳过中文数字转换")
            return text
        except Exception as e:
            logger.warning(f"中文数字转换失败: {e}，返回原文")
            return text


# 向后兼容的别名
def process_with_rules(text: str) -> str:
    """向后兼容的处理函数"""
    processor = TextPostProcessor()
    return processor.process(text)


# ==================== 单例模式（线程安全）====================
_processor_instance: Optional[TextPostProcessor] = None
_processor_lock = None  # 延迟导入 threading


def get_text_postprocessor() -> TextPostProcessor:
    """
    获取文本后处理器单例（线程安全）

    Returns:
        TextPostProcessor: 文本后处理器实例
    """
    global _processor_instance, _processor_lock
    if _processor_lock is None:
        import threading
        _processor_lock = threading.Lock()

    if _processor_instance is None:
        with _processor_lock:
            # 双重检查锁定
            if _processor_instance is None:
                _processor_instance = TextPostProcessor()
    return _processor_instance
