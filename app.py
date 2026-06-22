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
    STAGE_DETAILS,  # 注意：若原文件为 STAGE_DETAILS 请保持原样，下方已适配
    DEFAULT_CHAPTER_FORMAT_PROMPT,
    get_chapter_stage,
    extract_text_from_file,  # 从 functions 导入
    try_repair_and_load_json  # 从 functions 导入
)
from PIL import Image
import os
import io  # 用于将剪贴板图片转换为 file 流，完美适配原有的解析函数
import hashlib  # 用于对粘贴的截图进行唯一性校验（去重）
import openai  # 用于精准捕获底层 API 的合规性审查异常
import re  # 用于精准提取或修补截断的文本名字



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
if "source_material_context" not in st.session_state:
    st.session_state.source_material_context = ""
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

# 【新增保留机制】用于在后续页面展示的全量图片资产库列表（包含文件图片与粘贴截图）
if "all_saved_images" not in st.session_state:
    st.session_state.all_saved_images = []

if "custom_stages" not in st.session_state:
    st.session_state.custom_stages = {k: v.copy() for k, v in STAGE_DETAILS.items()}
if "chapter_format_prompt" not in st.session_state:
    st.session_state.chapter_format_prompt = DEFAULT_CHAPTER_FORMAT_PROMPT

# 用于多张粘贴截图的持久化存储列表
if "pasted_screenshots" not in st.session_state:
    st.session_state.pasted_screenshots = []


# ====================== 核心优化：动态逆向同步函数 ======================
def sync_persona_to_global_prompt():
    """将当前被修改后的最新人设字典转化为强约束文本，覆盖到全局提示词中，确保后续大纲与剧情严格继承修改"""
    p = st.session_state.persona
    if not p:
        return
    build_prompt = []
    build_prompt.append(f"【最新调整-核心姓名】: {p.get('name', '')}")
    build_prompt.append(f"【最新调整-核心性别】: {p.get('gender', '')}")
    build_prompt.append(f"【最新调整-背景设定】:\n{p.get('character_description', '')}")
    build_prompt.append(f"【最新调整-性格特征】: {p.get('personality', '')}")
    build_prompt.append(f"【最新调整-说话风格】: {p.get('speaking_style', '')}")
    build_prompt.append(f"【最新调整-核心介绍】:\n{p.get('intro', '')}")
    if st.session_state.uploaded_image_desc:
        build_prompt.append(f"【原图特征参考】:\n{st.session_state.uploaded_image_desc}")

    st.session_state.user_prompt = "\n\n".join(build_prompt)


# ====================== 侧边栏 ======================
render_sidebar()

# ====================== 主界面 ======================
st.title("🤖 角色生成器")

if st.session_state.step_mode == "greeting" and st.session_state.get("persona"):
    st.session_state.step_mode = "story"
    st.rerun()

