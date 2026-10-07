document.querySelectorAll('[data-select-page]').forEach(toggle=>toggle.addEventListener('change',()=>{
 toggle.closest('form').querySelectorAll('input[name="selected"]').forEach(box=>{box.checked=toggle.checked;});
}));
