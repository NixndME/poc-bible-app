"""
Central registry of POC scope modules.

Single source of truth for optional modules that expand a POC's scope.
Adding a new module later = add one entry here + build its guide section
in static/index.html (MODULE_WEEKS) using the same key + week id(s).

Fields:
  key        - stable identifier stored in Poc.modules JSON and used by the guide
  label      - human-friendly name shown in the SE/admin UI
  week_ids   - the guide week id(s) this module renders (used to detect whether
               the customer has any progress on the module). Empty = no dedicated
               section, so it is always safe to remove.
"""

MODULES = [
    {"key": "hvm",         "label": "HVM / VM Essentials",   "week_ids": ["hvm-w1"]},
    {"key": "hks",         "label": "HKS / MKS",             "week_ids": ["hks-w1"]},
    {"key": "terraform",   "label": "Terraform",             "week_ids": ["tf-w1"]},
    {"key": "ansible",     "label": "Ansible",               "week_ids": []},
    {"key": "sdn",         "label": "SDN / Networking",      "week_ids": ["sdn-w1"]},
    {"key": "optionlists", "label": "Option Lists",          "week_ids": ["opl-w1"]},
    {"key": "pricing",     "label": "Prices & Price Sets",   "week_ids": ["price-w1"]},
    {"key": "whitelabel",  "label": "White Labelling",       "week_ids": ["wl-w1"]},
]

MODULE_BY_KEY = {m["key"]: m for m in MODULES}
MODULE_KEYS = set(MODULE_BY_KEY)
