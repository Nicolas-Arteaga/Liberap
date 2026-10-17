"""Bucle Research↔Máquina aislado: artefactos inmutables, nunca producción."""
from __future__ import annotations
import datetime as dt
import os
import hashlib
import json
import bisect
import math
import statistics
import shutil
import subprocess
from pathlib import Path

import lab_audit as A
import lab_core as C
from audit_context import AuditContext, _rv20_mid_schedule
from lab_adapters import get_adapter

RECIPES = {"ENTRADA": ("entry_adx14_ge_25", "entry_realized_vol_20_mid"),
           "COSTOS": ("cost_hourly_range_ge_2x_roundtrip",),
           "SALIDA": ("exit_giveback_10", "exit_giveback_25", "exit_giveback_50"),
           "SL": ("sl_atr_1_0", "sl_atr_1_5", "sl_atr_2_0"),
           "TIMEOUT": ("timeout_12h", "timeout_24h", "timeout_36h", "timeout_24h_if_losing"),
           "PAYOFF": ("payoff_tp_short_50", "payoff_break_even_1r", "payoff_trailing_2r")}
SIM_VARIANT = {"exit_giveback_10":"giveback_10", "exit_giveback_25":"giveback_25", "exit_giveback_50":"giveback_50",
 "sl_atr_1_0":"sl_atr_1.0", "sl_atr_1_5":"sl_atr_1.5", "sl_atr_2_0":"sl_atr_2.0",
 "timeout_12h":"time_exit_12h", "timeout_24h":"time_exit_24h", "timeout_36h":"time_exit_36h", "timeout_24h_if_losing":"time_stop_24h_if_losing",
 "payoff_tp_short_50":"tp_short_50", "payoff_break_even_1r":"break_even_1r", "payoff_trailing_2r":"trailing_2r"}

# El catálogo documental es más amplio que la máquina actual. No se finge que
# una regla sin ejecutor fue probada: queda registrada como cobertura pendiente
# y el estado terminal conserva esa distinción.
UNIMPLEMENTED_CATALOG = {
    'ENTRADA': ('entry_hour_00_05_btc_bear', 'entry_hour_18_23_btc_bull',
                'entry_hour_00_05_vol_low', 'entry_hour_18_23_vol_high',
                'entry_btc_bear_vol_high', 'entry_btc_bull_vol_low', 'entry_invert_side',
                'entry_rsi14_oversold_ma50_long'),
    'COSTOS': ('cost_atr14_ge_1_5x_roundtrip', 'cost_atr14_ge_2_0x_roundtrip',
               'cost_volume_ge_1_5x_mean20'),
    'SALIDA': ('exit_opposite_ma_profile', 'exit_opposite_ma_or_close_below_ma7',
               'exit_opposite_ma_or_giveback_25', 'exit_close_below_ma7_or_giveback_25',
               'exit_all_three_confirmation'),
}

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

def materialize_candidate(root, adapter_name, candidate_id, entries, condition, display_name,
                          research_run=None, entry_source=None):
    """Entrada formal Fase A: Research aporta señales normalizadas, nunca código."""
    root=Path(root); dest=root/candidate_id/'1'; _new(dest); set_state(root,candidate_id,'Research generando',detail=display_name)
    adapter=get_adapter(adapter_name); entries=list(entries); dest.mkdir(parents=True); ep=dest/'entries.jsonl'; ep.write_bytes(_entries(entries))
    split=adapter.split_policy; policy=({'kind':'fixed_time','train_validation_ms':split.train_validation_ms,'validation_oos_ms':split.validation_oos_ms} if hasattr(split,'train_validation_ms') else {'kind':'temporal_quantile_50_25_25'})
    src=adapter.candle_source; manifest={'protocol_version':'1.0-draft','candidate_id':candidate_id,'revision':1,'display_name':display_name,'submitted_at_utc':now(),
      'research_run':research_run or {'run_id':'formal:external-candidate','family':'formal_candidate','hypothesis':condition,'source_commit':git_commit()},
      'adapter_definition':{'name':adapter.definition.name,'display_name':display_name,'aliases':[candidate_id],'population':adapter.definition.population,'bar_ms':adapter.definition.bar_ms,'cost_pct':adapter.definition.cost_pct,'require_coverage':adapter.definition.require_coverage},
      'entry_definition':{'source':entry_source or adapter.entry_definition.source,'condition':condition,'execution_time':adapter.entry_definition.execution_time,'side_convention':adapter.entry_definition.side_convention},
      'candle_source':{'key':src.key,'interval':src.interval,'start_ms':src.start_ms,'end_ms':src.end_ms},'split_policy':policy,'entries_artifact':{'path':'entries.jsonl','sha256':sha(ep),'count':len(entries)}}
    dump(dest/'candidate.json',manifest); verify_revision(dest); set_state(root,candidate_id,'Research generado',len(entries),len(entries),0,'revisión 1 inmutable'); return dest

