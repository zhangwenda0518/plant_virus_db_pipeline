"""Simple web UI for Plant Virus RAG with SSE streaming + thinking display."""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

HTML_PAGE = r"""
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Plant Virus Knowledge Base</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
*{box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;background:#f5f5f5;color:#333;margin:0}
.hero{background:linear-gradient(135deg,#1a5276,#2e86c1);color:#fff;padding:32px 24px;margin-bottom:20px}
.hero h1{margin:0;font-size:22px}.hero p{margin:6px 0 0;opacity:.85;font-size:13px}
.main{max-width:900px;margin:0 auto;padding:0 16px}
.sbar{display:flex;gap:10px;margin-bottom:18px}
.sbar input{flex:1;padding:12px 18px;border:2px solid #e0e0e0;border-radius:8px;font-size:15px;outline:none}
.sbar input:focus{border-color:#2e86c1}
.sbar button{padding:12px 28px;background:#1a5276;color:#fff;border:none;border-radius:8px;font-size:15px;cursor:pointer}
.sbar button:hover{background:#2e86c1}
#answer{background:#fff;padding:20px;border-radius:8px;min-height:100px;margin-bottom:12px;white-space:pre-wrap;line-height:1.6}
#thinking{background:#f0f7ff;border:1px solid #b3d9ff;padding:10px 16px;border-radius:6px;margin-bottom:12px;font-size:13px;color:#1a5276;display:none}
#thinking .dot{animation:blink 1.5s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}
#citations{margin-bottom:12px}
.cite{background:#fff;padding:12px;border-radius:6px;margin-bottom:6px;font-size:13px;border-left:3px solid #2e86c1}
.cite .num{font-weight:700;color:#1a5276}
.cite .ama{color:#555}
.cite .chunk{color:#888;font-size:12px;margin-top:4px;border-top:1px solid #eee;padding-top:4px}
#meta{font-size:12px;color:#888;margin-bottom:8px}
.examples{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:20px}
.examples a{font-size:12px;color:#666;text-decoration:none;background:#fff;padding:5px 12px;border-radius:14px;border:1px solid #e0e0e0;cursor:pointer}
</style>
</head>
<body>
<script src="/lib/site-nav.js?v=2"></script>

<div class="hero"><h1>Plant Virus RAG</h1><p>33K papers (229K chunks) + DPV &amp; ICTV structured records. QA / Planning / Meta routing with DeepSeek V4 Pro reasoning.</p></div>
<div class="main">
<div class="sbar">
<input id="query" placeholder="Ask anything about plant viruses..." onkeydown="if(event.key===\"Enter\")search()">
<select id="model" style="padding:12px;border:2px solid #e0e0e0;border-radius:8px;font-size:14px;background:#fff"><option value="deepseek-v4-flash">V4 Flash (fast)</option><option value="deepseek-v4-pro">V4 Pro (reasoning)</option></select><select id="mode" style="padding:12px;border:2px solid #e0e0e0;border-radius:8px;font-size:14px;background:#fff" onchange="search()"><option value="rag">RAG Knowledge Base</option><option value="llm">Bare LLM</option><option value="hybrid">Hybrid (RAG+LLM)</option></select><button onclick="search()">Search</button>
</div>
<div class="examples">
<a onclick="setQuery(&quot;What is tomato yellow leaf curl virus?&quot;)">What is TYLCV?</a>
<a onclick="setQuery(&quot;How to control whitefly-transmitted geminiviruses?&quot;)">Control geminiviruses</a>
<a onclick="setQuery(&quot;Design a surveillance plan for Rice stripe virus&quot;)">Surveillance plan</a>
<a onclick="setQuery(&quot;How many virus records are in the database?&quot;)">DB stats</a>
<a onclick="setQuery(&quot;Who are you?&quot;)">Who are you?</a>
</div>
<div id="meta"></div>
<div id="thinking"></div>
<div id="answer"></div>
<div id="citations"></div>
</div>
<script>
const STAGES=["Retrieving relevant papers...","Reranking candidates...","DeepSeek V4 Pro reasoning...","Generating answer..."];
let stageIdx=0,stageTimer=null,answerText="",citations=[];

/* 统一 HTML 转义：所有进入 innerHTML 的服务端字段（citation 标题/AMA 引用/分片文本）必须先过这里 */
function esc(t){return String(t==null?"":t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;')}
function fidelityLabel(v){if(!v)return "n/a";if(v.fidelity_score==null)return "unavailable";return (v.fidelity_score*100).toFixed(0)+"%"+(v.is_reliable?"":" (low)")}

function updateThinking(text){
 const t=document.getElementById("thinking");
 t.style.display="block";
 t.innerHTML=text+STAGES.slice(0,Math.min(stageIdx,3)).map((s,i)=>i<stageIdx?"<br><span style=color:green>&#10003;</span> "+s:"<br><span class=dot>&#9679;</span> "+s).join("");
}

function startStages(){
 stageIdx=0;updateThinking("Processing: ");
 stageTimer=setInterval(()=>{stageIdx++;updateThinking("Processing: ");},3000);
}

function stopStages(){
 clearInterval(stageTimer);
 const t=document.getElementById("thinking");
 t.innerHTML="<span style=color:green>&#10003;</span> Done in "+(performance.now()-startTime).toFixed(0)+"ms";
 setTimeout(()=>{t.style.display="none"},3000);
}

function setQuery(q){document.getElementById("query").value=q;search()}

let startTime;
async function search(){
 const q=document.getElementById("query").value.trim();if(!q)return;
 document.getElementById("meta").innerHTML="";document.getElementById("answer").innerHTML="";document.getElementById("citations").innerHTML="";answerText="";citations=[];
 startTime=performance.now();startStages();
 try{
  const resp=await fetch("/knowledge/query",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query:q,top_k:7,mode:document.getElementById("mode").value,model:document.getElementById("model").value})});
  const d=await resp.json();
  stopStages();
  document.getElementById("meta").innerHTML="Type: <b>"+esc(d.task_type)+"</b> | Citations: "+d.citations.length+" | Valid: "+d.citation_valid+" | Fidelity: "+esc(fidelityLabel(d.answer_validation));
  document.getElementById("answer").textContent=d.answer;
  let html="";
  d.citations.forEach(c=>{
   html+="<div class=cite><span class=num>["+c.number+"]</span> <b>"+esc(c.title)+"</b><br><span class=ama>"+esc(c.ama)+"</span>";
   if(c.chunk_text&&c.chunk_text.length>1) html+="<div class=chunk>"+esc(c.chunk_text.substring(0,200))+"...</div>";
   html+="</div>";
  });
  document.getElementById("citations").innerHTML=html;
 }catch(e){stopStages();document.getElementById("answer").textContent="Error: "+e.message}
 }
</script>
<script src="/reference/i18n.js"></script>
<script>PVDB_i18n.init({navSelector:'nav'});</script>
</body></html>"""

@router.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE
