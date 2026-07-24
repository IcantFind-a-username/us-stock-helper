# Evidence-gated adviser layer

This package implements the safe boundary around the thirteen public
investment-style lenses shown in the app. It is inspired by the public agent
catalog in `virattt/ai-hedge-fund` at commit
`e7c784f118866c5dba8fc2c4ee545f08cc611c61` (MIT), but does not copy its
prompts or portfolio-manager/order path.

The upstream project describes itself as an educational proof of concept. Its
outputs are therefore treated as hypotheses, never as facts. This package:

- reads only an immutable, point-in-time evidence packet;
- selects only the few lenses relevant to the horizon and unresolved question;
- requires citations, counterarguments, missing evidence, and abstention;
- caps every adviser and the whole council as a soft score adjustment;
- preserves the deterministic baseline direction and every hard safety gate;
- emits analysis only—there is no broker, order, trade, account, or credential
  interface.

Run:

```bash
PYTHONPATH=services/adviser_layer \
  python3 -m unittest discover -s services/adviser_layer/tests -v
```
