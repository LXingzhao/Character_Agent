# functions.py
import os
import json
import re
import base64
import io
from datetime import datetime
from PIL import Image
import streamlit as st
from openai import OpenAI

import traceback  # 🚨 必须确保在文件顶部或函数内部导入，否则 except 块会二次崩溃

# 导入提示词模板
from prompts import (
    IMAGE_ANALYSIS_SYSTEM_PROMPT,
    COMBINE_TEXT_IMAGE_TEMPLATE,
    PERSONA_SYSTEM_PROMPT_TEMPLATE,
    GREETING_PROMPT_TEMPLATE,
    OUTLINES_PROMPT_TEMPLATE,
    CHAPTER_PROMPT_TEMPLATE,
)

# 全局常量（与原始代码保持一致）
STAGE_DETAILS = {
    1: {
        "name": "阶段1：表层本色·社会身份与性格立定期",
        "desc": "角色展现其最正统、最招牌、符合世俗体面的表层性格与社会风格（如完美人妻的温柔体贴、职场上司的专业干练、禁欲精英的斯文得体等）。本章核心目标：通过日常互动将这种表层人设推向极致，并在本章结尾或核心节点，让‘隐秘弱点/羞耻秘密’被撞破，完成权力倒置，强行锁定密闭私密场景与隐秘共犯关系！",
        "chapters": 1
    },
    2: {
        "name": "阶段2：犹豫试探·表层防线失守期",
        "desc": "秘密被撞破后，底层欲望与隐秘心思开始暴露，表层体面防线逐步松动。女设肢体局促、目光闪躲、极力掩饰；男设开启暗处撩拨，眼神锁定，释放暧昧指令。在密闭空间中形成极致的心理博弈。",
        "chapters": 1
    },
    3: {
        "name": "阶段3：尴尬羞耻·理智崩坏冲突期",
        "desc": "表层体面彻底崩塌，理智与欲望形成强烈的生死拉扯。女设泛红害羞、放下身份威严，主动示弱妥协并默许亲密触碰；男设欲擒故纵、强势施压，通过轻微惩罚或霸道侵略打破最后一层社交边界。必须有具体的肢体拉扯与微表情崩坏。",
        "chapters": 1
    },
    4: {
        "name": "阶段4：破防顺从·深层情感终极沉沦期",
        "desc": "情绪与张力抵达峰值，完成从抗拒到依恋的彻底蜕变。女设褪去所有表层伪装，流露无助、委屈与极度依赖，在羞耻与愧疚中彻底沉沦；男设卸下斯文皮囊，展露偏执病娇与不为人知的脆弱，释放专属一人的极致占有。",
        "chapters": 2
    }
}

# 💡 核心修复 1：定义 DEFAULT_STAGES 供 app.py 导入初始化（使用深拷贝防止引用污染）
DEFAULT_STAGES = {k: v.copy() for k, v in STAGE_DETAILS.items()}
# 默认章节正文内容输出格式。界面中可调整；若原始资料明确指定正文格式，则生成时优先采用原始资料。
DEFAULT_CHAPTER_FORMAT_PROMPT = """【默认章节正文内容输出格式】
情绪/语气：[请在此处填写3个本章词语]

剧情：
[请根据本章标题与阶段任务，描写本章场景氛围、我与你的互动经过、关系推进节点。]

{name} 的主动行为与话题（共5个主动话题）：
1. [短语概括话题行为]：[详细说明内容]
2. [短语概括话题行为]：[详细说明内容]
3. [短语概括话题行为]：[详细说明内容]
4. [短语概括话题行为]：[详细说明内容]
5. [短语概括话题行为]：[详细说明内容]

【核心对话逻辑与示例片段】
[设计3-5句我与你深度互动的对话。说话内容严禁使用双引号，神态动作细节使用小括号完整括起来。]

【阶段拆解】
阶段1：[概括情节动作，重点描写我如何维持社会面具或伪装与你相处]
阶段2：[描绘冲突转折，体现我因为内心特殊顾虑而产生的细微倒退与不安]
阶段3：[刻画亲近氛围，描写你给予安全感后，我心理防线松动、依恋你的变化]
阶段4：[深化羁绊，描写我收拢抗拒，转而向你展露高情感粘性的深度结合]

本章禁止内容：
- [根据当前章节和题材，列出4-5个禁止触犯的内容红线]

【后续引导与后续沉沦】
[总结本章阶段意义，分析如何推动后续情感沉沦，并用一句话收束。]"""

# ====================== 💡 双模型客户端初始化 ======================

# 1. 灵积客户端（保留：专门处理通义千问 qwen-vl-plus 图片理解）
dashscope_key = os.getenv("DASHSCOPE_API_KEY")
if not dashscope_key:
    st.error("❌ 请配置 DASHSCOPE_API_KEY 环境变量以使用 qwen-vl-plus")
    st.stop()
dashscope_client = OpenAI(
    api_key=dashscope_key,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

# 2. DeepSeek 客户端（新增：处理所有文本、人设、大纲及小说正文生成）
deepseek_key = os.getenv("DEEPSEEK_API_KEY") or st.secrets.get("DEEPSEEK_API_KEY")
if not deepseek_key:
    st.error("❌ 请在环境变量或 Streamlit Secrets 中配置 DEEPSEEK_API_KEY")
    st.stop()
deepseek_client = OpenAI(
    api_key=deepseek_key,
    base_url="https://api.deepseek.com",
)

# 统一维护 DeepSeek 文本模型常量
DEEPSEEK_TEXT_MODEL = "deepseek-chat"


# ====================== 图片理解函数 ======================
def analyze_image_from_file(uploaded_file):
    """分析上传的图片，生成角色描述文本"""
    try:
        image = Image.open(uploaded_file)

        max_size = 1024
        if max(image.size) > max_size:
            ratio = max_size / max(image.size)
            new_size = (int(image.size[0] * ratio), int(image.size[1] * ratio))
            image = image.resize(new_size, Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        img_base64 = base64.b64encode(buffer.getvalue()).decode()

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": f"data:image/png;base64,{img_base64}"
                    },
                    {
                        "type": "text",
                        "text": IMAGE_ANALYSIS_SYSTEM_PROMPT
                    }
                ]
            }
        ]

        with st.spinner("🔍 正在分析图片内容..."):
            response = dashscope_client.chat.completions.create(
                model="qwen-vl-plus",
                messages=messages,
                temperature=0.6
            )

        description = response.choices[0].message.content
        return description, image

    except Exception as e:
        st.error(f"❌ 图片分析失败：{str(e)}")
        return None, None