if st.session_state.step_mode == "input":
    st.info(
        "💡 提示：你可以直接输入指定的姓名与性别，并上传多张参考图片、参考文档（TXT/PDF/Word），最后通过专门的“粘贴区”直接粘贴多张截图来生成角色。")

    preview_tab1, preview_tab2, preview_tab3 = st.tabs(["人设信息", "开场白", "章节剧情"])
    with preview_tab1:
        st.info("请先在下方生成人设。生成完成后，这里会显示可编辑的人设信息。")
    with preview_tab2:
        st.info("开场白分页已开放。请先生成人设，之后可生成或选择 0 句开场白。")
        pending_greeting_count = st.number_input("生成几句开场白？", 0, 5, 0, key="pending_greeting_num_input")
        if st.button("✨ 生成开场白", width='stretch', key="pending_greeting_btn"):
            st.warning("请先生成爆款人设，才能生成开场白。")
    with preview_tab3:
        st.info("章节剧情分页已开放。请先生成人设，之后可不生成开场白，直接生成连载大纲与章节剧情。")
        if st.button("✨ 根据上方配置，重新重置并生成连载大纲（章节名）", width='stretch', key="pending_outline_btn"):
            st.warning("请先生成爆款人设，才能生成章节剧情。")

    st.divider()
    # 角色基础约束
    st.markdown("### 👤 角色基础约束（选填）")
    col_name, col_gender = st.columns([1, 1])
    with col_name:
        input_explicit_name = st.text_input(
            "📛 角色姓名：",
            placeholder="例如：宋知秋（若填写则严格锁定以此名字生成）",
            key="explicit_name_input"
        ).strip()
    with col_gender:
        input_explicit_gender = st.selectbox(
            "🚻 角色性别：",
            options=["男", "女", "其他"],
            index=1,  # 默认选中“女”
            key="explicit_gender_input"
        )
    st.divider()

    # 1. 素材统一接收区
    st.markdown("### 📎 角色参考素材上传（可多选图片、文档）")
    col_upload, col_preview = st.columns([1, 1])

    with col_upload:
        uploaded_files = st.file_uploader(
            "选择或拖拽文件（支持图片、txt、pdf、docx、md、json 等）",
            type=['png', 'jpg', 'jpeg', 'webp', 'txt', 'pdf', 'doc', 'docx', 'md', 'json', 'csv', 'PNG', 'JPG', 'JPEG',
                  'WEBP'],
            accept_multiple_files=True,
            key="mixed_files_uploader",
            help="支持同时选择并上传多张图片和多个背景文档"
        )

    img_files = []
    doc_files = []
    if uploaded_files:
        for f in uploaded_files:
            ext = os.path.splitext(f.name)[1].lower()
            if ext in ['.png', '.jpg', '.jpeg', '.webp']:
                img_files.append(f)
            elif ext in ['.txt', '.pdf', '.doc', '.docx', '.md', '.json', '.csv']:
                doc_files.append(f)

    with col_preview:
        if img_files:
            st.markdown(f"📸 **已检测到 {len(img_files)} 张图片：**")
            cols = st.columns(min(4, len(img_files)))
            for idx, img_f in enumerate(img_files):
                with cols[idx % 4]:
                    st.image(Image.open(img_f), width=180)
        if doc_files:
            st.markdown(f"📄 **已检测到 {len(doc_files)} 个背景文档：**")
            for doc_f in doc_files:
                st.caption(f"已加载文档: `{doc_f.name}`")

    st.divider()

    # 2. 多模态统一输入与生成区
    st.markdown("### 📝 角色设定描述与截图粘贴")

    with st.container(border=True):
        pure_text_prompt = st.text_area(
            "✍️ 文字设定描述：",
            placeholder="在此输入角色的文字背景、风格、人设或具体的调整要求...",
            height=120,
            key="main_text_prompt"
        )

        from streamlit_paste_button import paste_image_button

        st.write("📸 **截图快捷粘贴区：**")
        paste_result = paste_image_button(
            label="📋 点击此处：自动读取并粘贴系统剪贴板中的最新截图",
            background_color="#FF4B4B",
            hover_background_color="#D33636"
        )

        if paste_result and paste_result.image_data is not None:
            pasted_pil_img = paste_result.image_data

            img_byte_arr_check = io.BytesIO()
            pasted_pil_img.save(img_byte_arr_check, format='PNG')
            img_md5 = hashlib.md5(img_byte_arr_check.getvalue()).hexdigest()

            if img_md5 not in [x["md5"] for x in st.session_state.pasted_screenshots]:
                st.session_state.pasted_screenshots.append({
                    "md5": img_md5,
                    "img": pasted_pil_img
                })
                st.toast("✅ 成功从剪贴板捕获到新截图！", icon="📸")

        if st.session_state.pasted_screenshots:
            st.markdown(f"📋 **已捕获的剪贴板截图 ({len(st.session_state.pasted_screenshots)} 张)：**")
            p_cols = st.columns(min(4, len(st.session_state.pasted_screenshots)))

            to_delete_idx = None

            for p_idx, p_data in enumerate(st.session_state.pasted_screenshots):
                with p_cols[p_idx % 4]:
                    st.image(p_data["img"], caption=f"截图 #{p_idx + 1}", width=180)
                    if st.button(f"🗑️ 删除 #{p_idx + 1}", key=f"del_paste_{p_data['md5']}_{p_idx}",
                                 width='stretch'):
                        to_delete_idx = p_idx

            if to_delete_idx is not None:
                st.session_state.pasted_screenshots.pop(to_delete_idx)
                st.toast("🗑️ 已移除该截图", icon="👋")
                st.rerun()

        chat_pasted_files = []
        for idx, p_data in enumerate(st.session_state.pasted_screenshots):
            img_byte_arr = io.BytesIO()
            p_data["img"].save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0)
            img_byte_arr.name = f"clipboard_screenshot_{idx + 1}.png"
            chat_pasted_files.append(img_byte_arr)

        trigger_gen = st.button("✨ 融合全量素材并开始生成角色", width='stretch', type="primary")

    if trigger_gen:
        with st.spinner("正在分析并融合所有文字、图片及文档信息..."):
            all_file_img_descs = []
            all_paste_img_descs = []
            extracted_doc_text = ""
            st.session_state.all_saved_images = []

            # 提取文档内容
            if doc_files:
                for doc_f in doc_files:
                    try:
                        doc_text = extract_text_from_file(doc_f)
                        if doc_text.strip():
                            extracted_doc_text += f"\n--- 参考文档【{doc_f.name}】内容 ---\n{doc_text}\n"
                    except Exception as e:
                        st.error(str(e))

            # 提取文件图片特征
            if img_files:
                for idx, img_f in enumerate(img_files):
                    description, _ = analyze_image_from_file(img_f)
                    if description:
                        all_file_img_descs.append(f"[文件参考图片#{idx + 1} 特征]: {description}")
                    try:
                        img_f.seek(0)
                        st.session_state.all_saved_images.append(Image.open(img_f))
                    except Exception:
                        pass
                if img_files and not st.session_state.get("current_image_file"):
                    st.session_state.current_image_file = img_files[0]

            # 提取粘贴截图特征
            if chat_pasted_files:
                for idx, pasted_f in enumerate(chat_pasted_files):
                    pasted_desc, _ = analyze_image_from_file(pasted_f)
                    if pasted_desc:
                        all_paste_img_descs.append(f"[粘贴截图#{idx + 1} 特征]: {pasted_desc}")
                    try:
                        pasted_f.seek(0)
                        st.session_state.all_saved_images.append(Image.open(pasted_f))
                    except Exception:
                        pass
                    st.session_state.current_image_file = pasted_f

            # 汇总整合全量图片特征
            total_img_list = all_paste_img_descs + all_file_img_descs
            if total_img_list:
                st.session_state.uploaded_image_desc = "\n\n".join(total_img_list)

            # ====================== 核心优化：高优先级策略约束逻辑 ======================
            build_prompt = []
            build_prompt.append("⚠️【素材融合最高冲突处理原则 - 模型必须严格遵守以下优先级执行】:")
            build_prompt.append(
                "1. 最高优先级：用户在表单里指定的『角色姓名』和『角色性别』。如果下方任何截图、文字或文档文件提及了不一样的姓名或性别，必须全部作废！必须无条件以此最高优先级的姓名和性别为准。")
            build_prompt.append(
                "2. 次高优先级：【用户文字设定】。在不冲突最高姓名性别前提下，优先采纳这里的性格、风格和设定描述。")
            build_prompt.append("3. 第三优先级：【输入框粘贴截图特征】。提取并融合截图中的核心视觉和角色描述。")
            build_prompt.append(
                "4. 最低优先级：【文档背景设定】和【文件参考图片特征】。若与上述高优先级素材产生重名、性别相左或人设背景冲突，必须无条件被高优先级覆盖。")
            build_prompt.append("-" * 30)

            # 注入最高优先级：指定的名字与性别约束
            if input_explicit_name:
                build_prompt.append(
                    f"【最高优先级-严格锁定核心姓名】:\n指定生成的名字必须为：{input_explicit_name}。不允许被任何下层文件、截图或资料内的名字所误导或篡改！")
            if input_explicit_gender:
                build_prompt.append(
                    f"【最高优先级-严格锁定核心性别】:\n指定生成的性别必须为：{input_explicit_gender}。不允许被任何下层文件、截图或资料内的性别所误导或篡改！")

            # 注入次高优先级：文字设定描述
            if pure_text_prompt.strip():
                build_prompt.append(f"【次高优先级-用户文字设定】:\n{pure_text_prompt}")

            # 注入第三优先级：粘贴的截图特征
            if all_paste_img_descs:
                build_prompt.append(f"【第三优先级-输入框粘贴截图特征】:\n" + "\n".join(all_paste_img_descs))

            # 注入最低优先级：参考文件和参考图片
            if extracted_doc_text.strip():
                build_prompt.append(f"【最低优先级-文档背景设定（仅供背景参考，若冲突则无视）】:\n{extracted_doc_text}")
                with st.expander("📄 查看已成功解析的文档文字背景详情", expanded=False):
                    st.text(extracted_doc_text)
            if all_file_img_descs:
                build_prompt.append(
                    f"【最低优先级-文件参考图片特征（仅供背景参考，若冲突则无视）】:\n" + "\n".join(all_file_img_descs))

            # 组合成最终发送给 AI 的 Prompt 约束体
            final_fused_prompt = "\n\n".join(build_prompt)
            st.session_state.user_prompt = final_fused_prompt
            st.session_state.source_material_context = final_fused_prompt
            st.success("✅ 素材完成优先级高维融合！正在尝试生成角色人设...")

            # 兼容非必填项下的兜底正则表达式名字提取
            explicit_name = input_explicit_name if input_explicit_name else None
            explicit_gender = input_explicit_gender if input_explicit_gender else None

            if not explicit_name and pure_text_prompt.strip():
                name_match = re.search(r'(?:姓名|名字|叫|我是)[:：\s]*([^\s\n，。,]+)', pure_text_prompt)
                if name_match:
                    explicit_name = name_match.group(1).strip()

            try:
                # 统一交由大模型生成，传递已经完成了优先级严格层级排布的 prompt
                if pure_text_prompt.strip() or extracted_doc_text.strip():
                    if total_img_list:
                        combined_desc = combine_text_and_image(final_fused_prompt, "\n".join(total_img_list))
                        stream_gen_persona(combined_desc)
                    else:
                        stream_gen_persona(final_fused_prompt)
                elif total_img_list:
                    combined_desc = combine_text_and_image("根据高级优先级提示词生成人设:\n" + final_fused_prompt,
                                                           "\n".join(total_img_list))
                    stream_gen_persona(combined_desc)
                else:
                    stream_gen_persona(st.session_state.user_prompt)

            except openai.BadRequestError as e:
                err_msg = str(e)
                if "sensitive" in err_msg or "content" in err_msg or "inspection" in err_msg:
                    st.error("⚠️ **生成失败：触发表端/内容合规风控拦截！**")
                    st.warning(
                        f"📋 **具体原因**：输入素材或模型预输出的内容可能包含了敏感词汇，已被内容安全网关拦截。内部错误信息: {err_msg}")
                else:
                    st.error(f"❌ 接口请求错误 (400): {err_msg}")
            except Exception as e:
                err_msg = str(e)
                if "JSON" in err_msg or "Expecting" in err_msg or not st.session_state.persona:
                    st.warning(
                        "⚠️ 检测到模型流式输出意外截断，系统启动非破坏性容错机制，正在尽力恢复并填充已生成的人设资产...")
                    if hasattr(e, 'doc') and getattr(e, 'doc'):
                        repaired_data = try_repair_and_load_json(e.doc)
                        if repaired_data:
                            st.session_state.persona = repaired_data

                if not st.session_state.persona:
                    st.error(f"❌ 运行时发生意外错误: {err_msg}")

            # 无论大模型内部生成了什么结果，代码前端硬性再次重写锁死，确保万无一失
            if st.session_state.persona:
                if input_explicit_name:
                    st.session_state.persona["name"] = input_explicit_name
                elif explicit_name:
                    st.session_state.persona["name"] = explicit_name

                if input_explicit_gender:
                    st.session_state.persona["gender"] = input_explicit_gender
                elif explicit_gender:
                    st.session_state.persona["gender"] = explicit_gender

                st.session_state.persona = st.session_state.persona
                st.session_state.step_mode = "story"
                st.toast("🎉 角色配置就绪！")
                st.rerun()

