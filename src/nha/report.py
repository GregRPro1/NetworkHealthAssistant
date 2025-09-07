from .utils import write_json
from .advice import priority_actions

def make_report(analyzed, summary, root_paths):
    actions = priority_actions(analyzed)
    report = {"summary": summary, "actions": actions, "devices": analyzed}
    write_json(root_paths["report_json"], report)

    lines = []
    lines.append("# Network Health Report\n")
    lines.append(f"**Total devices:** {summary['total']}  \n**New devices:** {summary['new_devices']}\n")
    lines.append(f"**Risk:** High={summary['risk_buckets']['high']}, Medium={summary['risk_buckets']['medium']}, Low={summary['risk_buckets']['low']}\n")
    lines.append("## Priority Actions\n")
    for i, a in enumerate(actions, 1):
        lines.append(f"{i}. **{a['title']}**  \n   {a['detail']}  \n   Targets: {', '.join(a['targets'])}\n")
    lines.append("## Devices (sorted by risk)\n")
    for d in analyzed:
        lines.append(f"- {d.get('ip','?')} `{d.get('mac','?')}` — **{d.get('vendor','?')} / {d.get('category','?')}** — risk={d.get('risk_score',0)} reasons={','.join(d.get('risk_reasons',[]))}")
    with open(root_paths["report_md"], "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
