const {test}=require('node:test'), assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
function setup(existing=false){
 const item=(value='')=>({value,dataset:{},events:{},addEventListener(n,f){this.events[n]=f;},dispatchEvent(e){this.events[e.type]?.(e);}});
 const names=['lake','location','latitude','longitude','fishing_spot','start_time','end_time','air_temperature','wind_speed','cloud_cover','precipitation','air_pressure'];
 const fields=Object.fromEntries(names.map(n=>[n,item()]));fields.lake.value=existing?'Vanha järvi':'';fields.location.value='Vapaa paikka';
 fields.fishing_spot.selectedOptions=[{textContent:'Oma selkä',dataset:{latitude:'62',longitude:'26'}}];
 const wrappers={location:{},save_spot:{}};const buttons=['start_time','end_time'].map(n=>Object.assign(item(),{dataset:{now:n}}));
 const form=item();form.elements={namedItem:n=>fields[n]};form.querySelector=s=>wrappers[s.includes('save_spot')?'save_spot':'location'];form.querySelectorAll=s=>s==='[data-now]'?buttons:[];
 const nodes={'trip-form':form,'trip-weather-summary':item(),'weather-status':{textContent:''},'trip-weather-error':item()};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static/fishinglog/trip_form.js'),'utf8'),{document:{getElementById:n=>nodes[n]},Event,Date:class{getHours(){return 9;}getMinutes(){return 5;}},MutationObserver:class{observe(){}}});
 return {fields,wrappers,buttons,form,nodes};
}
test('spot selection fills coordinates and restores other place; existing lake preserved',()=>{
 for(const existing of [false,true]){const app=setup(existing),f=app.fields;
 f.fishing_spot.value='7';f.fishing_spot.events.change();assert.equal(f.location.value,'Oma selkä');assert.equal(f.latitude.value,'62');assert.equal(app.wrappers.location.hidden,true);
 assert.equal(f.lake.value,existing?'Vanha järvi':'Oma selkä');
 f.fishing_spot.value='';f.fishing_spot.events.change();assert.equal(f.location.value,'Vapaa paikka');assert.equal(f.latitude.value,'');assert.equal(app.wrappers.location.hidden,false);}
});
test('now uses browser local clock and weather summary preserves zero',()=>{const app=setup();app.buttons[0].events.click();assert.equal(app.fields.start_time.value,'09:05');app.fields.air_temperature.value='0';app.form.events.input();assert.match(app.nodes['trip-weather-summary'].textContent,/0 °C/);});
