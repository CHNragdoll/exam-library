document.querySelector('[data-toggle-source]')?.addEventListener('click', function(){
  const visible=document.body.classList.toggle('show-source');
  this.textContent=visible?'隐藏 LaTeX':'显示 LaTeX';this.setAttribute('aria-pressed',String(visible));
});
document.addEventListener('click',async event=>{
  const formula=event.target.closest('.formula');if(!formula)return;
  const value=formula.getAttribute('data-tex');
  let copied=false;
  try{await navigator.clipboard.writeText(value);copied=true;}catch{
    const box=document.createElement('textarea');box.value=value;box.style.position='fixed';box.style.left='-9999px';document.body.appendChild(box);box.select();copied=document.execCommand('copy');box.remove();
  }
  const status=document.querySelector('.status');
  status.textContent=copied?'已复制 LaTeX 公式':'请点击“显示 LaTeX”后手动复制';status.classList.add('visible');setTimeout(()=>status.classList.remove('visible'),1800);
});
