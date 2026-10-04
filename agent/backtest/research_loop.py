"""Bucle Research↔Máquina aislado: artefactos inmutables, nunca producción."""
from __future__ import annotations
import datetime as dt
import os
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import lab_audit as A
from lab_adapters import get_adapter

RECIPES = {"SALIDA": ("exit_giveback_10", "exit_giveback_25", "exit_giveback_50"),
           "SL": ("sl_atr_1_0", "sl_atr_1_5", "sl_atr_2_0"),
           "TIMEOUT": ("timeout_12h", "timeout_24h", "timeout_36h", "timeout_24h_if_losing"),
           "PAYOFF": ("payoff_tp_short_50", "payoff_break_even_1r", "payoff_trailing_2r")}
SIM_VARIANT = {"exit_giveback_10":"giveback_10", "exit_giveback_25":"giveback_25", "exit_giveback_50":"giveback_50",
 "sl_atr_1_0":"sl_atr_1.0", "sl_atr_1_5":"sl_atr_1.5", "sl_atr_2_0":"sl_atr_2.0",
 "timeout_12h":"time_exit_12h", "timeout_24h":"time_exit_24h", "timeout_36h":"time_exit_36h", "timeout_24h_if_losing":"time_stop_24h_if_losing",
 "payoff_tp_short_50":"tp_short_50", "payoff_break_even_1r":"break_even_1r", "payoff_trailing_2r":"trailing_2r"}

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def canonical(value): return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',',':'), ensure_ascii=False).encode()).hexdigest()
def now(): return dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00','Z')
def dump(path, value): Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
def git_commit():
    # El contenedor de auditoría no monta .git; el invocador formal aporta
    # el SHA que ya verificó en el checkout de integración.
    if commit := os.environ.get('RESEARCH_SOURCE_COMMIT'):
        return commit
    try: return subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip()
    except Exception: return 'unknown'
def state_path(root): return Path(root)/'pipeline_state.json'
def set_state(root, candidate_id, phase, done=0, total=0, eta_seconds=None, detail=''):
    root=Path(root); root.mkdir(parents=True,exist_ok=True); previous=state(root)
    started = previous.get('started_at_utc') if previous.get('candidate_id') == candidate_id and previous.get('phase') == phase else now()
    dump(state_path(root), {'candidate_id':candidate_id,'phase':phase,'started_at_utc':started,'updated_at_utc':now(),
      'done':done,'total':total,'eta_seconds':eta_seconds,'detail':detail})
def state(root):
    path=state_path(root)
    return json.loads(path.read_text(encoding='utf8')) if path.exists() else {'candidate_id':None,'phase':'sin actividad','done':0,'total':0,'eta_seconds':None}
def _new(path):
    if path.exists(): raise FileExistsError(f'revisión inmutable ya existe: {path}')
