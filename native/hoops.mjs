// Hoop sizes a project can be designed for (mirrors hoops.py).
export const HOOPS={
  pp1:{id:'pp1',w:100,h:100,label:'Brother PP1 · 100 × 100 mm',short:'100 × 100',eyebrow:'BROTHER PP1'},
  '8x12':{id:'8x12',w:200,h:300,label:'8 × 12 in · 200 × 300 mm',short:'200 × 300',eyebrow:'8 × 12 IN HOOP'},
};
export const hoopOf=project=>HOOPS[project?.hoop]||HOOPS.pp1;
