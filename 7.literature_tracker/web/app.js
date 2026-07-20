// Plant Virus Literature Hub - Dashboard + Tabs
let papers=[], stats={}, cat='', page=1, PAGE=20;
let searchResults=[], _loaded={search:false,monthly:false,historical:false};
let _monthIndex={}, _trendChart=null;

// ── Init ──
(async function(){
  try{
    let sr=await fetch('data/stats.json');stats=await sr.json();
    document.getElementById('mTotal').textContent=stats.total?.toLocaleString()||'0';
    document.getElementById('mAI').textContent=stats.ai_summarized?.toLocaleString()||'0';
    document.getElementById('mCats').textContent=stats.by_category?Object.keys(stats.by_category).length:'-';
    document.getElementById('mUpdate').textContent=(stats.last_updated||'').substring(0,10);
    let yr=await fetch('data/index.json');let yi=await yr.json();
    document.getElementById('mYear').textContent=yi.length?yi[0].year+'-'+yi[yi.length-1].year:'-';
    renderCharts();
    loadLatestPapers();
    loadWeeklyDigest();
    // Preload for tabs
    for(let y of yi.slice(0,5)){
      try{let r=await fetch('data/'+y.year+'.json');papers=papers.concat(await r.json())}catch(e){}
    }
    let seen=new Set();papers=papers.filter(p=>{let k=p.pmid||p.doi||(p.title||'').substring(0,80);if(seen.has(k))return false;seen.add(k);return true});
  }catch(e){document.getElementById('latestPapers').innerHTML='<div class=empty>No data. Run <code>python pipeline.py auto --days 7</code> first.</div>'}
})();

// ── Charts ──
function renderCharts(){
  if(!stats.by_year)return;
  let ys=Object.keys(stats.by_year).sort().slice(-15);
  new Chart(document.getElementById('chartYear'),{type:'bar',data:{labels:ys,datasets:[{label:'Papers',data:ys.map(y=>stats.by_year[y]),backgroundColor:'#2e86c1',borderRadius:3}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{font:{size:9},maxTicksLimit:15}}}}});
  let ce=Object.entries(stats.by_category||{}).sort((a,b)=>b[1]-a[1]).slice(0,10);
  let cls=['#1a3a5c','#2f6848','#a07828','#2a5485','#6b4c8c','#c44e52','#5c8a4c','#8c5c22','#2f6848','#1a3a5c'];
  new Chart(document.getElementById('chartCat'),{type:'bar',data:{labels:ce.map(e=>e[0]),datasets:[{label:'Papers',data:ce.map(e=>e[1]),backgroundColor:ce.map((_,i)=>cls[i%cls.length]),borderRadius:3}]},options:{indexAxis:'y',responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{font:{size:9}}}}}});
}

// ── Latest Papers ──
async function loadLatestPapers(){
  try{
    let yi=await(await fetch('data/index.json')).json();
    let all=[];
    for(let y of yi.slice(0,3)){  // 3 most recent years
      try{let r=await fetch('data/'+y.year+'.json');all=all.concat(await r.json())}catch(e){}
    }
    all.sort((a,b)=>(b.year||0)-(a.year||0));
    all=all.slice(0,20);
    let h='<table><thead><tr><th style=width:70px>Journal/Year</th><th>Title & AI Extraction</th></tr></thead><tbody>';
    all.forEach(p=>{
      let cats=(p.categories||[]).slice(0,2).map(c=>'<span style="display:inline-block;padding:1px 6px;border-radius:10px;font-size:9px;background:var(--blue4);color:var(--blue2);margin:2px">'+c+'</span>').join(' ');
      let jq=p.journal_quality||'lo',jb=jq==='high'?'jb-hi':jq==='medium'?'jb-md':'jb-lo';
      let aid='abs_'+p.pmid;
      h+='<tr><td><span class="journal-badge '+jb+'">'+(p.journal||'?').substring(0,22)+'</span><br><span style="font-size:10px;color:var(--ink3)">'+p.year+'</span></td>';
      h+='<td><a class="paper-title" href="https://pubmed.ncbi.nlm.nih.gov/'+(p.pmid||'')+'" target="_blank">'+esc(p.title||'')+'</a><br><span style="font-size:10px;color:var(--ink3)">'+esc((p.first_author||'')+' '+(p.authors||'').substring(0,50))+'</span><br>'+cats;
      if(p.ai_done||p.virus_name)h+=aiCard(p);
      if(p.abstract)h+='<div class="abs-pv" id="'+aid+'">'+esc(p.abstract)+'</div><span class="abs-tg" onclick="toggleAbs(\''+aid+'\')">Show abstract</span>';
      h+='</td></tr>';
    });
    h+='</tbody></table>';
    document.getElementById('latestPapers').innerHTML=h;
  }catch(e){document.getElementById('latestPapers').innerHTML='<div class=empty>Error loading latest papers</div>'}
}

