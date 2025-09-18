// Basic state
let state = {
  messages: [],
  schemas: [],
  processedSystemPrompt: '',
};

function log(msg){
  const el = document.getElementById('eventLog');
  const ts = new Date().toISOString();
  el.textContent += `[${ts}] ${msg}\n`;
  el.scrollTop = el.scrollHeight;
}

// Tabs
for (const btn of document.querySelectorAll('.tab-button')){
  btn.addEventListener('click', ()=>{
    document.querySelectorAll('.tab-button').forEach(b=>b.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(btn.dataset.tab).classList.add('active');
  });
}

async function loadConfig(){
  const res = await fetch('/api/config');
  const data = await res.json();
  document.getElementById('cfgTargetBase').value = data.target_base_url || '';
  const headerTarget = document.getElementById('headerTargetBase');
  if (headerTarget) headerTarget.value = data.target_base_url || '';
  document.getElementById('cfgMsgDump').value = data.message_dump_path || '';
  document.getElementById('cfgToolDump').value = data.tool_dump_path || '';
  document.getElementById('cfgDisableStrict').checked = !!data.disable_strict_schemas;
  document.getElementById('cfgForceTool').checked = !!data.force_tool_calling;
}

async function saveConfig(e){
  e.preventDefault();
  const payload = {
    target_base_url: document.getElementById('cfgTargetBase').value.trim(),
    message_dump_path: document.getElementById('cfgMsgDump').value.trim() || null,
    tool_dump_path: document.getElementById('cfgToolDump').value.trim() || null,
    disable_strict_schemas: document.getElementById('cfgDisableStrict').checked,
    force_tool_calling: document.getElementById('cfgForceTool').checked,
  };
  const res = await fetch('/api/config',{method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
  const data = await res.json();
  document.getElementById('configStatus').textContent = JSON.stringify(data,null,2);
  log('Config updated');
}

async function parseTools(){
  const systemPrompt = document.getElementById('systemPrompt').value;
  const strict = document.getElementById('strictMode').checked;
  const res = await fetch('/api/parse-tools',{method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({system_prompt: systemPrompt, strict})});
  const data = await res.json();
  state.schemas = data.schemas || [];
  state.processedSystemPrompt = data.processed_system_prompt;
  document.getElementById('schemasDisplay').textContent = JSON.stringify(state.schemas,null,2);
  document.getElementById('processedPrompt').textContent = state.processedSystemPrompt;
  log('Tools parsed');
}

async function loadModels(){
  try {
    const res = await fetch('/v1/models');
    if (!res.ok){
      // fallback legacy path
      const res2 = await fetch('/api/v0/models');
      if (!res2.ok) throw new Error('Failed to load models');
      const data2 = await res2.json();
      document.getElementById('modelsDisplay').textContent = JSON.stringify(data2,null,2);
      return;
    }
    const data = await res.json();
    document.getElementById('modelsDisplay').textContent = JSON.stringify(data,null,2);
  } catch (e){
    document.getElementById('modelsDisplay').textContent = 'Error loading models';
  }
}

function renderMessages(){
  const container = document.getElementById('messages');
  container.innerHTML='';
  state.messages.forEach((m,i)=>{
    const div = document.createElement('div');
    div.className = 'message '+m.role;
    const header = `[${i}] ${m.role}` + (m.tool_calls?` tool_calls:${m.tool_calls.length}`:'');
    let content = m.content;
    if (Array.isArray(content)) content = content.map(c=>c.text||'').join('\n');
    div.textContent = header + '\n' + (content||'');
    container.appendChild(div);
  });
  container.scrollTop = container.scrollHeight;
}

function buildChatCompletionPayload(){
  // ensure system prompt first
  let messages = [...state.messages];
  if (!messages.some(m=>m.role==='system')){
    if (state.processedSystemPrompt){
      messages = [{role:'system', content: state.processedSystemPrompt}, ...messages];
    } else if (document.getElementById('systemPrompt').value.trim()){
      messages = [{role:'system', content: document.getElementById('systemPrompt').value.trim()}, ...messages];
    }
  }
  return { model:'dummy-model', messages, stream: document.getElementById('streamToggle').checked };
}

async function sendMessage(e){
  e.preventDefault();
  const role = document.getElementById('roleSelect').value;
  const content = document.getElementById('messageInput').value;
  if (!content.trim()) return;
  state.messages.push({role, content});
  document.getElementById('messageInput').value='';
  renderMessages();
  await runCompletion();
}

async function runCompletion(){
  const payload = buildChatCompletionPayload();
  log('Sending /v1/chat/completions');
  if (payload.stream){
    await streamChat(payload);
  } else {
    const res = await fetch('/v1/chat/completions',{method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
    const data = await res.json();
    handleCompletionResponse(data);
  }
}

function handleCompletionResponse(data){
  if (data.choices){
    data.choices.forEach(ch=>{
      if (ch.message){
        state.messages.push(ch.message);
      }
    });
    renderMessages();
  }
  document.getElementById('toolCallPreview').textContent = JSON.stringify(data,null,2);
}

async function streamChat(payload){
  const res = await fetch('/v1/chat/completions',{method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
  if (!res.body){
    log('Streaming not supported response');
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer='';
  let accumulated='';
  while(true){
    const {value, done} = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, {stream:true});
    const parts = buffer.split('\n\n');
    buffer = parts.pop();
    for(const part of parts){
      if (!part.startsWith('data: ')) continue;
      const datum = part.replace(/^data: /,'').trim();
      if (datum === '[DONE]'){ continue; }
      try{
        const obj = JSON.parse(datum);
        if (obj.choices){
          obj.choices.forEach(ch=>{
            const delta = ch.delta||{};
            if (delta.content){
              accumulated += delta.content;
            }
            if (delta.tool_calls){
              // naive merge: finalize at end
              accumulated += '\n[tool_calls emitted]\n';
            }
            if (ch.finish_reason){
              state.messages.push({role:'assistant', content: accumulated});
              renderMessages();
              accumulated='';
            }
          });
          document.getElementById('toolCallPreview').textContent = obj ? JSON.stringify(obj,null,2):'';
        }
      }catch(err){/* ignore parse errors */}
    }
  }
  if (accumulated){
    state.messages.push({role:'assistant', content: accumulated});
    renderMessages();
  }
}

function resetChat(){
  state.messages = [];
  renderMessages();
  document.getElementById('toolCallPreview').textContent='';
}

// Event bindings
 document.getElementById('parseToolsBtn').addEventListener('click', parseTools);
 document.getElementById('messageForm').addEventListener('submit', sendMessage);
 document.getElementById('resetChat').addEventListener('click', resetChat);
 document.getElementById('configForm').addEventListener('submit', saveConfig);

// Upstream apply & test
document.getElementById('upstreamForm').addEventListener('submit', async (e)=>{
  e.preventDefault();
  const val = document.getElementById('headerTargetBase').value.trim();
  if (!val) return;
  await fetch('/api/config',{method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({target_base_url: val})});
  document.getElementById('cfgTargetBase').value = val; // sync
  log('Updated upstream URL');
  await loadModels();
});

document.getElementById('testUpstream').addEventListener('click', async ()=>{
  const statusEl = document.getElementById('upstreamStatus');
  statusEl.textContent = 'Testing...';
  try {
    const res = await fetch('/api/test-upstream');
    const data = await res.json();
    if (data.ok){
      statusEl.textContent = `OK (${data.status_code}) ${data.latency_ms} ms`;
      statusEl.style.color = '#2ea043';
    } else {
      statusEl.textContent = `Fail ${data.status_code||''} ${data.error||''}`;
      statusEl.style.color = '#f85149';
    }
  } catch (e){
    statusEl.textContent = 'Error';
    statusEl.style.color = '#f85149';
  }
  await loadModels();
});

loadConfig();
renderMessages();
log('GUI loaded');
loadModels();
