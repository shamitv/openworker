# Phase 3 todo

- [ ] Implement direct local HTTP and exact advertised-model validation.
- [ ] Reject redirects, public/OpenRouter routes, credential inheritance and proxy routing.
- [ ] Implement JSON and native adapters using the same operation dispatcher.
- [ ] Implement the shared lifecycle with ordered result feedback and final answers only after operations finish.
- [ ] Verify adapter parity for state, result/error ordering, provisional answers and round accounting.
- [ ] Implement fixed settings, bounded operation rounds and a whole-turn deadline.
- [ ] Isolate condition/track/checkpoint state, verify track-order invariance and maintain correct fresh-chat/follow-up boundaries.
- [ ] Capture injected memory, transcripts, operations, snapshots and request metadata.
- [ ] Provide validate, smoke, run, replay and report actions with the documented selections.
- [ ] Record tool/model/API failures, partial coverage and missing usage honestly.
- [ ] Verify retries, fallback and silent parameter/response repair do not occur.
- [ ] Run mocked HTTP/lifecycle tests without OpenWorker or live inference and record evidence.
