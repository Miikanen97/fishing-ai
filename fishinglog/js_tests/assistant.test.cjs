const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
test('only first submit proceeds, pageshow resets and no background calls exist', () => {
  const handlers = {}, button = {disabled:false}, progress = {textContent:''};
  const form = {dataset:{}, querySelector:()=>button, addEventListener:(name,fn)=>handlers[name]=fn};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static/fishinglog/assistant.js'),'utf8'), {
    document:{getElementById:id=>id==='assistant-form'?form:progress, querySelector:()=>button},
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
