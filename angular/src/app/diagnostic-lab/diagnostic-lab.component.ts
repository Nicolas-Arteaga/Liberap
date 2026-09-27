import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';

type Lab = { strategy:string; generated_at_utc:number; report_markdown:string; result:any };
@Component({selector:'app-diagnostic-lab',standalone:true,imports:[CommonModule],templateUrl:'./diagnostic-lab.component.html',styleUrls:['./diagnostic-lab.component.scss']})
export class DiagnosticLabComponent implements OnInit {
  private http=inject(HttpClient); selected='ma3'; data:Lab|null=null; error='';
  ngOnInit(){this.load();}
  load(){this.error='';this.http.get<Lab>(`/vire-api/research/laboratory/${this.selected}`).subscribe({next:x=>this.data=x,error:()=>this.error='No se pudo leer el último informe del Laboratorio.'});}
  date(v:number){return new Date(v*1000).toLocaleString('es-AR',{timeZone:'America/Argentina/Buenos_Aires'});}
}
