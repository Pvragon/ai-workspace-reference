#!/usr/bin/env python3
"""Bridge: reads toolchain.yaml, emits JSON to stdout for jq consumption."""
import json, sys, yaml

with open(sys.argv[1]) as f:
    print(json.dumps(yaml.safe_load(f)))