def _entries(entries): return ('\n'.join(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')) for x in entries)+'\n').encode()

def materialize_adapter(root, adapter_name, candidate_id):
    """Crea candidate.json + entries.jsonl de revisión 1 desde un adaptador auditado."""
    root=Path(root); dest=root/candidate_id/'1'; _new(dest); set_state(root,candidate_id,'Research generando',detail=adapter_name)
    adapter=get_adapter(adapter_name); entries=adapter.entries(); dest.mkdir(parents=True)
    ep=dest/'entries.jsonl'; ep.write_bytes(_entries(entries))
    split=adapter.split_policy
    policy=({'kind':'fixed_time','train_validation_ms':split.train_validation_ms,'validation_oos_ms':split.validation_oos_ms}
            if hasattr(split,'train_validation_ms') else {'kind':'temporal_quantile_50_25_25'})
    src=adapter.candle_source
    manifest={'protocol_version':'1.0-draft','candidate_id':candidate_id,'revision':1,'display_name':adapter.definition.display_name,'submitted_at_utc':now(),
      'research_run':{'run_id':'adapter:'+adapter.name,'family':'audited_adapter','hypothesis':adapter.entry_definition.condition,'source_commit':git_commit()},
      'adapter_definition':{'name':adapter.definition.name,'display_name':adapter.definition.display_name,'aliases':list(adapter.definition.aliases),'population':adapter.definition.population,'bar_ms':adapter.definition.bar_ms,'cost_pct':adapter.definition.cost_pct,'require_coverage':adapter.definition.require_coverage},
      'entry_definition':{'source':adapter.entry_definition.source,'condition':adapter.entry_definition.condition,'execution_time':adapter.entry_definition.execution_time,'side_convention':adapter.entry_definition.side_convention},
      'candle_source':{'key':src.key,'interval':src.interval,'start_ms':src.start_ms,'end_ms':src.end_ms},'split_policy':policy,
      'entries_artifact':{'path':'entries.jsonl','sha256':sha(ep),'count':len(entries)}}
    dump(dest/'candidate.json',manifest); verify_revision(dest); set_state(root,candidate_id,'Research generado',len(entries),len(entries),0,'revisión 1 inmutable'); return dest

def materialize_candidate(root, adapter_name, candidate_id, entries, condition, display_name):
    """Entrada formal Fase A: Research aporta señales normalizadas, nunca código."""
    root=Path(root); dest=root/candidate_id/'1'; _new(dest); set_state(root,candidate_id,'Research generando',detail=display_name)
    adapter=get_adapter(adapter_name); entries=list(entries); dest.mkdir(parents=True); ep=dest/'entries.jsonl'; ep.write_bytes(_entries(entries))
    split=adapter.split_policy; policy=({'kind':'fixed_time','train_validation_ms':split.train_validation_ms,'validation_oos_ms':split.validation_oos_ms} if hasattr(split,'train_validation_ms') else {'kind':'temporal_quantile_50_25_25'})
    src=adapter.candle_source; manifest={'protocol_version':'1.0-draft','candidate_id':candidate_id,'revision':1,'display_name':display_name,'submitted_at_utc':now(),
      'research_run':{'run_id':'e2e:ma3-risk-filter-v1','family':'entry_risk_filter','hypothesis':condition,'source_commit':git_commit()},
      'adapter_definition':{'name':adapter.definition.name,'display_name':display_name,'aliases':[candidate_id],'population':adapter.definition.population,'bar_ms':adapter.definition.bar_ms,'cost_pct':adapter.definition.cost_pct,'require_coverage':adapter.definition.require_coverage},
      'entry_definition':{'source':'MA3 stream congelado + filtro de riesgo inicial','condition':condition,'execution_time':adapter.entry_definition.execution_time,'side_convention':adapter.entry_definition.side_convention},
      'candle_source':{'key':src.key,'interval':src.interval,'start_ms':src.start_ms,'end_ms':src.end_ms},'split_policy':policy,'entries_artifact':{'path':'entries.jsonl','sha256':sha(ep),'count':len(entries)}}
    dump(dest/'candidate.json',manifest); verify_revision(dest); set_state(root,candidate_id,'Research generado',len(entries),len(entries),0,'revisión 1 inmutable'); return dest

def verify_revision(path):
    path=Path(path); candidate=json.loads((path/'candidate.json').read_text(encoding='utf8')); ep=path/'entries.jsonl'
    if not ep.exists() or sha(ep)!=candidate['entries_artifact']['sha256']: raise ValueError('huella de entries.jsonl inválida')
    entries=[json.loads(line) for line in ep.read_text(encoding='utf8').splitlines() if line]
    if len(entries)!=candidate['entries_artifact']['count']: raise ValueError('conteo entries inválido')
    if any(a['open_ms']>b['open_ms'] for a,b in zip(entries,entries[1:])): raise ValueError('entries sin orden temporal')
    return candidate,entries,{'candidate_sha256':canonical(candidate),'entries_sha256':sha(ep)}

class FrozenAdapter:
    def __init__(self, base, entries):
        self._base,self._entries=base,entries
        for name in ('name','aliases','population','bar_ms','cost_pct','definition','entry_definition','candle_source','split_policy','fidelity_result','fidelity_note'): setattr(self,name,getattr(base,name))
    def entries(self): return list(self._entries)
    def candles(self,symbol): return self._base.candles(symbol)
    def split_of(self,open_ms): return self._base.split_of(open_ms)

def _evidence(result):
    fwd24 = result['forward_return_pct_day_block_ci'].get(24, result['forward_return_pct_day_block_ci'].get('24'))
    return {'ENTRADA':{'metric':'forward_return_24h_mean_pct','value':fwd24['mean']},'COSTOS':{'metric':'gross_edge_pct','value':result['gross_edge_pct']},'PAYOFF':{'metric':'break_even_minus_win_rate_pp','value':(result['break_even_win_rate_pct'] or 0)-(result['win_rate_pct'] or 0)},'SALIDA':{'metric':'reached_2pct_ended_loss_pct','value':result['reached_2pct_ended_loss_pct']},'SL':{'metric':'sl_cf_reaches_tp_pct','value':result['sl_cf_reaches_tp_pct']},'TIMEOUT':{'metric':'timeout_damage','value':result['timeout_pct']*max(0,-(result['timeout_mean_return_pct'] or 0))}}

def diagnose_revision(root,path,execution_variant=None):
    """Ejecuta auditor real y materializa result/informe/diagnosis una sola vez."""
    root,path=Path(root),Path(path); dp=path/'diagnosis.json'; _new(dp); candidate,entries,fingerprint=verify_revision(path); base=get_adapter(candidate['adapter_definition']['name']); adapter=FrozenAdapter(base,entries); started=dt.datetime.now(dt.timezone.utc)
    def progress(done,total,symbols_done,symbols_total):
        elapsed=max(.001,(dt.datetime.now(dt.timezone.utc)-started).total_seconds()); set_state(root,candidate['candidate_id'],'Máquina auditando',done,total,int((total-done)*elapsed/max(done,1)),f'{symbols_done}/{symbols_total} símbolos')
    set_state(root,candidate['candidate_id'],'Máquina auditando',0,len(entries),None,'auditor real')
    cached=path/'result.json'
    if cached.exists():
        result=json.loads(cached.read_text(encoding='utf8'))
    else:
        result,report,_=A.audit_adapter(adapter,progress=progress,execution_variant=execution_variant); dump(cached,result); (path/'informe.md').write_text(report+'\n',encoding='utf8')
    valid=result['integrity']['valid']; diagnosis={'protocol_version':'1.0-draft','candidate_id':candidate['candidate_id'],'revision':candidate['revision'],'status':'DIAGNOSED' if valid else 'INVALID','diagnosed_at_utc':now(),
      'input_fingerprint':{**fingerprint,'research_source_commit':candidate['research_run']['source_commit']},'machine_fingerprint':{'machine_commit':git_commit(),'adapter_contract':'Adapter/EntryDefinition v1','candle_source_key':candidate['candle_source']['key']},'integrity':result['integrity'],'diagnosis':{'net_expectancy_pct':result['net_expectancy_pct'],'gross_edge_pct':result['gross_edge_pct'],'main_area':result['main_area'],'severity':result['severity'],'evidence_by_area':_evidence(result)},'train_validation':{'net_expectancy_pct':(result['split_metrics']['TRAIN']['net_expectancy_pct']+result['split_metrics']['VALIDATION']['net_expectancy_pct'])/2,'severity':{area:max(result['split_metrics']['TRAIN']['severity'][area],result['split_metrics']['VALIDATION']['severity'][area]) for area in result['severity']}},'oos_once':{'net_expectancy_pct':result['split_metrics']['OOS']['net_expectancy_pct'],'severity':result['split_metrics']['OOS']['severity']},'artifacts':{'result_json':'result.json','report_markdown':'informe.md','audit_result':result},'safety':{'research_status':'DIAGNOSED' if valid else 'INVALID','strategy_profile_write':False,'agent_execution':False,'ledger_write':False}}
    dump(dp,diagnosis); set_state(root,candidate['candidate_id'],'sin actividad',len(entries),len(entries),0,'diagnóstico '+diagnosis['status']); return diagnosis

def next_revision(root,diagnosis_path,catalog_path,variant_id=None):
    diagnosis=json.loads(Path(diagnosis_path).read_text(encoding='utf8'))
    if diagnosis.get('status')!='DIAGNOSED': raise ValueError('diagnosis debe estar DIAGNOSED')
    area=diagnosis['diagnosis']['main_area']; variant=variant_id or RECIPES.get(area,(None,))[0]
    if variant not in RECIPES.get(area,()): raise ValueError(f'variant_id fuera del catálogo cerrado: {variant}')
    root,parent=Path(root),Path(diagnosis_path).parent; catalog_sha=sha(catalog_path); manifest=json.loads((parent/'candidate.json').read_text(encoding='utf8')); child=root/manifest['candidate_id']/str(manifest['revision']+1); _new(child); set_state(root,manifest['candidate_id'],'Research aplicando variante',detail=variant); child.mkdir(parents=True); shutil.copy2(parent/'entries.jsonl',child/'entries.jsonl'); manifest['revision']+=1; manifest['submitted_at_utc']=now(); manifest['entries_artifact']['sha256']=sha(child/'entries.jsonl'); manifest['execution_recipe']={'recipe_version':'1.0','area':area,'variant_id':variant,'parent_revision':manifest['revision']-1,'catalog_sha256':catalog_sha}; dump(child/'candidate.json',manifest); verify_revision(child); return child

def evaluate_attempt(parent,child,area):
    """Fase C: sólo acepta métricas explícitas TRAIN/VALIDATION; jamás usa OOS para decidir."""
    if not parent.get('train_validation') or not child.get('train_validation'): return {'status':'BLOCKED','reason':'faltan métricas TRAIN/VALIDATION explícitas; OOS no se consultó'}
    before,after=parent['train_validation'],child['train_validation']; ok=after['severity'][area]<before['severity'][area] and after['net_expectancy_pct']>=before['net_expectancy_pct']; return {'status':'PASS_TRAIN_VALIDATION' if ok else 'FAILED_ATTEMPT','area':area,'severity_before':before['severity'][area],'severity_after':after['severity'][area],'net_before':before['net_expectancy_pct'],'net_after':after['net_expectancy_pct']}

MAX_ATTEMPTS = 10
def history_path(root, candidate_id): return Path(root)/candidate_id/'history.json'
def record_attempt(root, candidate_id, attempt, allow_improved=False):
    """Historial append-only de investigación; el décimo fallo descarta."""
    path=history_path(root,candidate_id); current=json.loads(path.read_text(encoding='utf8')) if path.exists() else {'candidate_id':candidate_id,'attempts':[],'status':'IN_REFINEMENT'}
    if current['status']=='DISCARDED' or (current['status']=='IMPROVED' and not allow_improved): raise ValueError('candidato terminal; no se reemplaza su snapshot')
    current['attempts'].append({**attempt,'recorded_at_utc':now()})
    failed=sum(x.get('status') in ('FAILED_ATTEMPT','FAILED_OOS') for x in current['attempts'])
    current['status']='DISCARDED' if failed >= MAX_ATTEMPTS else ('IMPROVED' if attempt.get('status')=='PASSED_OOS' else 'IN_REFINEMENT')
    dump(path,current); return current

def rerun_improved(root, candidate_id, catalog_path):
    """Una vuelta desde un snapshot IMPROVED; sólo recetas cerradas, sin ejecución libre."""
    root=Path(root); history=json.loads(history_path(root,candidate_id).read_text(encoding='utf8'))
    if history.get('status')!='IMPROVED': raise ValueError('sólo un snapshot IMPROVED puede reenviarse')
    revisions=sorted((p for p in (root/candidate_id).iterdir() if p.is_dir() and (p/'diagnosis.json').exists()),key=lambda p:int(p.name))
    parent=revisions[-1]; before=json.loads((parent/'diagnosis.json').read_text(encoding='utf8')); area=before['diagnosis']['main_area']
    used=[x.get('variant_id') for x in history['attempts']]; variant=next((v for v in RECIPES[area] if v not in used),None)
    if variant is None: raise ValueError('catálogo cerrado agotado para esta categoría')
    child=next_revision(root,parent/'diagnosis.json',catalog_path,variant); after=diagnose_revision(root,child,SIM_VARIANT[variant]); attempt=evaluate_attempt(before,after,area); attempt.update({'variant_id':variant,'parent_revision':before['revision'],'child_revision':after['revision']})
    if attempt['status']=='PASS_TRAIN_VALIDATION':
        oos_before,oos_after=before['oos_once'],after['oos_once']; passes=oos_after['severity'][area]<oos_before['severity'][area] and oos_after['net_expectancy_pct']>=oos_before['net_expectancy_pct']; attempt['status']='PASSED_OOS' if passes else 'FAILED_OOS'
    return child,record_attempt(root,candidate_id,attempt,allow_improved=True)