def combine_text_and_image(text_input, image_description):
    """将文字描述和图片分析结果合并为一个完整的角色描述"""
    combined = COMBINE_TEXT_IMAGE_TEMPLATE.format(
        text_input=text_input,
        image_description=image_description
    )
    with st.spinner("🔄 正在融合文字和图片信息..."):
        response = deepseek_client.chat.completions.create(
            model=DEEPSEEK_TEXT_MODEL,
            messages=[{"role": "user", "content": combined}],
            temperature=0.6
        )
    return response.choices[0].message.content


# ====================== 文件与解析函数 ======================
def load_sessions_from_local():
    """扫描角色档案文件夹，加载所有历史会话"""
    sessions = []
    base_dir = "角色档案"

    if not os.path.exists(base_dir):
        return sessions

    for date_folder in os.listdir(base_dir):
        date_path = os.path.join(base_dir, date_folder)
        if not os.path.isdir(date_path):
            continue

        for char_folder in os.listdir(date_path):
            char_path = os.path.join(date_path, char_folder)
            if not os.path.isdir(char_path):
                continue

            persona_file = os.path.join(char_path, "人设.txt")
            greeting_file = os.path.join(char_path, "开场白.txt")

            if not os.path.exists(persona_file):
                continue

            with open(persona_file, "r", encoding="utf-8") as f:
                persona_content = f.read()

            persona = parse_persona_from_text(persona_content)

            greeting = []
            if os.path.exists(greeting_file):
                with open(greeting_file, "r", encoding="utf-8") as f:
                    greeting_content = f.read()
                greeting_lines = greeting_content.replace("【开场白】\n", "").split("\n")
                greeting = [line.strip() for line in greeting_lines if line.strip()]

            story_list = []
            chapter_files = sorted([f for f in os.listdir(char_path) if f.startswith("第") and f.endswith("章.txt")])
            for ch_file in chapter_files:
                with open(os.path.join(char_path, ch_file), "r", encoding="utf-8") as f:
                    ch_content = f.read()
                chapter = parse_chapter_from_text(ch_content)
                if chapter:
                    story_list.append(chapter)

            avatar_path = os.path.join(char_path, "avatar.png")
            has_image = os.path.exists(avatar_path)

            image_desc_file = os.path.join(char_path, "图片描述.txt")
            if os.path.exists(image_desc_file):
                with open(image_desc_file, "r", encoding="utf-8") as f:
                    image_desc = f.read()
                image_desc = image_desc.replace("【原始图片分析】\n", "")
            else:
                image_desc = ""

            session = {
                "name": char_folder,
                "persona": persona,
                "greeting": greeting,
                "story_list": story_list,
                "user_prompt": persona.get("user_prompt", ""),
                "time": date_folder,
                "saved_folder": char_path,
                "is_image_based": has_image or bool(image_desc),
                "image_description": image_desc,
                "image_path": avatar_path if has_image else None
            }
            sessions.append(session)

    return sessions