// ── Weekly AI Digest ──
async function loadWeeklyDigest(){
  try{
    let idx=await(await fetch('data/weekly/index.json')).json();
    if(!idx.length){document.getElementById('weeklyDigest').innerHTML='<div class=empty>No weekly digests yet. Run <code>python pipeline.py digest-weekly</code></div>';return}
    let h='';
    for(let w of idx.slice(0,4)){
      let d=await(await fetch('data/weekly/'+w.file)).json();
      h+='<div style="border:1px solid var(--rule);border-radius:var(--r2);padding:16px;margin-bottom:12px">';
      h+='<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px"><strong style="color:var(--blue);font-size:15px">'+d.week+'</strong><span style="font-size:11px;color:var(--ink3)">'+d.start+' ~ '+d.end+' · '+d.total_new+' papers</span></div>';
      if(d.ai_summary)h+='<div class="ai-digest">'+esc(d.ai_summary)+'</div>';
      else h+='<div style="font-size:12px;color:var(--ink3)">AI summary pending — <a href="#" onclick="return false">run digest-weekly with LLM key</a></div>';
      h+='</div>';
    }
    document.getElementById('weeklyDigest').innerHTML=h;
  }catch(e){document.getElementById('weeklyDigest').innerHTML='<div class=empty>No weekly digests available</div>'}
}

// ── AI Card ──
const AI_FIELDS=[['virus_name','病毒'],['overview','概要'],['host_plant','宿主'],['symptoms','症状'],['vector','媒介'],['location','地点'],['methods','方法'],['results','结果'],['discussion','讨论'],['is_review','类型']];
function aiCard(p){
  let rows='';
  for(let [k,label] of AI_FIELDS){
    let v=p[k];if(v&&v!=='未提及')rows+='<div class="ai-row"><span class="ai-label">'+label+'</span><span>'+esc(v)+'</span></div>';
  }
  return rows?'<div class="ai-card">'+rows+'</div>':'';
}

// ── Tabs ──
function switchTab(t){
  document.querySelectorAll('.tab').forEach(el=>el.classList.toggle('active',el.textContent.trim().toLowerCase().includes(t)));
  ['search','monthly','historical'].forEach(n=>{let el=document.getElementById('tab-'+n);if(el)el.style.display=n===t?'block':'none'});
  if(t==='search'&&!_loaded.search){_loaded.search=true;loadSearchTab()}
  if(t==='monthly'&&!_loaded.monthly){_loaded.monthly=true;loadMonthly()}
  if(t==='historical'&&!_loaded.historical){_loaded.historical=true;loadHistorical()}
}

