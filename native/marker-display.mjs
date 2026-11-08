const SVG='http://www.w3.org/2000/svg',ROLES=['guide-line','anchor-line','pattern'];
let artwork=null,pending=null;
export const markerSettings=p=>({visible:false,size:100,...p.markerDisplay});
export function loadMarkerArtwork(api){if(artwork)return Promise.resolve();if(!pending)pending=api('/api/marker-artwork').then(r=>{artwork=new DOMParser().parseFromString(r.svg,'image/svg+xml').documentElement;}).finally(()=>{pending=null;});return pending;}
const markerId=value=>String(value||'').match(/(?:^|#)(?:cmd-)*(?:nativeMarkerDisplay-|dialogMarkerDisplay-)?(inkstitch[^)\s"']*)/)?.[1];
const roleFor=value=>ROLES.find(role=>{const id=markerId(value);return id==='inkstitch-'+role+'-marker'||id?.startsWith('inkstitch-'+role+'-marker-');});
export function drawMarkerSymbols(art,project,prefix='nativeMarkerDisplay'){
  if(!artwork)return;
  const config=markerSettings(project),width=config.visible ? .125*config.size/100 : 0;
  for(const old of art.querySelectorAll('defs[data-marker-display]'))old.remove();
  const defs=document.importNode(artwork,true);defs.removeAttribute('id');defs.dataset.markerDisplay='true';
  for(const m of defs.children){const id=m.id;m.id=prefix+'-'+id;m.setAttribute('markerWidth',String(width));m.style.overflow='visible';for(const e of m.querySelectorAll('[id]'))e.removeAttribute('id');}
  art.prepend(defs);
  // Preserve imported marker artwork; repair only empty native placeholder defs.
  for(const m of art.querySelectorAll('marker')){
    if(m.closest('defs[data-marker-display]'))continue;
    const id=markerId(m.id);if(!id?.startsWith('inkstitch'))continue;
    if(!m.children.length){const source=[...artwork.children].find(e=>id===e.id||id.startsWith(e.id+'-'));if(source){const saved=m.id;for(const a of [...m.attributes])m.removeAttribute(a.name);for(const a of source.attributes)m.setAttribute(a.name,a.value);m.id=saved;for(const child of source.children)m.append(document.importNode(child,true));for(const e of m.querySelectorAll('[id]'))e.removeAttribute('id');}}
    m.setAttribute('markerWidth',String(width));m.style.overflow='visible';
  }
  const layers=new Map(project.layers.map(l=>[l.id,l]));
  for(const e of art.querySelectorAll('path,rect,circle,ellipse,polygon,polyline,line')){
    if(e.closest('defs,symbol')||e.getAttribute('fill')==='transparent')continue;
    const layer=layers.get(e.closest('[data-layer]')?.getAttribute('data-layer'));
    if(ROLES.includes(layer?.role)){e.style.markerStart=`url(#${prefix}-inkstitch-${layer.role}-marker)`;continue;}
    const role=roleFor(e.style.markerStart||e.getAttribute('marker-start'));
    if(!role)continue;
    if(!('markerOriginalDisplay' in e.dataset))e.dataset.markerOriginalDisplay=e.style.display;
    e.style.display=config.visible?'':e.dataset.markerOriginalDisplay;
  }
}