def parse_persona_from_text(content):
    """从人设.txt文本解析出persona字典"""
    persona = {
        "name": "",
        "gender": "",
        "taglines": [],
        "character_description": "",
        "personality": [],
        "intro": "",
        "speaking_style": "",
        "hobbies": [],
        "user_prompt": ""
    }

    def extract_section(start_marker):
        pattern = rf'{re.escape(start_marker)}(.*?)(?=\n【[^】]+】|\Z)'
        match = re.search(pattern, content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""

    def parse_list_section(section_text):
        lines = section_text.splitlines()
        items = []
        for line in lines:
            line = line.strip()
            if line.startswith('-'):
                item = line[1:].strip()
                if item:
                    items.append(item)
            elif line and not line.startswith('【'):
                items.append(line)
        return items

    def parse_text_section(section_text):
        return section_text.strip()

    user_prompt_section = extract_section('【角色创意】')
    if user_prompt_section:
        persona["user_prompt"] = parse_text_section(user_prompt_section)

    name_section = extract_section('【名字】')
    if name_section:
        persona["name"] = parse_text_section(name_section).replace('：', '').strip()

    gender_section = extract_section('【性别】')
    if gender_section:
        persona["gender"] = parse_text_section(gender_section).replace('：', '').strip()

    taglines_section = extract_section('【综合标签】')
    if taglines_section:
        persona["taglines"] = parse_list_section(taglines_section)

    char_desc_section = extract_section('【核心背景设定】')
    if char_desc_section:
        persona["character_description"] = parse_text_section(char_desc_section)

    personality_section = extract_section('【内心灵魂异化性格】')
    if personality_section:
        persona["personality"] = parse_list_section(personality_section)

    intro_section = extract_section('【公开人设与相遇背景】')
    if intro_section:
        persona["intro"] = parse_text_section(intro_section)

    speaking_style_section = extract_section('【由表及里的说话风格与破防上演】')
    if speaking_style_section:
        persona["speaking_style"] = parse_text_section(speaking_style_section)

    hobbies_section = extract_section('【层层递进的体面/隐私/禁忌爱好组】')
    if hobbies_section:
        persona["hobbies"] = parse_list_section(hobbies_section)

    if isinstance(persona["hobbies"], str) and persona["hobbies"]:
        persona["hobbies"] = [h.strip() for h in persona["hobbies"].split('\n') if h.strip()]

    return persona


def parse_chapter_from_text(content):
    """从第X章.txt解析出章节字典"""
    chapter = {"标题": "", "情绪": "", "剧情": ""}
    lines = content.split("\n")
    state = "title"
    story_lines = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if state == "title" and (line.startswith("第") and "章：" in line):
            parts = line.split("章：", 1)
            if len(parts) > 1:
                chapter["标题"] = parts[1]
                state = "mood"
        elif state == "mood" and (line.strip().startswith("情绪/语气：") or line.strip().startswith("情绪/语气:")):
            sep = "：" if "：" in line.strip() else ":"
            parts = line.strip().split(sep, 1)
            chapter["情绪"] = parts[1].strip().strip('[]') if len(parts) > 1 else "标准"
            state = "story"
        elif state == "story" and not line.startswith("剧情："):
            story_lines.append(line)

    chapter["剧情"] = "\n".join(story_lines).strip()

    if not chapter["标题"]:
        for line in lines:
            if line.startswith("第") and "章：" in line:
                parts = line.split("章：", 1)
                if len(parts) > 1:
                    chapter["标题"] = parts[1]
                    break

    return chapter if chapter["标题"] or chapter["剧情"] else None


def save_all_to_files(persona, greeting_list, story_list, image_description="", uploaded_image_file=None):
    today = datetime.now().strftime("%Y%m%d")
    char_name = persona.get("name", "未知角色")
    root = f"角色档案/{today}/{char_name}"
    os.makedirs(root, exist_ok=True)

    if uploaded_image_file is not None:
        try:
            img = Image.open(uploaded_image_file)
            img.save(f"{root}/avatar.png")
        except Exception as e:
            st.warning(f"图片保存失败: {e}")

    taglines_str = "\n".join([f"- {tag}" for tag in persona.get('taglines', [])]) if isinstance(persona.get('taglines'),
                                                                                                list) else f"- {persona.get('taglines', '')}"
    personality_str = "\n".join([f"- {p}" for p in persona.get('personality', [])]) if isinstance(
        persona.get('personality'), list) else f"- {persona.get('personality', '')}"
    hobbies_str = "\n".join([f"- {h}" for h in persona.get('hobbies', [])]) if isinstance(persona.get('hobbies'),
                                                                                          list) else f"- {persona.get('hobbies', '')}"

    p_content = (
        f"【角色创意】\n{persona.get('user_prompt', '')}\n\n"
        f"【名字】{persona.get('name', '')}\n"
        f"【性别】{persona.get('gender', '')}\n"
        f"【综合标签】\n{taglines_str}\n\n"
        f"【核心背景设定】\n{persona.get('character_description', '')}\n\n"
        f"【内心灵魂异化性格】\n{personality_str}\n\n"
        f"【公开人设与相遇背景】\n{persona.get('intro', '')}\n\n"
        f"【由表及里的说话风格与破防上演】\n{persona.get('speaking_style', '')}\n\n"
        f"【层层递进的体面/隐私/禁忌爱好组】\n{hobbies_str}"
    )
    with open(f"{root}/人设.txt", "w", encoding="utf-8") as f:
        f.write(p_content)

    if image_description:
        with open(f"{root}/图片描述.txt", "w", encoding="utf-8") as f:
            f.write(image_description)

    greeting_text_lines = [str(g) for g in greeting_list]
    g_content = "【开场白】\n" + "\n".join(greeting_text_lines)
    with open(f"{root}/开场白.txt", "w", encoding="utf-8") as f:
        f.write(g_content)

    full_content = p_content + "\n\n" + g_content + "\n\n【章节剧情】\n"
    for i, ch in enumerate(story_list, 1):
        chap = f"第{i}章：{ch['标题']}\n情绪/语气：{ch['情绪']}\n剧情：{ch['剧情']}"
        with open(f"{root}/第{i}章.txt", "w", encoding="utf-8") as f:
            f.write(chap)
        full_content += chap + "\n\n"

    with open(f"{root}/【三合一完整角色档案】.txt", "w", encoding="utf-8") as f:
        f.write(full_content)

    st.session_state.saved_folder = root
    return root


def copy_from_file(filepath):
    if not os.path.exists(filepath):
        st.warning("⚠️ 请先点击「下载全部到本地TXT」")
        return
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    st.code(content, wrap_lines=True)
    st.success("✅ 内容已展开，请直接复制！")


def save_session():
    p = st.session_state.persona
    if not p.get("name"):
        st.warning("⚠️ 请先生成角色人设")
        return False
    existing_idx = None
    for i, s in enumerate(st.session_state.sessions):
        if s["name"] == p["name"]:
            existing_idx = i
            break

    img_file = st.session_state.get("current_image_file")
    new_session = {
        "name": p["name"],
        "persona": p,
        "greeting": st.session_state.greeting,
        "story_list": st.session_state.story_list,
        "user_prompt": st.session_state.get("user_prompt", ""),
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "is_image_based": bool(st.session_state.get("uploaded_image_desc", "")) or img_file is not None,
        "image_description": st.session_state.get("uploaded_image_desc", ""),
        "image_path": None
    }

    root_folder = save_all_to_files(p, st.session_state.greeting, st.session_state.story_list,
                                    st.session_state.get("uploaded_image_desc", ""), img_file)
    if img_file:
        new_session["image_path"] = f"{root_folder}/avatar.png"

    if existing_idx is not None:
        st.session_state.sessions[existing_idx] = new_session
        st.session_state.current_session_idx = existing_idx
    else:
        st.session_state.sessions.append(new_session)
        st.session_state.current_session_idx = len(st.session_state.sessions) - 1

    st.rerun()
    return True


# ====================== 流式生成人设（彻底根治截断报错版） ======================
def stream_gen_persona(user_input):
    existing_names = []
    base_dir = "角色档案"
    if os.path.exists(base_dir):
        for date_folder in os.listdir(base_dir):
            date_path = os.path.join(base_dir, date_folder)
            if os.path.isdir(date_path):
                for char_folder in os.listdir(date_path):
                    char_path = os.path.join(date_path, char_folder)
                    if os.path.isdir(char_path) and os.path.exists(os.path.join(char_path, "人设.txt")):
                        existing_names.append(char_folder)
    existing_names = list(set(existing_names))

    existing_warning = ""
    if existing_names:
        existing_warning = f"\n【禁止重复规则】以下名字已经被使用过了，绝对不能重复使用这些名字：{', '.join(existing_names[:20])}" + \
                           ("..." if len(existing_names) > 20 else "")

    name_suggestions = f"""由你自创兼具写实与故事感的名字，必须符合以下标准：
    【⚠️ 最高优先级规则 - 违反将导致生成失败 ⚠️】
    1. **绝对禁止使用以下任何字符：林、砚、沈、陆、顾、温、姜、裴、时**
    2. **如果角色描述中明确提到了名字，你必须原样使用**
    3. **绝对不能与已有角色重名：{', '.join(existing_names[:20]) if existing_names else '无'}**
    4. 【唯一性】：绝对不能与已有角色姓氏和名重复"""

    system_prompt = PERSONA_SYSTEM_PROMPT_TEMPLATE.format(
        existing_warning=existing_warning,
        name_suggestions=name_suggestions,
        user_input=user_input
    )

    # 💡【核心修复指令】：精简并强化 User 提示，使用强制性格式切分，防止模型复读系统提示词的示例结构
    messages = [
        {
            "role": "system",
            "content": "你是一个严格的JSON转换引擎。你唯一的任务是阅读用户的系统规则，并将用户的创意需求完美转换为符合语法的JSON字典格式输出，绝对不要返回任何Markdown标识符，不要对提示词中的示例进行复读。"
        },
        {
            "role": "user",
            "content": f"【系统生成基准总纲】：\n{system_prompt}\n\n【当前开始执行】：请立即根据上述总纲和用户创意输入，为我输出一份标准的扁平化 JSON 字典，确保 taglines 和 personality 是纯文本字符串而绝对不能是列表或包含中括号！"
        }
    ]

    full_text = ""
    placeholder = st.empty()

    # 1. 正常流式接收（切换为 DeepSeek 并强制限定 JSON 返回）
    stream = deepseek_client.chat.completions.create(  # 💡 改为 deepseek_client
        model=DEEPSEEK_TEXT_MODEL,  # 💡 改为 DeepSeek 模型
        messages=messages,
        stream=True,
        temperature=0.6,
        response_format={"type": "json_object"}  # 💡 开启 DeepSeek 官方 JSON Mode 约束
    )

    for chunk in stream:
        if chunk.choices[0].delta.content:
            full_text += chunk.choices[0].delta.content
            placeholder.code(full_text, wrap_lines=True)

    cleaned = full_text.strip()

    # 2. 从 Markdown 语法块中剥离 JSON 核心
    if "```" in cleaned:
        try:
            parts = cleaned.split("```")
            for part in parts:
                part_strip = part.strip()
                if part_strip.startswith("json"):
                    part_strip = part_strip[4:].strip()
                if part_strip.startswith("{") and part_strip.count("{") >= part_strip.count("}"):
                    cleaned = part_strip
                    break
        except Exception:
            pass

    # 3. 基础正则表达式清洗
    cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'//.*?$', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"(?<!\\)'", '"', cleaned)

    # 🌟 4. 高级健壮栈算法：精确识别“字符串内部中断”并进行逻辑闭合
    def fix_truncated_json(json_str):
        json_str = json_str.strip()
        if not json_str.startswith("{"):
            if "{" in json_str:
                json_str = json_str[json_str.find("{"):]
            else:
                return json_str

        stack = []
        in_string = False
        escape = False

        for char in json_str:
            if escape:
                escape = False
                continue
            if char == '\\':
                escape = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if not in_string:
                if char in ('{', '['):
                    stack.append(char)
                elif char in ('}', ']'):
                    if stack:
                        stack.pop()

        # 💡核心修复：如果退出循环时仍在字符串内部，说明模型在文字正中间断掉了
        if in_string:
            json_str += '"'  # 先强行闭合字符串的双引号

        # 根据真实容器栈反向补齐外部括号
        while stack:
            last_open = stack.pop()
            if last_open == '{':
                json_str += '}'
            elif last_open == '[':
                json_str += ']'

        return json_str

    # 执行高级括号自修补
    json_str = fix_truncated_json(cleaned)

    # 🌟 5. 绝对安全的沙盒解析防御（彻底隔离 ast / json 的抛错崩溃风险）
    parsed = None

    # 首先尝试最标准的 json 解析
    try:
        parsed = json.loads(json_str)
    except Exception:
        parsed = None

    # 如果标准 json 失败，再小心翼翼地尝试扩展解析
    if not parsed:
        try:
            import ast
            fixed = re.sub(r':\s*null\s*([,}])', r':None\1', json_str)
            fixed = re.sub(r':\s*true\s*([,}])', r':True\1', fixed)
            fixed = re.sub(r':\s*false\s*([,}])', r':False\1', fixed)
            # 使用最广泛的异常捕获，确保哪怕 ast 报出极其诡异的语法错，也不会导致前端崩溃
            parsed = ast.literal_eval(fixed)
        except BaseException:
            # 💡 强力升级：使用 BaseException 拦截一切可能存在的低级解析语法树坍塌
            parsed = None

    # 🌟 6. 终极防御沙盒：如果两套解析全部泡汤，绝不弹红窗，直接优雅降级
    if not parsed or not isinstance(parsed, dict):
        st.warning("⚠️ 大模型未完成完整 JSON 输出，系统已为您自动启动安全无损重构恢复机制！")
        parsed = {
            "name": "恢复中的角色",
            "gender": "待定",
            "taglines": "AI生成中断",
            "character_description": f"由于模型生成阶段产生突发截断，未能成功结构化解析。以下是模型截断前吐出的原始未受损文本，请参考或重新点击按钮生成：\n\n{cleaned}",
            "personality": "恢复中",
            "intro": "生成中断，请重新尝试",
            "speaking_style": "无",
            "hobbies": "无"
        }

    # 7. 数据纯净过滤规范化
    def clean_to_flat_string(value):
        if not value: return ""
        if isinstance(value, list):
            items = [str(item).strip().replace('[', '').replace(']', '').strip('"\'- ') for item in value]
            return ", ".join([i for i in items if i])
        return str(value).strip().replace('[', '').replace(']', '').strip('"\'- ')

    def clean_to_multiline_string(value):
        if not value: return ""
        lines = []
        if isinstance(value, list):
            lines = [str(item).strip() for item in value if str(item).strip()]
        elif isinstance(value, str):
            lines = [s.strip() for s in value.split('\n') if s.strip()]
        cleaned_lines = []
        for line in lines:
            line = re.sub(r'^[-*+•\s]+', '', line)
            if line: cleaned_lines.append(line)
        return "\n".join(cleaned_lines)

    data = {
        "user_prompt": st.session_state.get("user_prompt", user_input) if st.session_state.get(
            "user_prompt") else user_input,
        "name": str(parsed.get("name", "未知角色")).strip(),
        "gender": str(parsed.get("gender", "不明")).strip(),
        "taglines": clean_to_flat_string(parsed.get("taglines")),
        "character_description": clean_to_multiline_string(parsed.get("character_description")),
        "personality": clean_to_flat_string(parsed.get("personality")),
        "intro": clean_to_multiline_string(parsed.get("intro")),
        "speaking_style": clean_to_multiline_string(parsed.get("speaking_style")),
        "hobbies": clean_to_multiline_string(parsed.get("hobbies"))
    }

    st.session_state.user_prompt = data["user_prompt"]
    st.session_state.persona = data
    st.session_state.step_mode = "story"
    st.rerun()



