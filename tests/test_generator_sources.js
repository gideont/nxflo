const assert=require('node:assert/strict');
const {extract}=require('../tools/generator-sources.js');
const brief=`Research notes and Smith et al. (2025).
Watch https://youtu.be/abcdefghijk?t=30 and https://www.youtube.com/shorts/abcdefghijk.
[Paper](https://example.com/research.pdf), https://example.com/research.pdf
https://en.wikipedia.org/wiki/Python_(programming_language).
DOI: 10.1234/xyz. Reference www.example.org/report.`;
assert.deepEqual(extract(brief,'https://www.youtube.com/watch?v=abcdefghijk\nhttps://youtube.com/live/123456789ab'),{
 youtube:['https://www.youtube.com/watch?v=abcdefghijk','https://www.youtube.com/watch?v=123456789ab'],
 references:['https://example.com/research.pdf','https://en.wikipedia.org/wiki/Python_(programming_language)','https://doi.org/10.1234/xyz','https://www.example.org/report']});
assert.deepEqual(extract('javascript:alert(1) file:///etc/passwd https://user:password@example.com/private'),{youtube:[],references:[]});
assert.deepEqual(extract('https://example.com/file?a=1&amp;b=2#page=3').references,['https://example.com/file?a=1&b=2#page=3']);
const {estimate}=require('../tools/generator-cost.js');
const cfg={summary_model:'test',draft_model:'test',polish_model:'test',length_mode:'content',cost_pages:12,review_passes:1,documents:[],topic:'https://youtu.be/abcdefghijk https://www.youtube.com/watch?v=abcdefghijk',youtube:'https://youtu.be/abcdefghijk',questions:'',web_search:false};
const result=estimate(cfg,{models:{test:{input:1,output:2}}});
assert.equal(result.sourceTokens,Math.ceil(cfg.topic.length/4)+6000);
console.log('Inline-source detection and deduplicated video-cost checks passed.');

assert.equal(extract('youtu.be/abcdefghijk youtube.com/watch?v=abcdefghijk').youtube.length,1);
assert.deepEqual(extract('https://example.org/path'+')'.repeat(5000)).references,['https://example.org/path']);
