const { app } = window.comfyAPI.app

app.registerExtension({
  name: 'StoryDirector.Console',
  async nodeCreated(node) {
    if (node.comfyClass !== 'StoryDirector') return
    const q = (name) => node.widgets?.find((w) => w.name === name)
    const hidden = () => q('director_state')
    const read = () => { try { return JSON.parse(hidden()?.value || '{}') } catch { return { assets: [] } } }
    const write = (state) => { const w = hidden(); if (w) { w.value = JSON.stringify(state); w.callback?.(w.value) }; node.graph?.setDirtyCanvas(true, true) }
    const set = (name, value) => { const w = q(name); if (w) { w.value = value; w.callback?.(value) } }
    const panel = document.createElement('div')
    panel.style.cssText = 'padding:10px;background:#171b22;color:#e8edf5;font:13px sans-serif;min-width:650px;max-height:560px;overflow:auto'
    const title = document.createElement('h3'); title.textContent = '故事导演 · 本地分镜工作台'; title.style.color = '#8bd5ff'; panel.append(title)
    const tabs = document.createElement('div'); tabs.style.cssText = 'display:flex;gap:4px;flex-wrap:wrap;margin-bottom:8px'
    const body = document.createElement('div'); panel.append(tabs, body)
    const names = ['故事', '素材', '镜头偏好', '本地LLM', '提示词']
    const buttons = {}; const views = {}
    names.forEach((name) => { const b = document.createElement('button'); b.textContent = name; b.onclick = () => { names.forEach(n => { views[n].style.display = n === name ? 'block' : 'none'; buttons[n].style.background = n === name ? '#27627f' : '' }) }; buttons[name] = b; tabs.append(b); const v = document.createElement('section'); v.style.display = 'none'; views[name] = v; body.append(v) })
    const row = (parent, label, name, type = 'text', choices = null) => { const wrap = document.createElement('label'); wrap.style.cssText = 'display:block;margin:6px 0'; wrap.textContent = label; let el; if (choices) { el = document.createElement('select'); choices.forEach(x => { const o = document.createElement('option'); o.value = x; o.textContent = x; el.append(o) }) } else { el = document.createElement(type === 'area' ? 'textarea' : 'input'); if (type !== 'area') el.type = type; if (type === 'number') el.step = 'any'; if (type === 'area') el.rows = 4 } el.name = name; el.style.cssText = 'display:block;width:100%;box-sizing:border-box'; el.value = q(name)?.value ?? ''; el.onchange = () => set(name, type === 'number' ? Number(el.value) : el.value); wrap.append(el); parent.append(wrap); return el }
    row(views['故事'], '故事文本', 'story', 'area')
    row(views['故事'], '故事风格', 'style')
    row(views['故事'], '语言', 'language', 'text', ['中文', 'English', '中英双语'])
    row(views['故事'], '分段数量', 'segment_count', 'number')
    row(views['故事'], '单段时长（秒）', 'segment_duration', 'number')
    row(views['镜头偏好'], '景别、机位、运动、节奏等', 'camera_preferences', 'area')
    row(views['本地LLM'], '运行模式', 'mode', 'text', ['确定性编排', '本地 LLM'])
    row(views['本地LLM'], 'GGUF 模型', 'llm_model', 'text')
    row(views['本地LLM'], '上下文长度', 'context_size', 'number')
    row(views['本地LLM'], 'GPU 层数（-1=全部）', 'gpu_layers', 'number')
    views['本地LLM'].append(Object.assign(document.createElement('p'), { textContent: '本地 LLM 仅通过 llama-cpp-python；确定性编排不需要模型。', style: 'color:#aab4c2' }))
    const assetBox = document.createElement('div'); views['素材'].append(assetBox)
    const assetPreview = (asset) => { const box = document.createElement('div'); box.style.cssText = 'width:110px;height:70px;overflow:hidden;background:#252c38'; const url = `/story-director/preview?path=${encodeURIComponent(asset.path || '')}`; let media; if (asset.type === 'image') media = document.createElement('img'); else if (asset.type === 'video') { media = document.createElement('video'); media.controls = true } else { media = document.createElement('audio'); media.controls = true }; media.src = url; media.style.cssText = 'max-width:100%;max-height:100%'; box.append(media); return box }
    const renderAssets = () => { assetBox.replaceChildren(); const state = read(); state.assets ||= []; state.assets.forEach((asset, i) => { const card = document.createElement('div'); card.style.cssText = 'display:grid;grid-template-columns:115px 1fr auto;gap:6px;align-items:center;border:1px solid #394454;padding:5px;margin:5px 0'; card.append(assetPreview(asset)); const fields = document.createElement('div'); const name = row(fields, '名称', 'asset-name'); name.value = asset.name || ''; const role = row(fields, '语义角色', 'asset-role', 'text', ['角色', '场景', '道具', '分镜', '音效', '音乐', '其他']); role.value = asset.role || '其他'; const desc = row(fields, '描述', 'asset-description'); desc.value = asset.description || ''; [name, role, desc].forEach(x => x.onchange = () => { asset.name = name.value.slice(0, 180); asset.role = role.value; asset.description = desc.value.slice(0, 2000); write(state) }); fields.append(Object.assign(document.createElement('small'), { textContent: asset.path || '' })); card.append(fields); const actions = document.createElement('div'); const enabled = document.createElement('input'); enabled.type = 'checkbox'; enabled.checked = asset.enabled !== false; enabled.title = '启用'; enabled.onchange = () => { asset.enabled = enabled.checked; write(state) }; const up = document.createElement('button'); up.textContent = '↑'; up.disabled = i === 0; up.onclick = () => { [state.assets[i - 1], state.assets[i]] = [state.assets[i], state.assets[i - 1]]; write(state); renderAssets() }; const down = document.createElement('button'); down.textContent = '↓'; down.disabled = i === state.assets.length - 1; down.onclick = () => { [state.assets[i + 1], state.assets[i]] = [state.assets[i], state.assets[i + 1]]; write(state); renderAssets() }; const del = document.createElement('button'); del.textContent = '删除'; del.onclick = async () => { if (confirm('同时删除 input/story_director 中的文件？')) await fetch('/story-director/delete', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({path: asset.path, remove_file: true}) }); state.assets.splice(i, 1); write(state); renderAssets() }; actions.append(enabled, up, down, del); card.append(actions); assetBox.append(card) }); if (!state.assets.length) assetBox.textContent = '暂无素材。导入后可编辑名称、角色、描述、顺序与启用状态。' }
    const importButton = document.createElement('button'); importButton.textContent = '导入素材'; importButton.onclick = () => { const input = document.createElement('input'); input.type = 'file'; input.multiple = true; input.accept = 'image/png,image/jpeg,image/webp,image/bmp,image/gif,video/mp4,video/quicktime,video/webm,video/x-matroska,video/x-msvideo,audio/wav,audio/mpeg,audio/flac,audio/mp4,audio/ogg'; input.onchange = async () => { for (const file of input.files) { const form = new FormData(); form.append('file', file, file.name); const response = await fetch('/story-director/upload', { method: 'POST', body: form }); const result = await response.json(); if (result.error) alert(result.error); else { const state = read(); state.assets = [...(state.assets || []), ...result.assets]; write(state) } } renderAssets() }; input.click() }
    const clear = document.createElement('button'); clear.textContent = '清空目录'; clear.onclick = () => { const state = read(); state.assets = []; write(state); renderAssets() }; views['素材'].prepend(importButton, clear)
    const override = row(views['提示词'], '提示词覆盖（留空则按模式编排）', 'prompt_override', 'area'); override.rows = 12
    views['提示词'].append(Object.assign(document.createElement('p'), { textContent: '输出严格包含每个镜头的 Visual、Action、Camera、Lighting、Audio 字段及递增时间码。', style: 'color:#aab4c2' }))
    buttons['故事'].click(); renderAssets(); node.addDOMWidget('director_console', '故事导演', panel, { getValue: () => hidden()?.value || '{}', setValue: renderAssets }); node.setSize([780, 620])
  },
})