// ── Full Search Tab ──
function loadSearchTab(){
  let cc={};papers.forEach(p=>{(p.categories||[]).forEach(c=>cc[c]=(cc[c]||0)+1)});
  let h='<span class="chip on" onclick="cat=\'\';renderTrack()">All ('+papers.length+')</span>';
  let sorted=Object.keys(cc).sort((a,b)=>cc[b]-cc[a]);
  for(let c of sorted)h+='<span class="chip'+(cat===c?' on':'')+'" onclick="cat=cat===c?\'\':c;renderTrack()">'+c+' ('+cc[c]+')</span>';
  document.getElementById('catChips').innerHTML=h;
  // Populate year dropdown
  let years={};papers.forEach(p=>{let y=p.year;if(y)years[y]=(years[y]||0)+1});
  let sf=document.getElementById('sYear');
  Object.keys(years).sort().reverse().forEach(y=>{let o=document.createElement('option');o.value=y;o.textContent=y+' ('+years[y]+')';sf.appendChild(o)});
  renderTrack();
}
function renderTrack(){
  let f=[...papers].filter(p=>p.title&&p.title.trim());
  if(cat)f=f.filter(p=>(p.categories||[]).includes(cat));
  let s=document.getElementById('sSearch').value.toLowerCase();
  if(s)f=f.filter(p=>(p.title+' '+p.authors+' '+p.journal+' '+(p.keyword_hits||[]).join(' ')).toLowerCase().includes(s));
  let y=document.getElementById('sYear').value;if(y)f=f.filter(p=>String(p.year)===y);
  document.getElementById('resultCount').textContent=f.length+' papers';
  document.querySelectorAll('#catChips .chip').forEach(el=>{
    let c=el.textContent.split(' (')[0];el.classList.toggle('on',cat===c||(!cat&&c==='All'));
  });
  if(!f.length){document.getElementById('paperList').innerHTML='<div class=empty>No papers match.</div>';document.getElementById('pagination').innerHTML='';return}
  let tp=Math.ceil(f.length/PAGE),st=(page-1)*PAGE,pg=f.slice(st,st+PAGE);
  let pgH='';for(let i=1;i<=Math.min(tp,10);i++)pgH+='<button class="'+(i===page?'on':'')+'" onclick="page='+i+';renderTrack();window.scrollTo(0,600)">'+i+'</button>';
  document.getElementById('pagination').innerHTML=pgH;
  let h='<table><thead><tr><th style=width:70px>Journal/Year</th><th>Title & AI Extraction</th></tr></thead><tbody>';
  pg.forEach(p=>{
    let cats=(p.categories||[]).slice(0,3).map(c=>'<span style="display:inline-block;padding:1px 6px;border-radius:10px;font-size:9px;background:var(--blue4);color:var(--blue2);margin:2px">'+c+'</span>').join(' ');
    let jq=p.journal_quality||'lo',jb=jq==='high'?'jb-hi':jq==='medium'?'jb-md':'jb-lo';
    let aid='sabs_'+p.pmid;
    h+='<tr><td><span class="journal-badge '+jb+'">'+(p.journal||'?').substring(0,22)+'</span><br><span style="font-size:10px;color:var(--ink3)">'+p.year+'</span></td>';
    h+='<td><a class="paper-title" href="https://pubmed.ncbi.nlm.nih.gov/'+(p.pmid||'')+'" target="_blank">'+esc(p.title||'')+'</a><br><span style="font-size:10px;color:var(--ink3)">'+esc((p.first_author||'')+' '+(p.authors||'').substring(0,50))+'</span><br>'+cats;
    if(p.ai_done||p.virus_name)h+=aiCard(p);
    if(p.abstract)h+='<div class="abs-pv" id="'+aid+'">'+esc(p.abstract)+'</div><span class="abs-tg" onclick="toggleAbs(\''+aid+'\')">Show abstract</span>';
    h+='</td></tr>';
  });
  h+='</tbody></table>';
  document.getElementById('paperList').innerHTML=h;
}

