"""Small inspectable model/tool feedback controller with prior durable intent."""

from __future__ import annotations

from copy import deepcopy

from .artifacts import digest_json, canonical_bytes
from .context import project_context, plan_context, validate_context_config
from .protocol import tool_schemas
from .protocol import ProtocolError, ToolCall, validate_linkage, validate_nebius_linkage
from .providers import (
    ScriptedModel, AnthropicMessages, NebiusChatCompletions, NebiusHTTPError,
    NEBIUS_ERROR_CONTENT_TYPE, decode_provider_payload,
    parse_anthropic_response, parse_anthropic_usage, parse_nebius_response, parse_nebius_usage,
)
from .billing import ProviderEnvelope


def _validate_response_model(raw, expected_model: str) -> None:
    # Usage counters alone cannot bind the frozen model's monetary rates.
    if not isinstance(raw, dict) or raw.get("model") != expected_model:
        raise ProtocolError("provider model identity mismatch")


class ToolBroker:
    def __init__(self, store, artifacts, owner: dict, workspace, capabilities: list[str], verifier=None,
                 *, skills_capture=None, skills_config=None, skills_mode="broker_skill_loads_v1"):
        if skills_mode not in {"broker_skill_loads_v1", "accepted_skills_v1"}:
            raise ValueError("unsupported skills mode")
        if skills_mode == "accepted_skills_v1" and skills_capture is None:
            raise ValueError("accepted skills require explicit capture")
        self.skills_mode = skills_mode
        self.store, self.artifacts, self.owner = store, artifacts, owner
        self.workspace, self.capabilities, self.verifier = workspace, set(capabilities), verifier
        self.context_acceptance = None
        self.context_dispatch_id = None
        self.source_checkpoint = None
        self.replay_only = False
        self.skills_capture, self.skills_config = None, None
        if (skills_capture is None) != (skills_config is None):
            raise ValueError("skills require capture and configuration")
        if skills_capture is not None:
            from .skill_runtime import SKILL_TOOLS
            from .skills import read_catalog_snapshot
            if not SKILL_TOOLS <= self.capabilities:
                raise PermissionError("skills require both frozen capabilities")
            records = self.store.read_skill_records(owner)
            if not SKILL_TOOLS <= set(records["contract"]["capabilities"]):
                raise PermissionError("skills require both durable capabilities")
            read_catalog_snapshot(artifacts, owner["tenant_id"], owner["task_id"], skills_capture, skills_config)
            self.skills_capture, self.skills_config = deepcopy(skills_capture), deepcopy(skills_config)

    def pin_context(self, dispatch):
        # Membership comes exclusively from the accepted durable dispatch record.
        snapshot = self.store.read_skill_records(self.owner) if self.skills_mode == "accepted_skills_v1" \
            else self.store.snapshot(self.owner["tenant_id"], self.owner["task_id"])
        record = next((d for d in snapshot["dispatches"] if d["dispatch_id"] == dispatch["dispatch_id"]), None)
        if record is None or record["owner"] != self.owner:
            raise ValueError("retrieval projection owner mismatch")
        self.context_acceptance = deepcopy(record.get("context_acceptance"))
        self.context_dispatch_id = record["dispatch_id"]

    def execute(self, call: ToolCall) -> dict:
        call = ToolCall(call.call_id, call.name, deepcopy(call.arguments))
        if call.name not in self.capabilities:
            raise PermissionError("tool absent from frozen capabilities")
        if call.name in {"load_skill", "read_skill_resource"}:
            if self.skills_capture is None:
                raise PermissionError("skills broker is not configured")
            if self.skills_mode == "accepted_skills_v1":
                from .skill_disclosure import execute_skill
            else:
                from .skill_runtime import execute_skill
            return execute_skill(self, call)
        owner = self.owner
        identity = digest_json({"attempt": owner["attempt_id"], "call": call.call_id})
        retrieval = None
        if call.name == "read_context_artifact":
            if self.context_acceptance is None:
                raise PermissionError("no accepted context projection for this response")
            retrieval = {"projection_id": self.context_acceptance["projection_id"],
                         "accepted_sequence": self.context_acceptance["accepted_sequence"],
                         "model_dispatch_id": self.context_dispatch_id}
        dispatch = self.store._begin_dispatch(
            owner, "action-" + identity[:32], "dispatch-" + identity[:32], call.name,
            digest_json({"call_digest": call.digest, "projection_id": retrieval["projection_id"]}) if retrieval else call.digest,
            0, context_retrieval=retrieval,
            replay_only=self.replay_only,
        )
        state = dispatch.get("effect_state")
        if dispatch.get("duplicate"):
            if state in {"succeeded", "failed_known"} and dispatch.get("result_ref"):
                return self.artifacts.get_json(
                    owner["tenant_id"], owner["task_id"], dispatch["result_ref"]["digest"]
                )
            # A known effect without its durable result also cannot run again.
            # Billing settlement never grants permission to repeat the effect.
            raise RuntimeError("unresolved duplicate dispatch requires a durable known result or reconciliation")
        if state == "unknown":
            raise RuntimeError("unknown effect requires reconciliation")
        try:
            args = call.arguments
            if call.name == "read_context_artifact":
                from .context_retrieval import read_context_artifact
                if self.context_acceptance is None:
                    raise PermissionError("no accepted context projection for this response")
                manifest = self.context_acceptance["manifest"]
                value = read_context_artifact(
                    self.artifacts, owner["tenant_id"], owner["task_id"], manifest["offload_refs"], args,
                    max_bytes=manifest["config"]["retrieval_max_bytes"],
                )
            elif call.name == "read_file":
                value = self.workspace.read(args["path"])
            elif call.name == "search":
                value = self.workspace.search(args["query"])
            elif call.name == "replace_text":
                value = self.workspace.replace(
                    args["path"], args["expected_digest"], args["old"], args["new"]
                )
            elif call.name == "run_tests":
                if self.verifier is None:
                    raise PermissionError("worker has no configured test recipe")
                value = self.verifier(self.workspace.snapshot())
            elif call.name == "finish":
                value = {"completion_proposal": args["summary"], "verified": False}
            else:
                raise PermissionError("unregistered tool")
            result, effect = (
                {"call_id": call.call_id, "tool": call.name, "ok": True, "value": value},
                "succeeded",
            )
        except (ValueError, PermissionError, FileNotFoundError) as exc:
            result, effect = (
                {
                    "call_id": call.call_id,
                    "tool": call.name,
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
                "failed_known",
            )
        except Exception:
            # A general I/O failure may follow a mutation; preserve uncertainty.
            self.store.finish_dispatch(
                owner["tenant_id"], dispatch["dispatch_id"], "unknown-" + identity[:32], "unknown", None, None
            )
            raise
        if call.name == "read_context_artifact" and self.context_acceptance is not None:
            result["context_provenance"] = {
                "projection_id": self.context_acceptance["projection_id"],
                "accepted_sequence": self.context_acceptance["accepted_sequence"],
            }
        ref = self.artifacts.put_json(owner["tenant_id"], owner["task_id"], result)
        self.store.finish_dispatch(
            owner["tenant_id"], dispatch["dispatch_id"], "receipt-" + identity[:32], effect, 0, ref
        )
        return result


class Harness:
    def __init__(
        self,
        store,
        artifacts,
        *,
        max_turns: int = 8,
        context_bytes: int = 131072,
        provider_envelopes: dict | None = None,
        context_config: dict | None = None,
        skills_capture=None, skills_config=None,
    ):
        self.store, self.artifacts = store, artifacts
        self.max_turns, self.context_bytes = max_turns, context_bytes
        from .contracts import freeze

        self.provider_envelopes = freeze(provider_envelopes or {})
        self.context_config = freeze(validate_context_config(context_config)) if context_config is not None else None
        if (skills_capture is None) != (skills_config is None):
            raise ValueError("skills require capture and configuration")
        if skills_capture is not None and self.context_config is None:
            raise ValueError("skills require explicit context configuration")
        self.skills_capture = freeze(skills_capture) if skills_capture is not None else None
        self.skills_config = freeze(skills_config) if skills_config is not None else None

    def run(
        self, owner: dict, contract: dict, workspace, model, verifier=None, *, restored: dict | None = None,
        pause_after_turn: int | None = None,
    ) -> dict:
        skills = self.skills_capture is not None
        if skills and restored is not None:
            if not isinstance(restored, dict) or not isinstance(restored.get("source_checkpoint"), str):
                raise ValueError("skills restore requires an authoritative checkpoint identity")
            from .recovery import restore_checkpoint
            authoritative = restore_checkpoint(self.store, self.artifacts, owner["tenant_id"], owner["task_id"],
                                               restored["source_checkpoint"])
            if "skills_state" not in authoritative or canonical_bytes(authoritative) != canonical_bytes(restored):
                raise ValueError("skills restore claims differ from authoritative checkpoint")
            restored = authoritative
        if not skills and restored is not None and "skills_state" in restored:
            raise ValueError("skills checkpoint requires explicit accepted-skills configuration")
        if not isinstance(model, (ScriptedModel, AnthropicMessages, NebiusChatCompletions)):
            raise ValueError("unsupported model adapter")
        native = isinstance(model, NebiusChatCompletions)
        usage_parser = parse_nebius_usage if native else parse_anthropic_usage
        envelope = None
        if isinstance(model, (AnthropicMessages, NebiusChatCompletions)):
            if not model.enabled or model.model != contract["model"]:
                raise PermissionError("live provider not explicitly enabled under frozen model identity")
            if native and model.endpoint != NebiusChatCompletions.ENDPOINT:
                raise PermissionError("unapproved Nebius endpoint")
            if not self.provider_envelopes.get(model.model) or self.provider_envelopes[
                model.model
            ] != contract.get("rate_snapshot"):
                raise PermissionError("task rate envelope is not approved by the trusted gateway")
            envelope = ProviderEnvelope(contract.get("rate_snapshot"), model.model)
            if native and envelope.data["cache_read_per_million"] > envelope.data["input_per_million"]:
                # Missing cache breakdown is billed at the input rate. That is
                # conservative only when cached tokens cannot carry a premium.
                raise PermissionError("Nebius cache premium envelope is unsupported")
        tenant, task = owner["tenant_id"], owner["task_id"]
        skills_snapshot = None
        if skills:
            from .providers import skills_capability
            from .skills import read_catalog_snapshot
            from .skill_disclosure import check_profile, render_system
            skills_capability(model)
            if not {"load_skill", "read_skill_resource"} <= set(contract["capabilities"]):
                raise PermissionError("skills require both frozen capabilities")
            skills_snapshot = read_catalog_snapshot(self.artifacts, tenant, task, self.skills_capture, self.skills_config)
            check_profile(self.store.read_skill_records(owner), self.skills_capture)
        else:
            if self.store.has_skills_acceptance(owner):
                raise ValueError("skills acceptance cannot continue with skills disabled")
        if pause_after_turn is not None:
            from .contracts import strict_int

            strict_int(pause_after_turn, "pause_after_turn", 1, self.max_turns)
        messages = [{"role": "user", "content": "\n".join(contract["requirements"])}]
        broker = ToolBroker(self.store, self.artifacts, owner, workspace, contract["capabilities"], verifier,
            **({"skills_capture": self.skills_capture, "skills_config": self.skills_config,
                "skills_mode": "accepted_skills_v1"} if skills else {}))
        broker.source_checkpoint = restored["source_checkpoint"] if skills and restored else None
        evidence = []
        first_turn = 0
        last_context = None
        previous_projection_id = None
        system = "Follow only the frozen task constraints: " + str(contract["requirements"])
        if skills:
            system = render_system(contract, skills_snapshot["catalog"])
        include_context = self.context_config is not None and self.context_config["strategy"] == "tool_result_offload_v1"
        adapter = None
        if self.context_config is not None:
            from .providers import context_capability
            if include_context and "read_context_artifact" not in contract["capabilities"]:
                raise PermissionError("context offload requires frozen retrieval capability")
            if include_context and isinstance(model, AnthropicMessages):
                raise ValueError("Anthropic offload is unsupported")
            adapter = {
                "provider": "nebius" if native else "anthropic" if envelope else "scripted",
                "protocol": "chat_completions" if native else "messages" if envelope else "anthropic",
                "adapter_version": "context_skills_v1" if skills else "context_v1", "model": contract["model"],
                "endpoint": model.endpoint if native else None,
                "system_digest": digest_json(system), "tools_digest": digest_json(
                    model.build_request(messages, system, envelope.data["max_output_tokens"],
                                        include_context=include_context,
                                        **({"include_skills": True} if skills else {}))["tools"]
                    if envelope else tool_schemas(include_context=include_context, include_skills=skills)),
                "continuation_capability": context_capability(model),
            }
            if skills:
                adapter["skills_capability"] = skills_capability(model)
        if restored is not None:
            if restored["contract_digest"] != digest_json(contract):
                raise ValueError("restored checkpoint contract drift")
            if restored["workspace_digest"] != digest_json(workspace.snapshot()):
                raise ValueError("restored workspace differs from checkpoint")
            messages, evidence, first_turn = (
                deepcopy(restored["messages"]), deepcopy(restored["evidence"]), restored["next_turn"]
            )
            if "context" in restored:
                if self.context_config is None:
                    raise ValueError("context checkpoint requires explicit compatible configuration")
                context = restored["context"]
                acceptance = context["acceptance"]
                manifest = acceptance["manifest"]
                if manifest["config"] != self.context_config or manifest["binding"]["adapter"] != adapter:
                    raise ValueError("restored context config/adapter drift")
                from .recovery import validate_context_manifest
                validated = validate_context_manifest(self.artifacts, tenant, task, manifest)
                if skills:
                    from .skill_disclosure import build_request
                    record, _ = build_request(model, validated["projection"], validated["catalog"], self.context_config)
                else:
                    rebuilt = model.build_request(validated["projection"]["messages"], system,
                    envelope.data["max_output_tokens"], include_context=include_context) if envelope else {
                    "projection": validated["projection"], "digest": manifest["projection_digest"],
                    "bytes": len(canonical_bytes(validated["projection"])),
                    "token_count": None, "token_count_status": "provider tokenizer not configured",
                }
                    record = {"provider": "nebius", "protocol": "chat_completions", "endpoint": model.endpoint,
                              "payload": rebuilt} if native else rebuilt
                if canonical_bytes(record) != canonical_bytes(validated["request"]):
                    raise ValueError("restored accepted request reconstruction mismatch")
                last_context = deepcopy(context)
            elif self.context_config is not None:
                raise ValueError("legacy checkpoint cannot restore context path")
            for item in evidence:
                saved = self.artifacts.get_json(tenant, task, item["request_ref"]["digest"])
                if native:
                    if (
                        saved.get("provider") != "nebius"
                        or saved.get("protocol") != "chat_completions"
                        or saved.get("endpoint") != model.endpoint
                        or saved.get("payload", {}).get("model") != model.model
                    ):
                        raise ValueError("restored provider identity drift")
                elif saved.get("provider") == "nebius":
                    raise ValueError("restored provider identity drift")

        def save_checkpoint(status, next_turn):
            if self.context_config is not None:
                last_context["checkpoint_history_digest"] = digest_json(messages)
                last_context["checkpoint_evidence_digest"] = digest_json(evidence)
            if skills:
                known = self.store.find_skill_checkpoint(owner, last_context, next_turn, status == "completion_proposed")
                if known is not None:
                    files = self.artifacts.get_json(tenant, task, known["manifest"]["workspace_ref"]["digest"])
                    if files != workspace.snapshot():
                        raise ValueError("known checkpoint workspace drift")
                    checkpoint = self.store.checkpoint(owner, known["manifest"])
                    return {"status": status, "turns": next_turn, "messages": messages, "evidence": evidence,
                            "checkpoint_id": checkpoint["checkpoint_id"]}
                if prior_dispatch_duplicate:
                    raise RuntimeError("known turn lacks accepted skills checkpoint; checkpoint reconciliation required")
            workspace_ref = self.artifacts.put_json(tenant, task, workspace.snapshot())
            checkpoint_payload = {
                "schema": 1, "messages": messages, "evidence": evidence,
                "workspace_ref": workspace_ref, "projection_version": 1, "status": status,
            }
            if self.context_config is not None:
                last_context["checkpoint_history_digest"] = digest_json(messages)
                last_context["checkpoint_evidence_digest"] = digest_json(evidence)
                checkpoint_payload.update(schema=2, kind="harness_context_v1", context=deepcopy(last_context))
            if skills:
                from .skill_disclosure import derive_skills_state
                after = derive_skills_state(self.store, self.artifacts, owner, self.skills_capture, self.skills_config,
                                           source_checkpoint=broker.source_checkpoint)
                after_ref = self.artifacts.put_json(tenant, task, after)
                post = {"state_ref": after_ref, "state_digest": digest_json(after)}
                checkpoint_payload.update(schema=3, kind="harness_skills_v1", skills_after_turn=post)
            checkpoint_ref = self.artifacts.put_json(tenant, task, checkpoint_payload)
            manifest = {
                "artifact_ref": checkpoint_ref, "workspace_ref": workspace_ref,
                "provider_artifacts": evidence, "next_turn": next_turn,
                "completion_proposed": status == "completion_proposed",
            }
            if self.context_config is not None:
                manifest.update(schema=2, kind="harness_context_v1", context=deepcopy(last_context))
            if skills:
                manifest.update(schema=3, kind="harness_skills_v1", skills_after_turn=post)
            existing = [] if skills else [
                c for c in self.store.snapshot(tenant, task)["checkpoints"]
                if c["owner"] == owner and c["manifest"] == manifest
            ]
            checkpoint = existing[-1] if existing else self.store.checkpoint(owner, manifest)
            return {
                "status": status, "turns": next_turn, "messages": messages,
                "evidence": evidence, "checkpoint_id": checkpoint["checkpoint_id"],
            }

        if restored is not None and restored.get("completion_proposed") is True:
            return {
                "status": "completion_proposed", "turns": first_turn,
                "messages": messages, "evidence": evidence,
                "checkpoint_id": restored["source_checkpoint"],
            }
        prior_dispatch_duplicate = False
        for turn in range(first_turn, self.max_turns):
            binding = None
            prior_dispatch = None
            if self.context_config is None:
                projection = project_context(contract, messages, evidence, self.context_bytes,
                                             protocol="nebius" if native else "anthropic")
            else:
                snapshot = self.store.read_skill_proof(owner, source_checkpoint=broker.source_checkpoint) if skills else self.store.snapshot(tenant, task)
                current_action = f"model-{owner['attempt_id']}-{turn}"
                prior_dispatch = next((d for d in snapshot["dispatches"] if d["dispatch_id"] == current_action), None)
                frontier = snapshot["frontier"]
                binding = {
                    "tenant_id": tenant, "task_id": task, "generation": owner["generation"], "owner": owner,
                    "contract_digest": digest_json(contract), "source_history_digest": digest_json(messages),
                    "source_evidence_digest": digest_json(evidence),
                    "source_workspace_digest": digest_json(workspace.snapshot()), "source_frontier": frontier,
                    "expected_previous_projection_id": previous_projection_id, "adapter": adapter,
                    "config_digest": digest_json(self.context_config),
                }
                if prior_dispatch is not None:
                    accepted = prior_dispatch.get("context_acceptance")
                    if accepted is None:
                        raise ValueError("legacy dispatch cannot become a context dispatch")
                    saved = accepted["manifest"]
                    if (saved["config"] != self.context_config or saved["binding"]["adapter"] != adapter
                            or saved["binding"]["owner"] != owner
                            or saved["source_history_digest"] != digest_json(messages)
                            or saved["source_evidence_digest"] != digest_json(evidence)
                            or saved["source_workspace_digest"] != digest_json(workspace.snapshot())):
                        raise ValueError("duplicate projected dispatch source/config drift")
                    binding = deepcopy(saved["binding"])
                    if skills:
                        from .recovery import validate_context_manifest
                        accepted_skills = validate_context_manifest(self.artifacts, tenant, task, saved)
                        skills_state = accepted_skills["skills_state"]
                        state_ref = saved["skills_state_ref"]
                elif skills:
                    from .skill_disclosure import derive_skills_state
                    skills_state = derive_skills_state(self.store, self.artifacts, owner,
                                                      self.skills_capture, self.skills_config,
                                                      source_checkpoint=broker.source_checkpoint)
                    binding["skills_state_digest"] = digest_json(skills_state)
                projection = plan_context(contract, messages, evidence, binding=binding,
                    config=self.context_config, protocol="nebius" if native else "anthropic")
            if skills:
                from .skill_disclosure import build_request
                request_record, prompt_digest = build_request(model, projection["projection"],
                                                              skills_snapshot["catalog"], self.context_config)
                payload = request_record["payload"] if native else request_record
                if prior_dispatch is not None:
                    if canonical_bytes(request_record) != canonical_bytes(accepted_skills["request"]):
                        raise ValueError("duplicate skills request drift")
                    request_ref = saved["request_ref"]
                else:
                    request_ref = self.artifacts.put_json(tenant, task, request_record)
                    state_ref = self.artifacts.put_json(tenant, task, skills_state)
                kind, bound = ("model.nebius", envelope.bound_units) if native else ("model.scripted", 0)
            elif envelope:
                payload = model.build_request(
                    projection["projection"]["messages"] if binding is not None else messages,
                    system,
                    envelope.data["max_output_tokens"],
                    **({"include_context": include_context} if binding is not None else {}),
                )
                if len(canonical_bytes(payload)) > envelope.data["max_request_bytes"]:
                    raise ValueError("frozen provider request byte bound exceeded")
                request_record = {
                    "provider": "nebius", "protocol": "chat_completions",
                    "endpoint": model.endpoint, "payload": payload,
                } if native else payload
                request_ref = self.artifacts.put_json(tenant, task, request_record)
                kind, bound = "model.nebius" if native else "model.anthropic", envelope.bound_units
            else:
                payload = {k: v for k, v in projection.items() if k != "offloads"}
                request_record = payload
                request_ref = self.artifacts.put_json(tenant, task, request_record)
                kind, bound = "model.scripted", 0
            action_id = f"model-{owner['attempt_id']}-{turn}"
            if binding is None:
                dispatch = self.store.begin_dispatch(owner, action_id, action_id, kind, digest_json(request_record), bound)
            else:
                offload_refs = []
                for offload in ([] if skills and prior_dispatch is not None else projection["offloads"]):
                    descriptor = {k: v for k, v in offload.items() if k != "body"}
                    descriptor["artifact_ref"] = self.artifacts.put(tenant, task, offload["body"].encode("utf-8"), "text/plain; charset=utf-8")
                    offload_refs.append(descriptor)
                projection_ref = saved["projection_ref"] if skills and prior_dispatch is not None else \
                    self.artifacts.put_json(tenant, task, projection["projection"])
                raw_history_ref = saved["raw_history_ref"] if skills and prior_dispatch is not None else self.artifacts.put_json(tenant, task, {
                    "schema": 1, "messages": messages, "evidence": evidence,
                    "workspace_digest": binding["source_workspace_digest"],
                })
                manifest = {
                    "context_schema": 2 if skills else 1, "strategy": self.context_config["strategy"],
                    "projection_ref": projection_ref, "projection_digest": projection["digest"],
                    "raw_history_ref": raw_history_ref,
                    **{k: binding[k] for k in ("source_history_digest", "source_evidence_digest", "source_workspace_digest")},
                    "request_ref": request_ref, "request_digest": digest_json(request_record),
                    "binding": binding, "config": self.context_config, "offload_refs": offload_refs,
                    "restored_from_projection_id": restored["context"]["acceptance"]["projection_id"] if restored else None,
                    "source_checkpoint": restored["source_checkpoint"] if restored else None,
                }
                if skills:
                    manifest.update(skills_state_ref=state_ref, skills_state_digest=digest_json(skills_state),
                                    prompt_digest=prompt_digest)
                    if prior_dispatch is not None:
                        manifest["offload_refs"] = deepcopy(saved["offload_refs"])
                dispatch = self.store.begin_projected_dispatch(owner, action_id, action_id, kind,
                    digest_json(request_record), bound, projection_manifest=manifest,
                    expected_frontier=binding["source_frontier"], expected_previous_projection_id=previous_projection_id,
                    **({"replay_only": True} if skills and prior_dispatch is not None else {}))
                previous_projection_id = dispatch["context_acceptance"]["projection_id"]
                last_context = {"acceptance": deepcopy(dispatch["context_acceptance"]), "dispatch_id": dispatch["dispatch_id"],
                                "source_message_count": len(messages), "source_evidence_count": len(evidence),
                                "checkpoint_history_digest": digest_json(messages), "checkpoint_evidence_digest": digest_json(evidence)}
            broker.pin_context(dispatch)
            prior_dispatch_duplicate = dispatch.get("duplicate", False)
            broker.replay_only = skills and prior_dispatch_duplicate
            if dispatch.get("duplicate"):
                if dispatch["effect_state"] != "succeeded" or not dispatch.get("result_ref"):
                    raise RuntimeError("unresolved model dispatch requires reconciliation")
                if skills:
                    from .skill_disclosure import _model
                    known = self.store.read_skill_turn_checkpoint(owner, dispatch["dispatch_id"])
                    if known is None:
                        raise RuntimeError("known turn lacks accepted skills checkpoint; checkpoint reconciliation required")
                    from .skill_recovery import validate_seed_proof
                    proof = self.store.read_skills_checkpoint(tenant, task, known["checkpoint_id"])
                    validate_seed_proof(proof, self.artifacts, require_frontier=False)
                    _model(self.artifacts, proof, dispatch)
                response_ref = dispatch["result_ref"]
                if native and response_ref.get("content_type") == NEBIUS_ERROR_CONTENT_TYPE:
                    raise ProtocolError("provider transport diagnostic is not a model completion")
                raw = decode_provider_payload(
                    self.artifacts.get(tenant, task, response_ref["digest"]),
                    model.max_bytes if envelope else 2_000_000,
                )
                if native and isinstance(raw, dict) and raw.get("kind") == "provider_transport_error":
                    raise ProtocolError("provider transport diagnostic is not a model completion")
                if envelope:
                    _validate_response_model(raw, model.model)
                usage = usage_parser(raw)
            else:
                try:
                    received = model.receive(payload) if envelope else model.response(turn)
                except NebiusHTTPError as error:
                    if not native:
                        self.store.finish_dispatch(
                            tenant, action_id, "unknown-" + action_id, "unknown", None, None
                        )
                        raise
                    try:
                        transport = error.as_dict()
                        if (
                            transport["provider"] != request_record["provider"]
                            or transport["protocol"] != request_record["protocol"]
                            or transport["endpoint"] != request_record["endpoint"]
                            or transport["model"] != payload["model"]
                            or transport["payload_digest"] != digest_json(payload)
                        ):
                            raise ValueError("provider transport diagnostic request mismatch")
                        diagnostic_ref = self.artifacts.put(
                            tenant, task, canonical_bytes({
                                "schema": 1, "kind": "provider_transport_error",
                                "dispatch_id": dispatch["dispatch_id"], "request_ref": request_ref,
                                "request_digest": digest_json(request_record), "transport": transport,
                            }), NEBIUS_ERROR_CONTENT_TYPE,
                        )
                    except Exception as persistence_error:
                        self.store.finish_dispatch(
                            tenant, action_id, "unknown-" + action_id, "unknown", None, None
                        )
                        raise persistence_error from None
                    self.store.finish_dispatch(
                        tenant, action_id, "unknown-" + action_id, "unknown", None, diagnostic_ref
                    )
                    raise
                except Exception:
                    self.store.finish_dispatch(
                        tenant, action_id, "unknown-" + action_id, "unknown", None, None
                    )
                    raise
                if envelope:
                    # Transport evidence survives unsupported/truncated content.
                    response_ref = self.artifacts.put(tenant, task, received, "application/json")
                    try:
                        raw = decode_provider_payload(received, model.max_bytes)
                        _validate_response_model(raw, model.model)
                        usage = usage_parser(raw)
                        actual_units = envelope.charge(usage)
                    except (ProtocolError, ValueError):
                        # The complete response is known; its charge is not yet
                        # trustworthy. Keep exposure and reject all proposals.
                        self.store.finish_dispatch(
                            tenant, action_id, f"model-receipt-{owner['attempt_id']}-{turn}",
                            "succeeded", None, response_ref,
                        )
                        raise
                else:
                    raw, usage = received.raw, received.usage
                    response_ref = self.artifacts.put_json(tenant, task, raw)
                    actual_units = 0
                self.store.finish_dispatch(
                    tenant,
                    action_id,
                    f"model-receipt-{owner['attempt_id']}-{turn}",
                    "succeeded",
                    actual_units,
                    response_ref,
                )
            if envelope and not envelope.within_token_bounds(usage):
                self.store.fail_execution(
                    tenant, task, owner["generation"], "infrastructure_failed", response_ref
                )
                raise RuntimeError("provider token-bound violation; actual receipt retained, run revoked")
            # A billing/transport receipt cannot authorize malformed tool calls,
            # unsupported finish states or successful task completion.
            response = parse_nebius_response(raw, model.model) if native else parse_anthropic_response(
                raw, model.model if isinstance(model, AnthropicMessages) else None
            )
            # Preserve opaque provider blocks verbatim, not only normalized tools.
            assistant = (
                response.raw["choices"][0]["message"] if native
                else {"role": "assistant", "content": response.raw["content"]}
            )
            # Check call IDs against prior history before dispatch, not only
            # before sending the next request. Opaque fields remain untouched.
            proposed_messages = messages + [assistant]
            if native:
                validate_nebius_linkage(proposed_messages + [
                    {"role": "tool", "tool_call_id": call.call_id, "content": ""}
                    for call in response.calls
                ])
            else:
                # Placeholders complete structural linkage only; they are never
                # persisted or treated as evidence of an executed tool effect.
                validate_linkage(proposed_messages + ([{"role": "user", "content": [
                    {"type": "tool_result", "tool_use_id": call.call_id, "content": ""}
                    for call in response.calls
                ]}] if response.calls else []))
            messages.append(assistant)
            evidence.append({"request_ref": request_ref, "response_ref": response_ref})
            if response.terminal:
                return save_checkpoint("completion_proposed", turn + 1)
            results = []
            proposed_finish = False
            for call in response.calls:
                result = broker.execute(call)
                results.append(
                    {"role": "tool", "tool_call_id": call.call_id,
                     "content": canonical_bytes(result).decode()} if native else {
                        "type": "tool_result",
                        "tool_use_id": call.call_id,
                        "content": canonical_bytes(result).decode(),
                        "is_error": not result["ok"],
                    }
                )
                proposed_finish |= call.name == "finish" and result["ok"]
            if native:
                messages.extend(results)
            else:
                messages.append({"role": "user", "content": results})
            checkpoint_result = save_checkpoint(
                "completion_proposed" if proposed_finish else "checkpointed", turn + 1
            )
            if proposed_finish:
                return checkpoint_result
            if pause_after_turn is not None and turn + 1 >= pause_after_turn:
                return {**checkpoint_result, "status": "paused"}
        if skills:
            if restored is not None and first_turn >= self.max_turns:
                return {"status": "turn_budget_exhausted", "turns": first_turn, "messages": messages,
                        "evidence": evidence, "checkpoint_id": restored["source_checkpoint"]}
            return {**save_checkpoint("checkpointed", self.max_turns), "status": "turn_budget_exhausted"}
        raise RuntimeError("harness turn budget exhausted")