def materialize_factory_candidate(root, candidate_id, entries, strategy_definition):
    """Materializa una hipótesis de la Fábrica como entrada formal Fase A.

    La Fábrica sólo entrega una definición declarativa y sus señales OHLC
    normalizadas. No puede ejecutar código arbitrario, iniciar procesos ni
    escribir StrategyProfiles: la admisión posterior de ``ResearchQueue``
    vuelve a verificar exactamente este manifiesto y su hash.
    """
    root = Path(root); dest = root / candidate_id / '1'; _new(dest)
    entries = sorted((dict(item) for item in entries), key=lambda item: (item['open_ms'], item['symbol']))
    if not entries:
        raise ValueError('la Fábrica no puede materializar un candidato sin señales')
    set_state(root, candidate_id, 'Research generando', detail='factory_candidate')
    dest.mkdir(parents=True); ep = dest / 'entries.jsonl'; ep.write_bytes(_entries(entries))
    base = get_adapter('rsi_reversal')
    manifest = {
        'protocol_version': '1.0-draft', 'candidate_id': candidate_id, 'revision': 1,
        'display_name': strategy_definition['display_name'], 'submitted_at_utc': now(),
        'research_run': {'run_id': 'evolutionary_lab:generator_only', 'family': 'factory_candidate',
                         'hypothesis': strategy_definition['condition'], 'source_commit': git_commit()},
        'factory_definition': strategy_definition,
        # El adaptador base aporta exclusivamente OHLC local y el split; las
        # entradas quedan congeladas en este artefacto, nunca se regeneran.
        'adapter_definition': {'name': 'factory_entries', 'base_candle_adapter': 'rsi_reversal',
                               'display_name': strategy_definition['display_name'], 'aliases': [candidate_id],
                               'population': 'raw', 'bar_ms': base.definition.bar_ms,
                               'cost_pct': base.definition.cost_pct, 'require_coverage': True},
        'entry_definition': {'source': 'evolutionary_lab generator-only sobre OHLC local',
                             'condition': strategy_definition['condition'],
                             'execution_time': 'cierre de la vela que confirma la condición',
                             'side_convention': '0=long, 1=short'},
        'candle_source': {'key': base.candle_source.key, 'interval': base.candle_source.interval,
                          'start_ms': base.candle_source.start_ms, 'end_ms': base.candle_source.end_ms},
        'split_policy': {'kind': 'temporal_quantile_50_25_25'},
        'entries_artifact': {'path': 'entries.jsonl', 'sha256': sha(ep), 'count': len(entries)},
    }
    dump(dest / 'candidate.json', manifest); verify_revision(dest)
    set_state(root, candidate_id, 'Research generado', len(entries), len(entries), 0, 'revisión 1 inmutable')
    return dest

def verify_revision(path):
    path=Path(path); candidate=json.loads((path/'candidate.json').read_text(encoding='utf8')); ep=path/'entries.jsonl'
    if not ep.exists() or sha(ep)!=candidate['entries_artifact']['sha256']: raise ValueError('huella de entries.jsonl inválida')
    entries=[json.loads(line) for line in ep.read_text(encoding='utf8').splitlines() if line]
    if len(entries)!=candidate['entries_artifact']['count']: raise ValueError('conteo entries inválido')
    if any(a['open_ms']>b['open_ms'] for a,b in zip(entries,entries[1:])): raise ValueError('entries sin orden temporal')
    return candidate,entries,{'candidate_sha256':canonical(candidate),'entries_sha256':sha(ep)}

