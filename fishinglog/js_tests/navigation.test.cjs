const test=require('node:test'), assert=require('node:assert/strict'), vm=require('node:vm'), fs=require('node:fs'), path=require('node:path');
function setup() {
  const element=()=>({events:{},attrs:{},addEventListener(n,f){this.events[n]=f;},setAttribute(n,v){this.attrs[n]=v;},getAttribute(n){return this.attrs[n];},focus(){this.focused=true;}});
  const nav=element(), button=element(), links=element(), document=element(), window=element(), media=element();
  const classes=new Set();nav.classList={add:c=>classes.add(c),remove:c=>classes.delete(c),toggle:(c,on)=>on?classes.add(c):classes.delete(c)};
  nav.contains=t=>[nav,button,links].includes(t);
  button.attrs['aria-expanded']='false';button.hidden=true;
  document.getElementById=id=>({'site-navigation':nav,'menu-toggle':button,'navigation-links':links})[id];
  window.matchMedia=()=>media;
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static/fishinglog/navigation.js'),'utf8'),{document,window});
  return {nav,button,links,document,window,media,classes};
}
test('mobile menu toggles accessibly and Escape returns focus',()=>{
  const {nav,button,classes}=setup();
  assert.equal(button.hidden,false);assert(classes.has('navigation-enhanced'));
  button.events.click();assert.equal(button.attrs['aria-expanded'],'true');assert(classes.has('menu-open'));
  nav.events.keydown({key:'Escape'});assert.equal(button.attrs['aria-expanded'],'false');assert(button.focused);
  button.events.click();button.events.click();assert.equal(button.attrs['aria-expanded'],'false');
});
test('menu closes on navigation, outside click, focus exit, resize and return',()=>{
  const s=setup();
  for(const close of [()=>s.links.events.click({target:{closest:()=>({})}}),()=>s.document.events.click({target:{}}),()=>s.nav.events.focusout({relatedTarget:null}),()=>s.media.events.change(),()=>s.window.events.pageshow()]){
    s.button.events.click();assert(s.classes.has('menu-open'));close();assert(!s.classes.has('menu-open'));assert.equal(s.button.attrs['aria-expanded'],'false');
  }
  s.button.events.click();s.nav.events.focusout({relatedTarget:s.links});assert(s.classes.has('menu-open'));
});
