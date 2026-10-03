# Phase 3 todo

- [x] Implement direct local HTTP and exact advertised-model validation.
- [x] Reject redirects, public/OpenRouter routes, credential inheritance and proxy routing.
- [x] Implement JSON and native adapters using the same operation dispatcher.
- [x] Implement the shared lifecycle with ordered result feedback and final answers only after operations finish.
- [x] Verify adapter parity for state, result/error ordering, provisional answers and round accounting.
- [x] Implement fixed settings, bounded operation rounds and a whole-turn deadline.
- [x] Isolate condition/track/checkpoint state, verify track-order invariance and maintain correct fresh-chat/follow-up boundaries.
- [x] Capture injected memory, transcripts, operations, snapshots and request metadata.
- [x] Provide validate, smoke, run, replay and report actions with the documented selections.
- [x] Record tool/model/API failures, partial coverage and missing usage honestly.
- [x] Verify retries, fallback and silent parameter/response repair do not occur.
- [x] Run mocked HTTP/lifecycle tests without OpenWorker or live inference and record evidence.
