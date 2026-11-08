import {createPrintWorkspace} from './print-workspace.mjs';
document.body.classList.add('print-standalone');
const api=async(path,data)=>{const response=await fetch(path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const r=await response.json();if(!response.ok)throw new Error(r.error||'The print request could not finish.');return r;};
const workspace=createPrintWorkspace({api});await workspace.open(document.body.dataset.printId);
const reopen=document.createElement('button');reopen.textContent='Open print workspace';reopen.onclick=()=>workspace.open(document.body.dataset.printId);document.body.append(reopen);