elif st.session_state.step_mode == "greeting":
    p = st.session_state.persona

    st.subheader("🎭 开场白生成与编辑")
    col1, col2 = st.columns([3, 1])
    with col1:
        num_lines = st.number_input("生成几句开场白？", 0, 5, 2, key="greeting_num_input")
    with col2:
        if st.button("✨ 生成开场白", width='stretch', type="primary"):
            # 【优化】生成前强行同步当前最新的修改框内容
            sync_persona_to_global_prompt()
            stream_gen_greeting(num_lines)

    if st.session_state.greeting:
        with st.expander("📖 已生成的开场白（可直接在下方框内任意修改编辑）", expanded=True):
            for i, line in enumerate(st.session_state.greeting):
                edited_line = st.text_area(f"✍️ 第 {i + 1} 句：", value=line, key=f"edit_greet_{i}", height=70)
                if edited_line != line:
                    st.session_state.greeting[i] = edited_line  # 实时回写

    st.divider()

    st.subheader("📝 用户原始设定")
    with st.expander("展开/折叠 查看用户原始设定内容", expanded=False):
        display_user_prompt = st.session_state.user_prompt if st.session_state.user_prompt else p.get("user_prompt", "")
        edited_user_prompt = st.text_area("全局原始设定：", value=display_user_prompt, key="edit_user_prompt_global",
                                          height=150)
        if edited_user_prompt != display_user_prompt:
            st.session_state.user_prompt = edited_user_prompt

    st.subheader("📋 角色人设详情（支持自由在线二次编辑微调）")

    if st.session_state.all_saved_images:
        st.markdown(f"📸 **全量参考图库与截图保留记录 ({len(st.session_state.all_saved_images)} 张)：**")
        img_cols = st.columns(min(4, len(st.session_state.all_saved_images)))
        for idx, saved_img in enumerate(st.session_state.all_saved_images):
            with img_cols[idx % 4]:
                st.image(saved_img, caption=f"参考图 #{idx + 1}", width=180)
    elif st.session_state.get("current_image_file"):
        try:
            img_show = Image.open(st.session_state.current_image_file)
            st.image(img_show, caption="当前角色参考图", width=180)
        except Exception:
            pass

    if st.session_state.get("uploaded_image_desc"):
        with st.expander("📝 查看图片提取的原始描述", expanded=False):
            st.text(st.session_state.uploaded_image_desc)


    def bind_persona_input(label, field_key, is_area=False, height=100):
        val = p.get(field_key, "")
        if isinstance(val, list):
            val = ", ".join([str(v) for v in val])

        if is_area:
            new_val = st.text_area(label, value=str(val), key=f"field_{field_key}", height=height)
        else:
            new_val = st.text_input(label, value=str(val), key=f"field_{field_key}")

        if new_val != str(val):
            if isinstance(p.get(field_key), list):
                st.session_state.persona[field_key] = [x.strip() for x in new_val.split(",") if x.strip()]
            else:
                st.session_state.persona[field_key] = new_val
            # 【优化】一旦用户手动修改框内数据，隐式自动同步
            sync_persona_to_global_prompt()


    col_p1, col_p2 = st.columns(2)
    with col_p1:
        bind_persona_input("名字", "name")
    with col_p2:
        bind_persona_input("性别", "gender")

    bind_persona_input("标签 (多个请用逗号隔开)", "taglines")
    bind_persona_input("背景设定", "character_description", is_area=True, height=120)
    bind_persona_input("介绍", "intro", is_area=True, height=120)
    bind_persona_input("性格 (多个请用逗号隔开)", "personality")
    bind_persona_input("说话风格和习惯", "speaking_style", is_area=True, height=100)
    bind_persona_input("兴趣爱好 (可以用回车或逗号分隔)", "hobbies", is_area=True, height=100)

    if st.session_state.saved_folder:
        st.divider()
        if st.button("📋 一键复制整个人设", width='stretch'):
            copy_from_file(f"{st.session_state.saved_folder}/人设.txt")

    st.divider()

