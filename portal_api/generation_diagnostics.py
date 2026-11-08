"""Current failure explanations, without provider payloads or execution history."""
import re


def failure_details(row,state,calls):
    if row['status']!='failed':return None
    error=row['error'] or row['message']
    validation='gate rejected' in error.lower() or 'publication-quality gate' in error.lower()
    issues=list(dict.fromkeys(value for value in state.get('quality_errors',[]) if isinstance(value,str))) if validation else []
    diagnostics=state.get('chapter_diagnostics',{}) if validation else {}
    plans=state.get('outline',{}).get('chapters',[]);chapters=[]
    for key,values in diagnostics.items():
        if not str(key).isdigit() or not isinstance(values,list):continue
        number=int(key)
        if number<1:continue
        problems=list(dict.fromkeys(value for value in values if isinstance(value,str)))
        if not problems:continue
        title=plans[number-1].get('title','') if number<=len(plans) else ''
        chapters.append({'number':number,'title':title,'issues':problems})
    chapters.sort(key=lambda chapter:chapter['number'])
    all_issues=issues+[issue for chapter in chapters for issue in chapter['issues']]
    highlights=[]
    for pattern in (r'empirical|source evidence|source verification',r'prose number',r'lost original author anchor'):
        match=next((issue for issue in all_issues if re.search(pattern,issue,re.I)),None)
        if match and match not in highlights:highlights.append(match)
    grouped={issue for chapter in chapters for issue in chapter['issues']}
    grouped.update('Chapter '+str(chapter['number'])+': '+issue for chapter in chapters for issue in chapter['issues'])
    general=[issue for issue in issues if issue not in grouped]
    corrected=validation and any(call['status']=='complete' and call['stage'].startswith('intent-repair-'+row['step']) for call in calls)
    return {'summary':('The draft did not pass evidence and author-intent validation.' if row['step']=='draft' and validation else 'The document did not pass publication validation.' if validation else error),
            'highlights':highlights,'chapters':chapters,'issues':general,'error':error,'automatic_correction_completed':corrected,
            'next_action':('Saved automatic corrections were checked, but these issues remain. Resume reuses saved responses; unchanged results can fail the same checks again.' if corrected else 'Saved work is preserved. Review the details below before resuming.')}