def _base_adapter(candidate: dict):
    """Resuelve el proveedor OHLC permitido por un manifiesto formal."""
    definition = candidate['adapter_definition']
    if definition['name'] == 'factory_entries':
        return get_adapter(definition['base_candle_adapter'])
    return get_adapter(definition['name'])

class FrozenAdapter:
    def __init__(self, base, entries):
        self._base,self._entries=base,entries
        for name in ('name','aliases','population','bar_ms','cost_pct','definition','entry_definition','candle_source','split_policy','fidelity_result','fidelity_note'): setattr(self,name,getattr(base,name))
        if hasattr(self.split_policy, 'fit'):
            self.split_policy.fit(self._entries)
    def entries(self): return list(self._entries)
    def candles(self,symbol): return self._base.candles(symbol)
    def split_of(self,open_ms): return self._base.split_of(open_ms)


def _hourly_context(adapter, symbol, cache):
    """Velas 1h derivadas de la fuente del adaptador; cacheadas por símbolo.

    Todos los filtros de entrada/coste se calculan al último cierre 1h anterior
    a ``open_ms``. No hay consulta de red ni lectura de velas posteriores.
    """
    if symbol not in cache:
        hours = C.hourly_series(adapter.candles(symbol))
        cache[symbol] = (hours, [row[0] for row in hours])
    return cache[symbol]


def _closed_hours(adapter, entry, cache):
    hours, starts = _hourly_context(adapter, entry['symbol'], cache)
    # La entrada al cierre de hora puede usar esa hora ya cerrada; ninguna
    # posterior. Para entradas intrahora se usa la hora previa completa.
    end = bisect.bisect_right(starts, int(entry['open_ms']) - C.HOUR)
    return hours[:end]


def _adx14(hours):
    """ADX Wilder causal de la última vela, o None si no hay 28 velas."""
    period = 14
    if len(hours) < period * 2:
        return None
    trs, plus_dm, minus_dm = [], [], []
    for index in range(1, len(hours)):
        _t, high, low, close = hours[index]
        _pt, prev_high, prev_low, prev_close = hours[index - 1]
        up, down = high - prev_high, prev_low - low
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    if len(trs) < period:
        return None
    atr = sum(trs[:period]) / period
    plus = sum(plus_dm[:period]) / period
    minus = sum(minus_dm[:period]) / period
    dx = []
    for index in range(period - 1, len(trs)):
        if index > period - 1:
            atr = (atr * (period - 1) + trs[index]) / period
            plus = (plus * (period - 1) + plus_dm[index]) / period
            minus = (minus * (period - 1) + minus_dm[index]) / period
        denominator = plus + minus
        dx.append(0.0 if denominator <= 0 else 100.0 * abs(plus - minus) / denominator)
    if len(dx) < period:
        return None
    adx = sum(dx[:period]) / period
    for value in dx[period:]:
        adx = (adx * (period - 1) + value) / period
    return adx


def _realized_vol_mid(hours):
    """Filtro discreto de tercil medio con percentiles estrictamente causales."""
    window = 20
    if len(hours) < window + 21:
        return None
    closes = [row[3] for row in hours]
    returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))
               if closes[i] > 0 and closes[i - 1] > 0]
    if len(returns) < window + 20:
        return None
    vols = [statistics.stdev(returns[i - window:i]) for i in range(window, len(returns) + 1)]
    current, history = vols[-1], vols[:-1]
    if len(history) < 20:
        return None
    ordered = sorted(history)
    low = ordered[int((len(ordered) - 1) * (1 / 3))]
    high = ordered[int((len(ordered) - 1) * (2 / 3))]
    return low <= current <= high


def _realized_vol_mid_schedule(hours):
    """Precalcula el mismo filtro causal una vez por cierre 1h.

    La versión directa de :func:`_realized_vol_mid` se conserva como
    referencia. Aquí se mantiene ordenada sólo la distribución histórica de
    volatilidades que ya existía antes de cada vela; evita recalcularla por
    cada señal de 15m, sin cambiar percentiles ni ventana.
    """
    values = _rv20_mid_schedule(hours)
    return {end: value for end, value in enumerate(values) if value is not None}


