const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
test('only first submit proceeds, pageshow resets and no background calls exist', () => {
  const handlers = {}, button = {disabled:false}, progress = {textContent:''};
  const form = {dataset:{}, querySelector:()=>button, addEventListener:(name,fn)=>handlers[name]=fn};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static/fishinglog/assistant.js'),'utf8'), {
    document:{getElementById:id=>id==='assistant-form'?form:id==='assistant-progress'?progress:null, querySelector:()=>button, querySelectorAll:()=>[]},
    window:{addEventListener:(name,fn)=>handlers[name]=fn},
    fetch:()=>assert.fail('No background API call allowed')
  });
  let prevented = 0;
  handlers.submit.call(form,{preventDefault:()=>prevented++});
  assert.equal(button.disabled,true);
  handlers.submit.call(form,{preventDefault:()=>prevented++});
  assert.equal(prevented,1);
  handlers.pageshow();
  assert.equal(button.disabled,false);
  handlers.submit.call(form,{preventDefault:()=>prevented++});
  assert.equal(prevented,1);
});

test('quick questions and saved/free place only fill fields', () => {
  const element = () => ({value:'', dataset:{}, addEventListener(name, fn){this[name]=fn;}, focus(){this.focused=true;}});
  const nodes = Object.fromEntries(['assistant-form','assistant-progress','id_question','id_place','assistant-spot'].map(id=>[id,element()]));
  const quick = element(); quick.dataset.question = 'Mihin huomenna?';
  const submit = element(); nodes['assistant-form'].querySelector=()=>submit;
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static/fishinglog/assistant.js'),'utf8'), {
    document:{getElementById:id=>nodes[id],querySelector:()=>submit,querySelectorAll:()=>[quick]},
    window:{addEventListener(){}}, fetch:()=>assert.fail('No automatic call')
  });
  quick.click(); assert.equal(nodes.id_question.value, 'Mihin huomenna?');
  assert.equal(nodes.id_question.focused,true);
  nodes['assistant-spot'].value='Oma paikka';nodes['assistant-spot'].change();
  assert.equal(nodes.id_place.value,'Oma paikka');
  nodes['assistant-spot'].value='';nodes['assistant-spot'].change();
  assert.equal(nodes.id_place.value,''); assert.equal(nodes.id_place.focused,true);
  assert.equal(nodes['assistant-form'].dataset.pending,undefined);
  assert.equal(submit.disabled,undefined);
});
