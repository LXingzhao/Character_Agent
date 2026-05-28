# app.py
import streamlit as st
from functions import (
    analyze_image_from_file,
    combine_text_and_image,
    stream_gen_persona,
    stream_gen_greeting,
    stream_gen_all_outlines,
    stream_gen_one_chapter_optimized,
    render_sidebar,
    copy_from_file,
    STAGE_DETAILS,
    get_chapter_stage,
)
from PIL import Image

# ====================== 页面配置 ======================
st.set_page_config(page_title="角色生成器", layout="wide")
hide_style = ""
st.markdown(hide_style, unsafe_allow_html=True)

# ====================== 状态初始化 ======================
if "sessions" not in st.session_state:
    from functions import load_sessions_from_local

    st.session_state.sessions = load_sessions_from_local()
if "current_session_idx" not in st.session_state:
    st.session_state.current_session_idx = None
if "step_mode" not in st.session_state:
    st.session_state.step_mode = "input"
if "persona" not in st.session_state:
    st.session_state.persona = {}
if "greeting" not in st.session_state:
    st.session_state.greeting = []
if "story_list" not in st.session_state:
    st.session_state.story_list = []
if "now_chapter" not in st.session_state:
    st.session_state.now_chapter = 1
if "user_prompt" not in st.session_state:
    st.session_state.user_prompt = ""
if "last_search" not in st.session_state:
    st.session_state.last_search = ""
if "saved_folder" not in st.session_state:
    st.session_state.saved_folder = None
if "uploaded_image_desc" not in st.session_state:
    st.session_state.uploaded_image_desc = ""
if "current_image" not in st.session_state:
    st.session_state.current_image = None
if "current_image_file" not in st.session_state:
    st.session_state.current_image_file = None
# 找到状态初始化群落，在最底下追加一行：
if "custom_stages" not in st.session_state:
    # 💡 完美修复：直接使用最顶端已经成功导入的 STAGE_DETAILS 进行深度拷贝，彻底丢弃讨厌的 DEFAULT_STAGES
    st.session_state.custom_stages = {k: v.copy() for k, v in STAGE_DETAILS.items()}

# ====================== 侧边栏 ======================
render_sidebar()

# ====================== 主界面 ======================
st.title("🤖 角色生成器")

if st.session_state.step_mode == "input":
    st.info("💡 提示：你可以选择以下任意一种方式来生成角色人设")

    tab_text, tab_image, tab_combine = st.tabs(["📝 仅文字描述", "🖼️ 仅图片分析", "🔗 文字+图片融合"])

    with tab_text:
        st.markdown("### 输入文字描述")
        user_prompt = st.text_area(
            "角色设定：",
            value=st.session_state.user_prompt,
            height=200,
            key="text_input",
            placeholder="例如：一个冷酷的女杀手，平时伪装成花店老板娘，外表温柔内心却藏着致命的秘密..."
        )
        if user_prompt:
            st.session_state.user_prompt = user_prompt

        if st.button("✅ 生成角色人设", use_container_width=True, type="primary"):
            if not user_prompt.strip():
                st.warning("请先输入角色设定")
            else:
                st.session_state.uploaded_image_desc = ""
                stream_gen_persona(user_prompt)

    with tab_image:
        st.markdown("### 上传图片并分析")
        uploaded_file = st.file_uploader(
            "选择图片文件",
            type=['png', 'jpg', 'jpeg', 'webp'],
            key="image_upload",
            help="支持 PNG、JPG、JPEG、WEBP 格式"
        )
        if uploaded_file is not None:
            image = Image.open(uploaded_file)
            display_width = min(400, image.width)
            st.image(image, caption="上传的图片", width=display_width)

            if st.button("✅ 分析图片并生成角色", use_container_width=True, type="primary"):
                with st.spinner("正在分析图片..."):
                    description, img = analyze_image_from_file(uploaded_file)
                    if description:
                        st.session_state.uploaded_image_desc = description
                        st.session_state.current_image_file = uploaded_file
                        st.session_state.user_prompt = f"【图片分析设定】\n{description}"
                        st.success("✅ 图片分析完成！正在生成角色人设...")
                        stream_gen_persona(description)

            if st.session_state.uploaded_image_desc:
                st.divider()
                st.markdown("### 📋 图片分析结果")
                with st.expander("查看详细分析", expanded=False):
                    st.text(st.session_state.uploaded_image_desc)

    with tab_combine:
        st.markdown("### 文字描述 + 图片分析 融合生成")
        st.info("💡 此模式将结合你的文字描述和上传的图片，生成更完整的角色设定")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### 📝 文字描述")
            combine_text = st.text_area(
                "角色设定：",
                height=200,
                key="combine_text_input",
                placeholder="例如：她是一个表面温柔内心腹黑的千金大小姐..."
            )
        with col2:
            st.markdown("#### 🖼️ 上传图片")
            combine_image = st.file_uploader(
                "选择图片文件",
                type=['png', 'jpg', 'jpeg', 'webp'],
                key="combine_image_upload",
                help="上传角色参考图片"
            )
            if combine_image is not None:
                img = Image.open(combine_image)
                display_width = min(300, img.width)
                st.image(img, caption="参考图片", width=display_width)

        if st.button("🔗 融合文字和图片生成角色", use_container_width=True, type="primary"):
            if not combine_text.strip():
                st.warning("请先输入文字描述")
            elif combine_image is None:
                st.warning("请先上传图片")
            else:
                with st.spinner("正在分析图片并融合文字..."):
                    description, img = analyze_image_from_file(combine_image)
                    if description:
                        combined_desc = combine_text_and_image(combine_text, description)
                        st.session_state.uploaded_image_desc = description
                        st.session_state.user_prompt = f"【用户输入描述】:\n{combine_text}\n\n【AI提取图片特征】:\n{description}"
                        st.success("✅ 融合完成！正在生成角色人设...")
                        stream_gen_persona(combined_desc)

