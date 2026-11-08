import {selectionShelfModel} from './selection-shelf-model.mjs';
import {resizedTTFSettings} from './ttf-lettering.mjs';
import {resizedDimensions} from './geometry.mjs';
import {hoopOf} from './hoops.mjs';

export function textKey(s){return JSON.stringify([s.font,s.text,s.scale,s.align,s.lineSpacing||0,s.letterSpacing||0,s.wordSpacing||0,s.trim||'line',s.colorSort||'off',!!s.commandSymbols]);}

// Shared by the inspector, swatches and selection shelf.
export function setLayerColor(layer,color){
  layer.color=color;
  if(layer.link)layer.link.inheritColor=false;
  if(layer.type==='import')layer.recolor=true;
  if(layer.type==='text')layer.preserveFontColors=false;
  if(layer.multicolorSatin?.bands?.length)layer.multicolorSatin.bands[0].color=color;
}

// A committed setting is one Undo step. Engine results are prepared before that
// step, and cannot replace a design that changed while the request was running.
export function createShelfSettings(ctx){
  const requests=new Map();
  return function edit({projectId,layerId,key,value}){
    const project=ctx.getProject(),layer=project.layers.find(l=>l.id===layerId);
    if(project.id!==projectId||!layer)throw new Error('Select the artwork again before editing.');
    const placementEdit=['x','y','width','height','aspectLock'].includes(key);
    if(layer.locked||layer.linkedHelper||layer.link&&!placementEdit)throw new Error('Unlock or detach the artwork before editing.');
    const model=selectionShelfModel({selection:[layer]});
    if(key==='aspectLock'){
      if(!model.proportions||typeof value!=='boolean')throw new Error('Select artwork with editable dimensions.');
      if(model.proportions.fixed&&!value)throw new Error('Embroidery lettering keeps its font proportions.');
      if(value===model.proportions.value)return;
      ctx.commit(()=>{layer.aspectLock=value;},layer);return;
    }
    const control=[...model.actions,...model.dimensions,...model.positions].find(a=>a.editor?.key===key)?.editor;
    if(!control)throw new Error('This setting is unavailable for the selected artwork.');
    if(control.type==='color'){
      if(layer.preserveFontColors)throw new Error('Turn off “Keep font thread colors” to choose a single thread.');
      if(typeof value!=='string'||!/^#[0-9a-f]{6}$/i.test(value))throw new Error('Choose a valid thread color.');
      const color=value.toLowerCase();
      if(color===control.value.toLowerCase())return;
      ctx.commit(()=>setLayerColor(layer,color),layer);
      return;
    }
    if(typeof value!=='number'||!Number.isFinite(value)||value<control.min||value>control.max)throw new Error(`Choose a value from ${control.min} to ${control.max} ${control.unit}.`);
    if(value===control.value)return;
    if(key==='width'||key==='height'){
      const size=resizedDimensions(layer,key,value,Math.max(hoopOf(project).w,hoopOf(project).h)),linked=project.layers.some(l=>l.link);
      if(layer.type!=='text'&&!linked){ctx.commit(()=>Object.assign(layer,size),layer);return;}
      const revision=ctx.getRevision(),run=Symbol();requests.set(layerId,run);
      const fresh=()=>{if(requests.get(layerId)!==run||ctx.getProject()!==project||ctx.getRevision()!==revision)throw new Error('The design changed during resizing. Enter the size again.');};
      return (async()=>{
        const next=structuredClone(layer);let lettering;
        if(layer.type==='text'){
          const factor=value/layer[key],s=layer.lettering;
          lettering=await ctx.api('/api/lettering',{...s,scale:s.scale*factor,lineSpacing:(s.lineSpacing||0)*factor,letterSpacing:(s.letterSpacing||0)*factor,wordSpacing:(s.wordSpacing||0)*factor});
          fresh();
          if(![lettering.width,lettering.height].every(v=>Number.isFinite(v)&&v>=.2&&v<=100))throw new Error('The regenerated lettering must fit the 0.2–100 mm size limits.');
          Object.assign(next,{lettering:lettering.settings,width:lettering.width,height:lettering.height,x:layer.x+(layer.width-lettering.width)/2,y:layer.y+(layer.height-lettering.height)/2});
        }else Object.assign(next,size);
        let resolved;
        if(linked){const proposed=structuredClone(project);Object.assign(proposed.layers.find(l=>l.id===layerId),next);resolved=await ctx.api('/api/linked-resolve',{project:proposed,fixedSizeIds:[layerId]});fresh();}
        if(lettering)ctx.textCache.set(ctx.textKey(lettering.settings),lettering);
        ctx.commit(()=>{if(resolved)project.layers=resolved.layers;else Object.assign(layer,next);},next);
        await ctx.hydrateLinkedText?.();
        const actual=project.layers.find(l=>l.id===layerId);
        if(lettering&&Math.abs(actual[key]-value)>.01)return {notice:`Font sizing applied ${Math.round(actual.width*1000)/1000} × ${Math.round(actual.height*1000)/1000} mm at ${actual.lettering.scale}% scale.`};
      })().finally(()=>{if(requests.get(layerId)===run)requests.delete(layerId);});
    }
    if(['spacing','stitchLength','opacity','x','y'].includes(key)){
      ctx.commit(()=>{layer[key]=key==='opacity'?value/100:value;},layer);
      return;
    }
    const revision=ctx.getRevision(),run=Symbol();requests.set(layerId,run);
    const fresh=()=>{
      if(requests.get(layerId)!==run||ctx.getProject()!==project||ctx.getRevision()!==revision)
        throw new Error('The design changed while updating spacing. Enter the value again.');
    };
    const prepare=async()=>{
      if(key==='letterSpacing'){
        const result=await ctx.api('/api/lettering',{...layer.lettering,letterSpacing:value});
        fresh();
        if(result.width>100||result.height>100)throw new Error('This spacing makes the lettering larger than the 100 mm hoop. Choose a smaller value.');
        const cx=layer.x+layer.width/2,cy=layer.y+layer.height/2;
        ctx.textCache.set(ctx.textKey(result.settings),result);
        ctx.commit(()=>Object.assign(layer,{lettering:result.settings,width:result.width,height:result.height,x:cx-result.width/2,y:cy-result.height/2}),layer);
      }else if(key==='ttfSpacing'){
        const pose={cx:layer.x+layer.width/2,cy:layer.y+layer.height/2,rotation:layer.rotation||0,flipX:!!layer.flipX,flipY:!!layer.flipY};
        const result=await ctx.api('/api/outline-lettering',{settings:{...resizedTTFSettings(layer),spacing:value},color:layer.color,pose});
        fresh();
        ctx.assets.set(result.asset.key,result.asset);
        // Retain the layer's name, order, commands, thread overrides and helpers.
        // Only the generated asset, recipe and physical bounds are replaced.
        ctx.commit(()=>{
          const next=result.layer;
          for(const prop of ['asset','ttfLettering','x','y','width','height'])layer[prop]=next[prop];
        },layer);
      }
    };
    return prepare().finally(()=>{if(requests.get(layerId)===run)requests.delete(layerId);});
  };
}
