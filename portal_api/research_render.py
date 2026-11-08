"""Reader-facing evidence ledger; provider credentials and costs stay in the portal."""
from html import escape


def verification_appendix(state):
    e=lambda value:escape(str(value),quote=True)
    claims=state.get('research',{}).get('claims',[])
    html='<section class="appendix" id="research-evidence"><h2>Independent verification and sources</h2><p>Factual assertions were checked against retrieved sources as of '+e(state['research'].get('as_of',''))+'. Findings apply to their stated jurisdiction and time period. Source availability and unresolved questions are recorded below.</p><ol>'
    for claim in claims:
        html+='<li><strong>'+e(claim['status'].title())+'</strong> · '+e(claim['text'])+'<p>'+e(claim.get('reason',''))+'</p>'
        for proof in claim.get('evidence',[]):
            html+='<p><a href="'+e(proof['url'])+'">'+e(proof['url'])+'</a> · retrieved '+e(proof.get('retrieved_at',''))+'</p><blockquote>'+e(proof['quote'][:700])+('…' if len(proof['quote'])>700 else '')+'</blockquote>'
        html+='</li>'
    html+='</ol></section>'
    corrections=state.get('research_corrections',[])
    if corrections:
        html+='<section class="appendix" id="research-corrections"><h2>Factual correction log</h2>'
        for patch in corrections:
            html+='<h3>'+e(patch['block'])+'</h3><p>'+e(patch.get('reason',''))+'</p><p><strong>Previous wording:</strong> '+e(patch['before'])+'</p><p><strong>Corrected wording:</strong> '+e(patch['after'])+'</p>'
        html+='</section>'
    return html