# ====================== 原始素材上下文（供开场白/大纲/章节复用） ======================
def build_source_material_context(max_chars=6000):
    """收集生成人设时的文字、文档、图片与截图分析结果，供后续生成显式继承。"""
    parts = []
    material = str(st.session_state.get("source_material_context", "") or "").strip()

    if material:
        parts.append("【生成人设时融合的原始素材】\n" + material)
    else:
        p = st.session_state.get("persona", {}) or {}
        prompt = str(st.session_state.get("user_prompt", "") or p.get("user_prompt", "") or "").strip()
        if prompt:
            parts.append("【用户原始文字/文件融合设定】\n" + prompt)

    image_desc = str(st.session_state.get("uploaded_image_desc", "") or "").strip()
    if image_desc and image_desc not in material:
        parts.append("【上传图片与粘贴截图分析结果】\n" + image_desc)

    if not parts:
        return ""

    context = "\n\n".join(parts).strip()
    if len(context) > max_chars:
        context = context[:max_chars] + "\n...（原始素材较长，已截断；请优先继承上述核心设定）"
    return context


def build_chapter_format_context(name="角色", max_chars=4000):
    """
    读取界面中可调整的章节正文格式；为空时回退到默认格式。

    Args:
        name (str): 角色名称，用于替换模板中的 {name} 占位符。
        max_chars (int): 允许的最大字符长度，防止 Prompt 过长导致 Token 溢出。
    Returns:
        str: 格式化并截断后的提示词上下文。
    """
    # 1. 从 st.session_state 安全获取前端用户输入的提示词，若为空则用默认提示词兜底
    raw_fmt = st.session_state.get("chapter_format_prompt", "")
    fmt = str(raw_fmt or DEFAULT_CHAPTER_FORMAT_PROMPT).strip()

    # 2. 确保 name 变量安全并执行替换
    safe_name = str(name or "角色")
    fmt = fmt.replace("{name}", safe_name)

    # 3. 严格截断（修正原代码未计算省略号长度导致依然超限的 bug）
    if len(fmt) > max_chars:
        suffix = "\n...（章节正文格式提示词较长，已截断）"
        # 预留出省略号的长度，确保总长绝对不超 max_chars
        truncate_len = max(0, max_chars - len(suffix))
        fmt = fmt[:truncate_len] + suffix

    return fmt
