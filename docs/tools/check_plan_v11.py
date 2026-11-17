import csv, re, glob, json, collections
MO = {m: i for i, m in enumerate(['M0','M1','M2','M3','M4a','M4b','M5','M6','M7'])}
PROP = {'FR-%d' % i for i in range(183, 194)}
W = list(csv.DictReader(open('out11/WORK_BREAKDOWN_STRUCTURE_v1.1.csv')))
D = list(csv.DictReader(open('out11/TASK_DEPENDENCY_MATRIX_v1.1.csv')))
R = list(csv.DictReader(open('out11/DEVELOPMENT_RISK_REGISTER_v1.1.csv')))
rtm = {r['id'] for r in csv.DictReader(open('src/04a_REQUIREMENTS_TRACEABILITY_MATRIX_v0.3.csv', encoding='utf-8-sig'))}
fcat = {'FN-KOP-14','FN-KOP-15','FN-KOP-16','FN-KOP-17','FN-KOP-18','FN-DES-08','FN-UIX-07','FN-UIX-08','FN-UIX-09','FN-MEA-05','FN-ANA-06','FN-PMV-13'} | {r['function_id'] for r in csv.DictReader(open('src/FUNCTION_CATALOG_v1.0.csv', encoding='utf-8-sig'))}
ids = {r['id'] for r in W}
tasks = {r['id']: r for r in W if r['level'] == 'Task'}
res = collections.OrderedDict()
res['wbs_rows'] = len(W); res['levels'] = dict(collections.Counter(r['level'] for r in W))
res['dup_ids'] = [k for k, v in collections.Counter(r['id'] for r in W).items() if v > 1]
res['dup_wbs_codes'] = [k for k, v in collections.Counter(r['wbs_code'] for r in W).items() if v > 1]
res['parent_missing'] = [r['id'] for r in W if r['parent_id'] and r['parent_id'] not in ids]
res['dep_missing'] = sorted({d for r in tasks.values() for d in r['dependencies'].split('; ') if d and d not in tasks})
res['edges_missing'] = [e for e in D if e['task_id'] not in tasks or e['depends_on'] not in tasks]
# edge list equals WBS dependency column
wb_edges = {(r['id'], d) for r in tasks.values() for d in r['dependencies'].split('; ') if d}
dm_edges = {(e['task_id'], e['depends_on']) for e in D}
res['edge_set_equal'] = wb_edges == dm_edges
res['ms_violations'] = [e for e in D if e['dep_ms'] != 'post-MVP' and e['task_ms'] != 'post-MVP' and MO[e['dep_ms']] > MO[e['task_ms']]]
# cycle check
g = collections.defaultdict(list)
for a, b in dm_edges: g[a].append(b)
state = {}
def dfs(n):
    state[n] = 1
    for m in g[n]:
        if state.get(m) == 1: return True
        if state.get(m) is None and dfs(m): return True
    state[n] = 2; return False
import sys; sys.setrecursionlimit(10000)
res['cycle'] = any(dfs(n) for n in list(tasks) if state.get(n) is None)
# requirement ids
bad = set()
for r in W:
    for q in r['requirement_ids'].replace(' (inherited)', '').split('; '):
        q = q.strip()
        if q and not q.startswith('(') and q not in rtm and q not in PROP: bad.add(q)
res['unknown_requirements'] = sorted(bad)
res['unknown_functions'] = sorted({f for r in W for f in r['function_id'].split('; ') if f.startswith('FN-') and f not in fcat})
mvp_tasks = [r for r in tasks.values() if r['release_scope'] in ('MVP-Core', 'MVP-Should')]
required = ['id', 'function_id', 'requirement_ids', 'description', 'expected_result', 'completion_criteria', 'priority', 'complexity',
            'effort_ml_pd', 'required_skills', 'deliverables', 'tests', 'definition_of_done', 'milestone', 'status']
res['empty_required_fields'] = [(r['id'], c) for r in mvp_tasks for c in required if not r[c].strip()]
res['tasks_no_deps'] = sorted(r['id'] for r in mvp_tasks if not r['dependencies'])
res['totals_ml'] = round(sum(float(r['effort_ml_pd']) for r in mvp_tasks), 1)
res['totals_pert'] = round(sum(float(r['effort_pert_pd']) for r in mvp_tasks), 1)
res['epic_rollup_ok'] = all(abs(float(e['effort_ml_pd']) - sum(float(t['effort_ml_pd']) for t in mvp_tasks if t['epic_id'] == e['id'])) < 0.05 for e in W if e['level'] == 'Epic')
# o<=ml<=p
res['est_order_bad'] = [r['id'] for r in mvp_tasks if not (float(r['effort_opt_pd']) <= float(r['effort_ml_pd']) <= float(r['effort_pess_pd']))]
# risk links
res['risk_task_missing'] = sorted({t.strip() for r in R for t in r['linked_tasks'].split(';') if t.strip() and t.strip() not in ('—',) and '*' not in t and not t.strip().startswith('All') and t.strip() not in tasks})
# task IDs referenced in markdown docs exist
md_missing = {}
for f in glob.glob('out11/*.md'):
    txt = open(f).read()
    refs = set(re.findall(r'\b(?:TSK-[A-Z]{3}-\d{2}-[A-Z]|XC-[A-Z]{3}-[A-Z0-9]+(?:-[A-Z0-9]+)?)\b', txt))
    miss = sorted(x for x in refs if x not in tasks and not x.endswith('-'))
    if miss: md_missing[f.split('/')[-1]] = miss
res['md_task_refs_missing'] = md_missing
fn_in_md = set()
for f in glob.glob('out11/*.md'):
    fn_in_md |= set(re.findall(r'\bFN-[A-Z]{3}-\d{2}\b', open(f).read()))
res['md_unknown_functions'] = sorted(x for x in fn_in_md if x not in fcat)
print(json.dumps(res, indent=1, default=str))
