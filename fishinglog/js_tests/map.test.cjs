const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
function setup({point=null,editable=true,leaflet=true}={}) {
 const item=value=>({value,events:{},textContent:'',addEventListener(n,fn){this.events[n]=fn;},dispatchEvent(e){this.events[e.type]?.(e);}});
 const fields={latitude:item(point?.[0]??''),longitude:item(point?.[1]??''),weather_latitude:item('62'),weather_longitude:item('26')};
 const form={elements:{namedItem:n=>fields[n]},events:{},addEventListener(n,fn){this.events[n]=fn;}};
 const element={dataset:{iconUrl:'/static/icon.abc.png',iconRetinaUrl:'/static/icon2.def.png',shadowUrl:'/static/shadow.ghi.png',editable:String(editable),latitude:point?.[0]??'',longitude:point?.[1]??''},closest:selector=>selector === 'form' ? form : null};
 const ui={'fishing-map':element,'map-status':item(''),'clear-location':item(''),'locate-me':item('')};
 let marker=null,geoSuccess,geoError,geoCalls=0;
 const map={events:{},setView(p,z){this.center=p;return this;},panTo(p){this.center=p;},on(n,fn){this.events[n]=fn;return this;},removeLayer(){marker=null;}};
 const L={icon:options=>options,map:()=>map,tileLayer:()=>({on(){return this;},addTo(){return this;}}),marker:(point,options)=>{
   marker={point,options,events:{},addTo(){return this;},on(n,fn){this.events[n]=fn;return this;},setLatLng(p){this.point=p;return this;},getLatLng(){return {lat:this.point[0],lng:this.point[1]};}};return marker;}};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static/fishinglog/map.js'),'utf8'),{
   document:{getElementById:n=>ui[n]},window:{L:leaflet?L:undefined},L,Event,
   navigator:{geolocation:{getCurrentPosition(ok,error){geoCalls++;geoSuccess=ok;geoError=error;}}}
 });
 return {fields,form,map,ui,get marker(){return marker;},get geoCalls(){return geoCalls;},
   success(p){geoSuccess({coords:{latitude:p[0],longitude:p[1],accuracy:12}});},error(code){geoError({code});}};
}
test('weather center is not a fishing marker; click stores the selected point',()=>{
 const app=setup();assert.equal(app.marker,null);
 app.map.events.click({latlng:{lat:61.123456,lng:27.456789}});
 assert.equal(app.fields.latitude.value,'61.12346');assert.equal(app.fields.longitude.value,'27.45679');
 assert.equal(app.marker.options.draggable,true);
});
test('existing point loads and dragging changes GPS only',()=>{
 const app=setup({point:[62,27]});assert.deepEqual(Array.from(app.marker.point),[62,27]);
 app.marker.point=[63.12345,28.12345];app.marker.events.dragend();
 assert.equal(app.fields.latitude.value,'63.12345');assert.equal(app.fields.weather_latitude.value,'62');
});
test('weather response cannot move a selected fishing marker',()=>{
 const app=setup({point:[62,27]});
 app.form.events['weather-location']({detail:{latitude:60,longitude:25}});
 assert.deepEqual(Array.from(app.marker.point),[62,27]);
});
test('geolocation is requested only on click; denial preserves point',()=>{
 const app=setup({point:[62,27]});assert.equal(app.geoCalls,0);
 app.ui['locate-me'].events.click();assert.equal(app.geoCalls,1);
 app.error(1);assert.match(app.ui['map-status'].textContent,/Sijaintilupaa/);assert.equal(app.fields.latitude.value,62);
});
test('geolocation success and clearing work',()=>{
 const app=setup();app.ui['locate-me'].events.click();app.success([61.5,27.5]);
 assert.equal(app.fields.latitude.value,'61.50000');
 app.ui['clear-location'].events.click();assert.equal(app.fields.latitude.value,'');assert.equal(app.marker,null);
});
test('late geolocation cannot replace a newer map choice',()=>{
 const app=setup();app.ui['locate-me'].events.click();
 app.map.events.click({latlng:{lat:62,lng:27}});app.success([60,25]);
 assert.equal(app.fields.latitude.value,'62.00000');
});
test('read-only map has no click handler or draggable marker',()=>{
 const app=setup({point:[0,0],editable:false});assert.equal(app.marker.options.draggable,false);assert.equal(app.map.events.click,undefined);
});
test('missing Leaflet produces a helpful error',()=>{
 const app=setup({leaflet:false});assert.match(app.ui['map-status'].textContent,/koordinaatit käsin/);
});



test('new, existing and read-only markers use explicit static icon URLs',()=>{
 for (const options of [{}, {point:[62,27]}, {point:[62,27],editable:false}]) {
  const app=setup(options);
  if (!app.marker) app.map.events.click({latlng:{lat:62,lng:27}});
  assert.equal(app.marker.options.icon.iconUrl,'/static/icon.abc.png');
  assert.equal(app.marker.options.icon.iconRetinaUrl,'/static/icon2.def.png');
  assert.equal(app.marker.options.icon.shadowUrl,'/static/shadow.ghi.png');
  assert.deepEqual(Array.from(app.marker.options.icon.iconAnchor),[12,41]);
 }
});
