"""The print cover and browser preview retain separate, stable page semantics."""
import unittest
from portal_api.generation_page_preview import print_css,paginated_preview
from portal_api.generation_cover import cover_markup

class DocumentPageTests(unittest.TestCase):
    def test_preview_uses_print_styles_without_mobile_reflow_or_empty_leading_page(self):
        css='p{color:black}@media screen{p{color:red}}@media print{.cover{height:297mm}}'
        result=print_css(css)
        self.assertIn('297mm',result);self.assertNotIn('red',result);self.assertIn('black',result)
        html='<html><head><style>'+css+'</style></head><body><div class="running-header">Company</div><main><header class="cover">Title</header><nav class="contents">Contents</nav><section class="report-chapter">Original content</section></main></body></html>'
        preview=paginated_preview(html)
        self.assertLess(preview.index('class="cover"'),preview.index('class="running-header"'))
        self.assertIn('Original content',preview);self.assertNotIn('<main>',preview)
    def test_cover_uses_embedded_vectors_and_escapes_author_text(self):
        markup=cover_markup({'report_type':'White paper','logo':'','version':'1.0','website':'https://www.nxflo.com'},'Investment <vision>','Nexusflow Inc.','2026-11-08')
        self.assertIn('data:image/svg+xml;base64,',markup);self.assertIn('Investment &lt;vision&gt;',markup)
        self.assertIn('White paper | 2026',markup);self.assertNotIn('Created by',markup)