def apply_entry_filter(adapter, entries, variant_id, context=None):
    """Aplica una sola regla cerrada a la población y devuelve evidencia causal.

    Las filas sin historia suficiente se excluyen; nunca se imputan indicadores.
    """
    context = context or AuditContext(adapter)
    kept, missing = [], 0
    for entry in entries:
        keep = context.filter_value(entry['symbol'], entry['open_ms'], variant_id)
        if keep is None:
            missing += 1
        elif keep:
            kept.append(entry)
    return kept, {'variant_id': variant_id, 'input_count': len(entries), 'kept_count': len(kept),
                  'removed_count': len(entries) - len(kept), 'missing_history_n': missing,
                  'calculation': 'causal_1h_closed_only'}

def _evidence(result):
    fwd24 = result['forward_return_pct_day_block_ci'].get(24, result['forward_return_pct_day_block_ci'].get('24'))
    return {'ENTRADA':{'metric':'forward_return_24h_mean_pct','value':fwd24['mean']},'COSTOS':{'metric':'gross_edge_pct','value':result['gross_edge_pct']},'PAYOFF':{'metric':'break_even_minus_win_rate_pp','value':(result['break_even_win_rate_pct'] or 0)-(result['win_rate_pct'] or 0)},'SALIDA':{'metric':'reached_2pct_ended_loss_pct','value':result['reached_2pct_ended_loss_pct']},'SL':{'metric':'sl_cf_reaches_tp_pct','value':result['sl_cf_reaches_tp_pct']},'TIMEOUT':{'metric':'timeout_damage','value':result['timeout_pct']*max(0,-(result['timeout_mean_return_pct'] or 0))}}

def diagnose_revision(root,path,execution_variant=None,funding_db=None,audit_context=None):
    """Audita sólo TRAIN/VALIDATION y materializa el diagnóstico de selección.

    No toca OOS. El único lector de OOS es :func:`audit_oos_once`, invocado
    sólo después de que una variante ya pasó el criterio TV.
    """
    root,path=Path(root),Path(path); dp=path/'diagnosis.json'; _new(dp); candidate,entries,fingerprint=verify_revision(path); base=_base_adapter(candidate); adapter=FrozenAdapter(base,entries); started=dt.datetime.now(dt.timezone.utc)
    def progress(done,total,symbols_done,symbols_total):
        elapsed=max(.001,(dt.datetime.now(dt.timezone.utc)-started).total_seconds()); set_state(root,candidate['candidate_id'],'Máquina auditando',done,total,int((total-done)*elapsed/max(done,1)),f'{symbols_done}/{symbols_total} símbolos')
    set_state(root,candidate['candidate_id'],'Máquina auditando',0,len(entries),None,'auditor real')
    cached=path/'result.json'
    if cached.exists():
        result=json.loads(cached.read_text(encoding='utf8'))
    else:
        funding_store = audit_context.funding_store if audit_context is not None else (A.FundingStore(funding_db) if funding_db else None)
        result,report,_=A.audit_adapter(adapter, progress=progress, execution_variant=execution_variant,
                                        funding_store=funding_store,
                                        allowed_splits=('TRAIN','VALIDATION'), audit_context=audit_context)
        dump(cached,result); (path/'informe.md').write_text(report+'\n',encoding='utf8')
    if result.get('funding_coverage', {}).get('enabled') and result.get('error', '').startswith('FUNDING_COVERAGE_INCOMPLETE'):
        raise ValueError(result['error'])
    valid=result['integrity']['valid']; diagnosis={'protocol_version':'1.0-draft','candidate_id':candidate['candidate_id'],'revision':candidate['revision'],'status':'DIAGNOSED' if valid else 'INVALID','diagnosed_at_utc':now(),
      'input_fingerprint':{**fingerprint,'research_source_commit':candidate['research_run']['source_commit']},'machine_fingerprint':{'machine_commit':git_commit(),'adapter_contract':'Adapter/EntryDefinition v1','candle_source_key':candidate['candle_source']['key']},'integrity':result['integrity'],'diagnosis':{'net_expectancy_pct':result['net_expectancy_pct'],'gross_edge_pct':result['gross_edge_pct'],'main_area':result['main_area'],'severity':result['severity'],'evidence_by_area':_evidence(result)},'train_validation':{'net_expectancy_pct':(result['split_metrics']['TRAIN']['net_expectancy_pct']+result['split_metrics']['VALIDATION']['net_expectancy_pct'])/2,'severity':{area:max(result['split_metrics']['TRAIN']['severity'][area],result['split_metrics']['VALIDATION']['severity'][area]) for area in result['severity']}},'oos_once':None,'funding':result.get('funding_coverage',{'enabled':False}),'artifacts':{'result_json':'result.json','report_markdown':'informe.md','audit_result':result},'safety':{'research_status':'DIAGNOSED' if valid else 'INVALID','strategy_profile_write':False,'agent_execution':False,'ledger_write':False}}
    dump(dp,diagnosis); set_state(root,candidate['candidate_id'],'sin actividad',len(entries),len(entries),0,'diagnóstico '+diagnosis['status']); return diagnosis

