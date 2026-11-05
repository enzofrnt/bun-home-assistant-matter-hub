#!/usr/bin/env python3
"""Compare an unchanged Node/pnpm checkout with this Bun checkout on macOS.

Run only on a quiet machine. Reinstalls remove node_modules in both checkouts,
use existing package caches, and do not alter source files or test configuration.
The test workload executes every upstream suite even if another suite fails.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import statistics
import subprocess
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline', type=Path, required=True)
parser.add_argument('--candidate', type=Path, default=Path(__file__).resolve().parents[1])
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--rounds', type=int, default=3)
parser.add_argument('--skip-install', action='store_true')
args = parser.parse_args()
if platform.system() != 'Darwin':
    parser.error('This harness uses macOS /usr/bin/time -l and RSS units.')
roots = {'node': args.baseline.resolve(), 'bun': args.candidate.resolve()}
args.output.mkdir(parents=True, exist_ok=True)
env = {**os.environ, 'CI': '1', 'NO_COLOR': '1', 'FORCE_COLOR': '0'}
records = []


def command_output(command):
    return subprocess.check_output(command, text=True).strip()


def test_hashes(root):
    paths = command_output(['git', '-C', str(root), 'ls-files']).splitlines()
    return {p: hashlib.sha256((root / p).read_bytes()).hexdigest()
            for p in paths if '.test.' in p or '.spec.' in p or '/test/' in p}


assert test_hashes(roots['node']) == test_hashes(roots['bun']), 'Test files differ!'
metadata = {
    'platform': platform.platform(),
    'cpu': command_output(['sysctl', '-n', 'machdep.cpu.brand_string']),
    'logical_cpus': os.cpu_count(),
    'memory_bytes': int(command_output(['sysctl', '-n', 'hw.memsize'])),
    'node': command_output(['node', '--version']),
    'bun': command_output(['bun', '--version']),
    'pnpm': subprocess.check_output(['pnpm', '--version'], cwd=roots['node'], text=True).strip(),
    'baseline_commit': command_output(['git', '-C', str(roots['node']), 'rev-parse', 'HEAD']),
    'test_files_unchanged': True,
    'rounds': args.rounds,
    'test_sha256': test_hashes(roots['node']),
    'rss_note': 'Sum of descendant RSS sampled every ~100 ms; shared pages may be counted multiple times. Not physical RAM or a hard upper bound.',
    'maxrss_note': 'macOS time -l maximum resident set size in bytes (largest process high-water mark, not sum of simultaneous children).',
}


def process_tree_rss(pid):
    rows = subprocess.check_output(['ps', '-axo', 'pid=,ppid=,rss='], text=True)
    processes = [tuple(map(int, row.split())) for row in rows.splitlines() if row.strip()]
    descendants = {pid}
    while True:
        added = {child for child, parent, _ in processes if parent in descendants}
        if added <= descendants:
            break
        descendants |= added
    return sum(rss * 1024 for child, _, rss in processes if child in descendants)


def measure(variant, workload, command, cwd, round_index):
    prefix = args.output / f'{round_index}-{variant}-{workload.replace("/", "-")}'
    start = time.perf_counter()
    peak = 0
    with prefix.with_suffix('.stdout.log').open('w') as out, prefix.with_suffix('.stderr.log').open('w') as err:
        proc = subprocess.Popen(['/usr/bin/time', '-l', *command], cwd=cwd, env=env,
                                stdout=out, stderr=err, start_new_session=True)
        deadline = start + 600
        while proc.poll() is None:
            peak = max(peak, process_tree_rss(proc.pid))
            if time.perf_counter() > deadline:
                import signal
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=20)
                raise RuntimeError(f'Timeout: {variant} {workload}')
            time.sleep(0.1)
        exit_code = proc.returncode
    stderr = prefix.with_suffix('.stderr.log').read_text()
    timing = re.findall(r'([\d.]+) real\s+([\d.]+) user\s+([\d.]+) sys', stderr)
    maxrss = re.findall(r'(\d+)\s+maximum resident set size', stderr)
    if not timing or not maxrss:
        raise RuntimeError(f'Missing timing output in {prefix}')
    wall, user, system = map(float, timing[-1])
    stdout = prefix.with_suffix('.stdout.log').read_text()
    counts = re.findall(r'Tests\s+([^\n]+)', stdout)
    row = dict(variant=variant, workload=workload, round=round_index,
               command=command, cwd=str(cwd), exit_code=exit_code,
               wall_seconds=wall, cpu_seconds=user + system,
               max_process_rss_bytes=int(maxrss[-1]), sampled_tree_rss_bytes=peak,
               tests=counts[-1].strip() if counts else None)
    records.append(row)
    (args.output / 'results.json').write_text(json.dumps({'metadata': metadata, 'records': records}, indent=2) + '\n')
    print(f'{round_index} {variant:4} {workload:18} exit={exit_code} wall={wall:.2f}s CPU={user+system:.2f}s RSS(tree)={peak/1024**2:.0f}MiB', flush=True)
    return row


for round_index in range(1, args.rounds + 1):
    # Alternate the first runtime to reduce order/cache bias.
    for variant in (['node', 'bun'] if round_index % 2 else ['bun', 'node']):
        root = roots[variant]
        if not args.skip_install:
            for relative in ['node_modules', 'packages/backend/node_modules', 'packages/common/node_modules',
                             'packages/frontend/node_modules', 'apps/home-assistant-matter-hub/node_modules']:
                path = root / relative
                if path.is_symlink():
                    path.unlink()
                elif path.exists():
                    shutil.rmtree(path)
            command = ['pnpm', 'install', '--offline', '--frozen-lockfile'] if variant == 'node' else ['bun', 'install', '--offline', '--frozen-lockfile']
            result = measure(variant, 'install-cached', command, root, round_index)
            if result['exit_code']:
                raise RuntimeError('Offline install failed; warm package caches before benchmarking.')
        measure(variant, 'build', ['pnpm' if variant == 'node' else 'bun', 'run', 'build'], root, round_index)
        # Same Vitest version, files, config and arguments. Only runtime/install differ.
        vitest = str((root / 'node_modules/vitest/vitest.mjs').resolve())
        for suite in ['packages/common', 'packages/backend', 'packages/frontend', 'apps/home-assistant-matter-hub']:
            measure(variant, f'test-{Path(suite).name}', [variant, vitest, 'run'], root / suite, round_index)

summary = {}
for variant in roots:
    summary[variant] = {}
    workloads = sorted({r['workload'] for r in records})
    for workload in workloads:
        rows = [r for r in records if r['variant'] == variant and r['workload'] == workload]
        summary[variant][workload] = {key: statistics.median(r[key] for r in rows)
                                     for key in ['wall_seconds', 'cpu_seconds', 'max_process_rss_bytes', 'sampled_tree_rss_bytes']}
        summary[variant][workload]['exit_codes'] = [r['exit_code'] for r in rows]
    totals = []
    for round_index in range(1, args.rounds + 1):
        rows = [r for r in records if r['variant'] == variant and r['round'] == round_index and r['workload'].startswith('test-')]
        totals.append({key: (sum if key.endswith('seconds') else max)(r[key] for r in rows)
                       for key in ['wall_seconds', 'cpu_seconds', 'max_process_rss_bytes', 'sampled_tree_rss_bytes']})
    summary[variant]['tests-total'] = {key: statistics.median(r[key] for r in totals) for key in totals[0]}
(args.output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
assert test_hashes(roots['node']) == test_hashes(roots['bun']), 'Tests changed during run!'
print(json.dumps(summary, indent=2))
