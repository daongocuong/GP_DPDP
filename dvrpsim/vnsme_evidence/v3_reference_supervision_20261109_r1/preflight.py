"""Verify only the authorized development instances and current Java build."""
import json
from pathlib import Path
import subprocess
import sys
root=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(root))
from dpdp_vnsme_reference_v3 import metadata,preflight_build
data=dict(instances=[metadata(i) for i in (2,3,4,5,6,9,10,13)],java=preflight_build(),
          head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
          rollouts=0,training=0,final_test_instances_opened=False)
(Path(__file__).parent/'preflight.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
print(json.dumps(dict(instance_roles={x['instance']:x['role'] for x in data['instances']},java=data['java']),indent=2))
