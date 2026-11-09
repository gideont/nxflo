"""Folio report design system with Nexusflow branding and responsive additions."""
from pathlib import Path

_FOLIO = Path(__file__).with_name('vendor') / 'folio'
CONTENTS_ROW_CSS = '.contents li{border-bottom:0}'
REPORT_CSS = '\n'.join((_FOLIO / name).read_text(encoding='utf-8') for name in ('base.css', 'report.css')) + r'''
/* Nexusflow brand adapter; upstream components remain in vendor/folio. */
:root{
  --brand:var(--theme);--brand-deep:var(--theme);--brand-tint:#f0f4ee;
  --font-body:'DejaVu Serif',Georgia,serif;--font-ui:'DejaVu Sans',Arial,sans-serif;
  --font-mono:'DejaVu Sans Mono',monospace;
}
body{overflow-wrap:anywhere;text-align:start}
h1,h2,h3{hyphens:none}
a:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
img,svg{max-width:100%;height:auto}figure img{width:auto;max-height:145mm;margin:auto;object-fit:contain}
.cover{--cover-plate-h:100mm;justify-content:space-between;padding:18mm;min-width:0}
.cover>*{position:relative;min-width:0}.cover-brand{padding:0;margin:0;left:auto;right:auto;top:auto}
.cover-company{font:600 15px var(--font-ui);color:inherit;margin:12px 0}
.cover-body{padding:8mm 0}.cover h1{max-width:100%;bookmark-level:none}
.cover .eyebrow{color:#fff;margin:0 0 6mm}.cover-rule{background:var(--accent);margin:8mm 0 0}
.logo{display:block;width:auto;max-width:46mm;max-height:24mm;object-fit:contain;background:#fff;padding:3mm}
.cover-meta{display:flex;flex-wrap:wrap;gap:8mm;margin:0 0 5mm}
.cover-meta>div{min-width:0;flex:1}.cover-meta dt{font-size:8pt;margin-bottom:2mm}.cover-meta dd{margin:0;font-weight:600}
.prepared-by,.cover-website{font:9pt/1.6 var(--font-ui);margin:0 0 3mm}
.cover p{max-width:none}.cover a,.cover strong{color:inherit}.cover-details p:last-child{margin-bottom:0}
.contents{padding-top:3mm;break-after:page}.contents h2{font:600 18pt var(--font-ui);bookmark-level:none;border-bottom:2px solid var(--brand);padding-bottom:4mm}
.contents ol{max-width:none;list-style:none;padding:0}.contents li{font:10pt/1.6 var(--font-ui);padding:3mm 0}.contents a{display:block}
.report-chapter,.appendix,.document-control{break-before:page;padding-top:3mm}
h2{font:600 16pt/1.3 var(--font-ui);break-after:avoid;margin:0 0 6mm;color:var(--ink)}
.report-chapter .eyebrow{color:var(--brand)}
.sources-list{font-size:9pt;padding-left:6mm}.sources-list li{padding:3mm 0;break-inside:avoid}
.small{font:8.5pt/1.6 var(--font-ui);color:var(--ink-soft)}
.document-register{display:grid;grid-template-columns:minmax(100px,1fr) minmax(0,3fr);gap:2mm 5mm;font:9pt/1.6 var(--font-ui)}
.document-register dt{font-weight:600}.document-register dd{margin:0;min-width:0}
.revision-table{table-layout:fixed;font-size:9pt}.revision-table th{white-space:normal}.revision-table th:first-child{width:12%}.revision-table th:nth-child(2){width:20%}.revision-table th:nth-child(3){width:28%}
.revision-table th,.revision-table td{overflow-wrap:anywhere}
.document-contact{border-top:2px solid var(--brand);margin-top:9mm;padding-top:6mm;font:10pt/1.6 var(--font-ui)}.document-contact h2{font-size:15pt}
footer,.running-header,.running-footer{display:none}
@page{
  @top-left{content:element(report-header)}
  @top-right{content:none}
  @bottom-left{content:element(report-footer)}
  @bottom-right{content:'Page ' counter(page) ' of ' counter(pages)}
}
@media print{
  .running-header{display:block;position:running(report-header);font:8pt var(--font-ui);color:var(--ink-mute)}
  .running-footer{display:block;position:running(report-footer);font:8pt var(--font-ui);color:var(--ink-mute)}
  .contents li a::after{content:' ' leader('.') ' ' target-counter(attr(href),page)}
}
@media screen{
  html{background:#eeede8;padding:0}body{font-size:17px;line-height:1.7;max-width:none;padding:0;margin:0;background:transparent;box-shadow:none}
  main{max-width:920px;margin:auto;padding:clamp(20px,6vw,65px);background:white}
  p,ul,ol,blockquote{max-width:none}
  .cover{width:100%;height:auto;min-height:760px;margin:0;padding:clamp(22px,4vw,45px);margin-bottom:40px}
  .cover h1{font-size:clamp(30px,5vw,49px);line-height:1.17}
  .cover-body{padding:40px 0}.prepared-by,.cover-website{font-size:13px}
  .contents{padding:0 0 35px}.contents li{font-size:15px}.contents a{min-height:44px;padding:9px 0}
  .report-chapter,.appendix,.document-control{padding-top:40px}
  h2,h2.section{font-size:27px}.appendix h2.section{font-size:25px}
  .eyebrow{font-size:12px}.callout{font-size:15px}.callout .ico{font-size:12px}
  .sources-list,.appendix{font-size:15px}.small{font-size:13px}
  figcaption{font-size:12px}.document-register,.revision-table,.document-contact{font-size:13px}
  .revision-table{display:table;overflow:visible}.revision-table th{font-size:12px}.revision-table caption{font-size:13px}
  .document-contact a,.sources-list a{display:inline-block;min-height:44px;padding:8px 0}
  footer{display:block;margin-top:40px;border-top:1px solid var(--rule);padding-top:16px;font:12px/1.6 var(--font-ui);color:var(--ink-soft)}
}
@media screen and (max-width:450px){
  .cover{min-height:720px}.cover-meta{gap:14px}.cover-meta>div{flex-basis:100%}
  .callout{flex-direction:column;gap:8px}.callout .ico{flex-basis:auto}
  .document-register{grid-template-columns:1fr;gap:3px}.document-register dd{margin-bottom:10px}
  .revision-table,.revision-table tbody{display:block}.revision-table caption{display:block;width:100%}
  .revision-table thead{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}
  .revision-table tr{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);border:1px solid var(--rule);margin-bottom:14px}
  .revision-table td{display:block;border:0;padding:9px;font-size:12px}
  .revision-table td::before{content:attr(data-label);display:block;font-weight:bold;color:var(--brand);font-size:11px;margin-bottom:3px}
  .revision-table td:nth-child(3),.revision-table td:last-child{grid-column:1/-1;border-top:1px solid var(--rule)}
}
'''