// ── Monthly Archive ──
async function loadMonthly(){
  try{
    let idx=await(await fetch('data/monthly/index.json')).json();
    idx.forEach(m=>_monthIndex[m.month]=m);
    let curY=new Date().getFullYear();
    let years=[];for(let y=curY;y>=2020;y--)years.push(String(y));
    document.getElementById('monthYear').innerHTML=years.map(y=>'<option>'+y+'</option>').join('');
    renderMonthGrid();
  }catch(e){}
}
function renderMonthGrid(){
  let y=document.getElementById('monthYear').value,g=document.getElementById('monthGrid'),h='';
  let yrTotal=0;
  for(let m=1;m<=12;m++){
    let mk=y+'-'+String(m).padStart(2,'0'),info=_monthIndex[mk];
    let mn=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][m-1];
    if(info){yrTotal+=info.count;h+='<div class="chip on" style="text-align:center;padding:10px;cursor:pointer" onclick="loadMonth(\''+mk+'\')">'+mn+'<br><span style="font-size:10px">'+info.count+'</span></div>';}
    else h+='<div style="text-align:center;padding:10px;border:1px dashed var(--rule);border-radius:14px;color:var(--ink3);font-size:11px;opacity:.4">'+mn+'</div>';
  }
  let yrSummary=document.getElementById('yearSummary');
  if(yrTotal>0){yrSummary.style.display='block';loadYearSummary(y).then(s=>{yrSummary.innerHTML='<strong>'+y+'</strong>: '+s.total.toLocaleString()+' papers · '+s.catCount+' categories · top: '+s.topCats.map(c=>'<span style="font-size:11px;margin:0 3px">'+c+'</span>').join('');});}
  else yrSummary.style.display='none';
  g.innerHTML=h;
}
async function loadYearSummary(y){
  try{let pl=await(await fetch('data/'+y+'.json')).json();let cats={};pl.forEach(p=>{(p.categories||[]).forEach(c=>cats[c]=(cats[c]||0)+1);});return{total:pl.length,catCount:Object.keys(cats).length,topCats:Object.entries(cats).sort((a,b)=>b[1]-a[1]).slice(0,5).map(([k,v])=>k+'('+v+')')}}
  catch(e){return{total:0,catCount:0,topCats:[]}}
}
async function loadMonth(mk){
  let info=_monthIndex[mk];if(!info)return;
  let d=await(await fetch('data/monthly/'+info.file)).json();
  document.getElementById('monthDigestCard').style.display='block';
  document.getElementById('monthDigestTitle').innerHTML=mk+' · '+d.total+' papers';
  let cats=Object.entries(d.by_category||{}).map(([k,v])=>'<span style="display:inline-block;padding:2px 8px;margin:2px;border-radius:10px;font-size:10px;background:var(--blue4);color:var(--blue2)">'+k+' '+v+'</span>').join('');
  let tops=(d.top_papers||[]).map(p=>{
    let aid='mo_abs_'+p.pmid;
    return '<div style="margin:6px 0;padding:4px 0;border-bottom:1px dotted var(--rule)"><a href="https://pubmed.ncbi.nlm.nih.gov/'+p.pmid+'" target=_blank>'+esc(p.title||'').substring(0,100)+'</a><div style="font-size:10px;color:var(--ink3);margin-top:2px">'+(p.journal||'')+' · '+p.year+(p.first_author?' · '+esc(p.first_author):'')+'</div>'+(p.abstract?'<div class="abs-pv" id="'+aid+'">'+esc(p.abstract)+'</div><span class="abs-tg" onclick="toggleAbs(\''+aid+'\')">Show abstract</span>':'')+'</div>';
  }).join('');
  let h='';if(d.ai_summary)h+='<div class="ai-digest">'+esc(d.ai_summary)+'</div>';
  h+='<div style="margin:10px 0">'+cats+'</div>';if(tops)h+='<div style="font-size:12px">'+tops+'</div>';
  document.getElementById('monthDigestContent').innerHTML=h;
  document.getElementById('monthDigestCard').scrollIntoView({behavior:'smooth'});
}