elif st.session_state.step_mode == "greeting":
    p = st.session_state.persona

    st.subheader("🎭 开场白生成")
    col1, col2 = st.columns([3, 1])
    with col1:
        num_lines = st.number_input("生成几句开场白？", 1, 5, 2, key="greeting_num_input")
    with col2:
        if st.button("✨ 生成开场白", use_container_width=True, type="primary"):
            stream_gen_greeting(num_lines)

    if st.session_state.greeting:
        with st.expander("📖 已生成的开场白", expanded=True):
            for i, line in enumerate(st.session_state.greeting, 1):
                st.markdown(f"**第{i}句**")
                st.code(line, wrap_lines=True)
                if i < len(st.session_state.greeting):
                    st.divider()

    st.divider()

    # 用户原始设定（放在最前面）
    st.subheader("📝 用户原始设定")
    display_user_prompt = st.session_state.user_prompt if st.session_state.user_prompt else p.get("user_prompt", "")
    st.code(display_user_prompt, wrap_lines=True)

    st.subheader("📋 角色人设详情")

    if st.session_state.get("current_image_file"):
        try:
            img_show = Image.open(st.session_state.current_image_file)
            st.image(img_show, caption="当前角色参考图", width=250)
        except Exception:
            pass

    if st.session_state.get("uploaded_image_desc"):
        with st.expander("📝 查看图片提取的原始描述", expanded=False):
            st.text(st.session_state.uploaded_image_desc)


    # 辅助函数：安全显示字段内容
    def safe_display(value, default="暂无数据"):
        if not value or (isinstance(value, str) and not value.strip()):
            return default
        if isinstance(value, list):
            return "\n".join([f"- {v}" for v in value if v])
        return str(value).strip()


    # 按照指定顺序和标题显示各个字段
    st.subheader("名字")
    st.code(safe_display(p.get("name")), wrap_lines=True)

    st.subheader("性别")
    st.code(safe_display(p.get("gender")), wrap_lines=True)

    st.subheader("标签")
    tag_val = p.get("taglines", [])
    display_tags = ", ".join(tag_val) if isinstance(tag_val, list) else safe_display(tag_val)
    st.code(display_tags, wrap_lines=True)

    st.subheader("背景设定")
    st.code(safe_display(p.get("character_description")), wrap_lines=True)

    st.subheader("介绍")
    st.code(safe_display(p.get("intro")), wrap_lines=True)

    st.subheader("性格")
    pers_val = p.get("personality", [])
    display_pers = ", ".join(pers_val) if isinstance(pers_val, list) else safe_display(pers_val)
    st.code(display_pers, wrap_lines=True)

    st.subheader("说话风格和习惯")
    st.code(safe_display(p.get("speaking_style")), wrap_lines=True)

    st.subheader("兴趣爱好")
    hob_val = p.get("hobbies", [])
    display_hobbies = "\n".join(hob_val) if isinstance(hob_val, list) else safe_display(hob_val)
    st.code(display_hobbies, wrap_lines=True)

    if st.session_state.saved_folder:
        st.divider()
        if st.button("📋 一键复制整个人设", use_container_width=True):
            copy_from_file(f"{st.session_state.saved_folder}/人设.txt")

    st.divider()

