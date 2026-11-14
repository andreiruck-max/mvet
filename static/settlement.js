/* Recalculate actual for a partial payment; manual actual remains editable. */
(() => {
  const principal=document.getElementById('id_principal'), actual=document.getElementById('id_actual');
  if(!principal||!actual)return;
  const cents=el=>{let s=el.value.trim();if(s.includes(','))s=s.replaceAll('.','').replace(',','.');if(!/^\d+(\.\d{1,2})?$/.test(s))return null;let [a,b='']=s.split('.');return BigInt(a)*100n+BigInt(b.padEnd(2,'0'));};
  const update=()=>{
    const p=cents(principal),i=cents(document.getElementById('id_interest')),d=cents(document.getElementById('id_discount'));
    if(p===null||i===null||d===null||p+i<d)return;
    const n=p+i-d;actual.value=`${n/100n}${actual.type==='number'?'.':','}${String(n%100n).padStart(2,'0')}`;
    actual.dispatchEvent(new Event('change',{bubbles:true}));
  };
  [principal,document.getElementById('id_interest'),document.getElementById('id_discount')].forEach(el=>el.addEventListener('input',update));
})();
