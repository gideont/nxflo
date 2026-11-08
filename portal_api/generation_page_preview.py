"""Private browser pagination; immutable approved HTML remains the export source."""
from bs4 import BeautifulSoup
import tinycss2


def print_css(css):
    output=[]
    for rule in tinycss2.parse_stylesheet(css,skip_comments=True,skip_whitespace=True):
        if rule.type=='at-rule' and rule.lower_at_keyword=='media':
            media=tinycss2.serialize(rule.prelude).strip()
            if media=='print':output.append(print_css(tinycss2.serialize(rule.content)))
            elif 'screen' not in media:output.append(tinycss2.serialize([rule]))
        else:output.append(tinycss2.serialize([rule]))
    return '\n'.join(output)


def paginated_preview(html):
    soup=BeautifulSoup(html,'html.parser')
    # Start with the named cover page, without an anonymous wrapper page.
    main=soup.find('main')
    if main:main.unwrap()
    chapter=soup.select_one('.report-chapter')
    if chapter:
        for running in soup.select('.running-header,.running-footer'):chapter.insert(0,running.extract())
    for style in soup.find_all('style'):style.string=print_css(style.string or '')
    style=soup.new_tag('style');style.string='html,body{margin:0;padding:0;background:#e8e9ed}main{max-width:none;margin:0;padding:0;background:white}footer{display:none}'
    soup.head.append(style)
    for src in ('/tools/document-preview.js','/tools/vendor/paged-0.4.3.min.js'):
        script=soup.new_tag('script',src=src);script['defer']='';soup.head.append(script)
    return str(soup)
