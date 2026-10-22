# Search visibility

## Audit and implementation — October 2026

The live site initially served semantic, mobile-friendly HTML, but `robots.txt`
and `sitemap.xml` returned 404. Pages had generic titles and descriptions, no
canonical URLs, no social preview metadata, and no structured company data.
The home page was available on both the bare and www domains and `/index.html`.
Databricks, ETL, and Power BI appeared in general content; BMS and Entra ID did
not have content explaining the work. Actual Google indexing, impressions,
clicks, and ranking positions were not available during this audit.

The site now has shared, unique search metadata; Organization, WebSite, WebPage,
Service, and breadcrumb JSON-LD as appropriate; canonical URLs; a sitemap; and
a robots file. The thank-you utility page is `noindex, follow` and omitted from
the sitemap. No unsupported address, opening hours, certification, rating,
client result, or partner status is claimed in structured data or service copy.

Validation: all 11 pages returned HTTP 200 and matched the source on the local
Docker deployment and `https://www.nxflo.com`. Robots and sitemap returned 200;
bare-domain and home-alias redirects preserved query strings; missing URLs
returned 404; HTML compression was active. Ten unit checks passed. Browser
checks covered all pages' header/footer consistency, the homepage's arrow-only
cards, and the six new service pages at desktop and mobile widths down to 320px.

## Search intent and destination

| Search intent | Page |
| --- | --- |
| BMS / building management system data integration; HVAC, energy, sensor reporting | `bms-data-integration.html` |
| Vancouver IT support for a scoped technical project; support for local IT teams | `vancouver-it-support.html` |
| Microsoft Entra ID / Azure AD application integration and SSO | `entra-id-integration.html` |
| Databricks consulting; Apache Spark; growing pandas workloads | `databricks-consulting.html` |
| ETL development; data pipelines; database transfers | `etl-data-pipelines.html` |
| Power BI consulting, dashboards, models, and refresh support | `power-bi-consulting.html` |

These pages explain distinct client needs, possible deliverables, and scoped
examples. Examples describe possible workflows rather than claiming completed
client projects. The Services hub links to every page. Relevant homepage answer
cards also contain contextual links. Do not add repetitive city/keyword pages
or hide keyword lists in the design.

## Maintenance

- Edit visible service content in its root HTML file and metadata in `lib/seo.py`.
- Use one `include:site-seo`, header, and footer marker in every page.
- The build verifies that all root pages are registered. Sitemap URLs include
  only indexable, canonical pages. No artificial `lastmod` dates are generated.
- Keep the preferred origin `https://www.nxflo.com` consistent in metadata,
  sitemap, Nginx, and external business listings.
- The existing edge proxy terminates HTTPS. Do not redirect all container HTTP
  requests to HTTPS; this could create a proxy loop and break the local preview.
- Run unit checks, responsive browser checks, rebuild Docker, and verify the
  deployed pages, redirect targets, sitemap, robots file, and missing-page 404s.

## Account and evidence follow-up

1. Verify a Google Search Console property for `nxflo.com` using your DNS account.
   Submit `https://www.nxflo.com/sitemap.xml`. Inspect the home page and six
   service URLs and check indexing reports. This work has not submitted the
   sitemap to an account or requested indexing on your behalf.
2. Record a baseline in Search Console and review queries, impressions, clicks,
   and average position over time. Compare the target pages individually and
   use real query data to refine the copy. Search appearance may take time to
   change; submission and structured data do not guarantee a ranking.
3. If the business meets Google's eligibility requirements, maintain a verified
   Google Business Profile with accurate services, location or service area,
   contact information, and a link to this website. Do not publish a home/street
   address or opening hours simply to fill a search field.
4. Add real, client-approved project examples that explain the systems,
   constraints, work delivered, and measurable outcomes. Ask satisfied clients
   for honest reviews and relevant links through your own established channels.
   Keep these claims accurate and attributable.

## Primary references

- [Google SEO Starter Guide](https://developers.google.com/search/docs/fundamentals/seo-starter-guide)
- [Google canonical URLs](https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls)
- [Google sitemap guidance](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap)
- [Google Organization structured data](https://developers.google.com/search/docs/appearance/structured-data/organization)
- [Google local ranking factors](https://support.google.com/business/answer/7091?hl=en)
- [Microsoft Entra ID application authentication](https://learn.microsoft.com/en-us/entra/architecture/authenticate-applications-and-users)
- [Databricks ETL](https://docs.databricks.com/aws/en/getting-started/etl-quick-start)
- [Power BI and Databricks](https://learn.microsoft.com/en-us/azure/databricks/partners/bi/power-bi/)
- [OPC Foundation: OPC UA for BACnet](https://reference.opcfoundation.org/specs/OPC-30030/full)
