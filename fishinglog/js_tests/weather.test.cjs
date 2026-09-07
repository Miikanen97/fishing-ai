const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
function setup() {
  const elements = {};
  function element(value = '') {
    return {value, checked:true, textContent:'', disabled:false, dataset:{url:'/saa/hae/'}, events:{},
      addEventListener(name, handler) { this.events[name] = handler; }};
  }
  for (const name of ['date','start_time','location','weather_place','air_temperature','wind_speed','wind_gust','wind_direction','air_pressure','cloud_cover','precipitation','weather','latitude','longitude','weather_latitude','weather_longitude','weather_source','csrfmiddlewaretoken']) elements[name] = element();
  Object.assign(elements.date,{value:'2026-09-07'});
  elements.start_time.value = '12:00'; elements.location.value = 'Kyyvesi';
  const ui = Object.fromEntries(['fetch-weather','weather-status','auto-weather','wind-compass','weather-source'].map(x => [x, element()]));
  const form = element(); form.dispatchEvent = () => {}; form.elements = {namedItem:name=>elements[name]};
  ui['fetch-weather'].closest = () => form;
  let timers = [], calls=0, responder;
  const result = {values:{air_temperature:'12.5',wind_gust:'7.1',wind_direction:'270',weather:'Pilvistä',weather_latitude:'61.99757',weather_longitude:'27.16802'},source:'FMI',missing:[],location:{name:'Kyyvesi',latitude:61.99757,longitude:27.16802}};
  responder = async () => ({ok:true,headers:{get:()=> 'application/json'},json:async()=>result});
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static/fishinglog/weather.js'),'utf8'), {
    document:{getElementById:id=>ui[id]}, URLSearchParams, AbortController, CustomEvent:class {constructor(type,options){this.type=type;this.detail=options.detail;}},
    setTimeout:(callback,ms)=> {const t={callback,ms};timers.push(t);return t;},
    clearTimeout:t=> {timers=timers.filter(x=>x!==t);},
    fetch:(...args)=> {calls++;return responder(...args);}
  });
  return {elements,ui,form,result,
    get calls(){return calls;},
    respond(fn){responder=fn;},
    async automatic(){elements.location.events.change(); const timer=timers.find(t=>t.ms===800); if(timer) await timer.callback();},
    async manual(){await ui['fetch-weather'].events.click();}};
}
test('automatic lookup fills editable weather and target coordinates', async()=>{
 const app=setup(); await app.automatic();
 assert.equal(app.calls,1); assert.equal(app.elements.wind_gust.value,'7.1');
 assert.equal(app.elements.weather_latitude.value,'61.99757'); assert.equal(app.elements.latitude.value,''); assert.equal(app.ui['wind-compass'].textContent,'länsi');
});
test('automatic lookup protects manual changes; button explicitly refreshes',async()=>{
 const app=setup(); app.elements.air_temperature.value='19'; app.elements.air_temperature.events.input();
 await app.automatic(); assert.equal(app.elements.air_temperature.value,'19');
 await app.manual(); assert.equal(app.elements.air_temperature.value,'12.5');
});
test('missing data preserves values, network error leaves saving enabled',async()=>{
 const app=setup(); app.elements.wind_speed.value='4.5';
 await app.manual(); assert.equal(app.elements.wind_speed.value,'4.5');
 app.respond(async()=>{throw new Error('offline');}); await app.manual();
 assert.match(app.ui['weather-status'].textContent,/Voit tallentaa/);
 assert.equal(app.ui['fetch-weather'].disabled,false);
 assert.equal(app.elements.air_temperature.value,'12.5');
});
test('late response cannot overwrite changed place',async()=>{
 const app=setup(); let resolve;
 app.respond(()=>new Promise(r=>resolve=r)); const pending=app.manual();
 app.elements.location.value='Jyväskylä';
 resolve({ok:true,headers:{get:()=> 'application/json'},json:async()=>app.result});
 await pending; assert.equal(app.elements.latitude.value,'');
});
test('manual edit during request is preserved',async()=>{
 const app=setup(); let resolve;
 app.respond(()=>new Promise(r=>resolve=r)); const pending=app.manual();
 app.elements.air_temperature.value='22'; app.elements.air_temperature.events.input();
 resolve({ok:true,headers:{get:()=> 'application/json'},json:async()=>app.result});
 await pending; assert.equal(app.elements.air_temperature.value,'22');
});
test('incomplete query and disabled automatic lookup send no request',async()=>{
 const app=setup(); app.elements.start_time.value=''; await app.manual(); assert.equal(app.calls,0);
 app.elements.start_time.value='12:00'; app.ui['auto-weather'].checked=false; await app.automatic(); assert.equal(app.calls,0);
});


test('GPS is sent first and cannot be overwritten by weather results',async()=>{
 const app=setup(); app.elements.latitude.value='62.12345'; app.elements.longitude.value='26.12345';
 let body;
 app.respond(async(url,options)=>{body=options.body;return {ok:true,headers:{get:()=> 'application/json'},json:async()=>app.result};});
 await app.manual();
 assert.equal(body.get('latitude'),'62.12345');
 assert.equal(app.elements.latitude.value,'62.12345');
 assert.equal(app.elements.longitude.value,'26.12345');
});