// ── Historical ──
async function loadHistorical(){
  let c=document.getElementById('historicalContent');
  try{
    let ms=await(await fetch('data/trend_milestones.json')).json();
    if(!ms.length){c.innerHTML='<div class=empty>No milestones detected.</div>';return}
    let byYear={};ms.forEach(m=>{let y=m.year||'?';(byYear[y]=byYear[y]||[]).push(m)});
    let h='<div style="position:relative;padding-left:20px;border-left:2px solid var(--blue3)">';
    for(let y of Object.keys(byYear).sort().reverse()){
      h+='<div style="margin-bottom:18px"><div style="font-size:16px;font-weight:700;color:var(--blue);margin-bottom:8px;margin-left:-8px">● '+y+' <span style="font-size:11px;color:var(--ink3);font-weight:400">('+byYear[y].length+')</span></div>';
      byYear[y].slice(0,15).forEach(m=>{
        let badge=m.type==='new_virus'?'<span class="journal-badge jb-hi">NEW VIRUS</span>':'<span class="journal-badge jb-md">MILESTONE</span>';
        h+='<div style="margin:6px 0 6px 8px;font-size:12px">'+badge+' <a href="https://pubmed.ncbi.nlm.nih.gov/'+m.pmid+'" target=_blank>'+esc(m.title||'').substring(0,95)+'</a>';
        if(m.journal)h+='<div style="font-size:10px;color:var(--ink3);margin-top:1px">'+m.journal+' · '+m.year+'</div>';
        if(m.note)h+='<div style="font-size:11px;color:var(--ink2);margin-top:2px">'+esc(m.note)+'</div>';
        h+='</div>';
      });
      h+='</div>';
    }
    h+='</div>';c.innerHTML=h;
  }catch(e){c.innerHTML='<div class=empty>No milestone data.</div>'}
}

