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
        "desc": "角色展现其最正统、最招牌、符合世俗体面的表层性格与社会风格（如完美人妻的温柔体贴、职场上司的专业干练、禁欲精英的斯文得体等）。本章核心目标：通过日常互动将这种表层人设推向极致，并在本章结尾或核心节点，让‘隐秘弱点/羞耻秘密’被撞破，完成权力倒置，强行锁定密闭私密场景与隐秘共犯关系！"
    },
    2: {
        "name": "阶段2：犹豫试探·表层防线失守期",
        "desc": "秘密被撞破后，底层欲望与隐秘心思开始暴露，表层体面防线逐步松动。女设肢体局促、目光闪躲、极力掩饰；男设开启暗处撩拨，眼神锁定，释放暧昧指令。在密闭空间中形成极致的心理博弈。"
    },
    3: {
        "name": "阶段3：尴尬羞耻·理智崩坏冲突期",
        "desc": "表层体面彻底崩塌，理智与欲望形成强烈的生死拉扯。女设泛红害羞、放下身份威严，主动示弱妥协并默许亲密触碰；男设欲擒故纵、强势施压，通过轻微惩罚或霸道侵略打破最后一层社交边界。必须有具体的肢体拉扯与微表情崩坏。"
    },
    4: {
        "name": "阶段4：破防顺从·深层情感终极沉沦期",
        "desc": "情绪与张力抵达峰值，完成从抗拒到依恋的彻底蜕变。女设褪去所有表层伪装，流露无助、委屈与极度依赖，在羞耻与愧疚中彻底沉沦；男设卸下斯文皮囊，展露偏执病娇与不为人知的脆弱，释放专属一人的极致占有。"
    }
}

# 💡 核心修复 1：定义 DEFAULT_STAGES 供 app.py 导入初始化（使用深拷贝防止引用污染）
DEFAULT_STAGES = {k: v.copy() for k, v in STAGE_DETAILS.items()}

# 初始化 OpenAI 客户端（依赖环境变量 DASHSCOPE_API_KEY）
api_key = os.getenv("DASHSCOPE_API_KEY")
if not api_key:
    st.error("❌ 请配置 DASHSCOPE_API_KEY 环境变量")
    st.stop()
