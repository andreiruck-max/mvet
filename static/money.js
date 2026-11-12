/* Cent-based typing. Keep native field names, validation and canonical numbers. */
(() => {
  const states=new WeakMap();
  function isMoney(el) {
    if (!(el instanceof HTMLInputElement) || el.disabled || el.readOnly || !['text','number'].includes(el.type)) return false;
    const label=[...(el.labels||[])].map(x=>x.textContent).join(' ');
    if (/quantidade|alíquota|percentual|margem|dias/i.test(label)) return false;
    return el.step==='0.01' || label.includes('R$') || el.dataset.money==='true';
  }
  // Display Brazilian grouping without changing posted values or field precision.
  const enhanced=new WeakSet();
  function format(el) {
    if(!isMoney(el))return;
    if(!enhanced.has(el)) {
      el.dataset.numericType=el.type;
      if(el.type==='number')el.type='text';
      el.inputMode='decimal';enhanced.add(el);
    }
    let value=el.value.trim();
    if(!value)return;
    if(value.includes(','))value=value.replaceAll('.','');
    else value=value.replace('.',',');
    if(!/^-?\d+(,\d*)?$/.test(value))return;
    let [whole,fraction='']=value.split(',');
    el.value=whole.replace(/\B(?=(\d{3})+(?!\d))/g,'.')+','+fraction.padEnd(2,'0');
    const canonical=el.value.replaceAll('.','').replace(',','.');
    const number=Number(canonical);
    el.setCustomValidity((el.min!==''&&number<Number(el.min))||(el.max!==''&&number>Number(el.max))?'Valor fora do limite permitido.':'');
  }
  function enhance(root) {root.querySelectorAll('input').forEach(format);}
  document.addEventListener('DOMContentLoaded',()=>enhance(document));
  new MutationObserver(records=>records.forEach(r=>r.addedNodes.forEach(n=>{if(n.nodeType===1){if(n.matches('input'))format(n);enhance(n);}}))).observe(document.documentElement,{childList:true,subtree:true});
  document.addEventListener('change',e=>format(e.target));
  document.addEventListener('formdata',e=>{
    for(const el of e.target.elements) {
      if(!enhanced.has(el)||!el.name||el.disabled)continue;
      let value=el.value;
      if(value.includes(',')){value=value.replaceAll('.','');if(el.dataset.numericType==='number')value=value.replace(',','.');}
      e.formData.set(el.name,value);
    }
  });
  function state(el) {
    if(!states.has(el)) states.set(el,{replace:true});
    return states.get(el);
  }
  function write(el,cents,negative=false) {
    const digits=cents.replace(/^0+(?=\d)/,'').padStart(3,'0');
    if(digits.length>18)return;
    const separator=el.type==='number'?'.':',';
    el.value=(negative?'-':'')+digits.slice(0,-2)+separator+digits.slice(-2);
    format(el);
    el.dispatchEvent(new Event('input',{bubbles:true}));
    el.dispatchEvent(new Event('change',{bubbles:true}));
  }
  function edit(el,key) {
    const s=state(el), negative=el.value.startsWith('-');
    let digits=s.replace?'':el.value.replace(/\D/g,'');
    if(/^\d$/.test(key)){write(el,digits+key,!s.replace&&negative);s.replace=false;return true;}
    if(key==='Backspace'||key==='Delete'){
      if(s.replace||key==='Delete'){el.value='';el.setCustomValidity('');s.replace=true;el.dispatchEvent(new Event('input',{bubbles:true}));}
      else write(el,digits.slice(0,-1)||'0',negative);
      return true;
    }
    if(key==='-'&&(!el.min||Number(el.min)<0)){write(el,digits||'0',!negative);s.replace=false;return true;}
    return key===','||key==='.';
  }
  document.addEventListener('focusin',e=>{
    if(!isMoney(e.target))return;
    format(e.target);state(e.target).replace=true;e.target.inputMode='decimal';
    if(e.target.type==='text')e.target.select();
  });
  document.addEventListener('keydown',e=>{
    if(!isMoney(e.target))return;
    if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='a'){state(e.target).replace=true;return;}
    if(e.ctrlKey||e.metaKey||e.altKey)return;
    if(edit(e.target,e.key))e.preventDefault();
  });
  document.addEventListener('beforeinput',e=>{
    if(!isMoney(e.target)||!e.cancelable)return;
    const key=e.inputType==='deleteContentBackward'?'Backspace':e.inputType==='insertText'?e.data:null;
    if(key&&edit(e.target,key))e.preventDefault();
  });
  document.addEventListener('paste',e=>{
    if(!isMoney(e.target))return;
    const text=e.clipboardData.getData('text').trim().replace(/^R\$\s*/, '');
    if(!/^-?[\d.,]+$/.test(text))return;
    const negative=text.startsWith('-');
    if(negative&&e.target.min&&Number(e.target.min)>=0){e.preventDefault();return;}
    let raw=text.replace('-','');
    if(raw.includes(','))raw=raw.replace(/\./g,'').replace(',','.');
    if(raw.includes('.')){
      const [whole,fraction]=raw.split('.');
      if(!/^\d+$/.test(whole)||!/^\d{1,6}$/.test(fraction))return;
      // Pasted unit costs keep their existing precision; no rounding of CMV inputs.
      const precision=e.target.step?Math.max(2,(e.target.step.split('.')[1]||'').length):2;
      if(fraction.length>precision)return;
      e.preventDefault();e.target.value=(negative?'-':'')+whole+(e.target.type==='number'?'.':',')+fraction.padEnd(2,'0');
      format(e.target);e.target.dispatchEvent(new Event('input',{bubbles:true}));
    }else{e.preventDefault();write(e.target,raw,negative);}
    state(e.target).replace=false;
  });
})();
