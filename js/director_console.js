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
function row(p,label,value,change,options=null,area=false){const r=E("label","display:grid;grid-template-columns:170px 1fr;gap:10px;align-items:start;margin:9px 0;color:#bbb");r.append(E("span","padding-top:7px",label));const c=options?E("select"):E(area?"textarea":"input");c.style.cssText="width:100%;box-sizing:border-box;background:#202329;color:#eee;border:1px solid #494f59;border-radius:4px;padding:7px";if(area)c.rows=5;if(options)options.forEach(v=>c.append(new Option(v,v)));c.value=value??"";c.onchange=()=>change(c.value);r.append(c);p.append(r);return c}
function prefText(p){return `景别：${p.shot_size||"根据剧情"}\n运镜：${p.camera_move||"根据剧情"}\n切镜：${p.cut_rhythm||"根据剧情"}\n转场：${p.transition||"随机"}\n音乐：${p.music_style||"禁止音乐 / No Music"}\n创作要求：${p.creative_req||"无特别要求"}\n详细程度：${p.detail_length||"标准 (350-500字)"}${p.custom?`\n自定义：${p.custom}`:""}`}
function renderAssets(n,p,s){s.assets??=[];const tools=E("div","display:flex;gap:8px;margin-bottom:12px");const list=E("div");const draw=()=>{list.replaceChildren();for(const kind of ["image","video","audio"]){const items=s.assets.map((a,i)=>[a,i]).filter(([a])=>a.type===kind);list.append(E("h3","color:#8fc7e8;border-bottom:1px solid #3b424d;padding-bottom:5px",`${kind==="image"?"🖼️ 图片":kind==="video"?"🎬 视频":"🎧 音频"}（${items.length}）`));items.forEach(([a,i])=>{const card=E("div","display:grid;grid-template-columns:145px 1fr 70px;gap:9px;background:#202329;border:1px solid #414955;border-radius:7px;padding:9px;margin:7px 0");const pv=E("div","height:100px;background:#111;display:flex;align-items:center;justify-content:center;overflow:hidden");const m=document.createElement(kind==="image"?"img":kind==="video"?"video":"audio");m.src=api.apiURL(`/story-director/preview?path=${encodeURIComponent(a.path||"")}`);m.style.cssText="max-width:100%;max-height:100%";if(kind!=="image")m.controls=true;pv.append(m);card.append(pv);const f=E("div");row(f,"名称",a.name,v=>{a.name=v;save(n,s)});row(f,"类型",a.role||"其他",v=>{a.role=v;save(n,s)},TYPES[kind]);row(f,"描述",a.description||"",v=>{a.description=v;save(n,s)},null,true);f.append(E("small","color:#7896ae",a.path||""));card.append(f);const ac=E("div","display:flex;flex-direction:column;gap:5px");const en=document.createElement("input");en.type="checkbox";en.checked=a.enabled!==false;en.onchange=()=>{a.enabled=en.checked;save(n,s);draw()};ac.append(en,B("↑",()=>{if(i)[s.assets[i-1],s.assets[i]]=[s.assets[i],s.assets[i-1]];save(n,s);draw()}),B("↓",()=>{if(i<s.assets.length-1)[s.assets[i+1],s.assets[i]]=[s.assets[i],s.assets[i+1]];save(n,s);draw()}),B("删除",async()=>{if(!confirm("删除该素材及 input/story_director 中的副本？"))return;await api.fetchApi("/story-director/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({path:a.path,remove_file:true})});s.assets.splice(i,1);save(n,s);draw()}));card.append(ac);list.append(card)})}const intro=s.assets.filter(a=>a.enabled!==false).map((a,i)=>`${a.type==="image"?"图片":a.type==="video"?"视频":"音频"}${i+1} = ${a.name}${a.description?`（${a.description}）`:""}`).join("\n");const ta=row(list,"传给 LLM 的素材描述",intro,()=>{},null,true);ta.readOnly=true};tools.append(B("➕ 导入素材",()=>{const x=document.createElement("input");x.type="file";x.multiple=true;x.accept="image/*,video/*,audio/*";x.onchange=async()=>{for(const file of x.files){const fd=new FormData();fd.append("file",file,file.name);const r=await api.fetchApi("/story-director/upload",{method:"POST",body:fd});const d=await r.json();if(!r.ok)alert(d.error||"导入失败");else s.assets.push(...(d.assets||[]))}save(n,s);draw()};x.click()}),B("清空列表",()=>{if(confirm("只清空列表，保留托管文件？")){s.assets=[];save(n,s);draw()}}));p.append(tools,list);draw()}
function renderConfig(n,p){row(p,"运行模式",get(n,"mode"),v=>set(n,"mode",v),["拆解模式 (Decompose)","生成模式 (Generate)","离线预览"]);for(const [label,key] of [["故事风格","story_style"],["分段数量","segment_count"],["GGUF 模型","llm_model"]])row(p,label,get(n,key),v=>set(n,key,v),Array.from(W(n,key)?.options?.values||[]));row(p,"每段时长（秒）",get(n,"segment_duration"),v=>set(n,"segment_duration",Number(v)));row(p,"输出语言",get(n,"prompt_lang"),v=>set(n,"prompt_lang",v),["中文 [ZH]","英文 [EN]"]);p.append(E("h3","color:#8fc7e8;margin-top:20px","本地 LLM（llama-cpp-python）"));row(p,"上下文长度",get(n,"context_size"),v=>set(n,"context_size",Number(v)));row(p,"GPU 层数（-1=全部）",get(n,"gpu_layers"),v=>set(n,"gpu_layers",Number(v)));row(p,"随机种子",get(n,"seed"),v=>set(n,"seed",Number(v)))}
function renderPrefs(n,p,s){s.preference??={};const labels={shot_size:"景别偏好",camera_move:"运镜偏好",cut_rhythm:"切镜节奏",transition:"转场偏好",music_style:"音乐风格",creative_req:"创作要求",detail_length:"详细描述"};for(const [k,l] of Object.entries(labels))row(p,l,s.preference[k]||PREFS[k][0],v=>{s.preference[k]=v;save(n,s);set(n,"preference",prefText(s.preference))},PREFS[k]);row(p,"自定义镜头语言",s.preference.custom||"",v=>{s.preference.custom=v;save(n,s);set(n,"preference",prefText(s.preference))},null,true)}
async function renderResult(n,p){const ta=row(p,"完整 H3 剧本",get(n,"prompt_override"),v=>set(n,"prompt_override",v),null,true);ta.rows=22;const bar=E("div","display:flex;gap:8px");bar.append(B("读取最近结果",async()=>{const r=await api.fetchApi("/story-director/last-processed");const d=await r.json();if(d.script){ta.value=d.script;set(n,"prompt_override",d.script)}}),B("复制",()=>navigator.clipboard.writeText(ta.value||"")),B("清空覆盖",()=>{ta.value="";set(n,"prompt_override","")}));p.append(bar)}
function modal(n,id,title){document.querySelector(".storydirector-modal")?.remove();const s=Object.assign({assets:[],preference:{}},state(n));const o=E("div","position:fixed;inset:0;background:#000b;z-index:10000;display:flex;align-items:center;justify-content:center");o.className="storydirector-modal";const d=E("section","width:860px;max-height:90vh;background:#191b20;border:1px solid #464c56;border-radius:9px;display:flex;flex-direction:column;box-shadow:0 20px 70px #000");const h=E("header","display:flex;padding:17px 20px;border-bottom:1px solid #3a3f48");h.append(E("strong","font-size:18px;color:#eee;flex:1",title),B("✕",()=>o.remove()));const c=E("main","padding:16px 20px;overflow:auto;min-height:390px;color:#ddd");if(id==="assets")renderAssets(n,c,s);else if(id==="config")renderConfig(n,c);else if(id==="prefs")renderPrefs(n,c,s);else if(id==="result")renderResult(n,c);else c.innerHTML="<h3>使用步骤</h3><ol><li>在节点的故事内容框输入故事。</li><li>导入并描述参考素材。</li><li>配置拆解模式、本地 GGUF 和镜头偏好。</li><li>运行节点生成完整 H3 剧本。</li><li>在分段结果编辑中读取、修改或复制结果。</li></ol><p>本节点不编码、不采样、不解码、不保存视频。</p>";const f=E("footer","display:flex;justify-content:flex-end;padding:12px 20px;border-top:1px solid #3a3f48");f.append(B("完成",()=>o.remove()));d.append(h,c,f);o.append(d);document.body.append(o)}
function insertAssetName(node, name) {
  const story = W(node, "story");
  if (!story) return;
  const current = String(story.value || "");
  const separator = current && !/\s$/.test(current) ? " " : "";
  set(node, "story", current + separator + name);
}

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
      for (const name of ["prompt_override", "preference", "director_state"]) {
        const hidden = W(node, name);
        if (hidden) { hidden.hidden = true; hidden.computeSize = () => [0, -4]; }
      }
      const body = E("div", "background:#191b20;padding:4px");
      const toolbar = E("div", "display:grid;grid-template-columns:1fr 1fr;gap:6px;padding:5px");
      PANELS.forEach(([id, label]) => toolbar.append(B(label, () => modal(node, id, label))));
      body.append(toolbar, createAssetWindow(node));
      const dom = node.addDOMWidget("storydirector_console", "StoryDirector", body, { serialize:false, hideOnZoom:false });
      dom.computeSize = () => [node.size?.[0] || 560, 310];
      node.setSize([590, 690]);
      return result;
    };
    const oldConfigured = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      const result = oldConfigured?.apply(this, arguments);
      setTimeout(() => this.__storyDirectorRenderAssets?.(), 0);
      return result;
    };
  }
});
