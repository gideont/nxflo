"""Nexusflow's navy publication cover, drawn with embedded vector artwork."""
import base64
from datetime import date as calendar_date
from html import escape

WAVES='''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 840 1188"><defs><linearGradient id="blue"><stop stop-color="#08caff"/><stop offset=".35" stop-color="#123cca"/><stop offset=".75" stop-color="#7122fa"/><stop offset="1" stop-color="#e042ff"/></linearGradient><linearGradient id="pink"><stop stop-color="#fb2188"/><stop offset=".6" stop-color="#ce13ed"/><stop offset="1" stop-color="#ffb04a"/></linearGradient><radialGradient id="glow"><stop stop-color="#9e20fa" stop-opacity=".65"/><stop offset="1" stop-color="#07164b" stop-opacity="0"/></radialGradient><pattern id="dots" width="12" height="12" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" fill="#5267ff" opacity=".55"/></pattern></defs><rect width="840" height="1188" fill="#061641"/><ellipse cx="870" cy="50" rx="600" ry="530" fill="url(#glow)"/><path d="M550 0 Q745 125 840 365 V0Z" fill="#5421e0" opacity=".32"/><path d="M0 840 Q230 670 450 865 T840 720 V1010 Q600 1160 310 975 T0 1050Z" fill="url(#dots)"/><path d="M-40 742 Q120 650 310 760 T630 826 Q770 800 880 680 L880 760 Q720 970 480 890 T90 795 Q15 815 -40 850Z" fill="url(#blue)" opacity=".95"/><path d="M-40 742 Q120 650 310 760 T630 826 Q770 800 880 680" fill="none" stroke="#66b7ff" stroke-width="2" opacity=".65"/><path d="M-20 944 Q170 820 365 925 T670 965 Q780 930 870 850 L870 912 Q720 1090 495 1020 T175 907 Q60 900 -20 964Z" fill="url(#pink)"/><path d="M-20 944 Q170 820 365 925 T670 965 Q780 930 870 850" fill="none" stroke="#ff89e1" stroke-width="2"/></svg>'''
ART='data:image/svg+xml;base64,'+base64.b64encode(WAVES.encode()).decode()


def cover_markup(config,title,company,date,prepared=''):
    e=lambda value:escape(str(value),quote=True)
    try:release=calendar_date.fromisoformat(date).strftime('%B %Y')
    except ValueError:release=date
    year=date[:4] if date[:4].isdigit() else ''
    logo='<img class="logo" src="'+e(config['logo'])+'" alt="'+e(company)+' logo">' if config.get('logo') else ''
    website=config.get('website','')
    site='<a href="'+e(website)+'">'+e(website)+'</a>' if website else ''
    return '<img class="cover-art" alt="" aria-hidden="true" src="'+ART+'"><div class="cover-brand">'+logo+'<p class="cover-company">'+e(company)+'</p></div><div class="cover-body"><p class="eyebrow">'+e(config['report_type'])+(' | '+e(year) if year else '')+'</p><span class="cover-rule"></span><h1>'+e(title)+'</h1></div><div class="cover-details">'+prepared+'<div class="cover-bottom"><div class="cover-website">'+site+'</div><div class="cover-release">'+e(release)+'<br><span>Version '+e(config.get('version') or '1.0')+'</span></div></div></div>'

COVER_CSS=r'''
.cover{background:#061641;color:#fff;height:297mm;padding:24mm 19mm 18mm;justify-content:flex-start;isolation:isolate;overflow:hidden}
.cover::before{display:none}.cover>.cover-art{position:absolute;inset:0;width:100%;height:100%;max-width:none;object-fit:fill;z-index:-1}
.cover-brand{display:flex;align-items:center;gap:5mm;margin:0;padding:0;flex-shrink:0}
.cover-brand .logo{max-width:48mm;max-height:17mm;background:#fff;padding:2mm;border-radius:2mm}
.cover-company{font:600 20pt/1.2 var(--font-ui);margin:0;color:white}.cover-brand:has(.logo) .cover-company{border-left:1px solid #ccd4ef;padding-left:5mm}
.cover-body{padding:22mm 0 0;flex:1}.cover .eyebrow{font:700 11pt/1.5 var(--font-ui);letter-spacing:.16em;color:#ffbd18;margin:0}
.cover-rule{display:block;width:24mm;height:1mm;background:linear-gradient(90deg,#ff268c,#8c1cff);margin:6mm 0 10mm;border-radius:1mm}
.cover h1{font:700 32pt/1.12 var(--font-ui);letter-spacing:-.03em;color:#fff;max-width:100%;margin:0;overflow-wrap:break-word}
.cover-details{margin-top:auto;color:#fff}.cover .prepared-by{font:9pt/1.5 var(--font-ui);margin:0 0 5mm;max-width:100%}
.cover-bottom{display:flex;align-items:flex-end;justify-content:space-between;gap:6mm;font:9pt/1.5 var(--font-ui)}.cover-website{font:inherit;margin:0}.cover-release{text-align:right;flex-shrink:0}.cover-release span{font-size:8pt;color:#d3d9ec}
.contents{break-before:page;break-after:page}
@media screen{.cover{min-height:0;height:auto;aspect-ratio:210/297;padding:clamp(22px,6vw,65px)}.cover-company{font-size:clamp(16px,3vw,27px)}.cover-body{padding:clamp(24px,7vw,78px) 0 0}.cover h1{font-size:clamp(24px,4.8vw,46px)}.cover .eyebrow{font-size:clamp(10px,2vw,15px)}.cover-details{padding-top:120px}.cover-bottom,.cover .prepared-by{font-size:12px}.cover-brand .logo{max-width:35%;max-height:65px}.cover-rule{margin:18px 0 28px}.contents{border-top:1px solid #d5dce1;padding-top:30px}}
'''
