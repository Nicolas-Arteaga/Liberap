"""Motor Fase B: una receta cerrada por revisión, sin promoción ni OOS."""
from __future__ import annotations
import hashlib, json, shutil
from pathlib import Path

RECIPES = {
 "SALIDA": ("exit_giveback_10", "exit_giveback_25", "exit_giveback_50"),
 "SL": ("sl_atr_1_0", "sl_atr_1_5", "sl_atr_2_0"),
 "TIMEOUT": ("timeout_12h", "timeout_24h", "timeout_36h", "timeout_24h_if_losing"),
 "PAYOFF": ("payoff_tp_short_50", "payoff_break_even_1r", "payoff_trailing_2r"),
}
SIM_VARIANT = {"exit_giveback_10":"giveback_10", "exit_giveback_25":"giveback_25", "exit_giveback_50":"giveback_50",
 "sl_atr_1_0":"sl_atr_1.0", "sl_atr_1_5":"sl_atr_1.5", "sl_atr_2_0":"sl_atr_2.0",
 "timeout_12h":"time_exit_12h", "timeout_24h":"time_exit_24h", "timeout_36h":"time_exit_36h", "timeout_24h_if_losing":"time_stop_24h_if_losing",
 "payoff_tp_short_50":"tp_short_50", "payoff_break_even_1r":"break_even_1r", "payoff_trailing_2r":"trailing_2r"}

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def canonical(value): return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',',':'), ensure_ascii=False).encode()).hexdigest()

def next_revision(root, diagnosis_path, catalog_path):
    """Crea sólo la hija declarativa; no evalúa éxito ni OOS."""
    diagnosis=json.loads(Path(diagnosis_path).read_text(encoding='utf8'))
    if diagnosis.get('status') != 'DIAGNOSED': raise ValueError('diagnosis debe estar DIAGNOSED')
    area=diagnosis['diagnosis']['main_area']
    if area not in RECIPES: raise ValueError(f'{area}: familia no es execution_recipe en Fase B')
    parent=Path(diagnosis_path).parent
    manifest=json.loads((parent/'candidate.json').read_text(encoding='utf8'))
    variant=RECIPES[area][0]
    child=root/manifest['candidate_id']/str(manifest['revision']+1)
    if child.exists(): raise FileExistsError(child)
    child.mkdir(parents=True)
    shutil.copy2(parent/'entries.jsonl', child/'entries.jsonl')
    manifest['revision']+=1
    manifest['entries_artifact']['sha256']=sha(child/'entries.jsonl')
    manifest['execution_recipe']={'recipe_version':'1.0','area':area,'variant_id':variant,
      'parent_revision':manifest['revision']-1,'catalog_sha256':sha(catalog_path)}
    (child/'candidate.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    return child, manifest