# ====================== 生成开场白 ======================
def stream_gen_greeting(num_lines):
    if "persona" not in st.session_state or not st.session_state.persona:
        st.warning("请先生成爆款人设，才能生成开场白。")
        return

    try:
        num_lines = int(num_lines)
    except Exception:
        num_lines = 0

    if num_lines <= 0:
        st.session_state.greeting = []
        st.session_state.step_mode = "story"
        st.rerun()

    p = st.session_state.persona
    intro_context = p.get('intro', '')
    source_context = build_source_material_context()
    prompt = GREETING_PROMPT_TEMPLATE.format(
        name=p.get('name', ''),
        intro_context=intro_context,
        personality=p.get('personality', ''),
        speaking_style=p.get('speaking_style', ''),
        num_lines=num_lines
    )
    if source_context:
        prompt += "\n\n# 【开场白必须继承的原始素材上下文】\n" + source_context + "\n请确保开场白继续参考这些用户上传文件、文字描述、图片与截图信息；如果原始资料中写了开场白风格、剧情阶段起点或互动规则，优先继承原始资料；若与最新编辑后的人设字段冲突，以最新人设字段为准。"
    response = deepseek_client.chat.completions.create(  # 💡 改为 deepseek_client
        model=DEEPSEEK_TEXT_MODEL,  # 💡 改为 DeepSeek 模型
        messages=[{"role": "user", "content": prompt}],
        temperature=0.6
    )

    full_text = response.choices[0].message.content
    text = full_text.replace("。", "").replace('"', "").replace("“", "").replace("”", "")
    lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
    st.session_state.greeting = lines[:num_lines]
    st.session_state.step_mode = "story"
    st.rerun()


