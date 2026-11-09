// Transient workflow state only. Project files and HTTP payloads stay version 1.
// A request owns its result, error and cleanup until another request or cancel.
export function createTaskState(onChange=()=>{}) {
  let sequence=0, state=Object.freeze({status:'idle',sequence});
  const publish=(status,details={})=>{
    state=Object.freeze({status,sequence,...details});
    onChange(state);
  };
  return {
    get state(){return state;},
    get pending(){return state.status==='pending';},
    begin(context={}) {
      const owner=++sequence;
      const captured=Object.freeze({...context});
      publish('pending',{context:captured});
      const current=()=>owner===sequence;
      return Object.freeze({
        current,
        succeed(){if(!current()||state.status!=='pending')return false;publish('ready',{context:captured});return true;},
        fail(error){if(!current()||state.status!=='pending')return false;publish('error',{context:captured,error:String(error?.message??error)});return true;}
      });
    },
    cancel(){sequence++;publish('cancelled');}
  };
}

// Serialize writes, including after a rejected write. Updating a status label
// alone cannot prevent the server from persisting an older in-flight snapshot.
export function createSaveQueue({write,onChange=()=>{}}) {
  let tail=Promise.resolve();
  const pending=new Map();
  return {
    save(project,revision) {
      const key=JSON.stringify([project.id,revision]);
      if(pending.has(key))return pending.get(key);
      const snapshot=structuredClone(project), context={projectId:snapshot.id,revision};
      const publish=(status,error)=>onChange(Object.freeze({status,...context,...(error?{error:String(error.message??error)}:{})}));
      const operation=tail.then(async()=>{
        publish('saving');
        try {const result=await write(snapshot);publish('saved');return result;}
        catch(error){publish('error',error);throw error;}
        finally {pending.delete(key);}
      });
      pending.set(key,operation);
      tail=operation.catch(()=>{});
      publish('queued');
      return operation;
    }
  };
}

// Loading and saving must both complete against the same source revision before
// replacing it. Only one replacement may own this boundary at a time.
export function createProjectTransition({getProject,getRevision,save,onChange}) {
  const task=createTaskState(onChange);
  return {
    get state(){return task.state;},
    async run(load,commit) {
      if(task.pending)throw new Error('Wait for the current project to finish opening.');
      const projectId=getProject().id,revision=getRevision(),request=task.begin({projectId,revision});
      const assertFresh=()=>{
        if(getProject().id!==projectId||getRevision()!==revision)
          throw new Error('The design changed. Open the project again to keep your latest edits.');
      };
      try {
        const next=await load();assertFresh();
        await save();assertFresh();
        const result=await commit(next);request.succeed();return result;
      } catch(error){request.fail(error);throw error;}
    }
  };
}
