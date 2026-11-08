const editor = document.querySelector('#editor');
const session = () => editor.contentWindow;
const post = data => session().postMessage(data, location.origin);
editor.addEventListener('load', () => {
  session().addEventListener('message', event => {
    if (event.origin !== location.origin) return;
    if (event.data?.type === 'trackpadModeUpdate') {
      trackpad = !!event.data.enabled;
      document.querySelector('#trackpad').setAttribute('aria-pressed', String(trackpad));
    }
  });
});
let sending = false;
async function chord(button) {
  if (sending) return;
  sending = true;
  const w = session();
  const key = button.dataset.key, code = button.dataset.code || key;
  const modifiers = [];
  if (button.dataset.ctrl) modifiers.push(['Control', 'ControlLeft']);
  if (button.dataset.alt) modifiers.push(['Alt', 'AltLeft']);
  if (button.dataset.shift) modifiers.push(['Shift', 'ShiftLeft']);
  const state = {ctrlKey:!!button.dataset.ctrl, altKey:!!button.dataset.alt, shiftKey:!!button.dataset.shift};
  const emit = (type,k,c) => w.dispatchEvent(new w.KeyboardEvent(type, {key:k,code:c,...state,bubbles:true,cancelable:true}));
  // The same synth/key-event path used by Selkies' built-in soft keyboard.
  post({type:'setSynth',value:true});
  await new Promise(resolve => setTimeout(resolve, 30));
  try {
    modifiers.forEach(([k,c]) => emit('keydown',k,c));
    emit('keydown',key,code);
    await new Promise(resolve => setTimeout(resolve, 60));
    emit('keyup',key,code);
    [...modifiers].reverse().forEach(([k,c]) => emit('keyup',k,c));
  } finally {
    post({type:'setSynth',value:false});
    sending = false;
  }
}
document.querySelectorAll('[data-key]').forEach(b => b.addEventListener('click', () => chord(b)));
document.querySelector('#keyboard').onclick = () => {
  const input = session().document.querySelector('#keyboard-input-assist');
  if (input) { input.value=''; input.focus(); }
};
let trackpad = false;
document.querySelector('#trackpad').onclick = event => {
  trackpad = !trackpad;
  post({type:trackpad?'control:trackpad':'control:touch'});
  event.currentTarget.setAttribute('aria-pressed', String(trackpad));
};
document.querySelector('#help').onclick = () => document.querySelector('#guide').showModal();
document.querySelectorAll('.close').forEach(b => b.onclick = () => b.closest('dialog').close());
document.querySelector('#files').onclick = () => { document.querySelector('#file-dialog').showModal(); loadFiles(); };
document.querySelector('#refresh').onclick = loadFiles;
document.querySelector('#upload').onclick = () => {
  document.querySelector('#file-dialog').close();
  const w = session();
  w.dispatchEvent(new w.CustomEvent('requestFileUpload'));
};
async function loadFiles() {
  const list = document.querySelector('#file-list');
  list.textContent='Loading files…';
  try {
    const response = await fetch('/design-files/', {cache:'no-store'});
    if (!response.ok) throw Error('Files could not be loaded. Try Refresh files.');
    const files = (await response.json()).filter(f => f.type==='file' && /\.(pes|svg|png|txt|zip)$/i.test(f.name));
    files.sort((a,b) => b.mtime.localeCompare(a.mtime));
    list.replaceChildren();
    if (!files.length) list.textContent='Save a design in /designs to get started.';
    for (const file of files) {
      const row=document.createElement('div'); row.className='file-row';
      const name=document.createElement('div'); name.className='file-name'; name.textContent=file.name;
      const detail=document.createElement('small'); detail.textContent=`${Math.ceil(file.size/1024)} KB · ${file.name.toLowerCase().endsWith('.pes')?'For Respira / PP1':file.name.toLowerCase().endsWith('.svg')?'Editable master':'Preview / notes'}`;
      name.append(detail);
      const a=document.createElement('a'); a.href='/design-files/'+encodeURIComponent(file.name); a.download=file.name; a.textContent='Download';
      row.append(name,a);list.append(row);
    }
  } catch(error) { list.textContent=error.message; }
}
