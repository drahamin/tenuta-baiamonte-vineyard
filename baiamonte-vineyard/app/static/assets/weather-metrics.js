const weatherMetricDefinitions={
  'Temperature':{field:'temp_c',unit:'°C'},
  'Feels like':{field:'feels_like_c',unit:'°C'},
  'Humidity':{field:'humidity_pct',unit:'%',zero:true},
  'Daily rain':{field:'rain_mm',unit:'mm',zero:true,note:'Daily accumulation resets at midnight.'},
  'Rain rate':{field:'rain_rate_mm_h',unit:'mm/h',zero:true},
  'Raining now':{field:'rain_rate_mm_h',unit:'mm/h',title:'Rain rate',zero:true},
  'Wind':{field:'wind_kph',unit:'km/h',zero:true},
  'Gust':{field:'wind_gust_kph',unit:'km/h',zero:true},
  'Max gust today':{field:'gust_max_today_kph',unit:'km/h',zero:true,note:'Daily maximum resets at midnight.'},
  'Wind direction':{field:'wind_direction_deg',unit:'°',range:'Compass bearing'},
  '10-min direction':{field:'wind_direction_10m_deg',unit:'°',range:'10-minute compass bearing'},
  'Pressure':{field:'pressure_hpa',unit:'hPa'},
  'Solar':{field:'solar_wm2',unit:'W/m²',zero:true},
  'UV':{field:'uv_index',unit:'',zero:true},
  'Leaf wetness':{field:'leaf_wetness_pct',unit:'%',zero:true},
  'Soil moisture':{field:'soil_moisture_pct',unit:'%',zero:true},
  'Soil temperature':{field:'soil_temp_c',unit:'°C'},
  'Sensor battery':{field:'sensor_battery_v',unit:'V',range:'GW2000 sensor battery'},
  'Sensor capacitor':{field:'sensor_capacitor_v',unit:'V',range:'GW2000 sensor capacitor'},
  'Dew point':{field:'dew_point_c',unit:'°C'},
  'VPD':{field:'vpd_kpa',unit:'kPa',zero:true}
};

let selectedWeatherMetric=null;
let selectedWeatherHours=48;
const weatherHistoryCache=new Map();

function weatherMetricNumber(value){const number=Number(value);return Number.isFinite(number)?number:null}
function weatherMetricValue(value,unit){return value==null?'—':`${Number(value).toLocaleString(undefined,{maximumFractionDigits:2})}${unit?` ${unit}`:''}`}
function weatherMetricTime(value){
  if(!value)return'Unknown time';
  const parsed=new Date(String(value).replace(' ','T'));
  return Number.isNaN(parsed.getTime())?String(value):parsed.toLocaleString(undefined,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'});
}

function enhanceWeatherMetricCards(){
  const grid=$('weatherStationMetrics');
  if(!grid)return;
  [...grid.children].forEach(card=>{
    const label=card.querySelector('span')?.textContent?.trim();
    const definition=weatherMetricDefinitions[label];
    if(!definition)return;
    card.classList.add('weather-stat-clickable');
    card.dataset.weatherMetric=label;
    card.setAttribute('role','button');
    card.setAttribute('tabindex','0');
    card.setAttribute('aria-label',`Open ${definition.title||label} history graph`);
    card.title=`Open ${definition.title||label} history graph`;
    card.onclick=()=>openWeatherMetricGraph(label);
    card.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();openWeatherMetricGraph(label)}};
  });
}

async function weatherHistory(hours){
  const cached=weatherHistoryCache.get(hours);
  if(cached&&Date.now()-cached.savedAt<60000)return cached.request;
  const request=api(`api/v1/weather/history?hours=${hours}`).catch(error=>{weatherHistoryCache.delete(hours);throw error});
  weatherHistoryCache.set(hours,{savedAt:Date.now(),request});
  return request;
}

function renderWeatherMetricGraph(payload){
  const definition=weatherMetricDefinitions[selectedWeatherMetric];
  if(!definition)return;
  const observations=payload?.observations||[],values=observations.map(row=>weatherMetricNumber(row[definition.field])),recorded=values.map((value,index)=>({value,index})).filter(row=>row.value!=null);
  const loading=$('weatherMetricLoading'),empty=$('weatherMetricEmpty'),canvas=$('weatherMetricChart'),summary=$('weatherMetricSummary');
  loading.hidden=true;
  if(!recorded.length){empty.hidden=false;canvas.hidden=true;summary.hidden=true;return}
  empty.hidden=true;canvas.hidden=false;summary.hidden=false;
  const latest=recorded[recorded.length-1],minimum=Math.min(...recorded.map(row=>row.value)),maximum=Math.max(...recorded.map(row=>row.value));
  const latestRow=observations[latest.index];
  summary.innerHTML=`<span><small>Latest recorded</small><b>${esc(weatherMetricValue(latest.value,definition.unit))}</b><em>${esc(weatherMetricTime(latestRow.observed_at))}</em></span><span><small>Recorded range</small><b>${esc(weatherMetricValue(minimum,definition.unit))} – ${esc(weatherMetricValue(maximum,definition.unit))}</b><em>${recorded.length} measured reading${recorded.length===1?'':'s'}</em></span>${definition.note?`<span><small>Interpretation</small><b>${esc(definition.note)}</b><em>No interpolation or forecast values</em></span>`:''}`;
  const labels=observations.map(row=>weatherMetricTime(row.observed_at).replace(', ', ' · '));
  lineChart('weatherMetricChart',[{name:definition.title||selectedWeatherMetric,values,zeroBased:Boolean(definition.zero),points:false}],['#d4af37'],260,labels,{includeZero:Boolean(definition.zero),ariaLabel:`${definition.title||selectedWeatherMetric} recorded history for the last ${payload.hours} hours`});
}

async function loadWeatherMetricGraph(){
  const loading=$('weatherMetricLoading'),empty=$('weatherMetricEmpty'),canvas=$('weatherMetricChart'),summary=$('weatherMetricSummary');
  loading.hidden=false;loading.textContent='Loading recorded observations…';empty.hidden=true;canvas.hidden=true;summary.hidden=true;
  document.querySelectorAll('[data-weather-hours]').forEach(button=>{button.classList.toggle('active',Number(button.dataset.weatherHours)===selectedWeatherHours);button.setAttribute('aria-pressed',String(Number(button.dataset.weatherHours)===selectedWeatherHours))});
  try{renderWeatherMetricGraph(await weatherHistory(selectedWeatherHours))}
  catch(error){loading.textContent=error.message||'Weather history could not be loaded.'}
}

function openWeatherMetricGraph(label){
  const definition=weatherMetricDefinitions[label],dialog=$('weatherMetricDialog');
  if(!definition||!dialog)return;
  selectedWeatherMetric=label;
  $('weatherMetricTitle').textContent=definition.title||label;
  $('weatherMetricSubtitle').textContent=`${definition.range||'GW2000 measured history'}${definition.unit?` · ${definition.unit}`:''}`;
  if(!dialog.open)dialog.showModal();
  loadWeatherMetricGraph();
}

const renderWeatherBeforeMetricGraphs=renderWeather;
renderWeather=function(){renderWeatherBeforeMetricGraphs();enhanceWeatherMetricCards()};
document.querySelector('[data-close-weather-metric]')?.addEventListener('click',()=>$('weatherMetricDialog')?.close());
document.querySelectorAll('[data-weather-hours]').forEach(button=>button.addEventListener('click',()=>{selectedWeatherHours=Number(button.dataset.weatherHours);loadWeatherMetricGraph()}));
