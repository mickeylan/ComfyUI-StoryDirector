import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE = "StoryDirector";
const PANELS = [["assets","📁 参考素材管理"],["config","📝 剧本拆解配置"],["prefs","🎯 镜头参数预设"],["result","📖 分段结果编辑"],["help","❓ 使用说明"]];
const TYPES = {image:["角色","场景","道具","分镜","其他"],video:["主体","运镜","特效","其他"],audio:["音色","音效","配乐","念白","其他"]};
const PREFS = {
  shot_size:["根据剧情","随机组合","远景为主","全景为主","中景为主","近景为主","特写为主"],
  camera_move:["根据剧情","随机组合","固定机位","推拉","摇移","俯仰","升降","环绕","跟拍","手持晃动","旋转","一镜到底"],
  cut_rhythm:["根据剧情","随机组合","一镜到底","2~5镜","5~9镜","9~13镜","13~18镜"],
  transition:["随机","硬切","叠化","淡入淡出","擦除"],
  music_style:["禁止音乐 / No Music","不指定 / Unspecified","史诗战争","动作追逐","紧张悬疑","恐怖惊悚","温馨治愈","浪漫爱情","悲伤抒情","轻松喜剧","古风武侠","科幻未来"],
  creative_req:["无特别要求","节奏紧凑","舒缓留白","情感细腻","明快轻松","多反转结局","开放式结局","强冲突"],
  detail_length:["标准 (350-500字)","精简 (200-350字)","详细 (500-800字)","超详细 (800-1200字)"]
};
const E=(tag,css="",text="")=>{const x=document.createElement(tag);x.style.cssText=css;x.textContent=text;return x};
const B=(text,fn)=>{const x=E("button","background:#292d35;color:#eee;border:1px solid #505866;border-radius:5px;padding:8px;cursor:pointer",text);x.onclick=fn;return x};
const W=(n,k)=>n.widgets?.find(x=>x.name===k);
const get=(n,k)=>W(n,k)?.value??"";
const set=(n,k,v)=>{const w=W(n,k);if(w){w.value=v;w.callback?.(v)}n.graph?.setDirtyCanvas(true,true)};
const state=n=>{try{return JSON.parse(get(n,"director_state")||"{}")}catch{return {assets:[]}}};
const save=(n,s)=>{set(n,"director_state",JSON.stringify(s));n.__storyDirectorRenderAssets?.()};
const downloadJson=(name,data)=>{const blob=new Blob([JSON.stringify(data,null,2)],{type:"application/json"});const url=URL.createObjectURL(blob);const a=document.createElement("a");a.href=url;a.download=name;a.click();URL.revokeObjectURL(url)};
function row(p,label,value,change,options=null,area=false){const r=E("label","display:grid;grid-template-columns:170px 1fr;gap:10px;align-items:start;margin:9px 0;color:#bbb");r.append(E("span","padding-top:7px",label));const c=options?E("select"):E(area?"textarea":"input");c.style.cssText="width:100%;box-sizing:border-box;background:#202329;color:#eee;border:1px solid #494f59;border-radius:4px;padding:7px";if(area)c.rows=5;if(options)options.forEach(v=>c.append(new Option(v,v)));c.value=value??"";if(options)c.onchange=()=>change(c.value);else c.oninput=()=>change(c.value);r.append(c);p.append(r);return c}
function prefText(p){return `景别：${p.shot_size||"根据剧情"}\n运镜：${p.camera_move||"根据剧情"}\n切镜：${p.cut_rhythm||"根据剧情"}\n转场：${p.transition||"随机"}\n音乐：${p.music_style||"禁止音乐 / No Music"}\n创作要求：${p.creative_req||"无特别要求"}\n详细程度：${p.detail_length||"标准 (350-500字)"}${p.custom?`\n自定义：${p.custom}`:""}`}
function configureUploadedAssets(assets) {
  return new Promise((resolve) => {
    const overlay=E("div","position:fixed;inset:0;background:#000c;z-index:12000;display:flex;align-items:center;justify-content:center");
    const dialog=E("section","width:780px;max-height:88vh;background:#191b20;border:1px solid #4b5563;border-radius:9px;display:flex;flex-direction:column;box-shadow:0 20px 70px #000");
    const head=E("header","padding:16px 20px;border-bottom:1px solid #3b424d");
    head.append(E("strong","display:block;color:#eee;font-size:18px","设置新素材"),E("div","margin-top:5px;color:#9aa5b3;font-size:12px","请给素材填写剧情中使用的名称，例如“女主小雨”“废弃车站”。之后可直接在故事中输入 @名称 引用。"));
    const content=E("main","padding:14px 20px;overflow:auto");
    assets.forEach((asset,index)=>{
      asset.role=asset.type==="image"?"角色":asset.type==="video"?"主体":"音色";
      asset.sourceName=asset.name||asset.path?.split("/").pop()||"";
      asset.name="";
      const card=E("div","display:grid;grid-template-columns:130px 1fr;gap:12px;padding:10px;margin:8px 0;background:#202329;border:1px solid #414955;border-radius:7px");
      const preview=E("div","height:105px;background:#111;display:flex;align-items:center;justify-content:center;overflow:hidden;border-radius:5px");
      if(asset.type==="image") { const image=document.createElement("img");image.src=api.apiURL(`/story-director/preview?path=${encodeURIComponent(asset.path)}`);image.style.cssText="width:100%;height:100%;object-fit:cover";preview.append(image); }
      else preview.append(E("div","font-size:32px",asset.type==="video"?"🎬":"🎧"));
      card.append(preview);
      const fields=E("div");
      const name=row(fields,"引用名称（@使用）",asset.name,value=>asset.name=value.trim());
      name.placeholder=asset.type==="image"?"必填，例如：女主小雨 / 反派老周":asset.type==="video"?"必填，例如：追逐参考 / 环绕运镜":"必填，例如：女主音色 / 雨声音效";
      row(fields,"素材用途",asset.role,value=>asset.role=value,TYPES[asset.type]);
      row(fields,"详细描述（给 LLM）",asset.description||"",value=>asset.description=value.trim(),null,true);
      fields.append(E("div","color:#718096;font-size:11px",`${index+1}. 原文件：${asset.sourceName}`));
      card.append(fields);content.append(card);
    });
    const foot=E("footer","display:flex;justify-content:flex-end;gap:8px;padding:12px 20px;border-top:1px solid #3b424d");
    const close=async(accept)=>{if(accept&&assets.some(asset=>!String(asset.name||"").trim())){alert("每个素材都必须填写角色/素材名称");return}if(!accept){for(const asset of assets)await api.fetchApi("/story-director/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({path:asset.path,remove_file:true})})}overlay.remove();resolve(accept?assets:null)};
    foot.append(B("取消并删除上传",()=>close(false)),B("确认添加",()=>close(true)));
    dialog.append(head,content,foot);overlay.append(dialog);document.body.append(overlay);
  });
}

function renderAssets(n,p,s){s.assets??=[];const tools=E("div","display:flex;gap:8px;margin-bottom:12px");const list=E("div");const draw=()=>{list.replaceChildren();for(const kind of ["image","video","audio"]){const items=s.assets.map((a,i)=>[a,i]).filter(([a])=>a.type===kind);list.append(E("h3","color:#8fc7e8;border-bottom:1px solid #3b424d;padding-bottom:5px",`${kind==="image"?"🖼️ 图片":kind==="video"?"🎬 视频":"🎧 音频"}（${items.length}）`));items.forEach(([a,i])=>{const card=E("div","display:grid;grid-template-columns:145px 1fr 70px;gap:9px;background:#202329;border:1px solid #414955;border-radius:7px;padding:9px;margin:7px 0");const pv=E("div","height:100px;background:#111;display:flex;align-items:center;justify-content:center;overflow:hidden");const m=document.createElement(kind==="image"?"img":kind==="video"?"video":"audio");m.src=api.apiURL(`/story-director/preview?path=${encodeURIComponent(a.path||"")}`);m.style.cssText="max-width:100%;max-height:100%";if(kind!=="image")m.controls=true;pv.append(m);card.append(pv);const f=E("div");row(f,"引用名称（@使用）",a.name,v=>{const old=a.name||"";a.name=v;if(old&&old!==v){const text=String(get(n,"story")||"").split(old).join(v);set(n,"story",text);n.__storyDirectorRenderStory?.()}save(n,s)});row(f,"类型",a.role||"其他",v=>{a.role=v;save(n,s)},TYPES[kind]);row(f,"详细描述（给 LLM）",a.description||"",v=>{a.description=v;save(n,s)},null,true);f.append(E("small","color:#7896ae",a.path||""));card.append(f);const ac=E("div","display:flex;flex-direction:column;gap:5px");const en=document.createElement("input");en.type="checkbox";en.checked=a.enabled!==false;en.onchange=()=>{a.enabled=en.checked;save(n,s);draw()};ac.append(en,B("↑",()=>{if(i)[s.assets[i-1],s.assets[i]]=[s.assets[i],s.assets[i-1]];save(n,s);draw()}),B("↓",()=>{if(i<s.assets.length-1)[s.assets[i+1],s.assets[i]]=[s.assets[i],s.assets[i+1]];save(n,s);draw()}),B("删除",async()=>{if(!confirm("删除该素材及 input/story_director 中的副本？"))return;await api.fetchApi("/story-director/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({path:a.path,remove_file:true})});s.assets.splice(i,1);save(n,s);draw()}));card.append(ac);list.append(card)})}const intro=s.assets.filter(a=>a.enabled!==false).map((a,i)=>`${a.type==="image"?"图片":a.type==="video"?"视频":"音频"}${i+1} = ${a.name}${a.description?`（${a.description}）`:""}`).join("\n");const ta=row(list,"传给 LLM 的素材描述",intro,()=>{},null,true);ta.readOnly=true};tools.append(B("➕ 导入素材",()=>{const x=document.createElement("input");x.type="file";x.multiple=true;x.accept="image/*,video/*,audio/*";x.onchange=async()=>{const uploaded=[];for(const file of x.files){const fd=new FormData();fd.append("file",file,file.name);const r=await api.fetchApi("/story-director/upload",{method:"POST",body:fd});const d=await r.json();if(!r.ok)alert(d.error||"导入失败");else uploaded.push(...(d.assets||[]))}if(uploaded.length){const configured=await configureUploadedAssets(uploaded);if(configured)s.assets.push(...configured)}save(n,s);draw()};x.click()}),B("导出目录",()=>downloadJson("story-director-assets.json",{assets:s.assets})),B("导入目录",()=>{const x=document.createElement("input");x.type="file";x.accept=".json,application/json";x.onchange=async()=>{try{const raw=JSON.parse(await x.files[0].text());const r=await api.fetchApi("/story-director/import",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({catalog:raw})});const d=await r.json();if(!r.ok)throw new Error(d.error||"导入失败");const flat=[];for(const [key,kind] of [["images","image"],["videos","video"],["audios","audio"]])for(const a of d.catalog?.[key]||[])flat.push({...a,type:kind,role:a.type||"其他"});s.assets=flat;save(n,s);draw()}catch(e){alert(String(e.message||e))}};x.click()}),B("清空列表",()=>{if(confirm("只清空列表，保留托管文件？")){s.assets=[];save(n,s);draw()}}));p.append(tools,list);draw()}
function renderConfig(n,p){row(p,"运行模式",get(n,"mode"),v=>set(n,"mode",v),["拆解模式 (Decompose)","生成模式 (Generate)","离线预览"]);for(const [label,key] of [["故事风格","story_style"],["分段数量","segment_count"],["GGUF 模型","llm_model"]])row(p,label,get(n,key),v=>set(n,key,v),Array.from(W(n,key)?.options?.values||[]));row(p,"每段时长（秒）",get(n,"segment_duration"),v=>set(n,"segment_duration",Number(v)));row(p,"输出语言",get(n,"prompt_lang"),v=>set(n,"prompt_lang",v),["中文 [ZH]","英文 [EN]"]);row(p,"自定义生成规则",get(n,"custom_rules"),v=>set(n,"custom_rules",v),null,true);row(p,"拆解后二次增强",get(n,"enhance")?"开启":"关闭",v=>set(n,"enhance",v==="开启"),["关闭","开启"]);p.append(E("h3","color:#8fc7e8;margin-top:20px","本地 LLM（llama-cpp-python）"));row(p,"上下文长度",get(n,"context_size"),v=>set(n,"context_size",Number(v)));row(p,"GPU 层数（-1=全部）",get(n,"gpu_layers"),v=>set(n,"gpu_layers",Number(v)));row(p,"最大输出 tokens",get(n,"max_tokens"),v=>set(n,"max_tokens",Number(v)));row(p,"temperature",get(n,"temperature"),v=>set(n,"temperature",Number(v)));row(p,"top_k",get(n,"top_k"),v=>set(n,"top_k",Number(v)));row(p,"top_p",get(n,"top_p"),v=>set(n,"top_p",Number(v)));row(p,"min_p",get(n,"min_p"),v=>set(n,"min_p",Number(v)));row(p,"repeat_penalty",get(n,"repeat_penalty"),v=>set(n,"repeat_penalty",Number(v)));row(p,"随机种子",get(n,"seed"),v=>set(n,"seed",Number(v)))}
function renderPrefs(n,p,s){s.preference??={};const labels={shot_size:"景别偏好",camera_move:"运镜偏好",cut_rhythm:"切镜节奏",transition:"转场偏好",music_style:"音乐风格",creative_req:"创作要求",detail_length:"详细描述"};for(const [k,l] of Object.entries(labels))row(p,l,s.preference[k]||PREFS[k][0],v=>{s.preference[k]=v;save(n,s);set(n,"preference",prefText(s.preference))},PREFS[k]);row(p,"自定义镜头语言",s.preference.custom||"",v=>{s.preference.custom=v;save(n,s);set(n,"preference",prefText(s.preference))},null,true)}
async function renderResult(n,p){let blocks=[];let selected=0;const ta=row(p,"完整 H3 剧本",get(n,"prompt_override"),v=>set(n,"prompt_override",v),null,true);ta.rows=18;const segment=E("textarea","width:100%;height:250px;box-sizing:border-box;margin-top:10px;background:#202329;color:#eee;border:1px solid #494f59;border-radius:4px;padding:8px");const status=E("span","color:#9db0c4;padding:7px");const split=()=>{blocks=Array.from((ta.value||"").matchAll(/\[SHOT_START\][\s\S]*?\[SHOT_END\]/g),m=>m[0]);selected=Math.min(selected,Math.max(0,blocks.length-1));segment.value=blocks[selected]||"";status.textContent=blocks.length?`第 ${selected+1}/${blocks.length} 段`:"无可识别分段"};const apply=()=>{if(!blocks.length)return;blocks[selected]=segment.value;ta.value=blocks.join("\n\n");set(n,"prompt_override",ta.value)};ta.onchange=()=>{set(n,"prompt_override",ta.value);split()};segment.onchange=apply;const bar=E("div","display:flex;gap:8px;align-items:center");bar.append(B("读取最近结果",async()=>{const r=await api.fetchApi("/story-director/last-processed");const d=await r.json();if(d.script){ta.value=d.script;set(n,"prompt_override",d.script);split()}}),B("◀",()=>{apply();selected=Math.max(0,selected-1);split()}),status,B("▶",()=>{apply();selected=Math.min(blocks.length-1,selected+1);split()}),B("复制本段",()=>navigator.clipboard.writeText(segment.value||"")),B("复制全部",()=>navigator.clipboard.writeText(ta.value||"")),B("清空覆盖",()=>{ta.value="";segment.value="";blocks=[];set(n,"prompt_override","");split()}));p.append(bar,segment);split()}
function modal(n,id,title){document.querySelector(".storydirector-modal")?.remove();const s=Object.assign({assets:[],preference:{}},state(n));const o=E("div","position:fixed;inset:0;background:#000b;z-index:10000;display:flex;align-items:center;justify-content:center");o.className="storydirector-modal";const d=E("section","width:860px;max-height:90vh;background:#191b20;border:1px solid #464c56;border-radius:9px;display:flex;flex-direction:column;box-shadow:0 20px 70px #000");const h=E("header","display:flex;padding:17px 20px;border-bottom:1px solid #3a3f48");h.append(E("strong","font-size:18px;color:#eee;flex:1",title),B("✕",()=>o.remove()));const c=E("main","padding:16px 20px;overflow:auto;min-height:390px;color:#ddd");if(id==="assets")renderAssets(n,c,s);else if(id==="config")renderConfig(n,c);else if(id==="prefs")renderPrefs(n,c,s);else if(id==="result")renderResult(n,c);else c.innerHTML="<h3>使用步骤</h3><ol><li>在节点的故事内容框输入故事。</li><li>导入并描述参考素材。</li><li>配置拆解模式、本地 GGUF 和镜头偏好。</li><li>运行节点生成完整 H3 剧本。</li><li>在分段结果编辑中读取、修改或复制结果。</li></ol><p>本节点不编码、不采样、不解码、不保存视频。</p>";const f=E("footer","display:flex;justify-content:flex-end;padding:12px 20px;border-top:1px solid #3a3f48");f.append(B("完成",()=>o.remove()));d.append(h,c,f);o.append(d);document.body.append(o)}
function storyText(editor) {
  let text="";
  editor.childNodes.forEach(child=>{text+=child.nodeType===Node.TEXT_NODE?child.textContent:(child.dataset?.assetName??child.textContent);});
  return text.replace(/\u00a0/g," ");
}
function assetToken(node, asset) {
  const colors={image:"#296f99",video:"#7a4fa3",audio:"#9a6b25"};
  const token=E("span",`display:inline-flex;align-items:center;justify-content:center;background:${colors[asset.type]};color:#fff;border:1px solid ${colors[asset.type]};border-radius:4px;margin:0 2px;white-space:nowrap;vertical-align:middle;overflow:hidden`);
  token.contentEditable="false";token.dataset.assetName=asset.name;token.title=[asset.name,asset.description].filter(Boolean).join("\n");
  if(asset.type==="image"){
    const image=document.createElement("img");image.src=api.apiURL(`/story-director/preview?path=${encodeURIComponent(asset.path||"")}`);image.alt="";image.style.cssText="width:34px;height:34px;object-fit:cover;display:block";token.append(image);
  }else{
    token.style.paddingLeft="5px";token.append(E("span","font-size:18px",asset.type==="video"?"🎬":"🎧"));
  }
  token.append(E("span","padding:2px 6px;font-size:12px;max-width:130px;overflow:hidden;text-overflow:ellipsis",asset.name));
  return token;
}
function renderStory(node, caret=null) {
  const editor=node.__storyEditor;if(!editor)return;const text=String(get(node,"story")||"");const assets=(state(node).assets||[]).filter(a=>a.enabled!==false&&a.name).sort((a,b)=>b.name.length-a.name.length);editor.replaceChildren();let i=0,last=0;while(i<text.length){const hit=assets.find(a=>text.startsWith(a.name,i));if(hit){if(i>last)editor.append(document.createTextNode(text.slice(last,i)));editor.append(assetToken(node,hit));i+=hit.name.length;last=i}else i++}if(last<text.length)editor.append(document.createTextNode(text.slice(last)));if(caret!==null){const sel=getSelection(),range=document.createRange();let remain=caret;for(const child of editor.childNodes){const len=child.nodeType===Node.TEXT_NODE?child.textContent.length:(child.dataset?.assetName||"").length;if(remain<=len){range.setStartAfter(child);range.collapse(true);break}remain-=len}sel.removeAllRanges();sel.addRange(range)}}
function caretOffset(editor){const sel=getSelection();if(!sel.rangeCount||!editor.contains(sel.anchorNode))return storyText(editor).length;const range=sel.getRangeAt(0).cloneRange();range.selectNodeContents(editor);range.setEnd(sel.anchorNode,sel.anchorOffset);const box=E("div");box.append(range.cloneContents());return storyText(box).length}
function insertAssetName(node,name){const editor=node.__storyEditor;if(!editor)return;const text=storyText(editor),pos=node.__storyCaret??caretOffset(editor);const left=text.slice(0,pos),right=text.slice(pos);const value=left+(left&&!/\s$/.test(left)?" ":"")+name+(right&&!/^\s/.test(right)?" ":"")+right;set(node,"story",value);renderStory(node,(left+(left&&!/\s$/.test(left)?" ":"")+name).length);editor.focus()}
function attachMentionMenu(node) {
  const input=node.__storyEditor;if(!input||input.__storyDirectorMentions)return;input.__storyDirectorMentions=true;let active=0,items=[],match=null,pos=0;
  const menu=E("div","position:fixed;z-index:11000;display:none;max-height:260px;overflow:auto;background:#202329;border:1px solid #566171;border-radius:6px;box-shadow:0 8px 25px #000;padding:4px");document.body.append(menu);const close=()=>{menu.style.display="none";items=[]};
  const choose=(asset)=>{const text=storyText(input),start=pos-match[0].length,value=text.slice(0,start)+asset.name+text.slice(pos);set(node,"story",value);renderStory(node,start+asset.name.length);input.focus();close()};
  const paint=()=>items.forEach((x,i)=>{x.button.style.borderColor=i===active?"#6db7e5":"transparent";x.button.style.background=i===active?"#2d3945":"transparent"});
  input.addEventListener("input",()=>{const text=storyText(input);set(node,"story",text);pos=caretOffset(input);match=text.slice(0,pos).match(/@([^\s@]*)$/);if(!match){close();return}const query=match[1].toLowerCase(),assets=(state(node).assets||[]).filter(a=>a.enabled!==false&&String(a.name||"").toLowerCase().includes(query));menu.replaceChildren();items=[];active=0;if(!assets.length){close();return}const rect=input.getBoundingClientRect();menu.style.left=`${rect.left}px`;menu.style.top=`${Math.min(innerHeight-360,rect.bottom+4)}px`;menu.style.width="auto";menu.style.maxWidth="460px";menu.style.display="grid";menu.style.gridTemplateColumns=`repeat(${Math.min(5,Math.max(1,assets.length))},74px)`;menu.style.gap="6px";assets.forEach(asset=>{const b=E("button","width:74px;height:96px;padding:4px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;background:transparent;color:#ddd;border:1px solid transparent;border-radius:6px;cursor:pointer");b.type="button";b.title=[asset.name,asset.description].filter(Boolean).join("\n");if(asset.type==="image"){const image=document.createElement("img");image.src=api.apiURL(`/story-director/preview?path=${encodeURIComponent(asset.path||"")}`);image.alt="";image.style.cssText="width:64px;height:58px;object-fit:cover;border-radius:4px;display:block";b.append(image)}else b.append(E("div","width:64px;height:58px;display:flex;align-items:center;justify-content:center;background:#111;border-radius:4px;font-size:28px",asset.type==="video"?"🎬":"🎧"));b.append(E("span","width:66px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px",asset.name));b.onclick=()=>choose(asset);b.onmousedown=e=>e.preventDefault();menu.append(b);items.push({asset,button:b})});paint()});
  input.addEventListener("keydown",e=>{if(!items.length)return;if(e.key==="ArrowDown"||e.key==="ArrowUp"){e.preventDefault();active=(active+(e.key==="ArrowDown"?1:-1)+items.length)%items.length;paint()}else if(e.key==="Enter"||e.key==="Tab"){e.preventDefault();choose(items[active].asset)}else if(e.key==="Escape"){e.preventDefault();close()}});input.addEventListener("keyup",()=>node.__storyCaret=caretOffset(input));input.addEventListener("mouseup",()=>node.__storyCaret=caretOffset(input));input.addEventListener("blur",()=>setTimeout(()=>{close();renderStory(node)},150));
}
function createStoryEditor(node){const wrap=E("section","margin:4px 8px 8px");wrap.append(E("div","font-size:12px;color:#bbb;margin-bottom:4px","📝 故事内容（输入 @ 引用素材）"));const editor=E("div","min-height:150px;max-height:300px;overflow:auto;white-space:pre-wrap;background:#23262d;color:#ddd;border:1px solid #4b535f;border-radius:6px;padding:9px;line-height:1.55");editor.contentEditable="true";editor.spellcheck=false;node.__storyEditor=editor;node.__storyDirectorRenderStory=()=>renderStory(node);renderStory(node);wrap.append(editor);return wrap}

function createAssetWindow(node) {
  const root = E("section", "background:#15181d;border:1px solid #39414c;border-radius:6px;margin:4px 8px 8px;padding:7px;min-height:112px");
  const header = E("div", "display:flex;align-items:center;margin-bottom:6px");
  const title = E("strong", "color:#8fc7e8;flex:1", "🗂️ 资产显示窗口");
  const count = E("span", "font-size:11px;color:#8b96a5");
  header.append(title, count);
  const grid = E("div", "display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;max-height:190px;overflow-y:auto");
  root.append(header, grid);

  const render = () => {
    const assets = state(node).assets || [];
    const enabled = assets.filter((asset) => asset.enabled !== false);
    count.textContent = `${enabled.length} 个已启用素材`;
    grid.replaceChildren();
    if (!enabled.length) {
      grid.append(E("div", "grid-column:1/-1;color:#77818f;padding:22px 8px;text-align:center", "暂无素材，请打开“参考素材管理”导入"));
      return;
    }
    enabled.forEach((asset) => {
      const card = E("button", "position:relative;height:86px;padding:0;overflow:hidden;background:#20252c;border:1px solid #444d59;border-radius:5px;cursor:pointer;color:#eee");
      card.type = "button";
      card.title = `点击插入素材名：${asset.name}\n${asset.description || ""}`;
      if (asset.type === "image") {
        const image = document.createElement("img");
        image.src = api.apiURL(`/story-director/preview?path=${encodeURIComponent(asset.path || "")}`);
        image.style.cssText = "width:100%;height:62px;object-fit:cover;display:block";
        card.append(image);
      } else {
        card.append(E("div", "height:62px;display:flex;align-items:center;justify-content:center;font-size:26px;background:#111", asset.type === "video" ? "🎬" : "🎧"));
      }
      card.append(E("div", "position:absolute;left:0;right:0;bottom:0;background:#111d;padding:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:11px", asset.name || asset.path));
      card.onclick = () => insertAssetName(node, asset.name || "");
      grid.append(card);
    });
  };
  node.__storyDirectorRenderAssets = render;
  render();
  return root;
}

app.registerExtension({
  name: "StoryDirector.Console",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== NODE) return;
    const oldCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = oldCreated?.apply(this, arguments);
      const node = this;
      for (const name of ["prompt_override", "preference", "custom_rules", "enhance", "llm_model", "context_size", "gpu_layers", "max_tokens", "temperature", "top_k", "top_p", "min_p", "repeat_penalty", "seed", "director_state"]) {
        const hidden = W(node, name);
        if (hidden) { hidden.hidden = true; hidden.computeSize = () => [0, -4]; }
      }
      const body = E("div", "background:#191b20;padding:4px");
      const toolbar = E("div", "display:grid;grid-template-columns:1fr 1fr;gap:6px;padding:5px");
      PANELS.forEach(([id, label]) => toolbar.append(B(label, () => modal(node, id, label))));
      body.append(toolbar, createStoryEditor(node), createAssetWindow(node));
      const nativeStory=W(node,"story");if(nativeStory){nativeStory.hidden=true;nativeStory.computeSize=()=>[0,-4]}
      setTimeout(() => attachMentionMenu(node), 0);
      const dom = node.addDOMWidget("storydirector_console", "StoryDirector", body, { serialize:false, hideOnZoom:false });
      dom.computeSize = () => [node.size?.[0] || 560, 500];
      node.setSize([620, 790]);
      return result;
    };
    const oldConfigured = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      const result = oldConfigured?.apply(this, arguments);
      setTimeout(() => {this.__storyDirectorRenderStory?.();this.__storyDirectorRenderAssets?.()}, 0);
      return result;
    };
  }
});
