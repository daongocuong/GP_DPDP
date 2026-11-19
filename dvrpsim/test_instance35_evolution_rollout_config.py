import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dpdp_gp import Node, save_tree
from instance35_reduced_experiment import run_rollout
from instance35_gp_evolution import _run_vnsme_train, _validation_candidate_count


class Instance35ConfiguredRolloutTests(unittest.TestCase):
    def make_experiment(self, root):
        experiment = Path(root)
        (experiment/'data/train').mkdir(parents=True)
        (experiment/'data/validation').mkdir()
        (experiment/'data/test').mkdir()
        config = dict(config_sha256='config-hash',
            partitions={name:{'orders_sha256':f'{name}-hash','vehicles_sha256':'fleet-hash'}
                        for name in ('train','validation','test')},
            execution=dict(simulator_seed=0, supervisor_wall_seconds=300,
                runner_wall_guard_seconds=360, decision_hard_timeout_seconds=60,
                dispatch_step_seconds=600, simulation_horizon_seconds=604800,
                vnsme_internal_search_budget_seconds=50,
                vnsme_subprocess_hard_timeout_seconds=59))
        (experiment/'experiment_config.json').write_text(json.dumps(config),encoding='utf-8')
        tree=experiment/'tree.json'
        save_tree(tree,Node('feature','delta_distance_km'))
        return experiment,tree

    def capture_run(self, algorithm):
        with tempfile.TemporaryDirectory() as temp:
            experiment,tree=self.make_experiment(temp)
            captured={}
            def fake_supervise(command, supervisor_dir, timeout, **kwargs):
                captured.update(command=command,timeout=timeout,kwargs=kwargs)
                return dict(state='TIMEOUT',exit_code=1,valid_supervision=False,
                    remaining_job_processes=[],stop_event={'reason':'test stub'})
            with patch('instance35_reduced_experiment.supervise',side_effect=fake_supervise):
                record=run_rollout('config_probe',algorithm,'train',
                    tree_path=tree if algorithm=='gp' else None,experiment_dir=experiment)
            run_config=json.loads((experiment/'runs'/algorithm/'train'/'config_probe'/'run_config.json').read_text())
            self.assertEqual(record['J'],None)
            self.assertEqual(record['status'],'TIMEOUT')
            return captured,run_config

    def test_gp_uses_configured_stage_decision_and_runner_limits(self):
        captured,run_config=self.capture_run('gp')
        command=captured['command']
        self.assertEqual(captured['timeout'],300)
        self.assertEqual(captured['kwargs']['decision_timeout'],60)
        self.assertEqual(command[command.index('--wall-seconds')+1],'360')
        self.assertIn('--max-simulation-seconds',command)
        self.assertEqual(run_config['supervisor_wall_seconds'],300)
        self.assertEqual(run_config['runner_wall_guard_seconds'],360)
        self.assertEqual(run_config['decision_hard_timeout_seconds'],60)
        self.assertEqual(run_config['dispatch_step_seconds'],600)

    def test_vnsme_keeps_internal_search_separate_from_both_wall_limits(self):
        captured,run_config=self.capture_run('vnsme')
        command=captured['command']
        self.assertEqual(captured['timeout'],300)
        self.assertEqual(captured['kwargs']['decision_timeout'],60)
        self.assertEqual(command[command.index('--wall-seconds')+1],'360')
        self.assertEqual(command[command.index('--vnsme-search-budget-seconds')+1],'50')
        self.assertEqual(command[command.index('--vnsme-epoch-seconds')+1],'59')
        self.assertEqual(run_config['vnsme_internal_search_budget_seconds'],50)
        self.assertEqual(run_config['vnsme_subprocess_hard_timeout_seconds'],59)
        self.assertEqual(run_config['supervisor_wall_seconds'],300)
        self.assertEqual(run_config['decision_hard_timeout_seconds'],60)

    def test_absolute_task_deadline_caps_supervisor_without_changing_runner_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            experiment,tree=self.make_experiment(temp)
            fixed_now=1_800_000_000.0
            from datetime import datetime, timezone
            config=json.loads((experiment/'experiment_config.json').read_text(encoding='utf-8'))
            config['execution']['supervisor_wall_seconds']=3600
            config['execution']['runner_wall_guard_seconds']=3660
            config['execution']['decision_hard_timeout_seconds']=600
            config['execution']['task_deadline_utc']=datetime.fromtimestamp(
                fixed_now+12.5,timezone.utc).isoformat()
            (experiment/'experiment_config.json').write_text(json.dumps(config),encoding='utf-8')
            captured={}
            def fake_supervise(command, supervisor_dir, timeout, **kwargs):
                captured.update(command=command,timeout=timeout,kwargs=kwargs)
                return dict(state='TIMEOUT',exit_code=1,valid_supervision=False,
                    remaining_job_processes=[],stop_event={'reason':'test stub'})
            with patch('instance35_reduced_experiment.time.time',return_value=fixed_now), \
                 patch('instance35_reduced_experiment.supervise',side_effect=fake_supervise):
                result=run_rollout('deadline_probe','gp','train',tree_path=tree,
                    experiment_dir=experiment)
            run_config=json.loads((experiment/'runs/gp/train/deadline_probe/run_config.json')
                                  .read_text(encoding='utf-8'))
            self.assertAlmostEqual(captured['timeout'],12.5)
            self.assertEqual(captured['command'][captured['command'].index('--wall-seconds')+1],'3660')
            self.assertEqual(run_config['configured_supervisor_wall_seconds'],3600)
            self.assertAlmostEqual(run_config['supervisor_wall_seconds'],12.5)
            self.assertEqual(run_config['decision_hard_timeout_seconds'],600)
            self.assertIsNone(result['J'])

    def test_expired_task_deadline_prevents_launch(self):
        with tempfile.TemporaryDirectory() as temp:
            experiment,tree=self.make_experiment(temp)
            from datetime import datetime, timezone
            config=json.loads((experiment/'experiment_config.json').read_text(encoding='utf-8'))
            config['execution']['task_deadline_utc']=datetime.fromtimestamp(
                1_799_999_999,timezone.utc).isoformat()
            (experiment/'experiment_config.json').write_text(json.dumps(config),encoding='utf-8')
            with patch('instance35_reduced_experiment.time.time',return_value=1_800_000_000.0), \
                 patch('instance35_reduced_experiment.supervise') as supervise:
                with self.assertRaisesRegex(TimeoutError,'task deadline'):
                    run_rollout('expired_probe','gp','train',tree_path=tree,
                        experiment_dir=experiment)
            supervise.assert_not_called()
            self.assertFalse((experiment/'runs').exists())

    def test_vnsme_train_can_be_omitted_by_locked_protocol(self):
        self.assertFalse(_run_vnsme_train({'evaluation':{'run_vnsme_train':False}}))
        self.assertTrue(_run_vnsme_train({'evaluation':{'run_vnsme_train':True}}))
        self.assertTrue(_run_vnsme_train({}))

    def test_validation_candidate_count_reads_locked_evaluation_field(self):
        self.assertEqual(_validation_candidate_count({'evaluation':{'validation_candidate_count':3}}),3)
        self.assertEqual(_validation_candidate_count({'gp':{'validation_candidate_count':2},
            'evaluation':{'validation_candidate_count':3}}),2)


if __name__=='__main__':
    unittest.main()