elif st.session_state.step_mode == "story":
    p = st.session_state.persona

    st.success(f"✅ 当前角色：{p.get('name', '')} | 剧本库共有 {len(st.session_state.story_list)} 章")
    if st.session_state.uploaded_image_desc:
        st.info("📸 **本角色基于图片分析生成**")

    tab1, tab2, tab3 = st.tabs(["人设信息", "开场白", "章节剧情"])

    with tab1:
        # ====================== 【原始素材修改区】可随时修改并重新生成人设 ======================
        with st.expander("🛠️ 修改原始素材并重新生成人设（点击展开）", expanded=False):
            st.info("💡 你可以在此随时修改任何原始信息（姓名、性别、文字描述、文件、截图），然后点击底部按钮重新覆盖生成人设。")

            # 姓名 & 性别
            st.markdown("#### 👤 角色基础约束")
            col_re_name, col_re_gender = st.columns([1, 1])
            with col_re_name:
                re_input_name = st.text_input(
                    "📛 角色姓名：",
                    placeholder="例如：宋知秋（若填写则严格锁定）",
                    value=p.get("name", ""),
                    key="re_explicit_name_input"
                ).strip()
            with col_re_gender:
                _gender_options = ["男", "女", "其他"]
                _cur_gender = p.get("gender", "女")
                _gender_idx = _gender_options.index(_cur_gender) if _cur_gender in _gender_options else 1
                re_input_gender = st.selectbox(
                    "🚻 角色性别：",
                    options=_gender_options,
                    index=_gender_idx,
                    key="re_explicit_gender_input"
                )

            st.divider()

            # 文件上传（图片 + 文档）
            st.markdown("#### 📎 重新上传参考素材（可多选）")
            re_col_upload, re_col_preview = st.columns([1, 1])
            with re_col_upload:
                re_uploaded_files = st.file_uploader(
                    "选择或拖拽文件（支持图片、txt、pdf、docx、md、json 等）",
                    type=['png', 'jpg', 'jpeg', 'webp', 'txt', 'pdf', 'doc', 'docx', 'md', 'json', 'csv',
                          'PNG', 'JPG', 'JPEG', 'WEBP'],
                    accept_multiple_files=True,
                    key="re_mixed_files_uploader",
                    help="重新上传图片或文档来覆盖之前的参考素材"
                )

            re_img_files = []
            re_doc_files = []
            if re_uploaded_files:
                for f in re_uploaded_files:
                    ext = os.path.splitext(f.name)[1].lower()
                    if ext in ['.png', '.jpg', '.jpeg', '.webp']:
                        re_img_files.append(f)
                    elif ext in ['.txt', '.pdf', '.doc', '.docx', '.md', '.json', '.csv']:
                        re_doc_files.append(f)

            with re_col_preview:
                if re_img_files:
                    st.markdown(f"📸 **已检测到 {len(re_img_files)} 张图片：**")
                    re_cols = st.columns(min(4, len(re_img_files)))
                    for idx, img_f in enumerate(re_img_files):
                        with re_cols[idx % 4]:
                            st.image(Image.open(img_f), width=180)
                if re_doc_files:
                    st.markdown(f"📄 **已检测到 {len(re_doc_files)} 个背景文档：**")
                    for doc_f in re_doc_files:
                        st.caption(f"已加载文档: `{doc_f.name}`")
                # 若未重新上传，展示现有图库
                if not re_uploaded_files and st.session_state.all_saved_images:
                    st.markdown(f"📸 **当前已有参考图 ({len(st.session_state.all_saved_images)} 张)：**")
                    re_exist_cols = st.columns(min(4, len(st.session_state.all_saved_images)))
                    for idx, saved_img in enumerate(st.session_state.all_saved_images):
                        with re_exist_cols[idx % 4]:
                            st.image(saved_img, caption=f"参考图 #{idx + 1}", width=180)

            st.divider()

            # 文字描述 + 截图粘贴
            st.markdown("#### 📝 文字描述与截图")
            with st.container(border=True):
                re_pure_text_prompt = st.text_area(
                    "✍️ 文字设定描述：",
                    placeholder="在此修改角色的文字背景、风格、人设或具体的调整要求...",
                    height=120,
                    key="re_main_text_prompt"
                )

                from streamlit_paste_button import paste_image_button as _paste_btn

                st.write("📸 **截图快捷粘贴区：**")
                re_paste_result = _paste_btn(
                    label="📋 点击此处：自动读取并粘贴系统剪贴板中的最新截图",
                    background_color="#FF4B4B",
                    hover_background_color="#D33636",
                    key="re_paste_btn"
                )

                if re_paste_result and re_paste_result.image_data is not None:
                    re_pasted_pil_img = re_paste_result.image_data
                    re_img_byte_check = io.BytesIO()
                    re_pasted_pil_img.save(re_img_byte_check, format='PNG')
                    re_img_md5 = hashlib.md5(re_img_byte_check.getvalue()).hexdigest()
                    if re_img_md5 not in [x["md5"] for x in st.session_state.pasted_screenshots]:
                        st.session_state.pasted_screenshots.append({
                            "md5": re_img_md5,
                            "img": re_pasted_pil_img
                        })
                        st.toast("✅ 成功从剪贴板捕获到新截图！", icon="📸")

                if st.session_state.pasted_screenshots:
                    st.markdown(f"📋 **已捕获的剪贴板截图 ({len(st.session_state.pasted_screenshots)} 张)：**")
                    re_p_cols = st.columns(min(4, len(st.session_state.pasted_screenshots)))
                    re_to_delete_idx = None
                    for p_idx, p_data in enumerate(st.session_state.pasted_screenshots):
                        with re_p_cols[p_idx % 4]:
                            st.image(p_data["img"], caption=f"截图 #{p_idx + 1}", width=180)
                            if st.button(f"🗑️ 删除 #{p_idx + 1}",
                                         key=f"re_del_paste_{p_data['md5']}_{p_idx}",
                                         width='stretch'):
                                re_to_delete_idx = p_idx
                    if re_to_delete_idx is not None:
                        st.session_state.pasted_screenshots.pop(re_to_delete_idx)
                        st.toast("🗑️ 已移除该截图", icon="👋")
                        st.rerun()

                # 将粘贴截图统一转为 file-like 对象
                re_chat_pasted_files = []
                for idx, p_data in enumerate(st.session_state.pasted_screenshots):
                    re_buf = io.BytesIO()
                    p_data["img"].save(re_buf, format='PNG')
                    re_buf.seek(0)
                    re_buf.name = f"clipboard_screenshot_{idx + 1}.png"
                    re_chat_pasted_files.append(re_buf)

                re_trigger_gen = st.button("🔁 融合修改后的全量素材并重新覆盖生成人设",
                                           width='stretch', type="primary",
                                           key="re_trigger_gen_btn")

            if re_trigger_gen:
                with st.spinner("正在重新分析并融合所有修改后的文字、图片及文档信息..."):
                    re_all_file_img_descs = []
                    re_all_paste_img_descs = []
                    re_extracted_doc_text = ""

                    # 如有重新上传则更新图库
                    if re_img_files or re_doc_files:
                        st.session_state.all_saved_images = []

                    # 提取文档内容
                    if re_doc_files:
                        for doc_f in re_doc_files:
                            try:
                                doc_text = extract_text_from_file(doc_f)
                                if doc_text.strip():
                                    re_extracted_doc_text += f"\n--- 参考文档【{doc_f.name}】内容 ---\n{doc_text}\n"
                            except Exception as e:
                                st.error(str(e))

                    # 提取文件图片特征
                    if re_img_files:
                        for idx, img_f in enumerate(re_img_files):
                            description, _ = analyze_image_from_file(img_f)
                            if description:
                                re_all_file_img_descs.append(f"[文件参考图片#{idx + 1} 特征]: {description}")
                            try:
                                img_f.seek(0)
                                st.session_state.all_saved_images.append(Image.open(img_f))
                            except Exception:
                                pass
                        if re_img_files and not st.session_state.get("current_image_file"):
                            st.session_state.current_image_file = re_img_files[0]

                    # 提取粘贴截图特征
                    if re_chat_pasted_files:
                        for idx, pasted_f in enumerate(re_chat_pasted_files):
                            pasted_desc, _ = analyze_image_from_file(pasted_f)
                            if pasted_desc:
                                re_all_paste_img_descs.append(f"[粘贴截图#{idx + 1} 特征]: {pasted_desc}")
                            try:
                                pasted_f.seek(0)
                                if not re_img_files:
                                    st.session_state.all_saved_images.append(Image.open(pasted_f))
                            except Exception:
                                pass
                            st.session_state.current_image_file = pasted_f

                    # 汇总图片特征
                    re_total_img_list = re_all_paste_img_descs + re_all_file_img_descs
                    if re_total_img_list:
                        st.session_state.uploaded_image_desc = "\n\n".join(re_total_img_list)

                    # 构建优先级 prompt
                    re_build_prompt = []
                    re_build_prompt.append("⚠️【素材融合最高冲突处理原则 - 模型必须严格遵守以下优先级执行】:")
                    re_build_prompt.append("1. 最高优先级：用户在表单里指定的『角色姓名』和『角色性别』。")
                    re_build_prompt.append("2. 次高优先级：【用户文字设定】。")
                    re_build_prompt.append("3. 第三优先级：【输入框粘贴截图特征】。")
                    re_build_prompt.append("4. 最低优先级：【文档背景设定】和【文件参考图片特征】。")
                    re_build_prompt.append("-" * 30)

                    if re_input_name:
                        re_build_prompt.append(
                            f"【最高优先级-严格锁定核心姓名】:\n指定生成的名字必须为：{re_input_name}。")
                    if re_input_gender:
                        re_build_prompt.append(
                            f"【最高优先级-严格锁定核心性别】:\n指定生成的性别必须为：{re_input_gender}。")
                    if re_pure_text_prompt.strip():
                        re_build_prompt.append(f"【次高优先级-用户文字设定】:\n{re_pure_text_prompt}")
                    if re_all_paste_img_descs:
                        re_build_prompt.append("【第三优先级-输入框粘贴截图特征】:\n" + "\n".join(re_all_paste_img_descs))
                    if re_extracted_doc_text.strip():
                        re_build_prompt.append(
                            f"【最低优先级-文档背景设定】:\n{re_extracted_doc_text}")
                    if re_all_file_img_descs:
                        re_build_prompt.append(
                            "【最低优先级-文件参考图片特征】:\n" + "\n".join(re_all_file_img_descs))

                    re_final_fused_prompt = "\n\n".join(re_build_prompt)
                    st.session_state.user_prompt = re_final_fused_prompt
                    st.session_state.source_material_context = re_final_fused_prompt
                    st.success("✅ 素材重新融合完成！正在覆盖生成新人设...")

                    re_explicit_name = re_input_name if re_input_name else None
                    re_explicit_gender = re_input_gender if re_input_gender else None

                    if not re_explicit_name and re_pure_text_prompt.strip():
                        name_match = re.search(r'(?:姓名|名字|叫|我是)[:：\s]*([^\s\n，。,]+)', re_pure_text_prompt)
                        if name_match:
                            re_explicit_name = name_match.group(1).strip()

                    try:
                        if re_pure_text_prompt.strip() or re_extracted_doc_text.strip():
                            if re_total_img_list:
                                combined_desc = combine_text_and_image(re_final_fused_prompt,
                                                                       "\n".join(re_total_img_list))
                                stream_gen_persona(combined_desc)
                            else:
                                stream_gen_persona(re_final_fused_prompt)
                        elif re_total_img_list:
                            combined_desc = combine_text_and_image(
                                "根据高级优先级提示词生成人设:\n" + re_final_fused_prompt,
                                "\n".join(re_total_img_list))
                            stream_gen_persona(combined_desc)
                        else:
                            stream_gen_persona(st.session_state.user_prompt)

                    except openai.BadRequestError as e:
                        err_msg = str(e)
                        if "sensitive" in err_msg or "content" in err_msg or "inspection" in err_msg:
                            st.error("⚠️ **生成失败：触发内容合规风控拦截！**")
                            st.warning(f"📋 **具体原因**: {err_msg}")
                        else:
                            st.error(f"❌ 接口请求错误 (400): {err_msg}")
                    except Exception as e:
                        err_msg = str(e)
                        if "JSON" in err_msg or "Expecting" in err_msg or not st.session_state.persona:
                            st.warning("⚠️ 检测到模型流式输出意外截断，正在尽力恢复...")
                            if hasattr(e, 'doc') and getattr(e, 'doc'):
                                repaired_data = try_repair_and_load_json(e.doc)
                                if repaired_data:
                                    st.session_state.persona = repaired_data
                        if not st.session_state.persona:
                            st.error(f"❌ 运行时发生意外错误: {err_msg}")

                    # 前端硬性锁定姓名性别
                    if st.session_state.persona:
                        if re_input_name:
                            st.session_state.persona["name"] = re_input_name
                        elif re_explicit_name:
                            st.session_state.persona["name"] = re_explicit_name
                        if re_input_gender:
                            st.session_state.persona["gender"] = re_input_gender
                        elif re_explicit_gender:
                            st.session_state.persona["gender"] = re_explicit_gender
                        st.toast("🎉 人设已重新生成并覆盖！")
                        st.rerun()

        st.divider()

        # ====================== 用户原始设定（只读展示）======================
        st.subheader("📝 用户原始设定")
        with st.expander("展开/折叠 查看用户原始设定内容", expanded=False):
            disp_prompt = st.session_state.user_prompt if st.session_state.user_prompt else p.get("user_prompt", "")
            edited_story_prompt = st.text_area("全局设定关联词修改：", value=str(disp_prompt), key="edit_prompt_tab1",
                                               height=120)
            if edited_story_prompt != str(disp_prompt):
                st.session_state.user_prompt = edited_story_prompt

        if st.session_state.all_saved_images:
            st.markdown(f"📸 **全量参考图库与截图保留记录 ({len(st.session_state.all_saved_images)} 张)：**")
            img_cols_story = st.columns(min(4, len(st.session_state.all_saved_images)))
            for idx, saved_img in enumerate(st.session_state.all_saved_images):
                with img_cols_story[idx % 4]:
                    st.image(saved_img, caption=f"参考图 #{idx + 1}", width=180)

        if st.session_state.saved_folder:
            if st.button("📋 一键复制整个人设", width='stretch'):
                copy_from_file(f"{st.session_state.saved_folder}/人设.txt")

        st.subheader("📋 编辑核心人设资产数据")


        def bind_persona_story_tab(label, field_key, is_area=False, height=100):
            val = p.get(field_key, "")
            if isinstance(val, list):
                val = ", ".join([str(v) for v in val])
            if is_area:
                new_val = st.text_area(label, value=str(val), key=f"story_tab_{field_key}", height=height)
            else:
                new_val = st.text_input(label, value=str(val), key=f"story_tab_{field_key}")
            if new_val != str(val):
                if isinstance(p.get(field_key), list):
                    st.session_state.persona[field_key] = [x.strip() for x in new_val.split(",") if x.strip()]
                else:
                    st.session_state.persona[field_key] = new_val
                # 【优化】在标签页修改时也执行隐式数据同步，确保下一秒点击生成大纲/正文时完美继承
                sync_persona_to_global_prompt()


        col_tab1_n, col_tab1_g = st.columns(2)
        with col_tab1_n:
            bind_persona_story_tab("名字", "name")
        with col_tab1_g:
            bind_persona_story_tab("性别", "gender")
        bind_persona_story_tab("标签", "taglines")
        bind_persona_story_tab("背景设定", "character_description", is_area=True, height=100)
        bind_persona_story_tab("介绍", "intro", is_area=True, height=100)
        bind_persona_story_tab("性格", "personality")
        bind_persona_story_tab("说话风格和习惯", "speaking_style", is_area=True, height=80)
        bind_persona_story_tab("兴趣爱好", "hobbies", is_area=True, height=80)

    with tab2:
        if not st.session_state.greeting:
            st.info("未生成开场白")
            c1, c2 = st.columns([3, 1])
            with c1:
                n = st.number_input("生成几句开场白？", 0, 5, 2, key="g2")
            with c2:
                if st.button("✨ 生成开场白", width='stretch'):
                    if not st.session_state.get("persona"):
                        st.warning("请先生成爆款人设，才能生成开场白。")
                    else:
                        sync_persona_to_global_prompt()
                        stream_gen_greeting(n)
        else:
            st.markdown("### 📖 开场白编辑库")
            for i, line in enumerate(st.session_state.greeting):
                edited_line_tab2 = st.text_area(f"第 {i + 1} 句：", value=line, key=f"edit_greet_tab2_{i}", height=70)
                if edited_line_tab2 != line:
                    st.session_state.greeting[i] = edited_line_tab2
                st.divider()

    with tab3:
        st.write("### 🎬 爆款剧情多阶段配置面板")
        stage_keys = sorted(list(st.session_state.custom_stages.keys()))

        with st.expander("⚙️ 展开/折叠：自定义剧情阶段与演进提示词说明", expanded=True):
            for k in stage_keys:
                st.markdown(f"#### ❖ 剧情演进阶段 {k}")
                st.session_state.custom_stages[k]["name"] = st.text_input(f"阶段 {k} 名称：",
                                                                          value=st.session_state.custom_stages[k][
                                                                              "name"], key=f"stage_name_input_{k}")
                st.session_state.custom_stages[k]["desc"] = st.text_area(f"阶段 {k} 核心控制逻辑提示词：",
                                                                         value=st.session_state.custom_stages[k][
                                                                             "desc"], height=80,
                                                                         key=f"stage_desc_input_{k}")
                st.session_state.custom_stages[k]["chapters"] = st.number_input(f"该阶段包含的章节数：", min_value=1,
                                                                                max_value=100, value=int(
                        st.session_state.custom_stages[k].get("chapters", 3)), key=f"stage_chapters_input_{k}")

                if len(stage_keys) > 1:
                    if st.button(f"🗑️ 删除阶段 {k}", key=f"del_stage_btn_{k}"):
                        st.session_state.custom_stages.pop(k)
                        st.rerun()
                st.write("")

            if st.button("➕ 添加全新剧情演进阶段"):
                next_key = max(stage_keys) + 1 if stage_keys else 1
                st.session_state.custom_stages[next_key] = {
                    "name": f"阶段{next_key}：自定义新阶段标签说明",
                    "desc": "请输入该发展进程阶段中大纲应当遵从的核心拉扯与演进目标控制细节逻辑...",
                    "chapters": 3
                }
                st.rerun()


        with st.expander("⚙️ 展开/折叠：章节正文内容格式提示词", expanded=True):
            st.caption("默认按下方格式输出；如果生成人设时上传的原始资料明确写了阶段安排或正文格式，生成时会优先参考原始资料。这里也可以手动改成你想要的格式。")
            # 修改后（正确写法）
            st.text_area(
                "章节正文内容输出格式：",
                value=st.session_state.get("chapter_format_prompt", DEFAULT_CHAPTER_FORMAT_PROMPT),
                height=260,
                key="chapter_format_prompt"  # ← 直接用 chapter_format_prompt 作为 key
            )
        auto_total_chapters = sum(int(st.session_state.custom_stages[k].get("chapters", 3)) for k in stage_keys)
        total_chapters_input = st.number_input("1. 请确认要规划生成的总章节数（已根据上方阶段自动求和）：", min_value=1,
                                               max_value=100, value=auto_total_chapters)

        if st.button("✨ 根据上方配置，重新重置并生成连载大纲（章节名）", width='stretch', type="primary"):

            if not st.session_state.get("persona"):

                st.warning("请先生成爆款人设，才能生成章节剧情。")

            else:

                # 【优化】重新生成连载大纲前同步最新调整的人设

                sync_persona_to_global_prompt()

                stream_gen_all_outlines(int(total_chapters_input), st.session_state.custom_stages)

        st.divider()

        if st.session_state.story_list:
            st.write("### 📖 剧本章节详细内容库")

            if st.button("🚀 依次顺序一键生成全文章节剧情（从第一章至最后一章自动执行）", width='stretch',
                         type="primary"):
                # 【优化】一键序列化流式填充所有剧情前同步最新人设
                sync_persona_to_global_prompt()
                progress_bar = st.progress(0.0)
                status_txt = st.empty()
                total_len = len(st.session_state.story_list)

                loop_placeholder = st.empty()  # 循环外创建，整个批量复用同一个

                for idx in range(total_len):
                    ch_title = st.session_state.story_list[idx].get('标题', f'第{idx + 1}章')
                    status_txt.markdown(f"⏳ **正在自动生成第 {idx + 1}/{total_len} 章：《{ch_title}》... 请勿关闭页面**")

                    try:
                        # 🌟 提前构建格式化上下文
                        p_name = st.session_state.persona.get('name', '角色')
                        fmt_ctx = st.session_state.get("chapter_format_prompt", "")
                        # 显式传给单章生成函数
                        stream_gen_one_chapter_optimized(
                            idx,
                            st.session_state.custom_stages,
                            loop_placeholder,
                            batch_mode=True,
                            passed_format_context=fmt_ctx
                        )

                        if f"pending_content_{idx}" in st.session_state:
                            st.session_state[f"widget_ch_content_{idx}"] = st.session_state.pop(
                                f"pending_content_{idx}")
                        if f"pending_emo_{idx}" in st.session_state:
                            st.session_state[f"widget_ch_emo_{idx}"] = st.session_state.pop(f"pending_emo_{idx}")

                    except Exception as e:
                        st.error(f"生成第 {idx + 1} 章出错: {str(e)}")

                    progress_bar.progress((idx + 1) / total_len)

                loop_placeholder.empty()  # 全部完成后统一清理

                st.toast("🎉 全文章节内容已批量自动填充完毕！正在刷新页面呈现正文...", icon="✅")
                st.rerun()
            st.write("")

            for idx, ch in enumerate(st.session_state.story_list):
                if not isinstance(ch, dict):
                    continue

                curr_stg = get_chapter_stage(idx + 1, len(st.session_state.story_list), st.session_state.custom_stages)
                display_stg_name = st.session_state.custom_stages[curr_stg][
                    'name'] if curr_stg in st.session_state.custom_stages else f"未定义的自定义阶段 {curr_stg}"

                try:
                    display_ch_num = int(ch.get('章节', idx + 1))
                except Exception:
                    display_ch_num = idx + 1

                st.markdown(f"#### ❖ 第{display_ch_num}章")
                # 在这里提前创建流式输出占位符，位置在 expander 外部、主列中
                stream_placeholder = st.empty()  # ← 新增这一行

                ch_title_val = ch.get('标题', '')
                edited_ch_title = st.text_input(f"🎬 章节标题 [章 #{idx + 1}]：", value=ch_title_val,
                                                key=f"edit_ch_title_{idx}")
                if edited_ch_title != ch_title_val:
                    st.session_state.story_list[idx]['标题'] = edited_ch_title

                st.caption(f"🎯 归属进程阶段：{display_stg_name}")

                #  修改后的安全代码：
                with st.expander("展开/折叠 本章细节与文本正文内容（可在此处自由修改或手动写小说）", expanded=True):

                    # ★ 新增：消费 pending key，把待刷新内容强制覆盖到 widget key
                    if f"pending_content_{idx}" in st.session_state:
                        st.session_state[f"widget_ch_content_{idx}"] = st.session_state.pop(f"pending_content_{idx}")
                    if f"pending_emo_{idx}" in st.session_state:
                        st.session_state[f"widget_ch_emo_{idx}"] = st.session_state.pop(f"pending_emo_{idx}")

                    # widget key 不存在时用数据源初始化，存在时 Streamlit 自动用 session_state 里的值（value= 被忽略）
                    if f"widget_ch_emo_{idx}" not in st.session_state:
                        st.session_state[f"widget_ch_emo_{idx}"] = ch.get('情绪', '无')
                    edited_ch_emo = st.text_input(
                        "🎭 情绪 / 语气控制描述：",
                        key=f"widget_ch_emo_{idx}"
                    )

                    if f"widget_ch_content_{idx}" not in st.session_state:
                        st.session_state[f"widget_ch_content_{idx}"] = ch.get('剧情', '')
                    edited_ch_content = st.text_area(
                        "📝 小说小说正文细化：",
                        key=f"widget_ch_content_{idx}",
                        height=250
                    )
                    # 改后（直接从 widget key 读，widget key 由 Streamlit 自动维护）
                    if st.session_state.get(f"widget_ch_content_{idx}") != ch.get('剧情', ''):
                        st.session_state.story_list[idx]['剧情'] = st.session_state[f"widget_ch_content_{idx}"]

                col_btn_a, col_btn_b = st.columns([1, 1])
                with col_btn_a:
                    if st.button(f"🔄 重新单独生成/覆盖第 {idx + 1} 章", key=f"regen_btn_{idx}", width='stretch'):
                        # ====================== 控制台诊断日志开始 ======================
                        print(f"\n[诊断追踪] >>> 开始触发: 【重新单独生成/覆盖第 {idx + 1} 章】<<<")
                        print(f"[当前索引]: idx = {idx}")
                        print(
                            f"[全局 user_prompt 状态]: {'有内容' if st.session_state.get('user_prompt') else '❌ 空/不存在'}")
                        print(
                            f"[当前大纲字典 story_list 长度]: {len(st.session_state.story_list) if 'story_list' in st.session_state else '❌ 未初始化'}")

                        # 深度侦测核心人设资产
                        if not st.session_state.get("persona"):
                            print("❌【控制台警报】: st.session_state.persona 为空！AI 将失去人设背景。")
                        else:
                            print(f"[人设核心名字]: {st.session_state.persona.get('name', '未命名')}")
                            print(f"[人设核心性别]: {st.session_state.persona.get('gender', '未设定')}")

                        # 侦测自定义阶段配置
                        if not st.session_state.get("custom_stages"):
                            print("❌【控制台警报】: st.session_state.custom_stages 丢失！")
                        # ====================== 控制台诊断日志结束 ======================

                        try:
                            sync_persona_to_global_prompt()
                            print("[流程追踪]: sync_persona_to_global_prompt 执行完毕。")

                            # 🌟 显式获取当前最新的章节正文格式提示词
                            fmt_ctx = st.session_state.get("chapter_format_prompt", "")

                            # 🌟 传入形参 passed_format_context
                            stream_gen_one_chapter_optimized(
                                idx,
                                st.session_state.custom_stages,
                                stream_placeholder,
                                passed_format_context=fmt_ctx
                            )
                            print(f"[流程追踪]: stream_gen_one_chapter_optimized({idx}) 执行完毕。")

                            # 🛡️ 【核心修复】后台生成完，不仅要写进 cache，必须同时强行把新剧情同步给 widget 绑定的实际渲染 key
                            new_content = st.session_state.story_list[idx].get('剧情', '')
                            new_emo = st.session_state.story_list[idx].get('情绪', '无')

                            # 填充前检查模型是否真的吐出了数据
                            if not new_content or new_content.strip() == "":
                                print(
                                    f"⚠️【控制台警告】: 函数运行结束，但 story_list[{idx}] 中的 '剧情' 字段依然为空！可能是大模型未响应、被截断或报错。")
                            else:
                                print(f"✅【生成成功】: 第 {idx + 1} 章成功捕获到字符数: {len(new_content)}")

                            st.session_state[f"edit_ch_content_{idx}_cache"] = new_content
                            st.session_state[f"edit_ch_emo_{idx}_cache"] = new_emo

                            # 强行刷新前端组件缓存状态，防止文本框内容不更新
                            st.session_state[f"widget_ch_content_{idx}"] = new_content
                            st.session_state[f"widget_ch_emo_{idx}"] = new_emo

                            print("[流程追踪]: 前端 Key 双向绑定重写完成，准备刷新页面...\n")
                            st.rerun()

                        except Exception as e:
                            import traceback

                            print(f"❌❌❌【运行时异常】: 在执行『重新单独生成第 {idx + 1} 章』时崩溃！")
                            print(f"错误类型: {type(e)}")
                            print(f"错误原因: {str(e)}")
                            print("详细报错堆栈跟踪如下:")
                            traceback.print_exc()  # 打印最详细的报错行数
                            st.error(f"生成时发生底层错误: {str(e)}")

                with col_btn_b:
                    if idx + 1 == st.session_state.now_chapter and not ch.get('剧情'):
                        if st.button(f"🚀 快捷流式填充第 {idx + 1} 章正文", key=f"gen_btn_{idx}", width='stretch',
                                     type="primary"):
                            # ====================== 控制台诊断日志开始 ======================
                            print(f"\n[诊断追踪] >>> 开始触发: 【快捷流式填充第 {idx + 1} 章正文】<<<")
                            print(f"[当前索引]: idx = {idx}")
                            print(
                                f"[全局 user_prompt 状态]: {'有内容' if st.session_state.get('user_prompt') else '❌ 空/不存在'}")
                            if not st.session_state.get("persona"):
                                print("❌【控制台警报】: st.session_state.persona 为空！")
                            # ====================== 控制台诊断日志结束 ======================

                            try:
                                sync_persona_to_global_prompt()
                                print("[流程追踪]: sync_persona_to_global_prompt 执行完毕。")

                                # 🌟 同样显式获取并传入格式化上下文
                                fmt_ctx = st.session_state.get("chapter_format_prompt", "")

                                stream_gen_one_chapter_optimized(
                                    idx,
                                    st.session_state.custom_stages,
                                    stream_placeholder,
                                    passed_format_context=fmt_ctx
                                )
                                print(f"[流程追踪]: stream_gen_one_chapter_optimized({idx}) 执行完毕。")
                                # 🛡️ 【核心修复】同理，快捷填充后也必须双向强行赋值给 widget key
                                new_content = st.session_state.story_list[idx].get('剧情', '')
                                new_emo = st.session_state.story_list[idx].get('情绪', '无')

                                if not new_content or new_content.strip() == "":
                                    print(
                                        f"⚠️【控制台警告】: 函数运行结束，但 story_list[{idx}] 中的 '剧情' 字段依然为空！")
                                else:
                                    print(f"✅【生成成功】: 第 {idx + 1} 章成功捕获到字符数: {len(new_content)}")

                                st.session_state[f"edit_ch_content_{idx}_cache"] = new_content
                                st.session_state[f"edit_ch_emo_{idx}_cache"] = new_emo

                                st.session_state[f"widget_ch_content_{idx}"] = new_content
                                st.session_state[f"widget_ch_emo_{idx}"] = new_emo

                                print("[流程追踪]: 前端 Key 双向绑定重写完成，准备刷新页面...\n")
                                st.rerun()

                            except Exception as e:
                                import traceback

                                print(f"❌❌❌【运行时异常】: 在执行『快捷流式填充第 {idx + 1} 章』时崩溃！")
                                print(f"错误类型: {type(e)}")
                                print(f"错误原因: {str(e)}")
                                print("详细报错堆栈跟踪如下:")
                                traceback.print_exc()
                                st.error(f"填充时发生底层错误: {str(e)}")
                    else:
                        st.caption("✅ 已开放自由编辑或已完成序列")
                st.markdown("---")
        else:
            st.info("💡 暂无大纲，请先在上方设定总章节并点击按钮『重新重置并生成连载大纲（章节名）』。")

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        # ====================== 【优化痛点 2】：适配 Hugging Face Space 的标准内存下载组件 ======================
        # 在内存中实时构建合并文件文本流，避免对 HF 容器磁盘读写，从而实现一键下载
        try:
            download_io = io.BytesIO()
            combined_download_text = ""

            # 拼接人设资产
            combined_download_text += "================= 核心人设资产 ================="
            for key_k, val_v in p.items():
                if key_k != "user_prompt":
                    combined_download_text += f"\n【{key_k}】: {val_v}\n"

            # 拼接开场白资产
            if st.session_state.greeting:
                combined_download_text += "\n\n================= 开场白角色语料库 ================="
                for idx_g, line_g in enumerate(st.session_state.greeting):
                    combined_download_text += f"\n开场白 #{idx_g + 1}: {line_g}"

            # 拼接连载剧本正文
            if st.session_state.story_list:
                combined_download_text += "\n\n================= 全文章节剧本正文 ================="
                for idx_s, ch_s in enumerate(st.session_state.story_list):
                    if isinstance(ch_s, dict):
                        combined_download_text += f"\n\n--- 第 {idx_s + 1} 章：{ch_s.get('标题', '未命名')} ---"
                        combined_download_text += f"\n[语气控制]: {ch_s.get('情绪', '无')}"
                        combined_download_text += f"\n[正文剧情]:\n{ch_s.get('剧情', '暂无内容')}"

            download_io.write(combined_download_text.encode('utf-8'))
            download_io.seek(0)

            # 采用 Streamlit 官方原生下载组件，在浏览器层直接落盘
            char_filename = f"角色及小说剧本_{p.get('name', '未命名')}.txt"
            st.download_button(
                label="📥 完美一键下载全部资产到本地 (支持HF云环境)",
                data=download_io,
                file_name=char_filename,
                mime="text/plain",
                width='stretch',
                type="primary"
            )
        except Exception as e:
            st.caption(f"标准下载加载中... ({str(e)})")

    with c2:
        if st.button("🔄 新建角色", width='stretch'):
            st.session_state.step_mode = "input"
            st.session_state.persona = {}
            st.session_state.greeting = []
            st.session_state.story_list = []
            st.session_state.user_prompt = ""
            st.session_state.now_chapter = 1
            st.session_state.saved_folder = None
            st.session_state.uploaded_image_desc = ""
            st.session_state.pasted_screenshots = []
            st.session_state.all_saved_images = []
            st.rerun()