elif st.session_state.step_mode == "story":
    p = st.session_state.persona

    st.success(f"✅ 当前角色：{p.get('name', '')} | 剧本库共有 {len(st.session_state.story_list)} 章")
    if st.session_state.uploaded_image_desc:
        st.info("📸 **本角色基于图片分析生成**")

    tab1, tab2, tab3 = st.tabs(["人设信息", "开场白", "章节剧情"])

    with tab1:
        # 用户原始设定放在最前面
        st.subheader("📝 用户原始设定")
        st.code(str(st.session_state.user_prompt), wrap_lines=True)

        if st.session_state.saved_folder:
            if st.button("📋 一键复制整个人设", use_container_width=True):
                copy_from_file(f"{st.session_state.saved_folder}/人设.txt")


        # 辅助函数
        def safe_display_story(value, default="暂无数据"):
            if not value or (isinstance(value, str) and not value.strip()):
                return default
            if isinstance(value, list):
                return "\n".join([f"- {v}" for v in value if v])
            return str(value).strip()


        st.subheader("名字")
        st.code(safe_display_story(p.get("name")), wrap_lines=True)

        st.subheader("性别")
        st.code(safe_display_story(p.get("gender")), wrap_lines=True)

        st.subheader("标签")
        tag_val = p.get("taglines", [])
        display_tags_story = ", ".join(tag_val) if isinstance(tag_val, list) else safe_display_story(tag_val)
        st.code(display_tags_story, wrap_lines=True)

        st.subheader("背景设定")
        st.code(safe_display_story(p.get("character_description")), wrap_lines=True)

        st.subheader("介绍")
        st.code(safe_display_story(p.get("intro")), wrap_lines=True)

        st.subheader("性格")
        pers_val = p.get("personality", [])
        display_pers_story = ", ".join(pers_val) if isinstance(pers_val, list) else safe_display_story(pers_val)
        st.code(display_pers_story, wrap_lines=True)

        st.subheader("说话风格和习惯")
        st.code(safe_display_story(p.get("speaking_style")), wrap_lines=True)

        st.subheader("兴趣爱好")
        hob_val = p.get("hobbies", [])
        display_hobbies_story = "\n".join(hob_val) if isinstance(hob_val, list) else safe_display_story(hob_val)
        st.code(display_hobbies_story, wrap_lines=True)

    with tab2:
        if not st.session_state.greeting:
            st.info("未生成开场白")
            c1, c2 = st.columns([3, 1])
            with c1:
                n = st.number_input("生成几句开场白？", 1, 5, 2, key="g2")
            with c2:
                if st.button("✨ 生成开场白", use_container_width=True):
                    stream_gen_greeting(n)
        else:
            for i, line in enumerate(st.session_state.greeting, 1):
                st.markdown(f"**第{i}句**")
                st.code(line, wrap_lines=True)
                st.divider()

    with tab3:
        st.write("### 🎬 爆款剧情多阶段配置面板")

        # 💡 这里改造成动态自定义阶段的可视化面板，支持前端界面直接增删改阶段与文本
        stage_keys = sorted(list(st.session_state.custom_stages.keys()))

        with st.expander("⚙️ 展开/折叠：自定义剧情阶段与演进提示词说明", expanded=True):
            for k in stage_keys:
                st.markdown(f"#### ❖ 剧情演进阶段 {k}")
                # 修改阶段名称
                st.session_state.custom_stages[k]["name"] = st.text_input(
                    f"阶段 {k} 名称：",
                    value=st.session_state.custom_stages[k]["name"],
                    key=f"stage_name_input_{k}"
                )
                # 修改阶段控制内容
                st.session_state.custom_stages[k]["desc"] = st.text_area(
                    f"阶段 {k} 核心控制逻辑提示词：",
                    value=st.session_state.custom_stages[k]["desc"],
                    height=80,
                    key=f"stage_desc_input_{k}"
                )

                # 💡 新增：让用户可以手动分配这个阶段包含几章
                # 默认值优先读取已有配置，没有的话默认给 3 章
                st.session_state.custom_stages[k]["chapters"] = st.number_input(
                    f"该阶段包含的章节数：",
                    min_value=1,
                    max_value=100,
                    value=int(st.session_state.custom_stages[k].get("chapters", 3)),
                    key=f"stage_chapters_input_{k}"
                )

                # 允许在阶段多于1个时执行删除
                if len(stage_keys) > 1:
                    if st.button(f"🗑️ 删除阶段 {k}", key=f"del_stage_btn_{k}"):
                        st.session_state.custom_stages.pop(k)
                        st.rerun()
                st.write("")

            if st.button("➕ 添加全新剧情演进阶段"):
                next_key = max(stage_keys) + 1 if stage_keys else 1
                st.session_state.custom_stages[next_key] = {
                    "name": f"阶段{next_key}：自定义新阶段标签说明",
                    "desc": "请输入该发展进程阶段中大纲应当遵从的核心拉扯与演进目标控制细节逻辑..."
                }
                st.rerun()

                # 💡 自动根据上面每个阶段配置的章节数计算出总和
        auto_total_chapters = sum(int(st.session_state.custom_stages[k].get("chapters", 3)) for k in stage_keys)

        total_chapters_input = st.number_input("1. 请确认要规划生成的总章节数（已根据上方阶段自动求和）：",
                                               min_value=1, max_value=100,
                                               value=auto_total_chapters)

        # 💡 重设生成逻辑调用：直接把前端组装配置字典 st.session_state.custom_stages 发送给大纲生成函数
        if st.button("✨ 根据上方配置，重新重置并生成连载大纲（章节名）", use_container_width=True, type="secondary"):
            stream_gen_all_outlines(total_chapters_input, st.session_state.custom_stages)

        st.divider()
        # ====================== 修复后的剧本章节详细内容库 ======================
        if st.session_state.story_list:
            st.write("### 📖 剧本章节详细内容库")
            for idx, ch in enumerate(st.session_state.story_list):
                # 🛡️ 核心安全修复：确保 ch 必须是字典，防止数据污染导致的崩溃
                if not isinstance(ch, dict):
                    continue

                # 💡 单章计算时无缝支持界面最新的自定义阶段结构
                curr_stg = get_chapter_stage(idx + 1, len(st.session_state.story_list), st.session_state.custom_stages)

                # 安全读取当前章节关联的阶段属性
                if curr_stg in st.session_state.custom_stages:
                    display_stg_name = st.session_state.custom_stages[curr_stg]['name']
                else:
                    display_stg_name = f"未定义的自定义阶段 {curr_stg}"

                # 🛡️ 安全防御：如果 ch['章节'] 意外不是数字，用 idx + 1 兜底，防止 int + dict 报错
                try:
                    display_ch_num = int(ch.get('章节', idx + 1))
                except Exception:
                    display_ch_num = idx + 1

                st.markdown(f"#### ❖ 第{display_ch_num}章 章节名称：")
                st.code(ch.get('标题', ''), language="text", wrap_lines=True)
                st.caption(f"🎯 归属进程：{display_stg_name}")

                if ch.get('剧情'):
                    with st.expander("查看本章已生成的内容", expanded=True):
                        st.markdown("**🎭 情绪/语气：**")
                        st.code(ch.get('情绪', '无'), language="text", wrap_lines=True)
                        st.markdown("**📝 正文内容：**")
                        st.code(ch.get('剧情', ''), language="text", wrap_lines=True)
                else:
                    st.info("💡 本章尚未填充具体小说正文。")

                if idx + 1 == st.session_state.now_chapter:
                    if st.button(f"🚀 开始流式填充第{idx + 1}章：《{ch.get('标题')}》具体内容", key=f"gen_btn_{idx}",
                                 use_container_width=True, type="primary"):
                        stream_gen_one_chapter_optimized(idx, st.session_state.custom_stages)
                elif idx + 1 > st.session_state.now_chapter:
                    st.button(f"🔒 锁定（请先生成前面章节）", key=f"disabled_btn_{idx}", disabled=True,
                              use_container_width=True)
                else:
                    if st.button(f"🔄 重新覆盖生成第{idx + 1}章内容", key=f"regen_btn_{idx}", use_container_width=True):
                        stream_gen_one_chapter_optimized(idx, st.session_state.custom_stages)
                st.markdown("---")
        else:
            st.info("💡 暂无大纲，请先在上方设定总章节并点击按钮『重新重置并生成连载大纲（章节名）』。")

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        if st.button("📥 下载全部到本地TXT", use_container_width=True):
            from functions import save_all_to_files

            img_file = st.session_state.get("current_image_file")
            folder = save_all_to_files(p, st.session_state.greeting, st.session_state.story_list,
                                       st.session_state.uploaded_image_desc, img_file)
            st.success(f"✅ 已保存到：{folder}")
    with c2:
        if st.button("🔄 新建角色", use_container_width=True):
            st.session_state.step_mode = "input"
            st.session_state.persona = {}
            st.session_state.greeting = []
            st.session_state.story_list = []
            st.session_state.user_prompt = ""
            st.session_state.now_chapter = 1
            st.session_state.saved_folder = None
            st.session_state.uploaded_image_desc = ""
            st.rerun()