def audit_oos_once(root, path, execution_variant=None, funding_db=None, audit_context=None):
    """Lee OOS una única vez, exclusivamente después de un PASS TV."""
    root,path=Path(root),Path(path); out=path/'oos_result.json'
    if out.exists():
        return json.loads(out.read_text(encoding='utf8'))
    candidate,entries,_=verify_revision(path); base=_base_adapter(candidate); adapter=FrozenAdapter(base,entries)
    set_state(root,candidate['candidate_id'],'Máquina auditando OOS',0,len(entries),None,'lectura OOS única tras PASS TV')
    funding_store=audit_context.funding_store if audit_context is not None else (A.FundingStore(funding_db) if funding_db else None)
    result,report,_=A.audit_adapter(adapter, execution_variant=execution_variant, funding_store=funding_store,
                                    allowed_splits=('OOS',), audit_context=audit_context)
    dump(out,result); (path/'oos_informe.md').write_text(report+'\n',encoding='utf8')
    return result

def next_revision(root,diagnosis_path,catalog_path,variant_id=None,area_override=None,child_revision=None,audit_context=None):
    diagnosis=json.loads(Path(diagnosis_path).read_text(encoding='utf8'))
    if diagnosis.get('status')!='DIAGNOSED': raise ValueError('diagnosis debe estar DIAGNOSED')
    # El orquestador puede saltar una categoría más grave sin ejecutor (por
    # ejemplo COSTOS) y trabajar la siguiente categoría ejecutable. Esa área
    # debe quedar explícita en el recipe; no se vuelve a inferir del baseline.
    area=area_override or diagnosis['diagnosis']['main_area']; variant=variant_id or RECIPES.get(area,(None,))[0]
    if variant not in RECIPES.get(area,()): raise ValueError(f'variant_id fuera del catálogo cerrado: {variant}')
    root,parent=Path(root),Path(diagnosis_path).parent
    catalog_sha=sha(catalog_path)
    manifest=json.loads((parent/'candidate.json').read_text(encoding='utf8'))
    target_revision = int(child_revision or (manifest['revision'] + 1))
    child=root/manifest['candidate_id']/str(target_revision)
    _new(child)
    set_state(root,manifest['candidate_id'],'Research aplicando variante',detail=variant)
    child.mkdir(parents=True)
    parent_entries=[json.loads(line) for line in (parent/'entries.jsonl').read_text(encoding='utf8').splitlines() if line]
    filter_evidence = None
    if area in ('ENTRADA', 'COSTOS'):
        base=_base_adapter(manifest)
        parent_entries, filter_evidence = apply_entry_filter(FrozenAdapter(base,parent_entries), parent_entries, variant, audit_context)
    ep=child/'entries.jsonl'
    ep.write_bytes(_entries(parent_entries))
    parent_revision = manifest['revision']
    manifest['revision']=target_revision
    manifest['submitted_at_utc']=now()
    manifest['entries_artifact']={'path':'entries.jsonl','sha256':sha(ep),'count':len(parent_entries)}
    if filter_evidence is not None:
        # Los filtros de población no son reglas de ejecución: el protocolo
        # prohíbe colocar execution_recipe en estas revisiones.
        manifest.pop('execution_recipe', None)
        manifest['entry_filter']={**filter_evidence,'area':area,'catalog_sha256':catalog_sha,
                                  'parent_revision':parent_revision}
    else:
        manifest['execution_recipe']={'recipe_version':'1.0','area':area,'variant_id':variant,
                                      'parent_revision':parent_revision,'catalog_sha256':catalog_sha}
    dump(child/'candidate.json',manifest)
    verify_revision(child)
    return child

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