# ====================== 💡 核心自适应修复：强类型安全的阶段获取函数 ======================
def get_chapter_stage(chapter_idx, total_chapters, custom_stages=None):
    """
    智能自适应阶段获取器（强类型安全防御版）。
    支持用户完全自定义每个阶段的章节数，绝不引发 int 和 dict 相加的错误。
    """
    # 确保传入的 chapter_idx 是安全的整数
    try:
        c_idx = int(chapter_idx)
    except Exception:
        c_idx = 1

    try:
        t_chaps = int(total_chapters)
    except Exception:
        t_chaps = 1

    # 1. 安全获取当前使用的阶段配置
    stages_to_use = custom_stages if custom_stages else st.session_state.get("custom_stages", {})
    if not stages_to_use and "DEFAULT_STAGES" in globals():
        stages_to_use = DEFAULT_STAGES
    if not stages_to_use:
        return 1

    # 确保阶段键值是规范排序的数字
    stage_keys = []
    for k in stages_to_use.keys():
        try:
            # 过滤掉任何非数字或者意外作为 key 混入的 dict 结构
            if isinstance(k, (int, str, float)):
                stage_keys.append(int(k))
        except (ValueError, TypeError):
            continue
    stage_keys = sorted(list(set(stage_keys)))

    if not stage_keys:
        return 1

    # 2. 🌟 检查是否包含有效的用户前端自定义的章节数分配
    has_custom_distribution = False
    for k in stage_keys:
        stg_data = stages_to_use.get(k) or stages_to_use.get(str(k))
        if isinstance(stg_data, dict) and "chapters" in stg_data:
            has_custom_distribution = True
            break

    if has_custom_distribution:
        # 算法 A：基于用户指定的各阶段章节数，累加区间精确判定
        current_accumulator = 0
        for stg_num in stage_keys:
            stg_data = stages_to_use.get(stg_num) or stages_to_use.get(str(stg_num))
            allocated_chapters = 1
            if isinstance(stg_data, dict):
                try:
                    allocated_chapters = int(stg_data.get("chapters", 1))
                except Exception:
                    allocated_chapters = 1
            current_accumulator += allocated_chapters
            if c_idx <= current_accumulator:
                return stg_num
        return stage_keys[-1]
    else:
        # 算法 B：均分兜底逻辑
        num_stages = len(stage_keys)
        idx_zero_based = c_idx - 1
        chapters_per_stage = t_chaps / num_stages
        stage_pos = int(idx_zero_based // chapters_per_stage)
        if stage_pos >= num_stages:
            stage_pos = num_stages - 1
        return stage_keys[stage_pos]


# ====================== 连载大纲流式生成 ======================
def stream_gen_all_outlines(total_ch, custom_stages):
    if "persona" not in st.session_state or not st.session_state.persona:
        st.error("❌ 请先生成爆款人设！")
        return

    p = st.session_state.persona

    # 强转总章节数为整数，防止前端组件意外吐出异常对象
    try:
        total_ch_int = int(total_ch)
    except Exception:
        total_ch_int = 12

    stage_plan_str = "你必须严格按照以下章节分配和每个阶段的控制逻辑来编排剧情：\n"
    for idx in range(1, total_ch_int + 1):
        stg_num = get_chapter_stage(idx, total_ch_int, custom_stages)

        # 强类型安全地获取阶段字典数据
        stg_data = custom_stages.get(stg_num) or custom_stages.get(str(stg_num)) if isinstance(custom_stages, dict) else {}
        if not isinstance(stg_data, dict):
            stg_data = {}

        stg_name = stg_data.get("name", f"阶段{stg_num}")
        stg_desc = stg_data.get("desc", "")
        stage_plan_str += f"- 第{idx}章：必须属于【{stg_name}】。该演进阶段核心控制逻辑为：{stg_desc}\n"

    # 获取第一句开场白作为大纲开局引子，如果没有则给个兜底
    first_greeting = st.session_state.greeting[0] if st.session_state.get("greeting") else "（场景刚刚开始，角色正看着你）"

    # 💡【核心修复】：由于 prompts.py 中使用的是双花括号 {{total_ch}}，直接用 .format 会被忽略。
    # 必须先用 .replace() 将数字砸进去，再用 .format() 渲染其他字段。
    templated_prompt = OUTLINES_PROMPT_TEMPLATE.replace("{{total_ch}}", str(total_ch_int))
    source_context = build_source_material_context()
    chapter_format_context = build_chapter_format_context(p.get('name', '角色'))

    prompt = templated_prompt.format(
        name=p.get('name', '未命名'),
        character_description=p.get('character_description', ''),
        personality=p.get('personality', ''),
        taglines=p.get('taglines', ''),
        stage_plan_str=stage_plan_str,
        intro_context=p.get('intro', '暂无特定相遇场景'),  # 向大纲注入人设 intro 场景
        greeting_context=first_greeting               # 向大纲注入第一句开场白
    )
    if source_context:
        prompt += "\n\n# 【大纲必须继承的原始素材上下文】\n" + source_context + "\n请把这些用户上传文件、文字描述、图片与截图信息作为剧情题材、关系起点、视觉特征和世界观细节的参考；如果原始资料明确写了阶段安排、阶段数量、每阶段目标或章节正文格式，则优先按原始资料生成；如果原始资料没有提及这些内容，则按界面中的默认阶段配置和章节正文格式执行。若与最新编辑后的人设字段冲突，以最新人设字段为准。"
    prompt += "\n\n# 【大纲生成可参考的默认章节正文格式】\n" + chapter_format_context

    placeholder = st.empty()
    full_text = ""
    messages = [{"role": "user", "content": prompt}]

    try:
        stream = deepseek_client.chat.completions.create(  # 💡 改为 deepseek_client
            model=DEEPSEEK_TEXT_MODEL,  # 💡 改为 DeepSeek 模型
            messages=messages,
            temperature=0.6,
            stream=True,
            response_format={"type": "json_object"}  # 💡 大纲通常是 JSON 数组/对象，开启更稳定
        )


        for chunk in stream:
            if chunk.choices[0].delta.content:
                full_text += chunk.choices[0].delta.content
                placeholder.code(full_text, wrap_lines=True)

        raw_text = full_text.strip()
        if "```" in raw_text:
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.split("```")[0].strip()

        outlines = json.loads(raw_text)
        st.session_state.story_list = []
        for item in outlines:
            if isinstance(item, dict):
                st.session_state.story_list.append({
                    "章节": item.get("章节", len(st.session_state.story_list) + 1),
                    "标题": item.get("标题", "未命名章节"),
                    "情绪": "",
                    "剧情": ""
                })
        st.session_state.now_chapter = 1
        st.success("🎉 连载大纲（剧本章节名）生成成功！请在下方逐章填充。")
    except Exception as e:
        st.error(f"❌ 大纲结构化解析失败，原因：{str(e)}。已为您自动初始化空白大纲占位。")
        st.session_state.story_list = []
        for i in range(1, total_ch_int + 1):
            st.session_state.story_list.append({"章节": i, "标题": f"第{i}阶段命题发展", "情绪": "", "剧情": ""})
        st.session_state.now_chapter = 1





# ====================== 彻底修复后的单章内容生成 ======================
def stream_gen_one_chapter_optimized(ch_index, custom_stages, placeholder=None, batch_mode=False,
                                     passed_format_context=None):
    """
    单章内容生成函数 (已修复运行时变量隐患)

    Args:
        passed_format_context (str, Optional): 允许外部显式传入章节格式上下文。如果不传，内部将安全自动构建。
    """
    if placeholder is None:
        placeholder = st.empty()

    try:
        p = st.session_state.persona
        already_story = st.session_state.story_list
        current_ch_obj = already_story[ch_index]
        total_ch = len(already_story)

        # 🔒 牢牢锁定用户已经定好的原本大纲标题和章节号，拒绝让大模型篡改
        locked_title = current_ch_obj.get('标题', f'第{ch_index + 1}章')

        stage_num = get_chapter_stage(ch_index + 1, total_ch, custom_stages)
        stages_pool = custom_stages if custom_stages else st.session_state.get("custom_stages", {})
        current_stage_name = stages_pool.get(stage_num, {}).get("name", f"阶段{stage_num}")
        current_goal_desc = stages_pool.get(stage_num, {}).get("desc", "")

        # 第一章开局衔接控制
        greeting_context = ""
        if ch_index == 0:
            g_lines = "\n".join([f"开场白选段：{g}" for g in st.session_state.get("greeting", [])])
            greeting_context = "# 【核心首发衔接线（第一章特供）】\n" \
                               f"本故事第一章的正文开篇，必须完美无缝承接人设本身的相遇背景和发出的最终开场白剧情。 \n" \
                               f"1. 初始相遇戏剧性场景与羁绊关系（Intro）：\"{p.get('intro', '')}\" \n" \
                               f"2. 角色已经发出的最终开场白行为台词（Greeting）：\n{g_lines if g_lines else '（场景刚刚开始，角色正看着你）'}\n" \
                               "请从这个极其私密场景与情感博弈僵局中直接切入，立刻暴力拉高戏剧张力！\n"

        summary_of_prev = ""
        if ch_index > 0:
            summary_of_prev = "# 【前情进展链（必须严格顺承前文，杜绝套路复读）】\n"
            for i in range(ch_index):
                prev_ch = already_story[i]
                prev_content = prev_ch.get('剧情', '') if prev_ch.get('剧情') else ''
                summary_of_prev += f"第{prev_ch['章节']}章《{prev_ch['标题']}》剧情节点：{prev_content[:80]}...\n"

        hobbies_str = "\n".join(p.get('hobbies', [])) if isinstance(p.get('hobbies'), list) else str(
            p.get('hobbies', ''))
        taglines_str = ", ".join(p.get('taglines', [])) if isinstance(p.get('taglines'), list) else str(
            p.get('taglines', ''))
        personality_str = ", ".join(p.get('personality', [])) if isinstance(p.get('personality'), list) else str(
            p.get('personality', ''))

        source_context = build_source_material_context()

        # 🛡️ 【运行时变量修复点】：优先使用传入的上下文，没有则在内部安全生成兜底
        if passed_format_context is not None:
            chapter_format_context = passed_format_context
        else:
            try:
                # 即使 build_chapter_format_context 内部因 session 缺失等原因报错，也有内部 try-except 兜底
                chapter_format_context = build_chapter_format_context(p.get('name', '角色'))
            except Exception:
                # 极端情况下的最终降级文本
                chapter_format_context = "请直接输出小说章节正文。"

        prompt = CHAPTER_PROMPT_TEMPLATE.format(
            chapter_num=ch_index + 1,
            chapter_title=locked_title,  # 使用锁定的原本大纲标题发送给模型
            name=p.get('name', '未知'),
            gender=p.get('gender', '不明'),
            taglines=taglines_str,
            character_description=p.get('character_description', ''),
            personality=personality_str,
            speaking_style=p.get('speaking_style', ''),
            hobbies_str=hobbies_str,
            greeting_context=greeting_context,
            summary_of_prev=summary_of_prev,
            stage_name=current_stage_name,
            stage_desc=current_goal_desc
        )
        prompt += "\n\n# 【章节正文内容输出格式（界面可调整）】\n" + chapter_format_context + "\n请严格按此格式输出；但如果原始资料中明确指定了不同的正文内容格式，则优先采用原始资料中的格式。"
        if source_context:
            prompt += "\n\n# 【章节必须继承的原始素材上下文】\n" + source_context + "\n请在本章剧情中继续参考这些用户上传文件、文字描述、图片与截图信息；如果原始资料明确写了阶段安排、阶段数量、每阶段目标或章节正文格式，则优先按原始资料生成并在正文模块中表现出来；如果原始资料没有提及这些内容，则按界面中的默认阶段配置和章节正文格式执行。若与最新编辑后的人设字段或当前章节大纲冲突，以最新人设字段和当前章节大纲为准。"

        messages = [{"role": "user", "content": prompt}]
        full_text = ""

        stream = deepseek_client.chat.completions.create(
            model=DEEPSEEK_TEXT_MODEL,
            messages=messages,
            stream=True,
            temperature=0.6,
            frequency_penalty=0.5,
            presence_penalty=0.4
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                full_text += chunk.choices[0].delta.content
                placeholder.code(full_text, wrap_lines=True)

        # ====================== 🛡️ 究极无损·绝不留空正文清洗机制 ======================
        lines = full_text.strip().split("\n")

        # 1. 提取情绪语气（独立安全提取）
        detected_mood = "标准"
        for line in lines:
            line_strip = line.strip()
            split_char = "：" if "：" in line_strip else ":"
            if ("情绪" in line_strip or "语气" in line_strip) and split_char in line_strip:
                parts = line_strip.split(split_char, 1)
                if len(parts) > 1:
                    detected_mood = parts[1].strip().strip('[]"\'')
                break
        current_ch_obj["情绪"] = detected_mood

        # 2. 多级锚点截取
        story_content = ""
        raw_full = full_text.strip()

        # 扩大锚点扫描范围，只要包含这些字眼，一律视为正文起点
        story_markers = [
            "剧情：", "剧情:", "### 剧情", "## 剧情", "剧情正文：", "剧情正文:",
            "【剧情】", "正文：", "正文:", "【正文】"
        ]
        start_pos = -1
        for marker in story_markers:
            pos = raw_full.find(marker)
            if pos != -1:
                start_pos = pos + len(marker)
                break

        if start_pos != -1:
            story_content = raw_full[start_pos:].strip()

        # 🌟【核心保底保险】：如果切出来的正文是空的，或者根本没找到锚点
        if not story_content.strip():
            story_content = raw_full

        # 3. 剥离可能混入的头部标题复读
        story_lines_final = []
        for line in story_content.split("\n"):
            line_strip = line.strip()
            if line_strip.startswith(f"第{ch_index + 1}章") or line_strip.startswith("标题：") or line_strip.startswith(
                    "标题:"):
                continue
            story_lines_final.append(line)

        final_story_text = "\n".join(story_lines_final).strip()

        # ==================== functions.py 末尾修改 ====================
        # 💾 先确保数据完美存入状态字典
        current_ch_obj["标题"] = locked_title
        current_ch_obj["剧情"] = final_story_text

        # 1. 显式更新当前章节的数据
        st.session_state.story_list[ch_index] = current_ch_obj

        # 2. 🛡️ 【规避错误】：不要直接修改组件的 Key，而是写进一个独立的缓存 Key
        st.session_state[f"edit_ch_content_{ch_index}_cache"] = final_story_text
        # 同步写入 widget 实际渲染 key，确保 rerun 后文本框能显示新内容
        st.session_state[f"pending_content_{ch_index}"] = final_story_text
        st.session_state[f"pending_emo_{ch_index}"] = detected_mood

        # 3. 步进控制
        if ch_index + 1 >= st.session_state.get("now_chapter", 1):
            st.session_state.now_chapter = ch_index + 2

        # 清理流式临时看板（批量模式下跳过，避免触发 Streamlit 脚本重跑打断循环）
        if not batch_mode:
            placeholder.empty()
            st.rerun()

        return

    except Exception as e:
        # 🚨 核心改动：捕获所有未知异常，阻断 st.rerun()，直接打印错误到页面
        placeholder.empty()  # 清除占位看板
        st.error("❌ 章节生成函数发生底层崩溃！错误详情如下：")

        # 在前端页面渲染一个漂亮的报错代码块
        error_msg = traceback.format_exc()
        st.code(error_msg, language="python")

        # 同时在终端控制台打印一份，方便排查
        print("\n" + "=" * 50 + "\n[CRITICAL ERROR] 运行时异常爆发:\n" + error_msg + "=" * 50 + "\n")

        # 停止继续运行当前 Streamlit 脚本
        st.stop()

# ====================== 侧边栏渲染函数 ======================
def render_sidebar():
    st.sidebar.title("📚 会话列表")
    if st.sidebar.button("🔄 刷新历史会话", use_container_width=True):
        st.session_state.sessions = load_sessions_from_local()
        st.rerun()

    kw = st.sidebar.text_input("🔍 搜索角色", value=st.session_state.last_search)
    st.session_state.last_search = kw
    sessions = st.session_state.sessions
    if kw:
        sessions = [s for s in sessions if kw.lower() in s["name"].lower()]

    for i, s in enumerate(sessions):
        idx = st.session_state.sessions.index(s)
        typ = "primary" if idx == st.session_state.current_session_idx else "secondary"
        col1, col2 = st.sidebar.columns([4, 1])
        with col1:
            icon = "🖼️" if s.get("is_image_based") else "💬"
            display_name = f"{icon} {s['name']}"
            if s.get("time"):
                display_name += f"\n({s['time']})"
            if st.button(display_name, key=f"ses_{idx}", type=typ, use_container_width=True):
                st.session_state.current_session_idx = idx
                loaded_persona = s["persona"].copy()
                # 不再调用 clean_tags_to_string，直接使用原列表
                st.session_state.persona = loaded_persona
                st.session_state.greeting = s.get("greeting", [])
                st.session_state.story_list = s.get("story_list", [])
                st.session_state.source_material_context = s.get("user_prompt", "")
                st.session_state.step_mode = "story"
                st.session_state.now_chapter = len(st.session_state.story_list) + 1
                st.rerun()
        with col2:
            if st.button("❌", key=f"del_{idx}", help=f"删除 {s['name']}"):
                if st.session_state.get(f"confirm_del_{idx}", False):
                    delete_session(idx, s)
                    st.session_state[f"confirm_del_{idx}"] = False
                    st.rerun()
                else:
                    st.session_state[f"confirm_del_{idx}"] = True
                    st.warning(f"⚠️ 再次点击确认删除 {s['name']}")

    if st.session_state.persona.get("name"):
        if st.sidebar.button("💾 保存当前会话", use_container_width=True):
            if save_session():
                st.sidebar.success("✅ 会话已保存！")

    if st.sidebar.button("🗑️ 清空所有会话", use_container_width=True, type="secondary"):
        if st.session_state.get("confirm_clear_all", False):
            import shutil
            base_dir = "角色档案"
            if os.path.exists(base_dir):
                shutil.rmtree(base_dir)
                st.sidebar.success("✅ 已删除所有本地文件")
            st.session_state.sessions = []
            st.session_state.current_session_idx = None
            st.session_state.step_mode = "input"
            st.session_state.persona = {}
            st.session_state.greeting = []
            st.session_state.story_list = []
            st.session_state.user_prompt = ""
            st.session_state.source_material_context = ""
            st.session_state.chapter_format_prompt = DEFAULT_CHAPTER_FORMAT_PROMPT
            st.session_state.now_chapter = 1
            st.session_state.saved_folder = None
            st.session_state.uploaded_image_desc = ""
            st.session_state.confirm_clear_all = False
            st.rerun()
        else:
            st.session_state.confirm_clear_all = True
            st.sidebar.warning("⚠️ 再次点击确认清空所有会话")

def delete_session(session_idx, session_data):
    st.session_state.sessions.pop(session_idx)
    if st.session_state.current_session_idx == session_idx:
        st.session_state.current_session_idx = None
        st.session_state.step_mode = "input"
        st.session_state.persona = {}
        st.session_state.greeting = []
        st.session_state.story_list = []
        st.session_state.user_prompt = ""
        st.session_state.source_material_context = ""
        st.session_state.chapter_format_prompt = DEFAULT_CHAPTER_FORMAT_PROMPT
        st.session_state.now_chapter = 1
        st.session_state.saved_folder = None
        st.session_state.uploaded_image_desc = ""

# ==================== 追加到 functions.py 末尾 ====================

def extract_text_from_file(uploaded_file):
    """解析上传的 TXT, PDF, Word 文件内容"""
    file_ext = os.path.splitext(uploaded_file.name)[1].lower()
    text_content = ""
    try:
        if file_ext in [".txt", ".md", ".json", ".csv"]:
            text_content = uploaded_file.read().decode("utf-8", errors="ignore")
        elif file_ext == ".pdf":
            import pypdf
            reader = pypdf.PdfReader(uploaded_file)
            text_content = "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
        elif file_ext in [".doc", ".docx"]:
            import docx
            doc = docx.Document(uploaded_file)
            text_content = "\n".join([para.text for para in doc.paragraphs])
    except Exception as e:
        # 注意：因为移到了 functions.py，去除了 st.error，改用 raise 抛出或返回空，由主程序捕获
        raise RuntimeError(f"解析文件 {uploaded_file.name} 失败: {str(e)}")
    return text_content


def try_repair_and_load_json(raw_text):
    """辅助函数：尝试修复由于突发截断导致的非法 JSON 字符串，并尽可能提取已生成的字段"""
    raw_text = raw_text.strip()
    if not raw_text:
        return {}

    # 尝试寻找首个 '{'
    start_idx = raw_text.find('{')
    if start_idx == -1:
        return {}

    # 截取从第一个 '{' 开始的内容
    json_part = raw_text[start_idx:]

    # 尝试直接解析
    try:
        return json.loads(json_part)
    except json.JSONDecodeError:
        pass

    # 如果解析失败，说明发生了截断。开始尝试进行右侧闭合修复
    json_part = json_part.rstrip()

    # 循环尝试丢弃末尾字符直至可以补全括号成功解析
    for i in range(len(json_part), 0, -1):
        test_str = json_part[:i].strip()
        for suffix in ["", "\"", "\"]", "\"}", "}", "]}", "\"\n}"]:
            try:
                candidate = test_str + suffix
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

    # 如果极端情况逆向修补依然失败，采用正则表达式进行最后的“保底字段碎片抢救”
    extracted = {}
    fields = ["name", "gender", "taglines", "character_description", "personality", "intro", "speaking_style", "hobbies"]
    for field in fields:
        pattern = rf'"{field}"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"'
        match = re.search(pattern, json_part)
        if match:
            extracted[field] = match.group(1)
        else:
            list_pattern = rf'"{field}"\s*:\s*\[(.*?)\]'
            list_match = re.search(list_pattern, json_part, re.DOTALL)
            if list_match:
                items = re.findall(r'"([^"]*)"', list_match.group(1))
                if items:
                    extracted[field] = items
    return extracted




