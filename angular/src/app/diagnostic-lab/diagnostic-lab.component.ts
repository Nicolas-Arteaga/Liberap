import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';

type Lab = { strategy:string; generated_at_utc:number; report_markdown:string; result:any };
type IntegrityCheck = { key:string; label:string; status:string; detail:string };
type Finding = { area:string; severity:number; text:string };
@Component({selector:'app-diagnostic-lab',standalone:true,imports:[CommonModule],templateUrl:'./diagnostic-lab.component.html',styleUrls:['./diagnostic-lab.component.scss']})
export class DiagnosticLabComponent implements OnInit {
  private http=inject(HttpClient); selected='ma3'; data:Lab|null=null; error=''; showRaw=false;
  readonly areas=['ENTRADA','COSTOS','PAYOFF','SALIDA','SL','TIMEOUT'];
  readonly integrityLabels:Record<string,string>={entry_price_observable:'Precio de entrada observable',no_pre_entry_candle:'Sin velas previas a la entrada',no_exit_before_entry:'Sin salida previa a la entrada',split_at_entry:'Cortes temporales al instante de entrada',forward_1h_variance:'Variación del retorno a 1 hora',sample_counts:'Muestra y días efectivos'};
  ngOnInit(){this.load();}
  load(){this.error='';this.showRaw=false;this.http.get<Lab>(`/vire-api/research/laboratory/${this.selected}`).subscribe({next:x=>this.data=x,error:()=>this.error='No se pudo leer el último informe del Laboratorio.'});}
  date(v:number){return new Date(v*1000).toLocaleString('es-AR',{timeZone:'America/Argentina/Buenos_Aires'});}
  pct(v:any){return Number(v).toFixed(2)+'%';}
  integrity():IntegrityCheck[]{const c=this.data?.result?.integrity?.checks||{};return Object.keys(this.integrityLabels).map(key=>{const item=c[key]||{};const detail=item.pass_n!==undefined?`(${item.pass_n}/${item.n})`:key==='sample_counts'?`(${item.n||0} operaciones · ${item.n_days||0} días)`:item.variance!==undefined?`(varianza ${Number(item.variance).toFixed(4)})`:'';return {key,label:this.integrityLabels[key],status:item.status||'FAIL',detail};});}
  findings():Finding[]{const report=this.data?.report_markdown||'';return this.areas.map(area=>{const rx=new RegExp(`### \\[${area}\\] — severidad (\\d+)\\/100\\n([\\s\\S]*?)(?=\\n### |\\n## |$)`);const m=report.match(rx);return {area,severity:Number(m?.[1]||0),text:(m?.[2]||'Sin hallazgo disponible.').trim()};});}
  headline(){return (this.data?.report_markdown.match(/## TITULAR\n([^\n]+)/)?.[1]||'Sin titular disponible.');}
  invalid(){return this.data?.result?.integrity?.valid===false || this.data?.result?.valid===false;}
}