def _oos_view(result):
    """Reduce OOS para el historial sin asumir que la muestra sea diagnosticable.

    Un OOS con menos observaciones que el mínimo no puede convertir un intento
    TV válido en una excepción del worker. Es un fallo OOS explícito, no una
    métrica inventada.
    """
    valid = bool(result.get('integrity', {}).get('valid'))
    if not valid or 'net_expectancy_pct' not in result or 'severity' not in result:
        return {'valid': False, 'n': result.get('n', 0), 'artifact': 'oos_result.json',
                'reason': result.get('error', 'OOS no diagnosticable')}
    return {'valid': True, 'net_expectancy_pct': result['net_expectancy_pct'],
            'severity': result['severity'], 'n': result['n'],
            'artifact': 'oos_result.json'}

def _store_oos_view(path, view):
    dp=Path(path)/'diagnosis.json'; diagnosis=json.loads(dp.read_text(encoding='utf8'))
    diagnosis['oos_once']=view
    dump(dp, diagnosis)

def _set_terminal(root, candidate_id, status, reason, catalog_gaps, attempted_areas=()):
    """Persist a terminal outcome without pretending catalog coverage is full.

    The historical ``DISCARDED_CATALOG_PARTIAL`` label was useful but too
    coarse for a future reader: it did not say whether the attempt ceiling
    prevented an executable family from being tried.  Keep the old status for
    compatibility and add a machine-readable completeness contract.
    """
    path=history_path(root,candidate_id)
    history=json.loads(path.read_text(encoding='utf8')) if path.exists() else {'candidate_id':candidate_id,'attempts':[]}
    attempted=set(attempted_areas)
    executable_areas=set(RECIPES)
    gaps={area:list(variants) for area,variants in catalog_gaps.items() if variants}
    history.update({'status':status,'terminal_reason':reason,
        'catalog_completeness':'COMPLETE' if not gaps else 'PARTIAL',
        'missing_executors':gaps,
        'attempt_policy':{
            'max_attempts':MAX_ATTEMPTS,
            'attempts_completed':len(history.get('attempts', [])),
            'executable_areas_attempted':sorted(attempted),
            'executable_areas_not_reached_before_terminal':sorted(executable_areas-attempted),
            'rule':'no terminal exhaustive claim when documented variants lack executors'},
        'catalog_coverage':{'execution_variants_available':RECIPES,
            'not_executable_yet':gaps,'catalog_complete':not bool(gaps)},
        'closed_at_utc':now()})
    dump(path,history)
    return history

