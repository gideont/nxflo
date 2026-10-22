# Nexusflow website illustrations

## Homepage illustration

The current homepage hero image is `images/holographic-analytics-office.png`.

### Previous homepage illustration generation notes

Generated with the built-in `image_gen` tool using the imagegen skill. The original homepage image is the composition reference and edit target; `images/contact-team.png` supplies the illustration style. The homepage asset is replaced at `images/collaborative-data-lab.png`, with a versioned image URL so browsers fetch the update.

Saved project asset: [Homepage connected data illustration](/home/gideon/nxflo_00/images/collaborative-data-lab.png).

Final dimensions: 1671 × 941 pixels. The original composition and connected-data story are retained, with a brighter, roomier office, pastel panels, and facial rendering matched to Contact.

### Initial edit prompt

Use case: style-transfer.
Asset type: replacement illustration for the Nexusflow homepage hero, landscape 16:9.
Input image 1 (collaborative-data-lab.png) is the edit target: preserve its composition, people placement, technical storytelling, and arrangement of the data panels.
Input image 2 (contact-team.png) is the STYLE reference only: match its warm daylight, softly rendered semi-realistic illustrated people, natural facial proportions, soft material textures, pastel lavender/pink/amber charts, light wood, leafy plants, and welcoming modern office.

Primary request: restyle image 1 to look like an illustration from the same world as image 2. Retain the central woman with dark hair in a bun, glasses and a lavender shirt, reaching toward connected data panels. Keep the colleague on the left and the three collaborating colleagues behind/right, in the same relative positions. Keep the left-hand panels for business/database data, finance, manufacturing, and a sensor circuit board; the central insights dashboard with graphs, pie chart and workflow; and the right-hand panels for world/map data and people/systems. Preserve the visual idea that separate systems feed connected data into useful insights.
Scene/backdrop: a slightly larger, airy office with high windows, more visible room depth and breathing space around the group, warm light wood tables, plants, soft daylight, and a subtle distant city view. Keep the current foreground/background hierarchy rather than replacing the composition with a generic team-at-a-table scene.
Style/medium: polished warm illustrated rendering matching reference 2, with believable anatomy and natural facial proportions. Re-render all people and the office in that style, including the central woman. Render the floating data panels as softly translucent pale-white/lavender glass with simple lavender, pink and amber diagrams; retain their relative placements, content and connecting paths, but soften the intense electric-blue glow to fit the Contact page's understated daytime palette.
Composition/framing: keep the original wide 16:9 composition and central focal point, all important faces and data panels comfortably within frame. Pull back only slightly to suggest a larger room without shrinking the main subject excessively. Full-bleed landscape artwork, no border.
Constraints: preserve the original story, five-person group, central woman/glasses/bun gesture, placement and purpose of the data panels, and the connected-system theme. Change the illustration style and office spaciousness only. No readable text, logos, branding, captions or watermark. Avoid oversized anime eyes, harsh neon, dark sci-fi atmosphere, extra people, generic replacement composition, or an excessive number of new panels.

### Facial-style refinement prompt



The refinement uses the first generated image as the edit target and `images/contact-team.png` as the style reference.

## About and Services illustrations

Generated with the built-in `image_gen` tool, using the imagegen skill. The reference is `images/contact-team.png`. These are new companion scenes; the Contact asset remains the source reference.

Saved project assets:
- [About collaboration](/home/gideon/nxflo_00/images/about-collaboration.png)
- [Services data workflow](/home/gideon/nxflo_00/images/services-data-workflow.png)

Both images are 1536 × 1024 pixels and are displayed as compact responsive illustrations on their respective pages.

### About prompt

Use case: illustration-story. Asset type: compact landscape website illustration for an About page, approximately 3:2 composition. Input image 1 is a style and character reference, not an edit target. Create a fresh companion illustration to the reference image: the same friendly colleagues in a bright Vancouver-style office, the man with glasses and cream shirt and the woman in lavender leaning together over a laptop, with the dark-haired colleague in navy listening. Frame the three people at the table in a closer, simpler composition suited to a small website image. Keep the warm daylight, leafy plants, soft pastel lavender and amber colors, polished friendly illustrated rendering, believable anatomy and approachable collaborative mood of the reference. Subtle small data chart on a screen in the background. Keep all important faces comfortably inside frame. No text, no branding, no watermark. This must feel like a smaller scene from the same office as the reference, not a neon tech fantasy.

### Services prompt

Use case: illustration-story. Asset type: compact landscape website illustration for a Services page, approximately 3:2 composition. Input image 1 is a style and character reference, not an edit target. Create a fresh companion illustration using the same office, warm natural daylight, plants, pastel purple pink amber charts, and friendly polished illustrated rendering as the reference. Focus on the dark-haired man in navy and the woman in orange working together at a laptop with clear simple floating data panels showing a connected workflow diagram and a bar chart. The people occupy the lower portion; the diagrams sit naturally above the laptop. Keep the scene simple enough to read at small size and both faces comfortably inside frame. Match the warm welcoming mood of the original, not a neon tech fantasy. No readable text, no branding, no watermark.
