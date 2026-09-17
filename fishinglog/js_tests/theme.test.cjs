const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
function setup(stored,dark=false,blocked=false){
 const events={}, attrs={},button={setAttribute(k,v){this[k]=v;},addEventListener(k,v){this[k]=v;}},system={matches:dark,addEventListener(k,v){this[k]=v;}};
 let ready=false,saved;
 const root={style:{},setAttribute(k,v){attrs[k]=v;},getAttribute(k){return attrs[k];}};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static/fishinglog/theme.js'),'utf8'),{document:{documentElement:root,getElementById:()=>ready?button:null,addEventListener(k,v){events[k]=v;}},window:{matchMedia:()=>system,addEventListener(k,v){events[k]=v;}},localStorage:{getItem(){if(blocked)throw Error();return stored;},setItem(k,v){if(blocked)throw Error();saved=v;}}});
 return {root,button,system,events,get theme(){return attrs['data-bs-theme'];},get saved(){return saved;},ready(){ready=true;events.DOMContentLoaded();}};
}
test('saved theme applied before DOM ready and toggled accessibly',()=>{const app=setup('dark');assert.equal(app.theme,'dark');app.ready();assert.equal(app.button.textContent,'☀️');app.button.click();assert.equal(app.theme,'light');assert.equal(app.saved,'light');assert.equal(app.button['aria-label'],'Vaihda tummaan teemaan');});
test('system preference used until explicit choice; storage failures safe',()=>{const app=setup(null,true,true);assert.equal(app.theme,'dark');app.ready();app.system.matches=false;app.system.change();assert.equal(app.theme,'light');app.button.click();app.system.change();assert.equal(app.theme,'dark');});
test('invalid preference ignored and other tabs synchronized',()=>{const app=setup('invalid');app.ready();assert.equal(app.theme,'light');app.events.storage({key:'fishingai-theme',newValue:'dark'});assert.equal(app.theme,'dark');});
