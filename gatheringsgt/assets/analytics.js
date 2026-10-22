/* Google Analytics 4 (visitas por región/departamento).
   Pega aquí el ID de medición (G-XXXXXXXXXX). Vacío = no se carga nada. */
(function(){
var GA_ID="G-CMDLKTR9FJ";
if(!GA_ID)return;
var KEY="gt_analytics";
function get(){try{return localStorage.getItem(KEY)}catch(e){return null}}
function set(v){try{localStorage.setItem(KEY,v)}catch(e){}}
if(get()==="no"){window["ga-disable-"+GA_ID]=true;return}
window.dataLayer=window.dataLayer||[];
function gtag(){dataLayer.push(arguments)}
gtag("js",new Date());
gtag("config",GA_ID,{allow_google_signals:false,allow_ad_personalization_signals:false});
var s=document.createElement("script");s.async=true;s.src="https://www.googletagmanager.com/gtag/js?id="+GA_ID;document.head.appendChild(s);
if(get())return;
/* Aviso breve la primera vez; «No permitir» apaga la medición en este navegador. */
var b=document.createElement("div");b.setAttribute("role","region");b.setAttribute("aria-label","Aviso de estadísticas");
b.style.cssText="position:fixed;left:12px;right:12px;bottom:12px;z-index:50;max-width:520px;margin:0 auto;background:#031666;color:#fff;border-radius:14px;padding:14px 16px;font:14px/1.4 'Gotham Narrow',system-ui,sans-serif;box-shadow:0 6px 24px rgba(0,0,0,.25)";
b.innerHTML='<p style="margin:0 0 10px">Usamos estadísticas anónimas (Google Analytics) para saber de qué zonas del país nos visitan y mejorar el sitio.</p>';
function btn(t,bg,fg,v){var x=document.createElement("button");x.type="button";x.textContent=t;x.style.cssText="border:0;border-radius:999px;padding:8px 18px;margin-right:8px;font:700 14px system-ui,sans-serif;cursor:pointer;background:"+bg+";color:"+fg;
x.onclick=function(){set(v);if(v==="no")window["ga-disable-"+GA_ID]=true;b.remove()};return x}
b.appendChild(btn("Entendido","#4EB969","#031666","si"));
b.appendChild(btn("No permitir","transparent","#fff","no")).style.border="1px solid #fff";
document.body.appendChild(b);
})();
