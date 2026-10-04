'use strict';
(() => {
  const section=document.querySelector('.gaze-scroll');
  if(!section)return;
  const media=matchMedia('(prefers-reduced-motion: reduce)');
  const pause=document.querySelector('#motionToggle');
  const hero=document.querySelector('.pet-hero');
  const peek=document.querySelector('.pets-peek');
  let paused=media.matches,queued=false;
  const clamp=(n,a=0,b=1)=>Math.max(a,Math.min(b,n));
  function frame(){
    queued=false;
    if(document.hidden||paused)return;
    const rect=section.getBoundingClientRect();
    const stage=section.querySelector('.gaze-stage');
    const progress=clamp(-rect.top/Math.max(1,rect.height-stage.offsetHeight));
    const gaze=clamp((progress-.12)/.58);
    section.style.setProperty('--progress',progress.toFixed(3));
    section.style.setProperty('--gaze',gaze.toFixed(3));
    section.style.setProperty('--pack-y',`${90-progress*170}px`);
    section.style.setProperty('--pack-rotate',`${-17+progress*32}deg`);
    section.style.setProperty('--pack-scale',`${.86+progress*.16}`);
    section.style.setProperty('--cat-rise',`${25-progress*32}px`);
    if(hero){const r=hero.getBoundingClientRect();hero.style.setProperty('--hero-drift',`${clamp(-r.top/12,-10,22)}px`)}
    if(peek){const r=peek.getBoundingClientRect();const reveal=clamp((innerHeight-r.top)/(innerHeight*.6));peek.style.setProperty('--peek-shift',`${(1-reveal)*35}px`)}
  }
  function schedule(){if(!queued){queued=true;requestAnimationFrame(frame)}}
  function setPaused(value){paused=value;document.documentElement.classList.toggle('motion-off',paused);pause.textContent=paused?'Enable motion':'Pause motion';pause.setAttribute('aria-pressed',String(paused));if(!paused)schedule()}
  pause.addEventListener('click',()=>setPaused(!paused));
  media.addEventListener('change',e=>setPaused(e.matches));
  addEventListener('scroll',schedule,{passive:true});addEventListener('resize',schedule,{passive:true});
  addEventListener('hashchange',schedule);document.addEventListener('visibilitychange',schedule);
  document.querySelector('#skipMotion').addEventListener('click',()=>document.querySelector('.categories').scrollIntoView({behavior:'instant'}));
  setPaused(paused);schedule();
})();