def run_autonomous(root, candidate_id, catalog_path, funding_db=None):
    """Recorre sin intervención las recetas con ejecutor y nunca escribe producción.

    Selecciona áreas por severidad TV descendente, agota una familia ejecutable
    antes de pasar a la siguiente y detiene en 10 intentos. Una receta pasa a
    OOS sólo cuando mejora TV; las reglas documentales sin ejecutor producen un
    descarte explícitamente parcial, no una falsa prueba exhaustiva.
    """
    root=Path(root); candidate_root=root/candidate_id; first=candidate_root/'1'
    if not first.exists(): raise FileNotFoundError(f'no existe revisión inicial: {first}')
    seed_manifest=json.loads((first/'candidate.json').read_text(encoding='utf8'))
    seed_adapter=_base_adapter(seed_manifest)
    # Una única instancia por candidato mantiene funding y derivados calientes.
    # El límite de OHLC se dimensiona contra memoria libre del worker.
    funding_store=A.FundingStore(funding_db) if funding_db else None
    # El límite se dimensiona contra la memoria física disponible del worker;
    # no contra un número fijo ajeno al universo real del candidato.
    audit_context=AuditContext(seed_adapter, funding_store=funding_store)
    first_diag=first/'diagnosis.json'
    baseline=diagnose_revision(root,first,funding_db=funding_db,audit_context=audit_context) if not first_diag.exists() else json.loads(first_diag.read_text(encoding='utf8'))
    if baseline.get('status') != 'DIAGNOSED':
        return _set_terminal(root,candidate_id,'INVALID','baseline_no_diagnosticable',UNIMPLEMENTED_CATALOG)
    baseline_oos=None
    used=[]; attempts=0; revision=1
    attempted_areas=set()
    while attempts < MAX_ATTEMPTS:
        severity=baseline['train_validation']['severity']
        ordered=sorted(severity, key=lambda area:(-severity[area], area))
        area=next((a for a in ordered if a in RECIPES and a not in attempted_areas),None)
        if area is None:
            return _set_terminal(root,candidate_id,'DISCARDED_CATALOG_PARTIAL',
                                 'agotadas las familias con ejecutor; el catálogo contiene variantes sin ejecutor',
                                 UNIMPLEMENTED_CATALOG, attempted_areas)
        variants=[v for v in RECIPES[area] if v not in used]
        if not variants:
            attempted_areas.add(area); continue
        for variant in variants:
            if attempts >= MAX_ATTEMPTS: break
            # Cada variante se mide contra la misma revisión 1, no contra la
            # población ya filtrada por una variante anterior. Así no se
            # combinan reglas sin preregistro y se puede atribuir causalidad.
            parent=first
            child=next_revision(root,parent/'diagnosis.json',catalog_path,variant,
                                area_override=area,child_revision=revision + 1,audit_context=audit_context)
            # Los filtros de COSTOS/ENTRADA ya quedaron materializados en
            # entries.jsonl; no tienen una regla de simulación de salida.
            # Las variantes de salida/SL/PAYOFF conservan su simulador.
            simulation_variant=SIM_VARIANT.get(variant)
            child_diag=diagnose_revision(root,child,simulation_variant,funding_db,audit_context)
            # Un filtro puede dejar una población con menos del mínimo de
            # observaciones. Eso es evidencia de que la variante no sirve;
            # jamás debe derribar al consumidor ni convertirse en un KeyError.
            if child_diag.get('status') != 'DIAGNOSED':
                attempt = {'status': 'FAILED_ATTEMPT', 'area': area,
                           'severity_before': baseline['train_validation']['severity'][area],
                           'severity_after': None,
                           'net_before': baseline['train_validation']['net_expectancy_pct'],
                           'net_after': None,
                           'invalid_child': True,
                           'invalid_reason': child_diag.get('integrity', {}).get('checks', {})}
            else:
                attempt=evaluate_attempt(baseline,child_diag,area)
            attempt.update({'variant_id':variant,'parent_revision':1,'child_revision':revision+1,
                            'selection_reference_revision':1,'oos_consulted':False})
            attempts += 1; used.append(variant); revision += 1
            if attempt['status']=='PASS_TRAIN_VALIDATION':
                if baseline_oos is None:
                    baseline_oos_result=audit_oos_once(root,first,funding_db=funding_db,audit_context=audit_context)
                    baseline_oos=_oos_view(baseline_oos_result); _store_oos_view(first,baseline_oos)
                child_oos_result=audit_oos_once(root,child,simulation_variant,funding_db,audit_context)
                child_oos=_oos_view(child_oos_result); _store_oos_view(child,child_oos)
                if not baseline_oos.get('valid') or not child_oos.get('valid'):
                    attempt.update({'status': 'FAILED_OOS', 'oos_consulted': True,
                                    'oos_not_diagnosticable': True,
                                    'baseline_oos': baseline_oos,
                                    'child_oos': child_oos})
                else:
                    passes=(child_oos['severity'][area] < baseline_oos['severity'][area]
                            and child_oos['net_expectancy_pct'] >= baseline_oos['net_expectancy_pct'])
                    attempt.update({'status':'PASSED_OOS' if passes else 'FAILED_OOS','oos_consulted':True,
                                    'oos_severity_before':baseline_oos['severity'][area],
                                    'oos_severity_after':child_oos['severity'][area],
                                    'oos_net_before':baseline_oos['net_expectancy_pct'],
                                    'oos_net_after':child_oos['net_expectancy_pct']})
            history=record_attempt(root,candidate_id,attempt)
            if attempt['status']=='PASSED_OOS':
                history['snapshot_revision']=revision; history['snapshot_path']=str(child)
                dump(history_path(root,candidate_id),history)
                return history
        attempted_areas.add(area)
    return _set_terminal(root,candidate_id,'DISCARDED_CATALOG_PARTIAL',
                         'límite de 10 intentos alcanzado; catálogo mantiene variantes sin ejecutor',
                         UNIMPLEMENTED_CATALOG, attempted_areas)