REPORT_CSS += r"""
.report-data-table{table-layout:fixed;width:100%;font-size:9pt;margin:6mm 0;overflow-wrap:anywhere}
.report-data-table th{white-space:normal}.report-data-table td,.report-data-table th{padding:2mm;vertical-align:top}
.worked-financials{margin-top:8mm}.worked-financials h3,.financial-example h4{break-after:avoid}
.financial-example{margin-top:8mm}.formula-register{font:9pt/1.6 var(--font-ui)}
.formula-register dt{font-weight:600;text-transform:capitalize;margin-top:3mm}.formula-register dd{margin:0}
.formula-register code,.registered-formula code{white-space:normal;overflow-wrap:anywhere}
@media screen{.report-data-table{display:table;font-size:13px}.report-data-table caption{font-size:14px}.report-data-table th{font-size:12px}.formula-register{font-size:13px}}
@media screen and (max-width:640px){
 .report-data-table,.report-data-table tbody{display:block;max-width:100%;overflow:visible}
 .report-data-table caption{display:block;width:100%;font-size:14px}
 .report-data-table thead{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}
 .report-data-table tr{display:block;border:1px solid var(--rule);margin-bottom:14px;padding:8px}
 .report-data-table td{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.4fr);gap:10px;border:0;padding:7px;font-size:13px;min-width:0}
 .report-data-table td::before{content:attr(data-label);font-weight:600;color:var(--brand);font-size:12px}
}
"""
REPORT_CSS += CONTENTS_ROW_CSS