// ── Manual Search ──
function updateSourceChips(){}
function copyPlantVirusQuery(){document.getElementById('mq').value='("novel virus"[Title/Abstract] OR "new virus"[Title/Abstract] OR "virus discovery"[Title/Abstract]) AND (plant[Title/Abstract] OR crop[Title/Abstract])'}
async function doSearch(){
  let q=document.getElementById('mq').value.trim(),df=document.getElementById('mdFrom').value,dt=document.getElementById('mdTo').value,mx=parseInt(document.getElementById('mMax').value);
  let src=[];document.querySelectorAll('#mSources input:checked').forEach(c=>src.push(c.value));
  if(!q){alert('Enter keywords');return}
  searchResults=[];
  for(let s of src){
    try{
      let papers=[];
      if(s==='pubmed')papers=await searchPubMed(q,df,dt,mx);
      else if(s==='biorxiv')papers=await searchBioRxiv(q,df,dt,mx);
      else if(s==='crossref')papers=await searchCrossref(q,df,dt,mx);
      else if(s==='openalex')papers=await searchOpenAlex(q,df,dt,mx);
      searchResults=searchResults.concat(papers);
    }catch(e){}
  }
  let seen={},merged=[];for(let p of searchResults){let k=(p.doi?'doi:'+p.doi.toLowerCase():p.pmid?'pmid:'+p.pmid:'title:'+(p.title||'').toLowerCase().replace(/[^a-z0-9]/g,'').slice(0,80));if(seen[k]){if((p.abstract||'').length>(seen[k].abstract||'').length)seen[k].abstract=p.abstract}else{seen[k]=p;merged.push(p)}}
  let qterms=q.toLowerCase().replace(/\[[^\]]*\]/g,' ').replace(/\b(and|or|not)\b/g,' ').split(/\s+/).filter(w=>w.length>3);
  merged.forEach(p=>{let txt=(p.title+' '+(p.abstract||'')).toLowerCase();p._score=qterms.filter(t=>txt.includes(t)).length});
  merged.sort((a,b)=>b._score-a._score);
  searchResults=merged;
  if(searchResults.length){
    document.getElementById('searchResults').style.display='block';
    document.getElementById('searchStats').innerHTML='<span style="font-size:14px;color:var(--blue)">'+searchResults.length+' unique papers</span> <button class="btn sm gold" onclick="downloadSearchJSON()" style="margin-left:12px">Download JSON</button> <button class="btn sm outline" onclick="exportSearchExcel()">Export XLSX</button>';
    document.getElementById('searchTable').innerHTML=searchResults.slice(0,50).map(p=>{
      let sc=p._score||0,scb=sc>=3?'jb-hi':sc>=1?'jb-md':'jb-lo';
      return '<tr><td><a class="paper-title" href="'+(p.doi?'https://doi.org/'+p.doi:'https://pubmed.ncbi.nlm.nih.gov/'+p.pmid)+'" target=_blank>'+esc(p.title||'').substring(0,100)+'</a></td><td><span style="font-size:10px">'+p.source+'</span></td><td>'+p.year+'</td><td><span class="journal-badge '+scb+'">'+sc+'</span></td><td><span style="font-size:10px;color:var(--ink3)">'+(p.journal||'').substring(0,30)+'</span></td></tr>';
    }).join('');
    document.getElementById('searchTable').innerHTML='<table><thead><tr><th>Title</th><th>Source</th><th>Year</th><th>Rel</th><th>Journal</th></tr></thead><tbody>'+document.getElementById('searchTable').innerHTML+'</tbody></table>';
  }
}
async function searchPubMed(q,df,dt,mx){
  let base='https://eutils.ncbi.nlm.nih.gov/entrez/eutils/',papers=[];
  let searchUrl=base+'esearch.fcgi?db=pubmed&term='+encodeURIComponent(q)+'&retmax='+mx+'&retmode=json&sort=date';
  if(df)searchUrl+='&mindate='+df.replace(/-/g,'/');if(dt)searchUrl+='&maxdate='+dt.replace(/-/g,'/');
  let sr=await fetch(searchUrl);let sd=await sr.json();
  let ids=sd.esearchresult.idlist||[];if(!ids.length)return[];
  let fr=await fetch(base+'efetch.fcgi?db=pubmed&id='+ids.join(',')+'&retmode=xml');
  let xml=await fr.text();let parser=new DOMParser();let doc=parser.parseFromString(xml,'text/xml');
  doc.querySelectorAll('PubmedArticle').forEach(a=>{papers.push({pmid:a.querySelector('PMID')?.textContent||'',title:a.querySelector('ArticleTitle')?.textContent||'',abstract:a.querySelector('AbstractText')?.textContent||'',journal:a.querySelector('Journal>Title')?.textContent||'',year:a.querySelector('PubDate>Year')?.textContent||'',first_author:a.querySelector('Author>LastName')?.textContent||'',source:'pubmed'});});
  return papers;
}
async function searchBioRxiv(q,df,dt,mx){
  let r=await fetch('https://api.biorxiv.org/details/biorxiv/'+(df||'2020-01-01')+'/'+(dt||new Date().toISOString().slice(0,10))+'/0');
  let d=await r.json(),papers=[],text=q.toLowerCase().replace(/\band\b/g,' ').split(/\s+/).filter(w=>w.length>2);
  (d.collection||[]).slice(0,mx).forEach(i=>{let txt=(i.title+' '+i.abstract).toLowerCase();if(text.some(w=>txt.includes(w)))papers.push({biorxiv_doi:i.doi,doi:i.doi,title:i.title,abstract:i.abstract,journal:'bioRxiv preprint',year:i.date?.substring(0,4),source:'biorxiv'});});
  return papers;
}
async function searchCrossref(q,df,dt,mx){
  let url='https://api.crossref.org/works?query='+encodeURIComponent(q)+'&rows='+mx+'&filter=type:journal-article';
  if(df)url+='&filter=from-pub-date:'+df;if(dt)url+='&filter=until-pub-date:'+dt;
  let r=await fetch(url);let d=await r.json();
  return (d.message?.items||[]).map(i=>({doi:i.DOI,title:(i.title||[])[0]||'',abstract:i.abstract||'',journal:(i['container-title']||[])[0]||'',year:i['published-print']?.['date-parts']?.[0]?.[0]||'',source:'crossref'}));
}
async function searchOpenAlex(q,df,dt,mx){
  let url='https://api.openalex.org/works?search='+encodeURIComponent(q)+'&per-page='+Math.min(mx,50);
  let flt=[];if(df)flt.push('from_publication_date:'+df);if(dt)flt.push('to_publication_date:'+dt);if(flt.length)url+='&filter='+flt.join(',');
  let r=await fetch(url);let d=await r.json();
  return (d.results||[]).map(i=>{let abs='';if(i.abstract_inverted_index){let words=[];for(let w in i.abstract_inverted_index)i.abstract_inverted_index[w].forEach(pos=>words[pos]=w);abs=words.join(' ')}return{doi:(i.doi||'').replace('https://doi.org/',''),title:i.title||i.display_name||'',abstract:abs,journal:i.host_venue?.display_name||i.primary_location?.source?.display_name||'',year:i.publication_year||'',source:'openalex'};});
}
function downloadSearchJSON(){
  let today=new Date().toISOString().slice(0,10);
  let arr=searchResults.map(p=>({pmid:p.pmid||'',doi:p.doi||'',title:p.title||'',abstract:p.abstract||'',journal:p.journal||'',year:parseInt(p.year)||0,pub_date:(p.year?p.year+'-01-01':''),first_author:p.first_author||'',authors:p.authors||'',source:p.source||'manual',source_strategy:'manual_search',categories:['General'],added_date:today,ai_done:false}));
  let blob=new Blob([JSON.stringify(arr,null,2)],{type:'application/json'});let a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='manual_search_'+today+'.json';a.click();
}
function exportSearchExcel(){
  let data=searchResults.map(p=>({DOI:p.doi||'',PMID:p.pmid||'',Title:p.title||'',Journal:p.journal||'',Year:p.year||'',Source:p.source||'',Score:p._score||0,Abstract:(p.abstract||'').substring(0,300)}));
  let wb=XLSX.utils.book_new(),ws=XLSX.utils.json_to_sheet(data);XLSX.utils.book_append_sheet(wb,ws,'Search');XLSX.writeFile(wb,'manual_search.xlsx');
}

// ── Export ──
function exportExcel(){
  let data=papers.map(p=>({PMID:p.pmid||'',DOI:p.doi||'',Title:p.title||'',Journal:p.journal||'',Year:p.year||'',Categories:(p.categories||[]).join(';'),Virus:p.virus_name||'',Taxonomy:p.taxonomy||'',Symptoms:p.symptoms||'',Host:p.host_plant||'',Location:p.location||'',Vector:p.vector||'',Transmission:p.transmission||'',Methods:p.methods||'',Results:p.results||'',Discussion:p.discussion||'',Abstract:(p.abstract||'').substring(0,300)}));
  let wb=XLSX.utils.book_new(),ws=XLSX.utils.json_to_sheet(data);XLSX.utils.book_append_sheet(wb,ws,'Papers');XLSX.writeFile(wb,'plant_virus_papers.xlsx');
}

// ── Helpers ──
function esc(s){if(!s)return'';let d=document.createElement('div');d.textContent=String(s);return d.innerHTML}
function toggleAbs(id){let el=document.getElementById(id);if(!el)return;el.classList.toggle('open');let tg=el.nextElementSibling;if(tg)tg.textContent=el.classList.contains('open')?'Hide abstract':'Show abstract'}
