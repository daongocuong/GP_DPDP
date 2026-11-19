"""Small, no-rollout checks for the manual instance_64 pipeline."""
import tempfile
from copy import deepcopy
from pathlib import Path
from shutil import copyfile
import unittest
from unittest.mock import patch

import instance64_temporal as m
import run_dpdp_insertion as runner
import subprocess
from dpdp_gp import Limits, Node, TreeError, validate_tree


class Instance64TemporalTests(unittest.TestCase):
    def test_time_boundaries_and_release_ties(self):
        bounds = m.split_bounds([3, 86398])
        self.assertEqual(tuple(map(str,bounds)), ('3','51840','69119','86398'))
        self.assertEqual([m.split_for(x,bounds) for x in (3,51839,51840,69118,69119,86398)],
                         ['train','train','validation','validation','test','test'])
        self.assertEqual(m.split_for(51840,bounds), m.split_for(51840,bounds))

    def test_overnight_slack(self):
        row = dict(creation_time='23:50:00',committed_completion_time='03:50:00')
        self.assertEqual(m.due_seconds(row)-m.seconds(row['creation_time']), 14400)

    def test_actual_partition_is_complete_and_loader_valid(self):
        m.check()  # reads CSV only, never imports or starts the simulator

    def test_cache_context_separates_splits(self):
        tree = Node('feature','delta_distance_km')
        self.assertNotEqual(m.runtime_context('train',tree),m.runtime_context('validation',tree))
        self.assertNotEqual(m.runtime_context('validation',tree),m.runtime_context('test',tree))

    def test_invalid_validation_candidate_cannot_win(self):
        rows = [dict(result=dict(valid=False,J=None),candidate=dict(nodes=1,tree_sha256='a',test_J=-1)),
                dict(result=dict(valid=True,J='10'),candidate=dict(nodes=2,tree_sha256='b',test_J=0)),
                dict(result=dict(valid=True,J='10'),candidate=dict(nodes=1,tree_sha256='c',test_J=999))]
        self.assertEqual(m.select_candidate(rows)['candidate']['tree_sha256'],'c')

    def test_tree_limits(self):
        chain = Node('feature','delta_distance_km')
        for _ in range(6):
            chain = Node('+',args=(chain,Node('const',1)))
        self.assertEqual(validate_tree(chain,Limits(6,63)),(13,6))
        too_deep = Node('+',args=(chain,Node('const',1)))
        with self.assertRaises(TreeError):
            validate_tree(too_deep,Limits(6,63))
        def full(depth):
            return Node('const',1) if not depth else Node('+',args=(full(depth-1),full(depth-1)))
        with self.assertRaises(TreeError):
            validate_tree(full(6),Limits(6,63))

    def test_population_and_generation_shape(self):
        rng,population,_ = m.initial_population()
        self.assertEqual(len(population),50)
        self.assertTrue(all(2 <= validate_tree(x,m.LIMITS)[1] <= 4 for x in population))
        evaluated = [dict(tree=t,valid=True,fitness=float(i),nodes=validate_tree(t,m.LIMITS)[0],
                          hash=m.tree_hash(t)) for i,t in enumerate(population)]
        next_population,_ = m.breed(rng,evaluated)
        self.assertEqual(len(next_population),50)
        self.assertEqual(next_population[:2],population[:2])
        self.assertEqual(m.CONFIG['additional_generations']+1,21)

    def test_missing_baseline_stops_before_training(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(m,'RUN',Path(tmp)), patch.object(m,'check'):
            with self.assertRaisesRegex(ValueError,'missing train baseline'):
                m.train()
            self.assertFalse((Path(tmp)/'training').exists())

    def test_train_probe_is_exact_pinned_subset_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'data/instance64_train'
            target.mkdir(parents=True)
            copyfile(m.inputs('train')['orders'],target/'train_orders.csv')
            copyfile(m.inputs('train')['vehicles'],target/'vehicle_info_100.csv')
            with patch.object(m,'RUN',Path(tmp)):
                record=m.prepare_train_probe()
                self.assertEqual(record['original_orders'],50)
                self.assertEqual(m.prepare_train_probe(),record)
                with (m.inputs('train_probe')['orders']).open('a',encoding='utf-8') as f:
                    f.write('tampered\n')
                with self.assertRaisesRegex(ValueError,'provenance or contents changed'):
                    m.prepare_train_probe()

    def test_pilot_reuses_baseline_and_invokes_only_gp_probe(self):
        calls=[]
        def invoke(split,policy,output,tree=None):
            calls.append((split,policy))
            return dict(J='5',wall_seconds=10,decision_wall_seconds_total=8)
        with (patch.object(m,'check'),patch.object(m,'baseline_score',return_value=12),
              patch.object(m,'prepare_train_probe',return_value={'original_orders':50}),
              patch.object(m,'invoke',side_effect=invoke),
              patch.object(m,'read',return_value={'peak_job_memory_bytes':1024}),
              patch.object(m,'write')):
            m.pilot()
        self.assertEqual(calls,[('train_probe','gp')])

    def test_completed_baseline_allows_only_manifest_pinned_orchestration_changes(self):
        recorded={'seed':0,'data_sha256':{'orders':'orders-hash'},
                  'source_fingerprint':{'instance64_temporal.py':'old-runner',
                                        'test_instance64_temporal.py':'old-test',
                                        'src/baselines/vnsme.py':'same-vnsme',
                                        'verify_dpdp_score.py':'same-scorer'}}
        current=deepcopy(recorded)
        current['source_fingerprint']['instance64_temporal.py']='new-runner'
        current['source_fingerprint']['test_instance64_temporal.py']='new-test'
        manifest={'source_sha256':dict(recorded['source_fingerprint'])}
        self.assertTrue(m.compatible_request_context(recorded,current,manifest,'vnsme','train'))
        for change in ('simulator','scorer','data','seed','manifest','policy'):
            with self.subTest(change=change):
                changed=deepcopy(current)
                pin=deepcopy(manifest)
                policy='vnsme'
                if change=='simulator': changed['source_fingerprint']['src/baselines/vnsme.py']='new-vnsme'
                elif change=='scorer': changed['source_fingerprint']['verify_dpdp_score.py']='new-scorer'
                elif change=='data': changed['data_sha256']['orders']='new-orders'
                elif change=='seed': changed['seed']=1
                elif change=='manifest': pin['source_sha256']['test_instance64_temporal.py']='wrong'
                else: policy='gp'
                self.assertFalse(m.compatible_request_context(recorded,changed,pin,policy,'train'))

    def test_git_stdout_utf8_preserves_diff_exactly(self):
        payload = 'diff --git a/x b/x\n+Đơn hàng “đúng” và dấu ngoặc kép cong ”\n'
        raw = payload.encode('utf-8')
        self.assertIn(b'\x9d', raw)
        with patch.object(runner.subprocess,'check_output',return_value=raw) as command:
            self.assertEqual(runner.git_stdout('diff','--'),payload)
        self.assertEqual(command.call_args.args[0][-2:],['diff','--'])

    def test_git_stdout_rejects_non_utf8_and_nonzero(self):
        with patch.object(runner.subprocess,'check_output',return_value=b'\x9d'):
            with self.assertRaisesRegex(ValueError,'non-UTF-8 stdout'):
                runner.git_stdout('diff','--')
        failure = subprocess.CalledProcessError(1,['git','diff'])
        with patch.object(runner.subprocess,'check_output',side_effect=failure):
            with self.assertRaises(subprocess.CalledProcessError):
                runner.git_stdout('diff','--')

    def test_supervision_failure_categories(self):
        folder = Path('example-supervision')
        with self.assertRaisesRegex(RuntimeError,'exit_code=1.*process.log'):
            m.require_clean_supervision(dict(state='EXITED',exit_code=1,valid_supervision=True),folder)
        with self.assertRaisesRegex(TimeoutError,'state=TIMEOUT.*process.log'):
            m.require_clean_supervision(dict(state='TIMEOUT',valid_supervision=False),folder)
        with self.assertRaisesRegex(RuntimeError,'supervision error.*SUPERVISOR_ERROR'):
            m.require_clean_supervision(dict(state='SUPERVISOR_ERROR',valid_supervision=False,error='watchdog'),folder)

    def test_invoke_nonzero_writes_invalid_reason_without_rollout(self):
        def fake_supervise(command, output, timeout, **kwargs):
            output.mkdir(parents=True,exist_ok=False)
            (output/'supervision.json').write_text(
                '{"state":"EXITED","exit_code":1,"valid_supervision":true}',encoding='utf-8')
            (output/'process.log').write_text('mock process failure',encoding='utf-8')
        with tempfile.TemporaryDirectory() as tmp, patch('dpdp_v3_supervisor.supervise',side_effect=fake_supervise):
            target=Path(tmp)/'attempt'
            with self.assertRaisesRegex(ValueError,'exit_code=1.*process.log'):
                m.invoke('train','vnsme',target)
            result=m.read(target/'audit.json')
            self.assertFalse(result['valid'])
            self.assertIsNone(result['J'])
            self.assertIn('exit_code=1',result['invalid_reason'])
            self.assertFalse((target/'run').exists())


if __name__ == '__main__':
    unittest.main()
