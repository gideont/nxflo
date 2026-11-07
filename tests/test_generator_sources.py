import unittest
from portal_api.generator_sources import extract_sources

class InlineSourcesTests(unittest.TestCase):
    def test_mixed_notes_markdown_doi_youtube_and_duplicates(self):
        brief='''Research notes and Smith et al. (2025).
        Watch https://youtu.be/abcdefghijk?t=30 and https://www.youtube.com/shorts/abcdefghijk.
        [Paper](https://example.com/research.pdf), https://example.com/research.pdf
        https://en.wikipedia.org/wiki/Python_(programming_language).
        DOI: 10.1234/xyz. Reference www.example.org/report.'''
        sources=extract_sources(brief,'https://www.youtube.com/watch?v=abcdefghijk\nhttps://youtube.com/live/123456789ab')
        self.assertEqual(sources['youtube'],['https://www.youtube.com/watch?v=abcdefghijk','https://www.youtube.com/watch?v=123456789ab'])
        self.assertEqual(sources['references'],['https://example.com/research.pdf','https://en.wikipedia.org/wiki/Python_(programming_language)','https://doi.org/10.1234/xyz','https://www.example.org/report'])
    def test_non_http_and_credentials_not_active_links(self):
        sources=extract_sources('javascript:alert(1) file:///etc/passwd https://user:password@example.com/private')
        self.assertEqual(sources,{'youtube':[],'references':[]})
    def test_bare_youtube_and_long_markdown_closing_punctuation(self):
        self.assertEqual(len(extract_sources('youtu.be/abcdefghijk youtube.com/watch?v=abcdefghijk')['youtube']),1)
        self.assertEqual(extract_sources('https://example.org/path'+')'*5000)['references'],['https://example.org/path'])
    def test_web_query_and_fragment_preserved(self):
        self.assertEqual(extract_sources('https://example.com/file?a=1&amp;b=2#page=3')['references'],['https://example.com/file?a=1&b=2#page=3'])

if __name__=='__main__':unittest.main()
