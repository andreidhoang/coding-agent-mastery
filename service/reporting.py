"""Compact evidence report from committed records; no inferred success metrics."""

from __future__ import annotations

import json
from pathlib import Path

from .artifacts import digest_json


def compact_report(snapshot: dict, events: list[dict]) -> dict:
    task = snapshot["task"]
    return {
        "schema": 1,
        "task_id": task["task_id"],
        "tenant_id": task["tenant_id"],
        "execution_state": task["execution_state"],
        "review_state": task["review_state"],
        "contract_digest": task["contract_digest"],
        "model": task["contract"]["model"],
        "profile": task["contract"]["profile"],
        "patch_slot_limit": task["contract"]["patch_slot_limit"],
        "budget": snapshot["budget"],
        "frontier": snapshot["frontier"],
        "requirements": task["contract"]["requirements"],
        "nodes": [
            {
                k: n.get(k)
                for k in ("node_id", "dependencies", "node_epoch", "attempt_id", "status", "candidate_id")
            }
            for n in snapshot["nodes"]
        ],
        "dispatches": [
            {
                k: d.get(k)
                for k in (
                    "dispatch_id",
                    "action_id",
                    "kind",
                    "effect_state",
                    "billing_state",
                    "bound_units",
                    "actual_units",
                    "result_ref",
                )
            }
            for d in snapshot["dispatches"]
        ],
        "candidate_trees": [
            {"candidate_id": c["candidate_id"], "tree_digest": c["tree_digest"], "kind": c["kind"]}
            for c in snapshot["candidates"]
        ],
        "verifications": snapshot["verifications"],
        "reviews": snapshot["reviews"],
        "physical_slots_retained": sum(s["status"] != "retired" for s in snapshot["sandboxes"]),
        "events": events,
        "raw_snapshot_digest": digest_json(snapshot),
        "evidence_kind": snapshot.get("evidence_kind", "runtime_records"),
        "limits": [
            "scripted fixture outcomes are not learned model capability",
            "human mastery and independent reproduction are not inferred from this report",
        ],
    }


def write_report(output: str | Path, snapshot: dict, events: list[dict]) -> dict:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    report = compact_report(snapshot, events)
    (output / "snapshot.json").write_text(json.dumps(snapshot, indent=2) + "\n")
    (output / "trace.json").write_text(json.dumps(report, indent=2) + "\n")
    # All user-controlled strings are rendered with textContent, never innerHTML.
    payload = json.dumps(report).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    document = (
        """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Durable agent execution trace</title><style>
:root{color-scheme:light dark;font-family:system-ui,sans-serif}body{max-width:1050px;margin:32px auto;padding:0 20px;line-height:1.5}
h1{font-size:1.7rem}select,input{font:inherit;padding:6px}pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:16px;background:light-dark(#f3f4f6,#20242b)}
.lanes{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin:20px 0}.lane{padding:16px;background:light-dark(#edf2f6,#232a33)}
.active{outline:3px solid light-dark(#006e86,#63d1e8)}.muted{opacity:.75}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:8px;border-bottom:1px solid light-dark(#ddd,#444)}
button{padding:10px;font:inherit}label{display:block;margin:16px 0}input[type=range]{width:100%;box-sizing:border-box}
</style><h1>One task, separate owners</h1><p id="summary"></p><p class="muted">Measured event order · scripted fixture · human review separate</p>
<div class="lanes" role="group" aria-label="State owners"><div class="lane" data-owner="task">Task authority</div><div class="lane" data-owner="attempt">Worker ownership</div><div class="lane" data-owner="dispatch">Action / receipt</div><div class="lane" data-owner="candidate">Candidate bytes</div><div class="lane" data-owner="verification">Verification / review</div></div>
<label for="step">Committed event <span id="position"></span><input id="step" type="range" min="0" value="0"></label><button id="prev">Previous</button> <button id="next">Next</button>
<h2 id="event-title"></h2><pre id="detail" aria-live="polite"></pre><h2>Final accounting</h2><pre id="account"></pre>
<h2>Follow the bytes</h2><table><thead><tr><th>Candidate</th><th>Tree SHA-256</th><th>Role</th></tr></thead><tbody id="trees"></tbody></table>
<script type="application/json" id="data">"""
        + payload
        + """</script><script>
const report=JSON.parse(document.getElementById('data').textContent),slider=document.getElementById('step'),events=report.events;
document.getElementById('summary').textContent=report.execution_state+' · review '+report.review_state+' · '+report.model;
slider.max=Math.max(0,events.length-1);
function render(){const i=Number(slider.value),event=events[i]||{};document.getElementById('position').textContent=(i+1)+' / '+events.length;
const kind=event.kind||event.type||'event';document.getElementById('event-title').textContent=kind;document.getElementById('detail').textContent=JSON.stringify(event,null,2);
document.querySelectorAll('.lane').forEach(el=>el.classList.toggle('active',kind.startsWith(el.dataset.owner)||(el.dataset.owner==='verification'&&(kind.startsWith('review')||kind.startsWith('eligib')))));}
slider.addEventListener('input',render);document.getElementById('prev').onclick=()=>{slider.value=Math.max(0,Number(slider.value)-1);render()};document.getElementById('next').onclick=()=>{slider.value=Math.min(events.length-1,Number(slider.value)+1);render()};
document.getElementById('account').textContent=JSON.stringify({budget:report.budget,physical_slots_retained:report.physical_slots_retained,limits:report.limits},null,2);
for(const candidate of report.candidate_trees){const row=document.createElement('tr');for(const value of [candidate.candidate_id.slice(0,12),candidate.tree_digest,candidate.kind]){const cell=document.createElement('td');cell.textContent=value;cell.style.overflowWrap='anywhere';row.appendChild(cell)}document.getElementById('trees').appendChild(row)}render();
</script></html>"""
    )
    (output / "trace.html").write_text(document)
    return report