client = OpenAI(
    api_key=api_key,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)


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
            response = client.chat.completions.create(
                model="qwen-vl-plus",
                messages=messages,
                temperature=0.8
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
        response = client.chat.completions.create(
            model="qwen-plus-character",
            messages=[{"role": "user", "content": combined}],
            temperature=0.8
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

    # 1. 正常流式接收
    stream = client.chat.completions.create(model="qwen-plus", messages=messages, stream=True,
                                            temperature=0.85)
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
    st.session_state.step_mode = "greeting"
    st.rerun()


# ====================== 生成开场白 ======================
def stream_gen_greeting(num_lines):
    p = st.session_state.persona
    intro_context = p.get('intro', '')
    prompt = GREETING_PROMPT_TEMPLATE.format(
        name=p.get('name', ''),
        intro_context=intro_context,
        personality=p.get('personality', ''),
        speaking_style=p.get('speaking_style', ''),
        num_lines=num_lines
    )
    response = client.chat.completions.create(model="qwen-plus-character",
                                              messages=[{"role": "user", "content": prompt}],
                                              temperature=0.9)
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
        stg_data = custom_stages.get(stg_num) or custom_stages.get(str(stg_num)) if isinstance(custom_stages,
                                                                                               dict) else {}
        if not isinstance(stg_data, dict):
            stg_data = {}

        stg_name = stg_data.get("name", f"阶段{stg_num}")
        stg_desc = stg_data.get("desc", "")
        stage_plan_str += f"- 第{idx}章：必须属于【{stg_name}】。该演进阶段核心控制逻辑为：{stg_desc}\n"

    # 💡【修改点 1】：获取第一句开场白作为大纲开局引子，如果没有则给个兜底
    first_greeting = st.session_state.greeting[0] if st.session_state.get("greeting") else "（场景刚刚开始，角色正看着你）"

    prompt = OUTLINES_PROMPT_TEMPLATE.format(
        name=p.get('name', '未命名'),
        character_description=p.get('character_description', ''),
        personality=p.get('personality', ''),
        taglines=p.get('taglines', ''),
        stage_plan_str=stage_plan_str,
        total_ch=total_ch_int,
        intro_context=p.get('intro', '暂无特定相遇场景'),  # 💡 新增：向大纲注入人设 intro 场景
        greeting_context=first_greeting               # 💡 新增：向大纲注入第一句开场白
    )

    placeholder = st.empty()
    full_text = ""
    messages = [{"role": "user", "content": prompt}]

    try:
        stream = client.chat.completions.create(
            model="qwen-plus",
            messages=messages,
            temperature=0.7,
            stream=True
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


# ====================== 单章内容生成 ======================
def stream_gen_one_chapter_optimized(ch_index, custom_stages):
    p = st.session_state.persona
    already_story = st.session_state.story_list
    current_ch_obj = already_story[ch_index]
    total_ch = len(already_story)

    stage_num = get_chapter_stage(ch_index + 1, total_ch, custom_stages)

    stages_pool = custom_stages if custom_stages else st.session_state.get("custom_stages", {})
    current_stage_name = stages_pool.get(stage_num, {}).get("name", f"阶段{stage_num}")
    current_goal_desc = stages_pool.get(stage_num, {}).get("desc", "")

    # 💡【修改点 2】：重构第一章开局衔接控制，强力融入 intro 和所有生成的开场白
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
            summary_of_prev += f"第{prev_ch['章节']}章《{prev_ch['标题']}》剧情节点：{prev_ch.get('剧情', '')[:80]}...\n"

    hobbies_str = "\n".join(p.get('hobbies', [])) if isinstance(p.get('hobbies'), list) else str(p.get('hobbies', ''))

    p_taglines = p.get('taglines', [])
    taglines_str = ", ".join(p_taglines) if isinstance(p_taglines, list) else str(p_taglines)

    p_personality = p.get('personality', [])
    personality_str = ", ".join(p_personality) if isinstance(p_personality, list) else str(p_personality)

    prompt = CHAPTER_PROMPT_TEMPLATE.format(
        chapter_num=ch_index + 1,
        chapter_title=current_ch_obj['标题'],
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

    messages = [{"role": "user", "content": prompt}]
    full_text = ""
    placeholder = st.empty()

    stream = client.chat.completions.create(
        model="qwen-plus-character",
        messages=messages,
        stream=True,
        temperature=0.9,
        frequency_penalty=0.5,
        presence_penalty=0.4
    )
    for chunk in stream:
        if chunk.choices[0].delta.content:
            full_text += chunk.choices[0].delta.content
            placeholder.code(full_text, wrap_lines=True)

    lines = full_text.strip().split("\n")
    story_lines = []
    current_field = None
    for line in lines:
        line_strip = line.strip()
        if not line_strip:
            if current_field == "story":
                story_lines.append("")
            continue
        split_char = "：" if "：" in line_strip else ":"
        if ("情绪" in line_strip or "语气" in line_strip) and split_char in line_strip and not current_field == "story":
            parts = line_strip.split(split_char, 1)
            if len(parts) > 1:
                current_ch_obj["情绪"] = parts[1].strip().strip('[]"\'')
            current_field = "mood"
            continue
        elif "剧情" in line_strip and split_char in line_strip:
            current_field = "story"
            parts = line_strip.split(split_char, 1)
            content_part = parts[1].strip() if len(parts) > 1 else ""
            if content_part:
                story_lines.append(content_part)
            continue
        if current_field == "story":
            story_lines.append(line_strip)

    current_ch_obj["剧情"] = "\n".join(story_lines).strip()
    st.session_state.story_list[ch_index] = current_ch_obj
    st.session_state.now_chapter = ch_index + 2
    st.rerun()
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
                if st.session_state.story_list:
                    st.session_state.step_mode = "story"
                else:
                    st.session_state.step_mode = "greeting"
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
        st.session_state.now_chapter = 1
        st.session_state.saved_folder = None
        st.session_state.uploaded_image_desc = ""