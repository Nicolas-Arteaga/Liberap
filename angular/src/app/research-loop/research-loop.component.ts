import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';

@Component({selector:'app-research-loop',standalone:true,imports:[CommonModule],templateUrl:'./research-loop.component.html',styleUrls:['./research-loop.component.scss']})
export class ResearchLoopComponent implements OnInit, OnDestroy {
  private http=inject(HttpClient); timer:any; state:any={phase:'sin actividad',done:0,total:0}; items:any[]=[]; error='';
  ngOnInit(){this.load();this.timer=setInterval(()=>this.load(),5000);}
  ngOnDestroy(){clearInterval(this.timer);}
  load(){this.http.get<any>('/vire-api/research/loop/status').subscribe({next:x=>this.state=x});this.http.get<any>('/vire-api/research/loop/improved').subscribe({next:x=>this.items=x.items||[]});}
  progress(){return this.state.total?Math.round(100*this.state.done/this.state.total):0;}
  date(v:string){return v?new Date(v).toLocaleString('es-AR',{timeZone:'America/Argentina/Buenos_Aires'}):'—';}
  retry(item:any){this.error='';this.http.post<any>(`/vire-api/research/loop/${encodeURIComponent(item.candidate_id)}/retry`,{}).subscribe({next:()=>this.load(),error:e=>this.error=e.error?.detail||'No se pudo iniciar el reintento.'});}
}
